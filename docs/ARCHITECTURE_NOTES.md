# Architecture Notes — HA + NyxID Edge Cases

Reference doc for future contributors (humans or AI assistants). Covers what's easy to get wrong about Home Assistant's auth model and NyxID's service lifecycle, and records what this project has tried, what broke, and why.

Organized as reference, not narrative. For the chronological "how we built this" see [DEVELOPMENT.md](../DEVELOPMENT.md).

---

## 1. HA Auth Model — The Full Picture

HA exposes four different API surfaces, each with DIFFERENT auth rules. Confusing them wastes hours.

```
┌───────────────────────────────────────────────────────────────────────┐
│                      Home Assistant                                   │
│                                                                       │
│   ┌─────────────────────┐    ┌─────────────────────────────────────┐  │
│   │ Core REST  /api/*   │    │ Supervisor proxy  /api/hassio/*     │  │
│   │                     │    │                                     │  │
│   │ Accepts: admin /    │    │ PATH WHITELIST only:                │  │
│   │ non-admin LLAT      │    │   - backups/*                       │  │
│   │                     │    │   - addons/<x>/logs|changelog|docs  │  │
│   │ Full CRUD on states │    │   - core|supervisor|cli logs        │  │
│   │ Call `hassio.*`     │    │                                     │  │
│   │ services (limited)  │    │ BLOCKED for every token:            │  │
│   │                     │    │   supervisor/info, addons (list),   │  │
│   │                     │    │   store/*, host/*, addons/*/install │  │
│   └─────────────────────┘    └─────────────────────────────────────┘  │
│                                                                       │
│   ┌─────────────────────┐    ┌─────────────────────────────────────┐  │
│   │ WebSocket           │    │ Internal http://supervisor/*        │  │
│   │ /api/websocket      │    │                                     │  │
│   │                     │    │ Only reachable from INSIDE an       │  │
│   │ Admin LLAT can send │    │ add-on container (add-on network)   │  │
│   │ `supervisor/api`    │    │                                     │  │
│   │ cmd → full          │    │ Auth: SUPERVISOR_TOKEN env var      │  │
│   │ Supervisor REST     │    │                                     │  │
│   │ passthrough         │    │ Scope depends on add-on's           │  │
│   │                     │    │ `hassio_role` in config.yaml        │  │
│   │ This is what HACS   │    │                                     │  │
│   │ uses.               │    │                                     │  │
│   └─────────────────────┘    └─────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```

### PATHS_ADMIN is the real gate

Source: `homeassistant/components/hassio/http.py:67-82` in HA Core. It's a regex whitelist, CVE-hardened 2022-2024. **Nothing** widens it — no owner role, no flag, no scope. Earlier versions (pre-0.96) allowed broader access; those days are gone.

### `hassio.*` services on the service bus

Core REST at `POST /api/services/{domain}/{service}` registers these (`homeassistant/components/hassio/services.py:53-67`):

| Domain.service | What it does |
|---|---|
| `hassio.addon_start` / `addon_stop` / `addon_restart` / `addon_stdin` | Lifecycle of an already-installed add-on |
| `hassio.host_reboot` / `host_shutdown` | Host controls |
| `hassio.backup_full` / `backup_partial` / `restore_full` / `restore_partial` | Backup management |
| `hassio.mount_reload` | Mount reload |

**Missing intentionally**: `hassio.addon_install`, `hassio.addon_update`, `hassio.addon_uninstall`, `hassio.store_add_repository`. Installing anything requires Supervisor API (via add-on internal path, WebSocket passthrough, or direct SUPERVISOR_TOKEN).

### `trusted_networks` does NOT bypass auth

Common misconception. `trusted_networks.py` is a login-flow provider — it replaces the password step with an IP check, but still mints and requires a standard `Authorization: Bearer <token>`. It does NOT skip authentication on API calls.

### What this means for remote management

