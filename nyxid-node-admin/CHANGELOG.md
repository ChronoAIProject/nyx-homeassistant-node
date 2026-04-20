# Changelog

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
