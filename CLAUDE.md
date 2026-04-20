# CLAUDE.md — project guide for AI assistants

This repo ships two Home Assistant add-ons that bridge HA to NyxID. Before making changes, skim this file top to bottom — it captures the non-obvious bits that cost the last session hours to re-discover.

For the full narrative / deeper architecture, see [`docs/ARCHITECTURE_NOTES.md`](docs/ARCHITECTURE_NOTES.md). This file is the quick reference.

## What ships

| Add-on | Permission surface | When to use |
|---|---|---|
| `nyxid-node/` | `homeassistant_api: true` — HA Core REST only | Always installed. Main pipe between NyxID and HA. |
| `nyxid-node-admin/` | adds `hassio_api: true` + `hassio_role: admin` | Temporary. Install only when you need Supervisor-level ops (install add-ons, manage host). **Uninstalling = physical revocation** of admin capability. |

Both auto-provision their NyxID service on first start as of v1.1.1. User fills API key + label, add-on creates + binds + pushes credential.

## Hard facts about HA's auth (often misunderstood)

**Do NOT repeat the mistake of thinking "admin long-lived tokens can hit `/api/hassio/*`".** They can't hit most of it. The mechanism is a path whitelist, not a token-level check.

| Path | Accepts admin LLAT? |
|---|---|
| `/api/*` (Core REST) | ✅ |
| `/api/hassio/backups/*`, `/api/hassio/addons/<x>/logs`, `/changelog`, `/documentation` | ✅ (in `PATHS_ADMIN`) |
| `/api/hassio/supervisor/info`, `/addons` (list), `/store/*`, `/host/*`, `/addons/*/install` | ❌ 401 (not in whitelist; no flag widens it) |
| `/api/websocket` + `hassio/update/addon` command | ✅ — Supervisor passthrough (what HACS uses) |
| `http://supervisor/*` from inside an add-on | ✅ — uses `SUPERVISOR_TOKEN` env var, scoped by `hassio_role` |

**`hassio.*` services on the HA service bus** (`POST /api/services/hassio/*`): `addon_start`, `addon_stop`, `addon_restart`, `host_reboot`, `backup_full`, etc. **No** `addon_install`, **no** `addon_update`, **no** `store_add_repository` — those require Supervisor proxy.

`trusted_networks` auth provider does NOT bypass auth; it's a login-flow provider that still mints a regular token.

## NyxID service state machine (the #1 thing that will bite you)

**A service's `credential_type` field decides whether the proxy can dispatch to it.** There is a silent trap:

| How created | Resulting `credential_type` | Proxy works? |
|---|---|---|
| `POST /keys` with `auth_method: bearer` + `node_id` in **one** body | `node_managed` | ✅ (once credential is pushed to node) |
| `POST /keys` with `auth_method: none`, then `PUT /keys/{id}` to add node + auth | **stays `none` forever** | ❌ 503 `node_offline` (misleading — the node is fine) |