If you want to install / uninstall / configure add-ons remotely, your options are exactly:

1. **An add-on inside HA** with `hassio_api: true` + `hassio_role: admin` — uses `SUPERVISOR_TOKEN` to hit `http://supervisor/*`. **This repo's admin variant.**
2. **WebSocket from LAN** using an admin long-lived access token + `supervisor/api` command. Works for LAN clients. Drawback: LLAT is persistent; no clean "revoke on uninstall" semantics.
3. **Nothing else.** Core REST API cannot do it.

---

## 2. NyxID Service Lifecycle

A NyxID "service" (a.k.a. "key" in backend code) has a `credential_type` field that gates whether the proxy layer can dispatch requests to it. Getting this state wrong gives misleading errors.

### State table

| `credential_type` | How you got there | Can proxy? |
|---|---|---|
| `none` | POST with `auth_method: none` | ❌ 503 `node_offline` even with a node bound |
| `node_managed` | POST with `auth_method: <bearer/…>` AND `node_id` in same request | ✅ (once a credential is pushed to the node) |
| `oauth2` / provider-specific | `--oauth` or `--device-code` flows | Provider-dependent |

### Trap: `none` can never be upgraded to `node_managed`

A service posted with `auth_method: none` ends up with `api_key_id: null` in the database. `PUT /keys/{id}` will let you change `auth_method` and `node_id`, but the reconcile function at `unified_key_service.rs:1000` **short-circuits** when `api_key_id` is missing. The service is permanently broken — delete and recreate.

