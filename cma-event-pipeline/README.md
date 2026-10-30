# Video Event Monitor — local Home Assistant add-on

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

1. Add this repository to the HA add-on store and install **Video Event Monitor** (the existing `cma-event-pipeline` slug).
2. Copy a fully resolved private JSON policy into `pipeline_config`. Use the
   upstream [configuration guide](https://github.com/ChronoAIProject/frigate-cma-events/blob/main/docs/pipeline.md)
   and dining, HA-state or driveway examples. This imports `default` v1 once;
   after startup, manage multiple persistent rules in **Open web UI**.
   Do not commit installation data.
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
6. Configure the existing ordinary NyxID node's services list with this add-on's
   internal URL and `Authorization: Bearer <worker_token>`. Create the matching
   bearer service with its node binding in the initial request. Use the actual
   hostname from Supervisor add-on info. Clients need the service and backing
   node authorization; CMA managed workers use the explicit delegation below.
   Keep a separate owner-only operator service injecting `api_token`.
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

## Rule management

Open **Settings → Add-ons → Video Event Monitor → Open web UI**. The panel uses
HA's admin-only Ingress; API credentials are not embedded in the page and no host
port is published. Create a rule by camera, labels/zone, duration, grouping,
cooldown, daily cap and evidence crop, or edit the full declarative JSON.
New rules default to disabled with CMA delivery off. Enable local observation,
review recent decisions, then enable delivery when the channel/worker supports
that rule's event type. A deployment currently has one configured CMA destination
and worker credential; it does not automatically provision new workers.

Rules persist in `/data/state/monitoring.sqlite3`. Each edit or enable/disable
creates an immutable revision with independent windows and counters. Old queues
are paused, history and callbacks remain available. Activities that started
before the new revision are ignored, so edit during quiet periods when continuity
matters. Startup `pipeline_config` is bootstrap-only after import; change rules
in the page/API. Credentials, connection URLs and timers still use private HA
options and a restart. Preserve the original default rule to retain the existing
restaurant workflow unchanged.

The page provides camera discovery, advanced JSON, copy/archive, version history
and recent decisions/results. There are 32 rule IDs and 256 total revisions;
archive retains data. Use the owner-only `api/rules` CRUD/history API for scripts.
Updates/archive require `If-Match` with the current revision (428 when missing,
409 when stale). Relay/worker/provider credentials cannot edit rules. The full
[management and API guide](https://github.com/ChronoAIProject/frigate-cma-events/blob/main/docs/monitoring.md)
describes paths, migration and lifecycle behavior.

For all camera rules to receive input, Relay must forward all Frigate review
subjects plus a separate shared-bridge heartbeat with `subject: "*"` and the
same source URI. The service filters events per rule. A local Frigate URL enables
review repair even when a rule does not collect images. Unmatched events do not
trigger CMA work. Original `/evidence`, `/results` and `/api/pipeline` paths stay
pinned to imported default v1; new events carry versioned callback paths.

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
   integration test and restart persistence. Remove `state_import_url` and stop
   the cloud instance. Retain the private snapshot/spec as rollback artifacts,
   then retire the obsolete live resources using the sequence below.

If import fails, the service stays stopped. Correct the private configuration or
restore deliberately from a backup; never discard existing state to retry.
Managed edits create separate revision state. Keep separate owners/credentials
in separate deployments. After managed revisions exist, use a full HA add-on
backup; the legacy portable state export refuses to omit the rule registry.

The core reserves intermediate temporal observations before visual
deduplication. In the rule editor, set
`evidence.options.max_selected_gap_seconds` to the desired maximum observation
gap (default 300 seconds; 0 disables). This shares the existing source-frame,
selected-frame and image budgets. Check `coverage.temporal` and its warnings:
missing recordings, quality filtering or the budget can prevent the target.
Temporal coverage does not establish a real-world outcome.

## Packaging and updates

`config.yaml` declares the HA options, architectures and published add-on image.
`Dockerfile` starts from the core image pinned by digest and copies only the
small `app/` startup wrapper. `app/options.py` converts allowlisted HA options
into core settings. `app/run.py` prepares private state, optionally imports an
empty state directory once, drops to UID/GID 1000 and execs the core's uvicorn.
HA Supervisor manages install, boot, restart, update and backup.

Core logic lives in `frigate-cma-events`; there is no second copy in this
repository. Publish/test a core release, update the pinned digest, bump this
add-on's `config.yaml` version and publish its image before updating HA. The
workflow builds amd64/arm64, tests the option mapping and boots the actual image
with Supervisor-style options to check health and state ownership.

## Verification

1. Verify both Relay and Pipeline are running, Relay targets this internal
   `/ingest`, and its metadata source/heartbeat agrees with the policy.
2. Read `healthz`, `api/status` and `api/pipeline` through the owner operator
   route. Confirm the worker route cannot access `api/status` / `api/pipeline`.
3. Use operator `POST api/replay` for isolated metadata checks: candidate rules,
   duplicates and suppression. It must report zero model calls and persistent
   writes. It does not exercise Relay/MQTT or deliver a worker event.
4. Submit operator `POST api/validation` once when Frigate has a completed review
   and retained history. Save the `integration_test_…` candidate ID. This uses one
   historical frame/image, bypasses real trigger thresholds and queues CMA.
   On an uncertain response, inspect existing deliveries before submitting again.
5. Check the worker actually views the supplied image within its budget, performs
   the configured destination write/readback, and posts `integration_test` to
   `/results/{candidate_id}`. Independently read the destination and operator
   `api/results/{candidate_id}`; a successful CMA admission/callback alone is
   insufficient. Test records must not count as real application outcomes.
6. Verify a normal real-source event separately. For dining, evaluate fixed
   camera framing, detection/quiet-window behavior and dish visibility during
   an actual meal. End-to-end plumbing does not prove recognition accuracy.

Restart Pipeline and verify state/results/outbox persist. Its CMA pending count
is separate from Relay's delivery backlog. Selected images are volatile cached
artifacts; durable state and raw Frigate recordings have separate lifecycles.

## Retiring a migrated cloud deployment or failed worker

Keep the current Relay, Pipeline, ordinary node, worker, channel and required
routing/delegation/operator services. Different credential roles pointing to
one container are not redundant deployments.

1. Privately save the source app spec, portable state export and relevant
   destination readbacks. Confirm the local deployment has no bootstrap URL or
   active route pointing to the source, and verify the local chain and restart.
2. Back up the retired app's database before clearing its data. Check the exact
   database and account scope, then verify no application collections remain.
   Database-user removal alone does not remove stored data. Check the platform's
   actual purge implementation rather than trusting its flag/response name.
3. Delete the old cloud application, routes/secrets and database account using
   supported platform operations. Read back that the app is absent. A stopped
   zero-replica app is still a retained deployment record.
4. For failed CMA attempts, verify their sandbox contains no active unrelated
   agents and no current channel targets them. Stop/delete the retired Agent
   and retire its dedicated sandbox through CMA lifecycle APIs. Observe actual
   terminal states; acceptance is not completed cleanup. CMA may retain history
   or tombstones according to its retention policy.
5. Revoke manual keys proved exclusive to the removed cloud reader/failed
   attempts. Leave current channel/delegation keys and unrelated credentials
   intact. Let CMA retire its sandbox-managed key through its lifecycle.
6. Update private active deployment records and NyxBot operational memory. Keep
   backup/cleanup receipts clearly marked historical, with credential values
   excluded from public documentation. Recheck current health, worker service
   access and destination data after removal.

The cloud deployment remains a supported upstream option for other installations.
See the core [HA deployment guide](https://github.com/ChronoAIProject/frigate-cma-events/blob/main/docs/home-assistant.md)
for shared credential roles and configuration mapping.

## Independent event contexts and health

Use a CMA profile target with `partition.key: per_event` for independent analysis
tasks. An `existing_agent` target intentionally reuses one native conversation,
regardless of the gateway partition. Use a stable CloudEvent ID for delivery
retries; store business results in the destination rather than prior context.

Optional `cma_context_config` and separate `cma_context_token` configure the core's
CMA resource cleanup. The JSON names an HTTPS public CMA API base (`cma_url`),
the profile channel's immutable `agent_profile_ids` list and exclusive `workspace_id`, and
`grace_seconds` (300–86400; default 600). Obtain these from the owner's actual
channel and first native Agent. Never point it at a shared workspace or borrowed
Agent. The token is a dedicated owner key restricted to the CMA service only;
it stays on HA, outside the worker's service scope. Matching workspace AND
immutable profile identity are required before retiring an idle Agent. Active
work and approvals are preserved. Deletion is confirmed through resource readback.
CMA retains audit records under its own retention; runtime cleanup does not
erase the destination or pipeline results.
The core excludes deleted inventory history and drains a bounded page per idle
state; `context_cleanup.scan_limited` reports that later runs have more to scan.

`api/status` reports cleanup health and pending/delivered/permanently failed CMA
deliveries. A credential-free summary is logged every minute. Relay queue status
is separate; enable its owner-only diagnostic endpoint to inspect it directly.
