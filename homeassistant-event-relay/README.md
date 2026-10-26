# Home Assistant Event Relay

This add-on is a configurable, local event relay. It can subscribe to selected
Home Assistant Event Bus event types and MQTT topics, filter them with declarative
rules, redact JSON paths, and deliver CloudEvents to configured authenticated HTTP endpoints. HTTPS is
the default; trusted local HTTP requires explicit opt-in.

It is intentionally a separate add-on from `nyxid-node`. NyxID node remains a
reverse proxy; this add-on owns persistent event delivery and explicit outbound
event permissions. A failed relay cannot disconnect the NyxID node.

The default configuration has no sources and no routes. Nothing leaves Home
Assistant until a route is configured. Destination URLs use HTTPS by default and
credentials are add-on password options. The SQLite outbox is kept in `/data`
and retries transient delivery failures after restarts.

For a trusted local add-on such as [CMA Event Pipeline](../cma-event-pipeline/README.md),
set a destination's `allow_local_http: true` explicitly. HTTP is then accepted
only for a private IP or a Supervisor add-on hostname (`core-…`, `local-…` or
the repository hash prefix), with the normal bearer credential. Public HTTP,
URL credentials and redirects remain refused. When migrating, change the URL
of the existing destination without renaming its ID: queued messages retain
that identity and will drain to the new local endpoint.

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
  - id: pipeline_ingest
    url: http://0123abcd-cma-event-pipeline:8080/ingest
    allow_local_http: true
    auth_type: bearer
    auth_token: <configured-in-HA>

routes:
  - id: frigate_reviews
    source: frigate
    destination: pipeline_ingest
    event_types: []
    # Heartbeats have no MQTT topic; the source already subscribes only to reviews.
    topics: []
    subjects: []
    json_equals: []
    redact_paths: []
    max_payload_bytes: 262144
    max_per_minute: 0

  - id: selected_states
    source: ha_state
    destination: pipeline_ingest
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

The add-on does not call CMA directly. The separate Pipeline validates the
relay token, aggregates metadata and signs only candidate events for CMA. It
can run on the same HA host or on an explicitly configured remote deployment.
The CMA HMAC secret belongs to Pipeline configuration, not Relay options.
For a remote destination use HTTPS and omit `allow_local_http`; no cloud
aggregation app is required for the local topology.

The relay forwards metadata only. Image selection and model work belong to the
downstream application.

## End-to-end application example

The [dining review reference application](https://github.com/ChronoAIProject/frigate-cma-events/tree/main/examples/dining)
connects this relay to local HA aggregation, a bounded historical image
endpoint, a CMA visual worker and Google Sheets. The application also supports
cloud aggregation as an alternative. Its walkthrough covers private
camera-filtered relay, pipeline, worker/channel and Sheet settings. Actual camera identifiers, accounts and credentials are filled in
private installation files outside the repositories. The scene-specific rules
and worker prompt are maintained with that application; this add-on provides
the reusable event transport.

## Operations and migration

Use the actual internal hostname from Supervisor's add-on information; the
repository prefix varies by installation. `0123abcd` above is synthetic.
Relay's `auth_token` must equal the receiving Pipeline's `relay_token`.
A worker/operator credential is not an ingest credential.

When moving an existing route, keep its destination ID and change only the
URL/credential/local-HTTP option deliberately. Durable queued entries reference
that ID; renaming it can strand old deliveries. Do not infer an empty Relay
queue from Pipeline's `cma_deliveries.pending`: they are separate outboxes.

Verify actual delivery and downstream candidate/result processing before
removing a retired destination or cloud application. A synthetic Pipeline replay
has no external side effects; explicit integration validation exercises its
outbound CMA/worker path and bypasses MQTT admission. A real source event is
needed to validate that upstream path. See the [Pipeline runbook](../cma-event-pipeline/README.md)
for the full test and cleanup sequence.
