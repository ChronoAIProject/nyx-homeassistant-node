# Changelog

## 1.1.1-alpha.1

- **Auto-provisioning**: users no longer need to pre-create the HA service slug on their own machine. The add-on creates the service automatically on first start, using the `ha_service_label` field.
- State is anchored by service UUID in `/data/ha-service-id`, immune to label edits/collisions.
- Legacy slug from `/data/configured-services.txt` first line is auto-migrated to UUID state on upgrade.
- Uses single-POST creation pattern (bearer + node_id in one call) to work around NyxID #419.
- Removed `ha_service_slug` option; added `ha_service_label` (default `Home Assistant`).

## 0.1.0

- Initial release
- NyxID credential node agent packaged as HA Add-on
- Auto-configured Home Assistant API access via SUPERVISOR_TOKEN
- Support for additional LAN service proxying
- Multi-arch support (amd64, aarch64)
