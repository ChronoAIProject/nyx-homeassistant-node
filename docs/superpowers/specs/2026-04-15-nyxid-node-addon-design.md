# NyxID Node Home Assistant Add-on — Design Spec

## Overview

A Home Assistant Add-on that packages the NyxID credential node agent (Rust) as a Docker container running on HAOS. The node agent connects to a NyxID server via outbound WebSocket, receives proxy requests, injects locally-stored credentials, and forwards them to Home Assistant and other LAN services. Credentials never leave the local network.

## Architecture

```
External Client (Claude Code / API)
        ↓ HTTPS
NyxID Server (Cloud)
        ↓ WebSocket (outbound from Add-on)
┌─────────────────────────────────────────┐
│  Home Assistant OS                      │
│  ┌───────────────────────────────────┐  │
│  │  NyxID Node Add-on (Docker)      │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  nyxid node agent (Rust)    │  │  │
│  │  │  - WS client → NyxID       │  │  │
│  │  │  - proxy executor           │  │  │
│  │  │  - credential store         │  │  │
│  │  │  - HMAC signing             │  │  │
│  │  └─────────────────────────────┘  │  │
│  └──────────┬────────────────────────┘  │
│             ↓ HTTP                       │
│  Home Assistant Core (supervisor/core)   │
│  Other LAN services (NAS, router, etc.)  │
└─────────────────────────────────────────┘
```

Key properties:
- Add-on runs a single process: `nyxid node start`
- WebSocket is outbound-only — no inbound ports required
- Add-on accesses HA Core via `http://supervisor/core/api` with auto-injected `SUPERVISOR_TOKEN`
- LAN services accessed via `host_network: true`
- All credentials stored in Add-on's persistent `/data/` directory, never transit NyxID servers

## Repository Structure

```
nyx-homeassistant-node/
├── README.md
├── repository.yaml                  # Add-on Repository metadata
└── nyxid-node/                      # Add-on directory
    ├── config.yaml                  # Add-on config (name, arch, options, schema)
    ├── Dockerfile                   # Multi-stage: compile Rust + Alpine runtime
    ├── build.yaml                   # Multi-arch build config (amd64, aarch64)
    ├── icon.png
    ├── logo.png
    ├── CHANGELOG.md
    ├── translations/
    │   └── en.yaml                  # i18n labels for config options
    └── rootfs/
        └── etc/
            └── s6-overlay/
                └── s6-rc.d/
                    ├── nyxid-node/
                    │   ├── type             # "longrun"
                    │   ├── run              # Start nyxid node agent
                    │   └── finish           # Cleanup
                    └── nyxid-node-setup/
                        ├── type             # "oneshot"
                        ├── up               # Register + sync credentials
                        └── dependencies.d/
```

## Add-on Configuration (config.yaml)

```yaml
name: "NyxID Node"
description: "Run a NyxID credential node agent on Home Assistant"
version: "0.1.0"
slug: "nyxid-node"
arch:
  - amd64
  - aarch64
homeassistant_api: true
host_network: true
map:
  - config:rw
options:
  nyxid_server_url: "wss://auth.nyxid.io/api/v1/nodes/ws"
  registration_token: ""
  node_name: "homeassistant"
  log_level: "info"
  services: []
schema:
  nyxid_server_url: url
  registration_token: str
  node_name: str
  log_level: list(debug|info|warn|error)
  services:
    - slug: str
      target_url: url
      credential_type: list(header|query_param)
      credential_name: str
      credential_value: password
```

- `homeassistant_api: true` — provides `SUPERVISOR_TOKEN` env var for HA API access
- `host_network: true` — allows access to LAN services beyond HA
- `services` — user-configured downstream services (NAS, router, etc.); HA itself is auto-configured
- `registration_token` — one-time NyxID registration token; only needed for first setup. After successful registration, this field is ignored on subsequent starts (node uses persisted auth_token). User can leave the old value or clear it.
- `credential_value` uses `password` schema type — masked in HA UI

## Startup Flow