**Rule: always create services with a single POST that includes `auth_method=bearer` + `node_id`.** Never rely on a follow-up PUT to change `auth_method` from `none`. NyxID issue [#419](https://github.com/ChronoAIProject/NyxID/issues/419).

After create, a **node-local credential must be pushed** for dispatch to succeed:

```bash
nyxid node credentials --config <node-config-dir> add \
  --service <slug> --header Authorization \
  --secret-format bearer --value "$TOKEN" \
  --url <endpoint>
```

Without this push → `503 node_offline` even though the node is online and the service exists.

## How we provision inside `setup.sh` / `supervisor.sh`

Both scripts follow the same pattern:

1. Read `ha_service_label` (main) or `supervisor_service_label` (admin). If empty/null, **skip provisioning entirely**. `bashio::config` returns the literal string `"null"` when a key is missing — check for `[ -z "$x" ] || [ "$x" = "null" ]`, not just `bashio::var.is_empty`.
2. Resolve node UUID from `/data/nyxid-node/config.toml` (populated by node register step).
3. Legacy migration (one-time): read old state file (`/data/configured-services.txt` for main, `/data/last-supervisor-slug` for admin), resolve slug → UUID via `GET /keys`, save to new state file.
4. Reuse check: `GET /keys/{saved_id}` — reuse only if `node_id` matches AND `credential_type == "node_managed"`. Anything else → delete state file, create fresh.
5. Create fresh: single POST with `auth_method=bearer`, `auth_key_name=Authorization`, `endpoint_url`, `node_id`. Save returned ID to state file.
6. Push credential with `SUPERVISOR_TOKEN` every start (token rotates across add-on restarts).

State files:
- `/data/ha-service-id` (main)
- `/data/supervisor-service-id` (admin)

## Testing and deployment

### Slugs to know

After fresh install per v1.1.1, user sees auto-generated slugs. Session-specific but representative:

```
home-assistant-XXXX    → main add-on / Core API via HA add-on node
ha-supervisor-XXXX     → admin add-on / full Supervisor API
home-assistant-admin-h8xl (example) → my-node (laptop) / LAN HA with admin LLAT
```

Proxy test commands:

```bash
nyxid proxy request <main-slug> ""                       # should be {"message":"API running."}
nyxid proxy request <main-slug> "states"                 # should return HA state array
nyxid proxy request <admin-slug> "supervisor/ping"       # should be {"result":"ok","data":{}}
nyxid proxy request <admin-slug> "supervisor/info"       # HA version, health, arch
```

### Reading add-on logs (doesn't need Supervisor admin)

```bash
# The /addons/<slug>/logs path is in HA's PATHS_ADMIN whitelist for admin LLATs:
nyxid proxy request <lan-node-slug> "api/hassio/addons/8404a721_nyxid-node/logs"
nyxid proxy request <lan-node-slug> "api/hassio/addons/8404a721_nyxid-node-admin/logs"
```

### Release process

- Feature work on branches: `dev-vX.Y.Z` (but since we're small-scale, merging directly to `main` with pre-release tag is fine).
- Pre-release: bump both `config.yaml` versions to `X.Y.Z-alpha.N` (or `-rc.N`). Add `stage: experimental` so default HA users don't see it.
- `gh release create vX.Y.Z-alpha.N --target main --prerelease ...` triggers the GitHub workflow (`on: release`).
- CI builds both images sequentially (admin FROMs main, so main must publish first). See `.github/workflows/build.yaml`.
- Main image: `ghcr.io/chronoaiproject/nyx-homeassistant-node:X.Y.Z-alpha.N`
- Admin image: `ghcr.io/chronoaiproject/nyx-homeassistant-node-admin:X.Y.Z-alpha.N` (admin's `build.yaml` must reference the matching main tag)

### The "admin can't update itself" trick

`POST /addons/<admin-slug>/update` through the admin add-on's own channel returns:

```json
{"message": "App 8404a721_nyxid-node-admin can't update itself!"}
```

This is `supervisor/api/store.py:247`. Supervisor rejects if the request comes from the add-on being updated. **Bypass**: use HA Core's update entity, which proxies to Supervisor as "Core", not as the add-on:

```bash
nyxid proxy request <lan-node-slug> "api/services/update/install" -m POST \
  -d '{"entity_id":"update.nyxid_node_admin_update"}' \
  -H "Content-Type:application/json"
```

This is the exact same entry point Supervisor's own `auto_update: true` scheduler uses (`hassio/update/addon` WS command). Works reliably. If the update entity's state lags, first `POST store/reload` (via admin channel) to refresh Supervisor's store cache.

If you need to trigger via WebSocket directly (Core-less scenarios), send:

```json
{ "id": 1, "type": "hassio/update/addon", "addon": "<slug>", "backup": true }
```

over `/api/websocket` with an admin LLAT.

## CLI gotchas

- `nyxid node credentials --config <path> add ...` — `--config` is a PARENT-level arg, must come before the subcommand.
- `nyxid service update <slug>` returns 404 — the CLI's `update` subcommand accepts only UUIDs. Resolve slug → UUID via `service list` / `service show` first.
- `nyxid api-key create --scopes "read write"` does NOT include `proxy` scope by default. API keys made per the README can create services but can't proxy-call them themselves. Add `proxy` explicitly if the same key needs to call proxy.
- `nyxid service add --custom --auth-method none` still tries to interactively prompt for "Auth key name" and fails in non-TTY with `Error: Device not configured (os error 6)`. Bypass: hit REST API directly with `~/.nyxid/access_token` as bearer. See NyxID [#417](https://github.com/ChronoAIProject/NyxID/issues/417).
- Slugs always get a random 4-char suffix, regardless of collision. Can't request an exact slug. NyxID [#415](https://github.com/ChronoAIProject/NyxID/issues/415).

## Filed NyxID issues (don't refile)

| # | Summary |
|---|---|
| [#414](https://github.com/ChronoAIProject/NyxID/issues/414) | `service add` browser wizard missing for bearer/via-node flows |
| [#415](https://github.com/ChronoAIProject/NyxID/issues/415) | Slug suffix unconditional |
| [#416](https://github.com/ChronoAIProject/NyxID/issues/416) | Dashboard doesn't show via-node routing |
| [#417](https://github.com/ChronoAIProject/NyxID/issues/417) | `--auth-method none` still demands TTY |
| [#418](https://github.com/ChronoAIProject/NyxID/issues/418) | `node_offline` error is a catch-all; masks real causes |
| [#419](https://github.com/ChronoAIProject/NyxID/issues/419) | PUT can't upgrade `credential_type: none` — forces single-POST creation pattern |

## Things NOT to do

- Don't set `ha_service_slug` / `supervisor_service_slug` as required input fields. Those are internal. Users fill labels, the add-on makes slugs.
- Don't POST a service then PUT to add `node_id` / `auth_method` — hits the `credential_type: none` trap. Single POST, always.
- Don't use `bashio::var.is_empty` alone to detect missing config keys. Also check for `"null"`.
- Don't rename / delete the inherited `setup.sh` in the admin add-on. Admin is `FROM` the main image; setup.sh runs first (lexicographic order: `setup.sh` < `supervisor.sh`). Admin skips HA provisioning because it has no `ha_service_label` in its config.
- Don't add `hassio_api`/`hassio_role` to main. Main is always-on; admin-scoped to the temporary admin variant.
- Don't release stable versions with `stage: experimental`. That's for alpha/rc only.
- Don't release without bumping `config.yaml:version`. HA caches by version.
- Don't forget to update `nyxid-node-admin/build.yaml` `BUILD_FROM` tags when bumping main's version — admin pins to a specific main tag.

## Pointers

- `docs/ARCHITECTURE_NOTES.md` — full architecture reference, HA auth model deep dive, design rationale
- `DEVELOPMENT.md` — chronological build history up to v1.0.0
- `SETUP_GUIDE.md` — user-facing install walkthrough
- `README.md` — overview + links

## Quick sanity check commands

```bash
# Nodes online?
nyxid node list

# Services bound where?
nyxid service list

# Main add-on Core API reachable?
nyxid proxy request <main-slug> ""

# Admin Supervisor API reachable?
nyxid proxy request <admin-slug> "supervisor/ping"

# Add-on versions (via any channel with Core API):
nyxid proxy request <lan-node-slug> "api/hassio/addons/8404a721_nyxid-node/info"
nyxid proxy request <lan-node-slug> "api/hassio/addons/8404a721_nyxid-node-admin/info"

# CI status
gh run list --limit 3
```
