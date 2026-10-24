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


if __name__ == "__main__":
    unittest.main()