```
Add-on starts
    │
    ▼
nyxid-node-setup (oneshot)
    ├── 1. Read /data/options.json (HA-injected config)
    ├── 2. Generate/update /data/config.toml
    │      - server.url = options.nyxid_server_url
    │      - Per-service credential entries
    ├── 3. Check if already registered (node.id exists in /data/config.toml?)
    │      ├── No  → nyxid node register --token <registration_token>
    │      └── Yes → Skip registration
    ├── 4. Update HA built-in service credential (every start)
    │      └── nyxid node credentials add --service homeassistant \
    │            --header "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    │            --url "http://supervisor/core/api"
    ├── 5. Sync other services credentials from options.json
    │      └── Diff by slug: add new, update changed, remove slugs no longer in options
    └── Done
    │
    ▼
nyxid-node (longrun, depends on setup)
    ├── Exec: nyxid node start --config /data/config.toml
    ├── WebSocket connects to NyxID server
    ├── Receives proxy requests → injects credentials → forwards to targets
    └── On crash → s6 auto-restarts
```

Key behaviors:
- `/data/` is the Add-on's persistent directory — survives container rebuilds. Stores node_id, auth_token, signing_secret.
- `SUPERVISOR_TOKEN` is re-injected on every start (it changes with each container lifecycle).
- Services from `options.json` are synced on every start — UI config changes take effect on restart.

## Dockerfile & Build Strategy

Multi-stage build:

```dockerfile
# Stage 1: Compile nyxid node agent
FROM rust:1.82-bookworm AS builder
RUN apt-get update && apt-get install -y pkg-config libssl-dev
ARG NYXID_VERSION=main
RUN git clone --depth 1 --branch ${NYXID_VERSION} \
    https://github.com/ChronoAIProject/NyxID.git /src
WORKDIR /src
RUN cargo build --release --bin nyxid && strip target/release/nyxid

# Stage 2: Runtime
FROM ghcr.io/home-assistant/{arch}-base:3.19
RUN apk add --no-cache ca-certificates
COPY --from=builder /src/target/release/nyxid /usr/local/bin/nyxid
COPY rootfs /
```

Build configuration (build.yaml):

```yaml
build_from:
  amd64: ghcr.io/home-assistant/amd64-base:3.19
  aarch64: ghcr.io/home-assistant/aarch64-base:3.19
args:
  NYXID_VERSION: v0.1.0
```

- NyxID source fetched via `git clone` in Dockerfile, version locked by `NYXID_VERSION` build arg
- HA official Alpine base images (include s6-overlay)
- Cross-compilation for aarch64 via QEMU + Docker Buildx in CI

## CI/CD & Distribution

```
GitHub Actions (trigger: push tag v*)
    │
    ▼
Multi-arch build matrix (amd64, aarch64)
    ├── QEMU + Docker Buildx
    ├── Rust cross-compile
    ├── Package into HA base image
    └── Push to GHCR
    │
    ▼
HA user side
    ├── Add Repository URL once
    ├── Auto-detect new versions
    └── One-click update
```

- Add-on version tracks Git tags (e.g., `v0.1.0`)
- `NYXID_VERSION` in `build.yaml` pins the NyxID source version

## Error Handling & Observability

Logging:
- Node agent stdout/stderr captured by HA Add-on log panel
- Log level configurable via `log_level` option (debug/info/warn/error)
- Key events logged: WS connect/disconnect, registration success/failure, proxy request forwarding, credential injection errors

Failure scenarios:

| Scenario | Handling |
|----------|----------|
| NyxID server unreachable | Node agent built-in exponential backoff reconnect (100ms → 60s) |
| Registration token invalid/expired | Setup phase logs error, prompts user to update token |
| Downstream service unreachable | Returns proxy_error (502), other services unaffected |
| Node agent process crash | s6-overlay auto-restart |
| SUPERVISOR_TOKEN invalid | Restart Add-on (token tied to container lifecycle) |

No additional health check panels or HA entities — the Add-on's sole job is running the node agent.
