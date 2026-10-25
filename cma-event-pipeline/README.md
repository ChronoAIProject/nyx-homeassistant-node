# CMA Event Pipeline — local Home Assistant add-on

Run the generic [CMA Event Pipeline](https://github.com/ChronoAIProject/frigate-cma-events)
beside Home Assistant and Frigate. The upstream repository owns the aggregation,
evidence and HTTP code; this directory only packages its pinned image and maps
explicit HA options. It needs no Supervisor admin, HA API, host network, Docker
socket, NAS mounts or machine/browser capability. No host port is published.

```text
HA / MQTT -> HA Event Relay -> this add-on /ingest
   -> configured filters, per-subject windows, deduplication and limits
   -> durable signed outbox -> owner's CMA channel -> worker
                                                   |
                            NyxID -> existing local node -> /evidence and /results
                                      |
                          local Frigate history -> bounded selected pages
```

## Installation and configuration

1. Add this repository to the HA add-on store and install **CMA Event Pipeline**.
2. Copy a fully resolved private JSON policy into `pipeline_config`. Use the
   upstream [configuration guide](https://github.com/ChronoAIProject/frigate-cma-events/blob/main/docs/pipeline.md)
   and dining, HA-state or driveway examples. A deployment has one policy and
   may handle many entity subjects. Do not commit installation data.
3. Set distinct random `relay_token`, `api_token`, `provider_token` and
   `worker_token` strings, each at least 32 characters. The provider token is
   reserved for the optional provider API. `worker_token` grants evidence and
   callbacks, not operator access. Credentials live in private HA options and
   HA backups; do not paste them into public issues or logs.
4. Set the exact CMA custom event URL, HMAC key ID and matching HMAC secret.
   Set `worker_service` to the owner's actual NyxID service slug and optionally
   `worker_name` for health/agent-card display. These are deployment parameters.
5. For Frigate evidence, configure `frigate_url` with its trusted internal base
   URL, for example `http://EXAMPLE-frigate:5000`. This uses the add-on network;
   source media is sampled locally. `frigate_api_key` is optional for a direct
   unauthenticated internal API, and is sent as bearer only when configured.
6. Configure the existing NyxID node's services list with this add-on's internal
   URL and `Authorization: Bearer <worker_token>`. Create or update the matching
   NyxID service, bound to that node, and authorize the CMA worker for the service
   and backing node. Use the actual hostname from Supervisor add-on info.
7. Point the selected HA Event Relay destination to
   `http://EXAMPLE-cma-event-pipeline:8080/ingest` with `auth_type: bearer` and
   `auth_token: <relay_token>`. Forward only explicitly selected events. Keep
   its source URI identical to the pipeline's source.

`heartbeat_seconds` and `tick_seconds` tune health freshness and processing.
Start the add-on and verify health and authenticated status over the local node.
The worker's existing event schema/prompt must agree with the configured output.
Do not expose the unauthenticated internal Frigate API or this port publicly.

CMA's current managed-key contract does not retain node grants
([CMA #1111](https://github.com/ChronoAIProject/cma/issues/1111)). For that client,
keep the original worker-facing NyxID service ID and use a bounded delegation:
create a separate node-bound service for this add-on, mint a `proxy read` key
restricted to exactly that service and its backing node (all broad access flags
false), then point the original worker-facing service at the HTTPS NyxID proxy
URL of the local service and inject that delegated key as bearer. The inner
service injects `worker_token` on the node. This uses existing NyxID service
routing; it adds no cloud application or model permission to raw Frigate.
Leave CMA-managed keys unchanged so its renewal contract remains valid. Keep
the delegate private, record its expiry, and rotate it through the original
service credential before expiry. Verify both proxy layers with the worker.

## Persistence and migration

SQLite databases live under `/data/state`, owned by the unprivileged runtime
user and included in HA add-on backups. Credentials/configuration remain in
`/data/options.json`; the service runs as UID 1000 after initialization. Images
are bounded volatile caches; raw recordings stay in Frigate/NAS. No MongoDB or
cloud database is required. Preserve `/data` when updating/restarting and run a
single instance per state set.

To move an existing cloud deployment:

1. Back up its private app spec, effective pipeline, results and downstream rows.
   Prepare the same pipeline, tokens, CMA channel and worker on the add-on.
2. Upgrade the source to an export-capable core and set
   `PROCESSING_ENABLED=false`. Wait for it to be healthy and verify zero pending
   delivery before migration. The still-running relay queues during the pause.
3. Download its operator-only `/api/state/export` for a private rollback backup.
   Set `state_import_url` to that exact HTTPS URL. On the first startup into an
   empty state directory, the add-on fetches it using `api_token`, validates all
   database checksums, source/policy digests and SQLite integrity, and restores
   before accepting requests. Redirects and existing database replacement are
   refused. Restarting with existing databases skips network import.
4. Update the original worker-service endpoint/node binding, or configure the
   bounded delegation above (preserving its service ID/grants), inject the
   worker token into the local NyxID node, then
   switch the relay's existing destination to this add-on. Avoid dual writers.
5. Verify historic IDs/results and downstream rows, relay recovery, an explicit
   integration test and restart persistence. Remove `state_import_url`, stop the
   cloud instance, and retain the private snapshot/spec for rollback.

If import fails, the service stays stopped. Correct the private configuration or
restore deliberately from a backup; never discard existing state to retry. The
core rejects an aggregation-policy change against an existing state history.
Evidence-only tuning remains compatible. Keep independent policies/owners in
separate deployments.

The cloud deployment remains a supported upstream option for other installations.