Filed as [NyxID issue #419](https://github.com/ChronoAIProject/NyxID/issues/419). This was the root cause of the historical commits `a7d9a23` / `73b66d2` that claimed "API keys can't create proxy-visible services" — that diagnosis was incomplete; the real issue is the state-machine trap, and it applies equally to access-token-created services.

### Correct POST shape for a via-node service

```json
{
  "label": "whatever user-facing name",
  "key_type": "http",
  "endpoint_url": "http://supervisor",
  "auth_method": "bearer",
  "auth_key_name": "Authorization",
  "node_id": "<target-node-uuid>"
}
```

All fields in the initial POST. Don't do POST-then-PUT.

### `credential_type: node_managed` needs a node-side credential push

Setting `node_managed` on the service record is only step 1. For dispatch to succeed, the TARGET node must have a local credential for that slug:

```bash
nyxid node credentials --config <node-config-dir> add \
  --service <slug> \
  --header Authorization \
  --secret-format bearer \
  --value "$THE_TOKEN" \
  --url "<endpoint>"
```

This pushes the bearer token into the node's local store. Without it, proxy returns 503 `node_offline` even though the node is online.

### Proxy error semantics

`503 {"error":"node_offline"}` can mean:
- The node is genuinely offline (WS disconnected) — rare
- The node is online but the dispatch request wasn't routable — common, and includes:
  - Service has `credential_type: none` (see trap above)
  - Service is bound to a node, but that node has no local credential for the slug
  - Node-internal target unreachable (e.g. `http://supervisor` from a LAN node, not an add-on)

See [NyxID issue #418](https://github.com/ChronoAIProject/NyxID/issues/418) — we've asked for a clearer error taxonomy here.

---

## 3. NyxID API Key Scopes

`nyxid api-key create --scopes "<list>"` takes space-separated values. The important three:

| Scope | Grants |
|---|---|
| `read` | GET on /keys, /nodes, /services etc. |
| `write` | POST/PUT/DELETE on /keys (service CRUD). Enough to create + bind services. |
| `proxy` | Call `/api/v1/proxy/s/*` |

**`--scopes "read write"` does NOT include `proxy`.** An API key created per the main add-on's README cannot call the proxy layer for services it creates. It CAN create proxy-visible services — but something else (user's access token, or a proxy-scoped API key) must do the actual proxy calls.

For our add-on flow, the in-container API key only needs `write` — it provisions services. The human user's access token is what does the proxy calls.

---

## 4. NyxID CLI Gotchas

Things that bit us. Each has an upstream issue link for tracking.

| Gotcha | Detail | Issue | Workaround |
|---|---|---|---|
| Browser wizard missing for bearer/via-node | `nyxid service add --custom --auth-method bearer --via-node` prints "next step: …" and exits. Wizard only fires for `--oauth` / `--device-code`. | [#414](https://github.com/ChronoAIProject/NyxID/issues/414) | Tell users to use CLI + paste token manually, or use direct REST API. |
| Slug always gets a 4-char random suffix | `generate_slug_from_label()` unconditionally appends it; collision handling is a separate `-2/-3/…` scheme on top. | [#415](https://github.com/ChronoAIProject/NyxID/issues/415) | Live with `home-assistant-zrdc`, `ha-supervisor-900n`, etc. |
| Dashboard hides via-node routing | Service list/detail don't show which node a service routes through. Key-detail page has the pattern (`RoutingSection`) but it isn't applied to service-detail. | [#416](https://github.com/ChronoAIProject/NyxID/issues/416) | Use CLI `service list` — has a `Node` column. |
| `--auth-method none` still prompts for `Auth key name` | CLI unconditionally prompts even when no auth key is needed. No TTY detection anywhere. | [#417](https://github.com/ChronoAIProject/NyxID/issues/417) | Direct REST API (`POST /api/v1/keys`) with the user's stored access token at `~/.nyxid/access_token`. |
| Misleading `node_offline` error | Covers many failure modes, most of which aren't actually "node offline". | [#418](https://github.com/ChronoAIProject/NyxID/issues/418) | Know the state machine in §2 above. |
| PUT cannot upgrade `credential_type: none` | Section 2 trap. | [#419](https://github.com/ChronoAIProject/NyxID/issues/419) | Always POST with `auth_method != "none"` + `node_id` in the same request. |
| `service update <slug>` returns 404 | The API accepts UUID only; CLI forwards the slug verbatim. | (not filed) | Resolve slug → UUID via `service list` / `service show`, then call `update`. |
| `--config` flag on `node credentials` is a parent-level arg | `nyxid node credentials --config /path add …` ✓, `nyxid node credentials add --config /path …` ✗ | (not filed — by design) | Put `--config` before the subcommand. |

---

## 5. HA Add-on Mechanics

### Permissions are baked in at build time

`hassio_api`, `hassio_role`, `homeassistant_api`, `host_network` et al. live in `config.yaml`. They are **not** user-toggleable at runtime, and they must be re-approved by the user when the add-on is updated if the declared set changes. This is intentional HA security — users see exactly which privileges an add-on requires before installing.

Implication: to offer "elevated privileges available temporarily", the cleanest mechanism is **a separate add-on variant** the user installs only when needed and uninstalls to revoke. That's why this repo ships two add-ons (`nyxid-node` + `nyxid-node-admin`) rather than one with a toggle.

### Multi-add-on repo

One HA add-on repository can host multiple add-ons. Each lives in its own top-level directory with its own `config.yaml`, `Dockerfile`, `rootfs/`. `repository.yaml` at the root names the repo. HA auto-scans subdirs.

### `boot: manual` for temporary-use add-ons

The admin variant uses `boot: manual` so it doesn't auto-start on HA boot. User installs → configures → **manually starts** when they need admin ops → stops or uninstalls when done.

### `FROM` inheritance for variant add-ons

The admin variant's Dockerfile is 3 lines:

```dockerfile
ARG BUILD_FROM
FROM ${BUILD_FROM}
COPY rootfs /
```

`BUILD_FROM` is set via `build.yaml` to a specific tag of the main add-on image on GHCR. All the base infrastructure (nyxid binary, bashio, s6-overlay, main setup.sh) is inherited; admin adds its own `supervisor.sh` on top. CI builds admin AFTER main to ensure the base tag exists.

### Script ordering in `cont-init.d`

s6-overlay runs scripts in lexicographic byte order. `setup.sh` (main's init) vs `supervisor.sh` (admin's addition): `e` < `u`, so setup runs first. Intentional — admin assumes main already registered the node.

### Version bumps are mandatory for updates

HA pulls images by the tag matching `config.yaml:version`. Same version = same tag = same image, even if GHCR has a newer build. Bump the version field every time you want users to actually update.

### Pre-release versions for testing

Semver pre-release tags (`1.1.1-rc1`, `1.1.1-beta.2`) work via `gh release create --prerelease`. HA shows them as "update available" by default. Standard flow:

```bash
git checkout -b dev-v1.1.1
# …changes…
# bump config.yaml: version: "1.1.1-rc1"
git push -u origin dev-v1.1.1
gh release create v1.1.1-rc1 --target dev-v1.1.1 --prerelease \
  --title "v1.1.1-rc1 — <description>" --notes "<notes>"
# CI builds + pushes ghcr.io/…:1.1.1-rc1
# In HA UI, click Update on the add-on
# Iterate: -rc2, -rc3
# When stable: bump to "1.1.1", release stable from main
```

To hide pre-releases from casual users, add `stage: experimental` to the variant's `config.yaml` — HA filters experimental add-ons by default.

---

## 6. Architectural Decisions (and Rejected Alternatives)

### Why `nyxid-node-admin` is a separate add-on, not a toggle

HA permissions are baked in. A runtime toggle for `hassio_role: admin` cannot exist. A user option that merely gates "whether to expose Supervisor via NyxID when the capability is already loaded in-container" doesn't actually revoke anything — the token is still there, a compromised add-on still has admin. True revocation = uninstall = container destruction = `SUPERVISOR_TOKEN` death.

### Why not skip the admin add-on and use WebSocket passthrough from LAN?

Viable but worse UX:

| Criterion | admin add-on | LAN WS + admin LLAT |
|---|---|---|
| Revocation model | `uninstall` = physical | User must manually delete LLAT |
| Credential lifetime | Ephemeral (`SUPERVISOR_TOKEN` rotates) | Long-lived (days/weeks/forever) |
| Client | Plain `nyxid proxy request …` | WS upgrade + `supervisor/api` command wrapping |
| NyxID dependency | HTTP passthrough (stable) | WS passthrough (works, but less battle-tested) |
| Future-proof | HA-blessed add-on interface | HA could tighten WS admin routes in future CVE fix |

Kept as Plan B; documented but not implemented.

### Why user-facing config uses `*_service_label`, not `*_service_slug`

Earlier versions required users to pre-create the slug on their own machine and paste it back. v1.1.1 flips this: user enters a label only, add-on auto-creates the service on first boot and stores the UUID in `/data/` for idempotency. Labels are allowed to collide (NyxID enforces no uniqueness on label) — the add-on never uses label as a key; it uses the saved UUID. See §7 for the provisioning flow.

### Why track services by UUID not by slug

Slug has random suffix and can be re-generated on re-create. UUID is stable forever, per the NyxID data model. Using UUID as the idempotency key in the add-on's `/data/` makes the state machine robust to label changes, slug regeneration, and label collisions.

---

## 7. v1.1.1 Provisioning Flow (spec)

Pseudocode for `supervisor.sh` (admin variant — main's `setup.sh` is symmetrical for `ha_service_label`):

```bash
#!/command/with-contenv bashio
# Read user config
label=$(bashio::config 'supervisor_service_label')        # default: "HA Supervisor"
api_key=$(bashio::config 'nyxid_api_key')
api_base=$(bashio::config 'nyxid_server_url' | sanitize)

NYX_CFG=/data/nyxid-node
STATE_FILE=/data/supervisor-service-id

# Resolve THIS node's UUID (setup.sh should have registered already)
node_id=$(grep '^id' "$NYX_CFG/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

# Try to reuse previously-provisioned service
service_id=$(cat "$STATE_FILE" 2>/dev/null)
reuse=false

if [ -n "$service_id" ]; then
  resp=$(curl -s "$api_base/api/v1/keys/$service_id" -H "Authorization: Bearer $api_key")
  if [ "$(echo $resp | jq -r .id)" = "$service_id" ] \
      && [ "$(echo $resp | jq -r .node_id)" = "$node_id" ]; then
    reuse=true
    slug=$(echo "$resp" | jq -r .slug)
    current_label=$(echo "$resp" | jq -r .label)
    # If user changed the label, sync it up
    if [ "$current_label" != "$label" ]; then
      curl -s -X PUT "$api_base/api/v1/keys/$service_id" \
        -H "Authorization: Bearer $api_key" \
        -d "{\"label\":\"$label\"}"
    fi
  else
    # Stale ID, forget it
    rm -f "$STATE_FILE"
    service_id=""
  fi
fi

# Create fresh service if needed — single POST, never POST-then-PUT
if [ -z "$service_id" ]; then
  resp=$(curl -s -X POST "$api_base/api/v1/keys" \
    -H "Authorization: Bearer $api_key" \
    -d "{
      \"label\": \"$label\",
      \"key_type\": \"http\",
      \"endpoint_url\": \"http://supervisor\",
      \"auth_method\": \"bearer\",
      \"auth_key_name\": \"Authorization\",
      \"node_id\": \"$node_id\"
    }")
  service_id=$(echo "$resp" | jq -r .id)
  slug=$(echo "$resp" | jq -r .slug)
  echo "$service_id" > "$STATE_FILE"
fi

# Push credential on this node (every start — SUPERVISOR_TOKEN rotates)
nyxid node credentials --config "$NYX_CFG" add \
  --service "$slug" \
  --header Authorization \
  --secret-format bearer \
  --value "$SUPERVISOR_TOKEN" \
  --url "http://supervisor"
```

Key properties:
- **Idempotent**: re-runs on every add-on start; no duplicate service creation
- **Recovery**: if the service is deleted server-side, `GET /keys/$id` 404s → state file cleared → fresh create
- **Label-follow**: user can edit the label in add-on config; on restart, it syncs to server
- **No user-visible slug**: slug is used only internally. Users interact via `nyxid proxy request <slug>` — they get the slug from the add-on log on first boot (or from `nyxid service list`)

---

## 8. Runbook: common operations

### "Add-on doesn't show up in HA store after git push"

HA caches the repo listing. Force refresh:
1. Settings → Add-ons → Add-on Store → ⋮ → Check for updates
2. If still missing: ⋮ → Repositories → remove this repo, add it back. HA re-clones and re-scans.

### "Supervisor admin proxy returns 503 after admin add-on start"

Almost always one of (in order of probability):
1. Node-local credential wasn't pushed — check add-on logs for the `nyxid node credentials add` line
2. Service is bound to the wrong node (check `nyxid service list` Node column)
3. Service is in `credential_type: none` state (see §2 trap) — delete + recreate

### "How do I test a new add-on version without polluting stable"

See §5 "Pre-release versions for testing".

### "Forgot my API key, want to rotate it"

```bash
# List keys (you'll see prefix only)
nyxid api-key list

# Rotate — gets new secret, invalidates old
nyxid api-key rotate <id>

# Update both add-ons' config with the new key, restart
```

---

## 9. Cross-references

- Build history / chronological story → [DEVELOPMENT.md](../DEVELOPMENT.md)
- User-facing setup → [SETUP_GUIDE.md](../SETUP_GUIDE.md)
- NyxID issues filed from this project → see §4 table above
- Admin variant spec → [README.md § Temporary admin mode](../README.md)
