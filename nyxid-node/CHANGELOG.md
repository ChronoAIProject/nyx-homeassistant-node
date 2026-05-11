# Changelog

## 1.1.1-alpha.4

- Bump bundled nyxid agent to 0.5.3 (picks up NyxID#696 — rustls `aws_lc_rs` `CryptoProvider` now installed at startup, so `nyxid node register` no longer panics on Linux GNU targets).
- Move runtime base from `debian:bookworm-slim` (GLIBC 2.36) to `debian:trixie-slim` (GLIBC 2.40) so the public release binary's symbol requirements are satisfied.
- End-to-end verified on a HAOS qemuarm-64 box: auto-provisioned service `home-assistant-haos`, `nyxid proxy request <slug> states` returns real entity data.

## 1.1.1-alpha.3

- Bump bundled nyxid agent to 0.5.2.
- Switch Dockerfile to pull the nyxid binary from public `ChronoAIProject/NyxID` release tarballs at build time, dropping the dependency on the private `ghcr.io/chronoaiproject/nyxid/node-agent` base image.

## 1.1.1-alpha.2

- Fix: inherited setup.sh in admin variant no longer misprovisions a `null` HA service. `bashio::config` returns the literal string `"null"` when the option key is missing, which wasn't caught by `is_empty`. Now treats missing/null/empty `ha_service_label` as "skip HA provision" — correct behavior for admin, unchanged for main (default label set).

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
