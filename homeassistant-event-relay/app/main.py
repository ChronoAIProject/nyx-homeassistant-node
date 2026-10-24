"""Configurable Home Assistant Event Bus and MQTT to HTTPS relay."""

from __future__ import annotations

import copy
from collections import deque
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from relay_core import (
    ConfigurationError,
    SQLiteOutbox,
    cloud_event,
    get_path,
    parse_options,
    redact,
    route_matches,
    stable_event_id,
)


LOG = logging.getLogger("homeassistant-event-relay")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


HTTP_OPENER = build_opener(_NoRedirect)


def _configure_logging(options: dict[str, Any]) -> None:
    level = str(options.get("log_level", "info")).upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")


class Relay:
    def __init__(self, options: dict[str, Any]):
        self.options = options
        self.routes = options.get("routes", [])
        self.destinations = {item["id"]: item for item in options.get("destinations", [])}
        self.sources = {
            item["id"]: item
            for item in options.get("mqtt_sources", []) + options.get("ha_sources", [])
        }
        self.outbox = SQLiteOutbox(
            "/data/events.sqlite",
            max_items=int(options.get("queue_max_items", 10000)),
        )
        self.stop_event = threading.Event()
        self.rate_windows: dict[str, deque[float]] = {}
        self.rate_lock = threading.Lock()
        self.delivery_thread = threading.Thread(target=self._deliver_loop, name="delivery", daemon=True)

    def start(self) -> None:
        self.delivery_thread.start()
        workers = []
        for source in self.options.get("mqtt_sources", []):
            worker = MQTTSource(self, source)
            worker.start()
            workers.append(worker)
        for source in self.options.get("ha_sources", []):
            worker = HomeAssistantSource(self, source)
            worker.start()
            workers.append(worker)
        LOG.info("relay started with %d route(s), %d queued message(s)", len(self.routes), self.outbox.pending_count())
        try:
            while not self.stop_event.wait(5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_event.set()
            for worker in workers:
                worker.stop()
            self.outbox.close()

    def stop(self) -> None:
        self.stop_event.set()

    def accept(self, source_id: str, event: dict[str, Any], *, topic: str | None = None) -> None:
        """Filter one normalized CloudEvent and enqueue matching destinations."""

        for route in self.routes:
            if route.get("source") != source_id:
                continue
            if not route_matches(route, event, topic=topic):
                continue
            if not self._within_rate(route):
                LOG.warning("rate limit reached route=%s", route.get("id"))
                continue
            outbound = copy.deepcopy(event)
            paths = route.get("redact_paths", []) or []
            if paths:
                outbound["data"] = redact(outbound.get("data"), paths)
            body = json.dumps(outbound, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            max_bytes = int(route.get("max_payload_bytes", 262144))
            if len(body) > max_bytes:
                LOG.warning("dropping oversized event route=%s bytes=%d", route.get("id"), len(body))
                continue
            destination = str(route["destination"])
            dedupe = f"{route['id']}:{outbound['id']}"
            content_type = "application/cloudevents+json"
            try:
                inserted = self.outbox.enqueue(dedupe, destination, body, content_type)
            except RuntimeError as exc:
                LOG.error("outbox full; event was not queued route=%s error=%s", route.get("id"), exc)
                continue
            if inserted:
                LOG.debug("queued event route=%s destination=%s", route.get("id"), destination)

    def _within_rate(self, route: dict[str, Any]) -> bool:
        limit = int(route.get("max_per_minute", 0) or 0)
        if limit <= 0:
            return True
        route_id = str(route["id"])
        now = time.monotonic()
        with self.rate_lock:
            window = self.rate_windows.setdefault(route_id, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    def _deliver_loop(self) -> None:
        while not self.stop_event.wait(0.2):
            message = self.outbox.due()
            if message is None:
                continue
            destination = self.destinations.get(message.destination)
            if destination is None:
                self.outbox.mark_failed(message.row_id, "destination removed", retryable=False)
                continue
            try:
                self._post(destination, message.body, message.content_type)
            except HTTPError as exc:
                retryable = exc.code == 429 or exc.code >= 500
                self.outbox.mark_failed(message.row_id, f"HTTP {exc.code}", retryable=retryable)
                LOG.warning("delivery failed destination=%s status=%d retryable=%s", message.destination, exc.code, retryable)
            except (URLError, TimeoutError, OSError) as exc:
                self.outbox.mark_failed(message.row_id, str(exc), retryable=True)
                LOG.warning("delivery unavailable destination=%s error=%s", message.destination, exc)
            except Exception as exc:  # keep the relay alive on a malformed destination
                self.outbox.mark_failed(message.row_id, str(exc), retryable=False)
                LOG.error("delivery failed destination=%s error=%s", message.destination, exc)
            else:
                self.outbox.mark_sent(message.row_id)
                LOG.debug("delivered destination=%s", message.destination)

    def _post(self, destination: dict[str, Any], body: bytes, content_type: str) -> None:
        headers = {"Content-Type": content_type, "User-Agent": "homeassistant-event-relay/0.1"}
        if destination.get("auth_type", "bearer") == "bearer":
            headers["Authorization"] = f"Bearer {destination['auth_token']}"
        request = Request(str(destination["url"]), data=body, headers=headers, method="POST")
        with HTTP_OPENER.open(request, timeout=float(self.options.get("http_timeout_seconds", 15))) as response:
            if not 200 <= response.status < 300:
                raise HTTPError(request.full_url, response.status, "unexpected response", response.headers, None)


class MQTTSource(threading.Thread):
    def __init__(self, relay: Relay, config: dict[str, Any]):
        super().__init__(name=f"mqtt:{config['id']}", daemon=True)
        self.relay = relay
        self.config = config
        self.client = None
        self.connected = threading.Event()
        self.heartbeat_thread = None

    def run(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            LOG.error("paho-mqtt is not installed; MQTT source %s is disabled", self.config["id"])
            return
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.config["id"],
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        self.client = client
        username = self.config.get("username")
        if username:
            client.username_pw_set(username, self.config.get("password", ""))
        if self.config.get("tls", False):
            client.tls_set()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        while not self.relay.stop_event.is_set():
            try:
                client.connect(str(self.config.get("host", "core-mosquitto")), int(self.config.get("port", 1883)), 60)
                client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                LOG.warning("MQTT source %s unavailable: %s", self.config["id"], exc)
                self.relay.stop_event.wait(5)
            finally:
                self.connected.clear()

    def stop(self) -> None:
        self.connected.clear()
        if self.client is not None:
            self.client.disconnect()

    def _emit_heartbeat(self, *, healthy: bool, resynced: bool) -> None:
        heartbeat = self.config.get("heartbeat")
        if not isinstance(heartbeat, dict) or not heartbeat.get("enabled", False):
            return
        data = heartbeat.get("data", {"healthy": healthy, "resynced": resynced})
        if not isinstance(data, dict):
            LOG.warning("MQTT source %s heartbeat data must be an object", self.config["id"])
            return
        data = dict(data)
        data["healthy"] = healthy
        data["resynced"] = resynced
        # Each periodic heartbeat must have a fresh identity; otherwise the
        # durable outbox would correctly deduplicate every heartbeat after the
        # first one and the downstream quiet-window timer would go stale.
        data["observed_at"] = time.time()
        event = cloud_event(
            self.config["id"],
            data,
            source_kind="mqtt",
            event_type=str(heartbeat.get("event_type", "frigate.bridge.heartbeat")),
            subject=str(heartbeat.get("subject")) if heartbeat.get("subject") else None,
            source_override=self.config.get("source_uri") or None,
        )
        self.relay.accept(self.config["id"], event)

    def _heartbeat_loop(self) -> None:
        heartbeat = self.config.get("heartbeat")
        interval = max(5.0, float(heartbeat.get("interval_seconds", 30))) if isinstance(heartbeat, dict) else 30.0
        while not self.relay.stop_event.wait(interval):
            if self.connected.is_set():
                self._emit_heartbeat(healthy=True, resynced=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", False):
            LOG.warning("MQTT source %s rejected: %s", self.config["id"], reason_code)
            return
        for item in self.config.get("topics", []):
            topic = item.get("topic") if isinstance(item, dict) else item
            qos = int(item.get("qos", 1)) if isinstance(item, dict) else 1
            client.subscribe(topic, qos=qos)
        self.connected.set()
        self._emit_heartbeat(healthy=True, resynced=True)
        if isinstance(self.config.get("heartbeat"), dict) and self.config["heartbeat"].get("enabled", False):
            if self.heartbeat_thread is None or not self.heartbeat_thread.is_alive():
                self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name=f"heartbeat:{self.config['id']}", daemon=True)
                self.heartbeat_thread.start()
        LOG.info("MQTT source %s connected", self.config["id"])

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected.clear()
        self._emit_heartbeat(healthy=False, resynced=False)
        LOG.warning("MQTT source %s disconnected: %s", self.config["id"], reason_code)

    def _on_message(self, client, userdata, message):
        raw = message.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"payload": raw}
        event_type = get_path(payload, str(self.config.get("event_type_path", "")))
        subject = get_path(payload, str(self.config.get("subject_path", "")))
        prefix = str(self.config.get("event_type_prefix", "mqtt."))
        event = cloud_event(
            self.config["id"],
            payload,
            source_kind="mqtt",
            topic=message.topic,
            event_type=f"{prefix}{event_type}" if event_type else "mqtt.message",
            subject=str(subject) if subject is not None else None,
            source_override=self.config.get("source_uri") or None,
        )
        self.relay.accept(self.config["id"], event, topic=message.topic)


class HomeAssistantSource(threading.Thread):
    def __init__(self, relay: Relay, config: dict[str, Any]):
        super().__init__(name=f"ha:{config['id']}", daemon=True)
        self.relay = relay
        self.config = config
        self.socket = None

    def run(self) -> None:
        try:
            import websocket
        except ImportError:
            LOG.error("websocket-client is not installed; HA source %s is disabled", self.config["id"])
            return
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            LOG.error("SUPERVISOR_TOKEN is unavailable; HA source %s is disabled", self.config["id"])
            return
        event_types = [str(item) for item in self.config.get("event_types", []) if item]
        if not event_types:
            LOG.error("HA source %s needs event_types; refusing an unbounded subscription", self.config["id"])
            return
        while not self.relay.stop_event.is_set():
            try:
                self.socket = websocket.create_connection(
                    "ws://supervisor/core/api/websocket",
                    timeout=30,
                    header=[f"Authorization: Bearer {token}"],
                )
                self._subscribe(event_types)
                self._read_loop()
            except Exception as exc:
                LOG.warning("HA source %s unavailable: %s", self.config["id"], exc)
                self.relay.stop_event.wait(5)
            finally:
                if self.socket is not None:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None

    def stop(self) -> None:
        if self.socket is not None:
            self.socket.close()

    def _subscribe(self, event_types: list[str]) -> None:
        message = json.loads(self.socket.recv())
        if message.get("type") != "auth_required":
            raise RuntimeError("HA websocket did not request authentication")
        self.socket.send(json.dumps({"type": "auth", "access_token": os.environ["SUPERVISOR_TOKEN"]}))
        auth_result = json.loads(self.socket.recv())
        if auth_result.get("type") != "auth_ok":
            raise RuntimeError("HA websocket authentication failed")
        for index, event_type in enumerate(event_types, start=1):
            request = {"id": index, "type": "subscribe_events"}
            if event_type != "*":
                request["event_type"] = event_type
            self.socket.send(json.dumps(request))
            result = json.loads(self.socket.recv())
            if result.get("success") is not True:
                raise RuntimeError(f"HA event subscription failed: {event_type}")
        LOG.info("HA source %s subscribed to %s", self.config["id"], ", ".join(event_types))

    def _read_loop(self) -> None:
        while not self.relay.stop_event.is_set():
            message = json.loads(self.socket.recv())
            if message.get("type") != "event":
                continue
            event = message.get("event", {})
            event_type = event.get("event_type", "unknown")
            data = event.get("data", {})
            subject = data.get("entity_id") if isinstance(data, dict) else None
            if isinstance(subject, list):
                subject = ",".join(str(item) for item in subject)
            envelope = cloud_event(
                self.config["id"],
                data,
                source_kind="event_bus",
                event_type=f"homeassistant.{event_type}",
                subject=str(subject) if subject else None,
                event_id=stable_event_id(self.config["id"], event, topic=event_type),
                occurred_at=event.get("time_fired"),
            )
            self.relay.accept(self.config["id"], envelope)


def main() -> None:
    options_path = Path("/data/options.json")
    if not options_path.exists():
        raise SystemExit("/data/options.json is missing")
    try:
        options = parse_options(json.loads(options_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ConfigurationError) as exc:
        raise SystemExit(f"invalid relay configuration: {exc}") from exc
    _configure_logging(options)
    Relay(options).start()


if __name__ == "__main__":
    main()
