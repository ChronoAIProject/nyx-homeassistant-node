# Changelog

## 1.1.1-alpha.12

- **Fix: `supervisor.sh` no longer dies with `exited 22` when it can't create the Supervisor service.** NyxID rejects service creation via API keys (403 / error_code 1002), so the create POST always failed and the blind `curl -sf` aborted the script before the credential was ever pushed → `ha-supervisor` returned 403 on every authenticated call. Now: (1) before creating, the add-on **adopts an existing node-managed `http://supervisor` service already bound to this node** — create it once as a user (`nyxid service add --custom --slug ha-supervisor --via-node <node> --endpoint-url http://supervisor --auth-method bearer`; add `--org <slug>` to scope it) and the add-on picks it up automatically, with no `/data` STATE_FILE seed; (2) the create call logs the HTTP status + body instead of crashing; (3) the `SUPERVISOR_TOKEN` credential push is guarded so a failed provision can't abort the run.

## 1.1.1-alpha.11

- Rebase on nyxid-node 1.1.1-alpha.11 (bundled agent actually 0.8.0 now; stale-node self-heal + surfaced service-creation errors — NyxID#1245).

## 1.1.1-alpha.10

- Version bump to stay in lockstep with the main add-on (no functional change to the admin variant).

## 1.1.1-alpha.9

- Bump bundled nyxid agent to 0.8.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.8

- Bump bundled nyxid agent to 0.7.1 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.7

- Bump bundled nyxid agent to 0.7.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.6

- Bump bundled nyxid agent to 0.6.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.5

- Bump bundled nyxid agent to 0.5.6 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.2

- Pins to main image 1.1.1-alpha.2 which fixes the inherited-setup.sh null-HA-service bug.

## 1.1.1-alpha.1

- **Auto-provisioning**: users no longer need to pre-create the Supervisor service slug. The add-on creates the service automatically on first start, using the `supervisor_service_label` field.
- State is anchored by service UUID in `/data/supervisor-service-id`, immune to label edits/collisions.
- Legacy `/data/last-supervisor-slug` is auto-migrated to UUID state on upgrade.
- Uses single-POST creation pattern (bearer + node_id in one call) to work around NyxID #419.
- Removed `supervisor_service_slug` and `ha_service_slug` options; added `supervisor_service_label` (default `HA Supervisor`).

## 1.0.0

- Initial release — temporary admin variant of NyxID Node
- Declares `hassio_api: true` + `hassio_role: admin` for full Supervisor access
- Auto-binds a Supervisor NyxID service via the add-on's `SUPERVISOR_TOKEN`
- Defaults to `boot: manual` — install when needed, uninstall to revoke entirely
- Built as a thin layer on top of `ghcr.io/chronoaiproject/nyx-homeassistant-node`
