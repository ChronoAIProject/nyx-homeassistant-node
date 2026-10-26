# NyxID Home Assistant add-ons

Run [NyxID](https://github.com/ChronoAIProject/NyxID) local credential routing and
configurable event processing on Home Assistant OS. This repository packages
four independent add-ons for amd64 and aarch64:

| Add-on | Responsibility | Permissions / storage |
| --- | --- | --- |
| **NyxID Node** | Proxy Home Assistant and selected LAN services through an outbound NyxID connection | HA Core API; host network; persistent node identity/credentials in `/data` |
| **NyxID Node (Admin)** | Temporary Supervisor management | Supervisor admin; install only for management work |
| **Home Assistant Event Relay** | Filter selected MQTT / HA events and reliably forward CloudEvents | HA Core API; persistent SQLite outbox in `/data` |
| **CMA Event Pipeline** | Aggregate, deduplicate, limit and select bounded historical evidence, then deliver candidates to CMA | No HA/Supervisor API permission or host ports; SQLite in `/data/state` |

## Installation

In **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:

```text
https://github.com/ChronoAIProject/nyx-homeassistant-node
```

Install the add-ons your workflow needs. Experimental versions may require
**Advanced mode** in your HA profile. This repository contains the HA packaging;
[CMA Event Pipeline's core](https://github.com/ChronoAIProject/frigate-cma-events)
is maintained and tested separately, and pinned by image digest in its Dockerfile.

## Set up NyxID Node

For an AI-assisted installation, give your assistant:

```text
Install the NyxID Node add-on on my Home Assistant. Follow https://github.com/ChronoAIProject/nyx-homeassistant-node/blob/main/SETUP_GUIDE.md
```

1. Sign in locally with `nyxid login` and create a dedicated provisioning key:

   ```sh
   nyxid api-key create --name ha-addon \
     --scopes "read write" --allow-all-nodes --allow-all-services
   ```

   Enter its one-time secret directly into HA's **NyxID API Key** field.
   This management key omits `proxy`; calling services requires separate proxy
   authorization. The broad service/node flags support provisioning; restrict
   management access according to your organization's policies.
2. Leave **HA Service Label** as `Home Assistant` and **HA Service Slug** empty
   for automatic provisioning. Set the server URL and node name, save, and start.
3. The add-on registers its node, creates/reuses a node-managed HA service when
   its key is allowed to manage services, and injects its Supervisor-issued Core
   credential locally on every start. If NyxID refuses service management for
   API keys, create the node-bound bearer service with an owner session and
   configure its returned `ha_service_slug`; see the [setup guide](SETUP_GUIDE.md).
4. Read the actual slug from the logs or `nyxid service list`, then verify:

   ```sh
   nyxid proxy request <ha-service-slug> ""
   nyxid proxy request <ha-service-slug> "states"
   ```

   Paths are relative to `http://supervisor/core/api`; the empty path returns
   `{"message":"API running."}`. Do not add another `api/` prefix.

Node credentials are injected on HA. Requests and responses still pass through
NyxID; local credential storage does not make the proxied response confidential
from that server. HA options and backups can also contain secrets.

## Local event processing

```text
Frigate / MQTT / selected HA Event Bus events
    -> Home Assistant Event Relay (filter + durable queue)
    -> CMA Event Pipeline on HA (aggregate + limits + historical selection)
    -> signed CMA Event Channel -> CMA visual worker -> configured destination

CMA worker -> NyxID -> ordinary HA node -> local pipeline /evidence and /results
                                            |
                                      local Frigate history
```

Raw recordings remain with Frigate and its configured storage. The local
pipeline samples historical frames and exposes only bounded candidate evidence.
CMA workers and NyxBot remain remote; selected images are sent to the worker for
analysis. This topology needs no cloud aggregation app or MongoDB. A NyxID
service entry is a credential/routing entry, not another application deployment.

- [Relay configuration](homeassistant-event-relay/README.md): explicit sources,
  routes, heartbeat semantics and trusted local HTTP destinations.
- [Pipeline installation and operations](cma-event-pipeline/README.md): HA
  options, storage, worker access, migration, verification and retirement.
- [Dining reference application](https://github.com/ChronoAIProject/frigate-cma-events/tree/main/examples/dining):
  whole-table observations, a CMA worker and verified Sheets writes.

The worker-facing evidence route, its node-bound delegate and the separate
operator route have different credential roles. Keep them while the workflow is
active. CMA currently requires scoped delegation for managed keys that cannot
retain node grants; the pipeline guide documents this and key rotation.

## Other LAN services and HA identities

Create the service with its final `node_id` and authentication method in the
initial request. For a bearer-protected LAN service, use the owner's supported
NyxID service setup / node-credential flow, or add a matching local entry:

```yaml
services:
  - slug: example-service
    target_url: http://example-device.local:8080
    credential_type: header
    credential_name: Authorization
    credential_value: "Bearer <device-token>"
```

Use the actual slug returned by NyxID. The `services` list configures local
credentials/targets; it does not create the server's service record. Restart the
node to apply changes. Values are private HA options and can be present in HA
backups. For additional HA identities, use separate HA users/tokens and separate
node-bound services pointing to `http://homeassistant.local:8123/api`.

Do not create a service as `auth_method: none` and later add bearer auth/node
binding: older NyxID versions can leave its credential type incompatible with
node routing. Follow the single-create pattern in the setup guide.

## Temporary Supervisor administration

The ordinary node has Core API permissions. To manage add-ons remotely, install
**NyxID Node (Admin)** temporarily. It registers a separate node and pushes a
Supervisor credential to a **pre-created** node-bound service named by
`supervisor_service_slug`; it does not auto-create that service. Create it with
an owner session, bearer auth, `endpoint_url: http://supervisor`, and the admin
node's actual ID. Configure the returned slug and restart the admin add-on.

```sh
nyxid proxy request <supervisor-service-slug> "supervisor/info"
nyxid proxy request <supervisor-service-slug> "addons"
```

Supervisor admin can install/remove add-ons and change host state. Grant this
route only to intended operators. Uninstall the admin add-on when finished and
retire its unused service/key grants. The Relay and Pipeline do not require it
for normal operation.

## Contributor references

- [Setup guide](SETUP_GUIDE.md) — current provisioning and verification.
- [Architecture notes](docs/ARCHITECTURE_NOTES.md) — auth boundaries and service lifecycle.
- [Assistant project guide](CLAUDE.md) — implementation and release facts.
- [Development history](DEVELOPMENT.md) and dated design documents — historical
  decisions; use current configuration/scripts for installation.
