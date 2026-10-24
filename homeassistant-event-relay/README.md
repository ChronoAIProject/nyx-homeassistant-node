# Home Assistant Event Relay

This add-on is a configurable, local event relay. It can subscribe to selected
Home Assistant Event Bus event types and MQTT topics, filter them with declarative
rules, redact JSON paths, and deliver CloudEvents to HTTPS destinations.

It is intentionally a separate add-on from `nyxid-node`. NyxID node remains a
reverse proxy; this add-on owns persistent event delivery and explicit outbound
event permissions. A failed relay cannot disconnect the NyxID node.

The default configuration has no sources and no routes. Nothing leaves Home
Assistant until a route is configured. Destination URLs must use HTTPS and
credentials are add-on password options. The SQLite outbox is kept in `/data`
and retries transient delivery failures after restarts.

## Example configuration

The values below are placeholders. Set real broker credentials, destination
tokens, entity IDs and camera names in the add-on configuration; none belong in
the public repository.

```yaml
mqtt_sources:
  - id: frigate
    host: core-mosquitto
    port: 1883
    username: relay_user
    password: <configured-in-HA>
    tls: false
    source_uri: urn:frigate:home
    event_type_path: type
    event_type_prefix: frigate.review.
    subject_path: after.camera
    heartbeat:
      enabled: true
      interval_seconds: 30
      event_type: frigate.bridge.heartbeat
      subject: example_dining_camera
    topics:
      - topic: frigate/reviews
        qos: 1

ha_sources:
  - id: ha_state
    event_types:
      - state_changed

destinations:
  - id: cloud_ingest
    url: https://example.invalid/ingest
    auth_type: bearer
    auth_token: <configured-in-HA>

routes:
  - id: frigate_reviews
    source: frigate
    destination: cloud_ingest
    event_types: []
    topics:
      - frigate/reviews
    subjects: []
    json_equals: []
    redact_paths: []
    max_payload_bytes: 262144
    max_per_minute: 0

  - id: selected_states
    source: ha_state
    destination: cloud_ingest
    event_types:
      - homeassistant.state_changed
    subjects:
      - sensor.example
    topics: []
    json_equals: []
    redact_paths:
      - new_state.attributes
    max_payload_bytes: 262144
    max_per_minute: 60
```

Set the Home Assistant source event_types list to ["*"] only when it is
intended to subscribe to the entire Event Bus. This is explicit because the
unfiltered stream is high volume and can contain sensitive data.

An MQTT source may optionally emit a connection health heartbeat. The heartbeat
is only useful when the source adapter has actually checked its broker
connection. `healthy` reports broker connectivity; `resynced` remains false
because a connection does not prove producer history was recovered. The
downstream consumer must repair gaps against its source API before treating
silence as a quiet period.

The add-on does not call CMA directly. The cloud destination validates the
relay token, performs aggregation and sends only the final candidate event to a
CMA custom channel. Keeping the CMA HMAC secret in the cloud service means the
HA relay cannot forge CMA events.

The relay forwards metadata only. Image selection and model work belong to the
downstream application.

## End-to-end application example

The [dining review reference application](https://github.com/ChronoAIProject/frigate-cma-events/tree/main/examples/dining)
connects this relay to deterministic cloud aggregation, a bounded historical
image endpoint, a CMA visual worker and Google Sheets. Its templates include a
camera-filtered relay configuration and the matching cloud/worker/channel/Sheet
parameters. Actual camera identifiers, accounts and credentials are filled in
private installation files outside the repositories. The scene-specific rules
and worker prompt are maintained with that application; this add-on provides
the reusable event transport.
