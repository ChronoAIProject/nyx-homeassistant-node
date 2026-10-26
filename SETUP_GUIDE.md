# NyxID Node HA add-on — setup guide

For an AI-assisted setup, inspect current add-on configuration and scripts.
Use private HA fields or the supported NyxID credential-entry flow for secrets;
keep installation-specific values out of source, logs and public issues.

This guide installs the ordinary credential node. The independent
[Event Relay](homeassistant-event-relay/README.md) and
[CMA Event Pipeline](cma-event-pipeline/README.md) have their own configuration
and lifecycle. A browser/machine node is not needed for this event workflow.

## Prerequisites

- Home Assistant OS with Supervisor and access to its add-on store.
- A local NyxID CLI and account session: `nyxid --version`, `nyxid whoami`.
  Run `nyxid login` if needed.
- The intended NyxID organization, server URL and owner authorization.

## 1. Install the ordinary add-on

In **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:

```text
https://github.com/ChronoAIProject/nyx-homeassistant-node
```

Install **NyxID Node**. Experimental releases may require Advanced mode in your
HA profile. The image supports amd64 and aarch64.

## 2. Supply the provisioning credential

Create a dedicated management key locally:

```sh
nyxid api-key create --name ha-addon \
  --scopes "read write" --allow-all-nodes --allow-all-services
```

Enter its one-time secret directly into the add-on's **NyxID API Key** field.
It needs permission to register/recover the node and, for automatic provisioning,
manage its HA service. This management credential omits `proxy`; the owner or
calling agent needs its own proxy authorization. Broad service/node flags support
initial provisioning and should follow your organization's management policy.

## 3. Configure and start

| Option | Value / behavior |
| --- | --- |
| `nyxid_server_url` | Your server's node WebSocket URL; the installed schema supplies the default |
| `nyxid_api_key` | Dedicated provisioning key |
| `ha_service_label` | Desired display label, default `Home Assistant` |
| `ha_service_slug` | Empty for automatic creation; set only to reuse a pre-created service |
| `node_name` | Desired node display name |
| `log_level` | `info` for normal operation |
| `services` | Explicit local credential/target entries for additional services |

Save and start. The startup script:

1. Registers the node when needed and checks that a saved node still exists.
2. Reuses an explicit `ha_service_slug`, or attempts to create/reuse a service
   identified by its saved UUID and `ha_service_label`.
3. For a new automatic service, sends bearer auth and this node's ID in the same
   create request. It uses endpoint `http://supervisor/core/api`.
4. Injects the Supervisor-issued HA credential on this node each start, because
   that token rotates. Then it synchronizes additional `services` entries.
5. Starts the node's outbound WebSocket connection.

The ordinary add-on has HA Core API access and host networking. It does not have
Supervisor admin privileges. Its persistent identity and credentials live in
`/data`; HA options and backups can contain secrets. Requests/responses pass
through NyxID even when credential injection happens locally.

## 4. If automatic service creation is refused

Some NyxID deployments refuse service-management operations made with an API
key. A `403` here is not evidence that the node cannot register or proxy.

Use the owner session to create a custom HTTP service bound to the node ID shown
in the add-on logs. Include the final fields in **one create request**:

```json
{
  "label": "Home Assistant",
  "key_type": "http",
  "endpoint_url": "http://supervisor/core/api",
  "auth_method": "bearer",
  "auth_key_name": "Authorization",
  "node_id": "<ordinary-node-id>"
}
```

Use NyxID's supported service registration interface (`POST /api/v1/keys` on
versions exposing this API). Store the owner credential privately; do not copy
HA's Supervisor token to the server. Put the returned slug in `ha_service_slug`
and restart. The add-on then skips service management and injects its token
locally. Confirm the service is node-managed and bound to the correct node.

Do not create it with `auth_method: none` and add authentication later. Older
NyxID versions can retain the wrong credential type, requiring recreation.

## 5. Verify

Read the actual node and service IDs from logs / inventory:

```sh
nyxid node list
nyxid service list
nyxid proxy request <ha-service-slug> ""
nyxid proxy request <ha-service-slug> "states"
```

The empty path returns `{"message":"API running."}`. Paths are relative to the
service endpoint `/core/api`: use `states` and `services/<domain>/<service>`,
not `api/states`. Do not assume that a requested slug is exactly the returned
slug; use the server's actual value. Updates to service configuration take the
service UUID on CLI versions whose `service update` resolves IDs only.

## Additional LAN services

Create a separate NyxID service with the target's final endpoint, authentication
method and this node's ID in the initial request. Use the supported encrypted
node-credential injection flow, or synchronize a local `services` entry:

```yaml
services:
  - slug: example-service
    target_url: http://example-device.local:8080
    credential_type: header
    credential_name: Authorization
    credential_value: "Bearer <device-token>"
```

The actual slug must match the server record. The list installs local
credentials/targets but does not create service records. Restart to apply it.
Removing a synchronized entry can remove its local credential on the next
startup; maintain a single intended source of configuration for each slug.

For a separate HA identity, create a dedicated HA user and long-lived token,
then a separate bearer service pointing at `http://homeassistant.local:8123/api`
on this ordinary node. Use the supported private credential-entry flow. Grant
only the intended callers access and verify relative paths against that base.

## Temporary Supervisor access

**NyxID Node (Admin)** is a separate add-on/node with
`hassio_api: true`, `hassio_role: admin`, and manual boot. Its current script
expects a pre-created service; there is no `supervisor_service_label` option.

1. Install/start it to obtain its separate node ID from the logs.
2. With an owner session, create a node-bound bearer service in one request,
   using `endpoint_url: http://supervisor` and the **admin node's** ID.
3. Set its actual returned slug in `supervisor_service_slug`, save, restart.
   The startup script pushes the rotating Supervisor token locally.
4. Verify `nyxid proxy request <supervisor-slug> "supervisor/info"`.
5. Uninstall when finished. Remove unused remote service records/grants after
   checking that they are not used elsewhere.

Ordinary HA events and local pipeline processing do not require this add-on.

## Event workflow and retirement

For Frigate/HA → aggregation → CMA, install the independent Relay and Pipeline.
See the [pipeline guide](cma-event-pipeline/README.md) for local URLs, distinct
credential roles, scoped worker delegation, testing, state migration and
retirement. Images are selected on HA; the CMA worker performs visual inference.

After moving a cloud deployment, verify historical state, relay routing, worker
access and downstream readback before deleting old resources. Preserve private
exports/specs; clear the retired app's database and revoke only its unused
credentials. Current worker-facing routing/delegation and operator services
remain part of the local deployment.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Node registration fails | Provisioning-key expiry/scope and WebSocket/server URL |
| Service creation returns 403 | Owner-created service + explicit `ha_service_slug` fallback above |
| Service not found | Actual returned slug and owner/organization scope |
| `node_offline` / 502 / 503 | Node connection, correct node binding, node-managed credential type, local credential and target reachability; older NyxID errors can conflate these |
| Double `/api/api` path / 404 | Request path relative to the configured endpoint |
| Remote service deleted | Automatic mode can recreate it; explicit-slug mode requires an intentional replacement/update |
| Restored node no longer exists | Startup checks stale registration; inspect logs before discarding `/data` |
| Add-on absent from store | Refresh the repository and enable Advanced mode for experimental releases |

See [architecture notes](docs/ARCHITECTURE_NOTES.md) for HA authentication
boundaries, service-state details and historical upstream issues.
