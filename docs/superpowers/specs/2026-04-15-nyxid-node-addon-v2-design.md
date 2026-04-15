# NyxID Node HA Add-on — Architecture Design v2

## Problem

The Add-on needs to register a NyxID credential node on HAOS, create a proxy-visible service, and keep credentials in sync — while respecting NyxID's auth model where only JWT sessions can create proxyable services.

## NyxID Auth Model

NyxID has two service storage models:

- **DownstreamService** — created via JWT login session (`nyxid service add`). Visible to the proxy endpoint. This is the "real" proxyable service.
- **UserService** — created via API key (`POST /api/v1/keys`). NOT visible to the proxy endpoint. Used for credential/key management.

This is by design: service creation is a privileged management operation that requires an authenticated user session. API keys are scoped for operational tasks (proxy access, credential management), not infrastructure provisioning.

### Capability Matrix

```
                      JWT (nyxid login)    API Key (nyx_...)
                      ─────────────────    ─────────────────
Create service        ✓ DownstreamService  ✗ UserService only
Proxy requests        ✓                    ✓ (needs proxy scope)
Create reg token      ✓                    ✓
Update service bind   ✓                    ✓
Node credentials      ✓                    ✓
```

## Architecture

```
User's Machine (one-time setup)          HAOS (automated)
═══════════════════════════════          ═══════════════════

nyxid login (existing session)

nyxid service add --custom \
  --label "Home Assistant" \
  --endpoint-url \                       Add-on startup (setup.sh):
  "http://supervisor/core/api" \           │
  --auth-method none                       ├─ Node registered?
  → slug: home-assistant-xxxx              │  └─ No → API key creates reg
                                           │         token → register node
nyxid api-key create \                     │
  --name ha-addon \                        ├─ Bind service to node
  --scopes "read write" \                  │  (service update --node-id,
  --allow-all-nodes \                      │   idempotent, uses API key)
  --allow-all-services                     │
  → key: nyx_...                           ├─ Create/update credential
                                           │  slug = ha_service_slug
HA Add-on config:                          │  value = SUPERVISOR_TOKEN
  api_key = nyx_...                        │
  ha_service_slug = home-assistant-xxxx    └─ Start nyxid node agent
```

## Request Flow

```
Client (Claude Code)
    │ nyxid proxy request home-assistant-xxxx "api/states"
    ▼
NyxID Server
    │ Lookup DownstreamService by slug → found
    │ Service bound to node "homeassistant" → online
    │ Forward proxy_request via WebSocket
    ▼
HA Add-on (node agent)
    │ Receive proxy_request (service_slug: home-assistant-xxxx)
    │ Lookup local credential (slug: home-assistant-xxxx) → match ✓
    │ Inject: Authorization: Bearer <SUPERVISOR_TOKEN>
    │ Forward to: http://supervisor/core/api/states
    ▼
HA Core → response → reverse path → Client
```

## Security Boundaries

```
┌──────────────────────────────────────┐
│ User's Machine                       │
│                                      │
│  JWT session (~/.nyxid/)             │
│  ├─ Highest privilege                │
│  ├─ Creates services (one-time)      │
│  ├─ Creates API keys (one-time)      │
│  └─ NEVER leaves this machine        │
└──────────────────────────────────────┘
          │
          │ Only API Key + slug cross this boundary
          ▼
┌──────────────────────────────────────┐
│ HA Add-on Container                  │
│                                      │
│  API Key (nyx_...)                   │
│  ├─ Scope: read write (no proxy)     │
│  ├─ Creates registration tokens      │
│  ├─ Updates service bindings         │
│  └─ Cannot make proxy requests       │
│                                      │
│  SUPERVISOR_TOKEN                    │
│  ├─ Injected by HA at container start│
│  ├─ Stored as node credential        │
│  ├─ Only flows: container → HA Core  │
│  └─ Never transits NyxID server      │
│                                      │
│  Node Auth Token + Signing Secret    │
│  ├─ Generated during registration    │
│  ├─ AES-256-GCM encrypted at rest   │
│  ├─ Used for WebSocket auth          │
│  └─ Persisted in /data/nyxid-node/   │
│                                      │
│  WebSocket (outbound only, TLS)      │
│  ├─ HMAC-SHA256 request signing      │
│  └─ Nonce-based replay protection    │
└──────────────────────────────────────┘
```

## Add-on Configuration

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `nyxid_server_url` | Yes | `wss://nyx-api.chrono-ai.fun/api/v1/nodes/ws` | NyxID WebSocket URL |
| `nyxid_api_key` | Yes | — | API key with `read write` scope |
| `ha_service_slug` | Yes | — | Slug from `nyxid service add` |
| `node_name` | No | `homeassistant` | Display name |
| `log_level` | No | `info` | Logging verbosity |
| `services` | No | `[]` | Additional LAN services |

## Setup Script Flow (setup.sh)

```
Start
  │
  ▼
config.toml has [node]? ──No──► Create reg token (API key)
  │                              → Register node
  │ Yes                          → Save config.toml
  ▼
ha_service_slug configured? ──No──► Log warning + node_id
  │                                  "Run nyxid service add
  │ Yes                               --via-node <id> ..."
  ▼
Bind service to node (idempotent)
  │ nyxid service update <slug>
  │   --node-id <id>
  │   --access-token <api_key>
  ▼
Update HA credential
  │ nyxid node credentials add
  │   --service <ha_service_slug>
  │   --value $SUPERVISOR_TOKEN
  ▼
Sync additional services from config
  ▼
Start node agent
  │ nyxid node start
  ▼
Running (WebSocket connected)
```

## User Setup Steps

```bash
# Step 1: Create the HA service (one-time, on your machine)
nyxid service add --custom \
  --label "Home Assistant" \
  --endpoint-url "http://supervisor/core/api" \
  --auth-method none
# Note the slug (e.g., home-assistant-xxxx)

# Step 2: Create an API key for the Add-on (one-time)
nyxid api-key create --name ha-addon \
  --scopes "read write" \
  --allow-all-nodes --allow-all-services
# Note the key (nyx_...)

# Step 3: In HA UI → Add-on config, fill:
#   NyxID API Key: nyx_...
#   HA Service Slug: home-assistant-xxxx
#   → Save → Start
```

## Dockerfile

Debian bookworm-slim base with manually installed s6-overlay + bashio. Pre-built `nyxid` binary copied from the official `ghcr.io/chronoaiproject/nyxid/node-agent` multi-arch image. Single multi-arch Docker manifest published to `ghcr.io/chronoaiproject/nyx-homeassistant-node`.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Wrong slug | Node returns 502 (no matching credential), visible in logs |
| Wrong API key | Registration fails with clear error message |
| Node deleted on server | WebSocket auth fails, agent reconnects with backoff. Fix: delete /data/nyxid-node/, restart |
| Service deleted on server | Proxy returns 404. Fix: recreate service, update slug in config |
| SUPERVISOR_TOKEN rotation | Handled automatically — credential updated on every start |
| API key revoked | Registration/binding fails on next restart. Fix: create new key, update config |
| HA reboots | Add-on auto-starts, setup re-runs (idempotent), credential refreshed |
