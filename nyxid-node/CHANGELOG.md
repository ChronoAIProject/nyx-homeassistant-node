# Changelog

## 1.1.1-alpha.22

- Bump bundled nyxid agent to 0.17.2 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.21

- Bump bundled nyxid agent to 0.17.1 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.20

- Bump bundled nyxid agent to 0.14.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.19

- Bump bundled nyxid agent to 0.11.7 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.18

- Bump bundled nyxid agent to 0.11.5 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.17

- Bump bundled nyxid agent to 0.11.1 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.16

- Bump bundled nyxid agent to 0.10.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.15

- Bump bundled nyxid agent to 0.9.0 (auto-bumped by watch-nyxid workflow).

## 1.1.1-alpha.14

- Version bump in lockstep with the admin add-on (`supervisor.sh` credential `--secret-format` fix). No functional change to the main add-on.

## 1.1.1-alpha.13

- Version bump in lockstep with the admin add-on (`supervisor.sh` rewrite — node-local token push to a known slug, no `/api/v1/keys`). No functional change to the main add-on.

## 1.1.1-alpha.12

- Version bump in lockstep with the admin add-on (`supervisor.sh` reuse-by-node fix). No functional change to the main add-on.

## 1.1.1-alpha.11

- **Fix: bundled agent was stuck at 0.5.3** — `build.yaml` pinned `NYXID_VERSION: "0.5.3"`, which the HA builder passes as a build-arg and which overrode the Dockerfile default every auto-bump had been updating. The pin is removed so the Dockerfile `ARG NYXID_VERSION` (0.8.0) is the single source of truth. This restores remote credential injection (`nyxid node-credential inject` — the agent now answers the X25519 pubkey handshake) and all other post-0.5.3 agent features. (NyxID#1245 Bug 2)
- **Fix: stale node registration self-heals after a HAOS restore-from-backup** — `setup.sh` now verifies the locally-stored node id against the server and re-registers when the server no longer knows it, instead of failing service creation with an invisible HTTP error. (NyxID#1245 Bug 1)
- **Fix: service-creation errors are surfaced** — the create call logs the HTTP status and response body on failure instead of dying blind with `cont-init: ... exited 22`. (NyxID#1245 Bug 1)

## 1.1.1-alpha.10

- Document exposing multiple HA identities via per-token NyxID services (closes #1). Now that NyxID #418/#414 have landed, users create a long-lived access token per HA identity (admin / bot / read-only) and add each as a `bearer` `--via-node` service pointing at this node — NyxID delivers the credential to the node over the WebSocket, so the token never touches the add-on config or `/data`.
- Setup log now prints the node name + id and a ready-to-run `nyxid service add` command for adding those identities.

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
