"""Pure routing and durable outbox primitives for the HA event relay.

The connector process is deliberately kept separate from these primitives so
the routing rules can be tested without a Home Assistant or MQTT connection.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import json
from pathlib import Path
import sqlite3
import re
import threading
import time
from typing import Any, Iterable
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when a relay option is unsafe or cannot be interpreted."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_event_id(source_id: str, payload: Any, *, topic: str | None = None) -> str:
    """Return an id stable across MQTT redelivery and relay restarts."""

    identity = {"source": source_id, "topic": topic, "payload": payload}
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return f"urn:ha-event-relay:{digest}"


def cloud_event(
    source_id: str,
    payload: Any,
    *,
    source_kind: str,
    topic: str | None = None,
    event_type: str | None = None,
    subject: str | None = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
    source_override: str | None = None,
) -> dict[str, Any]:
    """Wrap one source message in a CloudEvents 1.0 JSON envelope."""

    if not source_id:
        raise ConfigurationError("source id cannot be empty")
    event = {
        "specversion": "1.0",
        "source": source_override or f"urn:homeassistant:{source_kind}:{source_id}",
        "id": event_id or stable_event_id(source_id, payload, topic=topic),
        "type": event_type or f"homeassistant.{source_kind}",
        "datacontenttype": "application/json",
        "data": payload,
    }
    if topic:
        event["topic"] = topic
    if subject:
        event["subject"] = subject
    if occurred_at:
        event["time"] = occurred_at
    return event


def mqtt_topic_matches(pattern: str, topic: str) -> bool:
    """Match MQTT + and # wildcards without treating them as shell globs."""

    if not isinstance(pattern, str) or not isinstance(topic, str):
        return False
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")
    for index, part in enumerate(pattern_parts):
        if part == "#":
            return index == len(pattern_parts) - 1
        if index >= len(topic_parts) or (part != "+" and part != topic_parts[index]):
            return False
    return len(pattern_parts) == len(topic_parts)


def get_path(value: Any, path: str) -> Any:
    if not path:
        return None
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _delete_path(value: Any, path: str) -> None:
    parts = path.split(".") if path else []
    if not parts:
        return
    current = value
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return
        if current is None:
            return
    last = parts[-1]
    if isinstance(current, dict) and last in current:
        current[last] = "[redacted]"
    elif isinstance(current, list) and last.isdigit() and int(last) < len(current):
        current[int(last)] = "[redacted]"


def redact(value: Any, paths: Iterable[str]) -> Any:
    """Copy a JSON-compatible value and redact configured dotted paths."""

    result = json.loads(json.dumps(value, ensure_ascii=False))
    for path in paths:
        _delete_path(result, path)
    return result


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def route_matches(route: dict[str, Any], event: dict[str, Any], *, topic: str | None = None) -> bool:
    """Apply a conservative declarative route filter."""

    event_type = event.get("type", "")
    allowed_types = [str(item) for item in _as_list(route.get("event_types")) if item]
    if allowed_types and not any(_type_matches(item, event_type) for item in allowed_types):
        return False

    topics = [str(item) for item in _as_list(route.get("topics")) if item]
    if topics and (topic is None or not any(mqtt_topic_matches(item, topic) for item in topics)):
        return False

    subjects = [str(item) for item in _as_list(route.get("subjects")) if item]
    if subjects and not any(_type_matches(item, str(event.get("subject", ""))) for item in subjects):
        return False

    for condition in _as_list(route.get("json_equals")):
        if not isinstance(condition, dict) or "path" not in condition:
            raise ConfigurationError("json_equals entries need path and value")
        if get_path(event, str(condition["path"])) != condition.get("value"):
            return False
    return True


def _type_matches(pattern: str, value: str) -> bool:
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return pattern == value


@dataclass(frozen=True)
class OutboxMessage:
    row_id: int
    dedupe_key: str
    destination: str
    body: bytes
    content_type: str
    attempts: int


