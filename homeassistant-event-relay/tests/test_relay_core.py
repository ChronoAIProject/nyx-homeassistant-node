import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from relay_core import (  # noqa: E402
    ConfigurationError,
    SQLiteOutbox,
    cloud_event,
    mqtt_topic_matches,
    parse_options,
    redact,
    route_matches,
    stable_event_id,
)


class RelayCoreTests(unittest.TestCase):
    def test_event_id_is_stable(self):
        payload = {"type": "end", "after": {"id": "review"}}
        self.assertEqual(stable_event_id("frigate", payload, topic="frigate/reviews"), stable_event_id("frigate", payload, topic="frigate/reviews"))

    def test_source_uri_can_be_configured(self):
        event = cloud_event("mqtt", {"value": 1}, source_kind="mqtt", source_override="urn:frigate:home")
        self.assertEqual(event["source"], "urn:frigate:home")

    def test_mqtt_wildcards(self):
        self.assertTrue(mqtt_topic_matches("frigate/#", "frigate/reviews"))
        self.assertTrue(mqtt_topic_matches("frigate/+/snapshot", "frigate/camera/snapshot"))
        self.assertFalse(mqtt_topic_matches("frigate/+", "frigate/reviews/end"))
        self.assertFalse(mqtt_topic_matches("+/reviews", "other/events"))

    def test_route_filters_event_type_topic_and_json(self):
        event = cloud_event("source", {"type": "end", "after": {"camera": "dining"}}, source_kind="mqtt", topic="frigate/reviews", event_type="mqtt.end", subject="dining")
        route = {"event_types": ["mqtt.end"], "topics": ["frigate/#"], "json_equals": [{"path": "data.type", "value": "end"}]}
        self.assertTrue(route_matches(route, event, topic="frigate/reviews"))
        self.assertFalse(route_matches({**route, "event_types": ["mqtt.new"]}, event, topic="frigate/reviews"))

    def test_redact_does_not_mutate_input(self):
        value = {"data": {"secret": "keep-out", "nested": {"name": "ok"}}}
        redacted = redact(value, ["data.secret"])
        self.assertEqual(redacted["data"]["secret"], "[redacted]")
        self.assertEqual(value["data"]["secret"], "keep-out")

    def test_outbox_is_idempotent_and_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = SQLiteOutbox(Path(directory) / "events.sqlite", max_items=2)
            self.assertTrue(queue.enqueue("route:event", "cloud", b"{}", "application/json"))
            self.assertFalse(queue.enqueue("route:event", "cloud", b"{}", "application/json"))
            message = queue.due(now=0)
            self.assertEqual(message.attempts, 0)
            queue.mark_failed(message.row_id, "temporary", retryable=True, now=0)
            self.assertIsNone(queue.due(now=0))
            self.assertIsNotNone(queue.due(now=2))
            queue.mark_sent(message.row_id, now=2)
            self.assertEqual(queue.pending_count(), 0)
            queue.close()

    def test_queue_health_separates_retry_dead_and_delivered_without_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = SQLiteOutbox(Path(directory) / "events.sqlite")
            for i in range(3):queue.enqueue(str(i),"destination",b"private-payload","application/json")
            first=queue.due();queue.mark_sent(first.row_id)
            second=queue.due();queue.mark_failed(second.row_id,"private-error",retryable=False)
            third=queue.due();queue.mark_failed(third.row_id,"private-error",retryable=True)
            status=queue.status()
            self.assertEqual((status["pending"],status["dead"],status["delivered"],status["retrying"]),(1,1,1,1))
            self.assertGreaterEqual(status["oldest_pending_seconds"],0)
            self.assertNotIn("private",json.dumps(status))
            queue.close()

    def test_diagnostics_requires_token_and_excludes_event_data(self):
        from unittest.mock import patch
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import main
        with tempfile.TemporaryDirectory() as directory:
            queue=SQLiteOutbox(Path(directory)/"events.sqlite")
            token="synthetic-diagnostics-credential-only"
            with patch.object(main,"SQLiteOutbox",return_value=queue):
                relay=main.Relay({"diagnostics_token":token})
            relay._start_diagnostics(("127.0.0.1",0))
            base="http://127.0.0.1:"+str(relay.diagnostics_server.server_port)
            try:
                with self.assertRaises(HTTPError) as error:urlopen(base+"/api/status")
                self.assertEqual(error.exception.code,401)
                error.exception.close()
                req=Request(base+"/api/status",headers={"Authorization":"Bearer "+token})
                with urlopen(req) as response:status=json.load(response)
                self.assertEqual(status["queue"]["pending"],0)
                self.assertNotIn(token,json.dumps(status))
            finally:
                relay.diagnostics_server.shutdown();relay.diagnostics_server.server_close();queue.close()

    def test_options_require_https_and_explicit_routes(self):
        base = {
            "mqtt_sources": [{"id": "mqtt", "topics": [{"topic": "x"}]}],
            "ha_sources": [],
            "destinations": [{"id": "cloud", "url": "https://example.invalid/ingest", "auth_type": "none"}],
            "routes": [{"id": "r", "source": "mqtt", "destination": "cloud"}],
        }
        self.assertEqual(parse_options(base)["routes"][0]["id"], "r")
        with self.assertRaises(ConfigurationError):
            parse_options({**base, "destinations": [{"id": "cloud", "url": "http://example.invalid"}]})

    def test_plain_http_requires_explicit_local_destination(self):
        base = {"mqtt_sources": [], "ha_sources": [], "routes": []}
        for host in ('local-example-pipeline', 'core-example', '1234abcd-example', '172.30.33.9'):
            destination = {"id":"local", "url":"http://"+host+":8080/ingest", "auth_type":"bearer", "auth_token":"synthetic"}
            with self.subTest(host=host),self.assertRaises(ConfigurationError):
                parse_options({**base,"destinations":[destination]})
            self.assertEqual(parse_options({**base,"destinations":[{**destination,"allow_local_http":True}]})['destinations'][0]['url'],destination['url'])
        for url in ('http://public.example', 'http://8.8.8.8', 'http://0.0.0.0', 'http://user:pass@local-example', 'http://local-example/#secret'):
            with self.subTest(url=url),self.assertRaises(ConfigurationError):
                parse_options({**base,"destinations":[{"id":"local","url":url,"auth_type":"none","allow_local_http":True}]})


if __name__ == "__main__":
    unittest.main()