class SQLiteOutbox:
    """A small durable, idempotent queue safe for one relay process."""

    def __init__(self, path: str | Path, *, max_items: int = 10000):
        self.path = str(path)
        self.max_items = max_items
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL UNIQUE,
                destination TEXT NOT NULL,
                body BLOB NOT NULL,
                content_type TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                dead INTEGER NOT NULL DEFAULT 0,
                sent_at REAL
            );
            CREATE INDEX IF NOT EXISTS outbox_due_idx
                ON outbox(sent_at, next_attempt, id);
            """
        )
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(outbox)")}
        if "dead" not in columns:
            self.db.execute("ALTER TABLE outbox ADD COLUMN dead INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    def enqueue(self, dedupe_key: str, destination: str, body: bytes, content_type: str) -> bool:
        if not dedupe_key or not destination:
            raise ConfigurationError("outbox identity and destination are required")
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM outbox WHERE dedupe_key=?", (dedupe_key,)).fetchone():
                return False
            count = self.db.execute("SELECT count(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0]
            if count >= self.max_items:
                raise RuntimeError("outbox capacity reached")
            cursor = self.db.execute(
                """INSERT INTO outbox
                   (dedupe_key, destination, body, content_type)
                   VALUES (?, ?, ?, ?)""",
                (dedupe_key, destination, body, content_type),
            )
        return cursor.rowcount == 1

    def due(self, now: float | None = None) -> OutboxMessage | None:
        now = time.time() if now is None else now
        with self.lock:
            row = self.db.execute(
                """SELECT id, dedupe_key, destination, body, content_type, attempts
                   FROM outbox
                   WHERE sent_at IS NULL AND dead=0 AND next_attempt <= ?
                   ORDER BY id LIMIT 1""",
                (now,),
            ).fetchone()
        if row is None:
            return None
        return OutboxMessage(
            row_id=row["id"],
            dedupe_key=row["dedupe_key"],
            destination=row["destination"],
            body=bytes(row["body"]),
            content_type=row["content_type"],
            attempts=row["attempts"],
        )

    def mark_sent(self, row_id: int, now: float | None = None) -> None:
        with self.lock, self.db:
            self.db.execute("UPDATE outbox SET sent_at=? WHERE id=?", (time.time() if now is None else now, row_id))

    def mark_failed(self, row_id: int, error: str, *, retryable: bool, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.lock, self.db:
            row = self.db.execute("SELECT attempts FROM outbox WHERE id=?", (row_id,)).fetchone()
            if row is None:
                return
            attempts = int(row[0]) + 1
            # Permanent errors remain visible for diagnosis but are not retried.
            next_attempt = now + min(3600, 2 ** min(attempts, 10)) if retryable else 0
            self.db.execute(
                "UPDATE outbox SET attempts=?, next_attempt=?, last_error=?, dead=? WHERE id=?",
                (attempts, next_attempt, error[:1000], 0 if retryable else 1, row_id),
            )

    def pending_count(self) -> int:
        with self.lock:
            return int(self.db.execute("SELECT count(*) FROM outbox WHERE sent_at IS NULL AND dead=0").fetchone()[0])

    def close(self) -> None:
        with self.lock:
            self.db.close()


def parse_options(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate the security-sensitive parts of the add-on options."""

    if not isinstance(raw, dict):
        raise ConfigurationError("options must be an object")
    options = dict(raw)
    for key in ("mqtt_sources", "ha_sources", "destinations", "routes"):
        value = options.get(key, [])
        if not isinstance(value, list):
            raise ConfigurationError(f"{key} must be a list")
    destination_ids = set()
    for destination in options["destinations"]:
        if not isinstance(destination, dict) or not destination.get("id") or not destination.get("url"):
            raise ConfigurationError("each destination needs id and url")
        destination_id = str(destination["id"])
        if destination_id in destination_ids:
            raise ConfigurationError(f"duplicate destination id: {destination_id}")
        destination_ids.add(destination_id)
        url = urlsplit(str(destination["url"]))
        local_http = destination.get("allow_local_http", False)
        if type(local_http) is not bool:
            raise ConfigurationError("allow_local_http must be a boolean")
        local_host = bool(re.fullmatch(r"(?:core|local|[0-9a-f]{8})-[a-z0-9][a-z0-9-]*", url.hostname or ""))
        try:
            address = ipaddress.ip_address(url.hostname or "")
            local_host = address.is_private and not address.is_unspecified and not address.is_multicast
        except ValueError:
            pass
        if (not url.hostname or url.username or url.password or url.fragment
                or not (url.scheme == "https" or (url.scheme == "http" and local_http and local_host))):
            raise ConfigurationError("use HTTPS, or explicitly allow HTTP to a private IP/add-on hostname")
        auth_type = destination.get("auth_type", "bearer")
        if auth_type not in {"none", "bearer"}:
            raise ConfigurationError("destination auth_type must be none or bearer")
        if auth_type == "bearer" and not destination.get("auth_token"):
            raise ConfigurationError(f"destination {destination_id} needs auth_token")
    source_ids = set()
    for group in (options["mqtt_sources"], options["ha_sources"]):
        for source in group:
            if not isinstance(source, dict) or not source.get("id"):
                raise ConfigurationError("each source needs id")
            source_id = str(source["id"])
            if source_id in source_ids:
                raise ConfigurationError(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
    for route in options["routes"]:
        if not isinstance(route, dict) or not route.get("id"):
            raise ConfigurationError("each route needs id")
        if route.get("source") not in source_ids:
            raise ConfigurationError(f"route {route['id']} references unknown source")
        if route.get("destination") not in destination_ids:
            raise ConfigurationError(f"route {route['id']} references unknown destination")
    # No route means no egress. This is an intentional safe default.
    return options
