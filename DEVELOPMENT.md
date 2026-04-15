# Development Guide — NyxID Node HA Add-on

This document records how this project was built from scratch, the decisions made along the way, the mistakes encountered, and how they were resolved. It serves as both a development tutorial and a reference for future contributors.

## Table of Contents

1. [Project Genesis](#1-project-genesis)
2. [Design Phase](#2-design-phase)
3. [Scaffolding](#3-scaffolding)
4. [Dockerfile Evolution](#4-dockerfile-evolution)
5. [s6-overlay Service Management](#5-s6-overlay-service-management)
6. [CI/CD Pipeline](#6-cicd-pipeline)
7. [NyxID Auth Model Discovery](#7-nyxid-auth-model-discovery)
8. [Final Architecture](#8-final-architecture)
9. [Development Workflow](#9-development-workflow)
10. [Lessons Learned](#10-lessons-learned)

---

## 1. Project Genesis

**Goal**: Package the NyxID credential node agent as a Home Assistant Add-on, so HA can be securely reverse-proxied through NyxID without running a separate node process.

**Starting point**: An empty Git repo. NyxID's node agent is written in Rust, already published as a Docker image at `ghcr.io/chronoaiproject/nyxid/node-agent`.

**Key decisions made upfront**:
- HA Add-on (Docker container on HAOS), not a custom integration (Python)
- Multi-arch support (amd64 + aarch64)
- Configuration through HA's Add-on UI
- Distributed as a custom Add-on Repository on GitHub

## 2. Design Phase

Before writing code, we created a design spec (`docs/superpowers/specs/2026-04-15-nyxid-node-addon-design.md`) covering:

- Architecture diagram (client → NyxID server → WebSocket → Add-on → HA Core)
- Repository structure (HA Add-on conventions)
- config.yaml schema (options the user fills in)
- Startup flow (registration → credential sync → node agent)
- Dockerfile strategy (multi-stage Rust compilation)
- CI/CD (GitHub Actions → GHCR)

**Lesson**: Design before code. The initial design assumed we'd compile Rust from source — this was later changed to use pre-built binaries, saving 40+ minutes of CI time.

## 3. Scaffolding

The HA Add-on structure follows a strict convention:

```
repository.yaml              # Repo metadata (name, URL, maintainer)
nyxid-node/
  config.yaml                # Add-on definition (name, arch, options schema)
  build.yaml                 # Multi-arch base image mapping
  Dockerfile                 # Container build
  CHANGELOG.md
  icon.png / logo.png
  translations/en.yaml       # UI labels for config options
  rootfs/                    # Files copied into the container
    etc/
      cont-init.d/           # Init scripts (run once on start)
        setup.sh
      services.d/             # Long-running services
        nyxid-node/
          run                 # Start the node agent
          finish              # Cleanup on stop
```

**Key files**:
- `config.yaml` — Defines what appears in the HA UI. The `schema` section validates user input.
- `rootfs/` — Everything here gets `COPY`'d into the container root.

### Commits

```
88ad3ae feat: add add-on repository metadata
e18f700 feat: add add-on config, build, and translation files
b31242e feat: add multi-stage Dockerfile for nyxid node agent
36e82bc feat: add s6-overlay service structure
81b15c5 feat: add setup script for node registration and credential sync
0675f0f feat: add run and finish scripts for nyxid node agent
6c03b7b ci: add multi-arch build workflow with HA Builder
65a9f40 docs: add repository README, icon, and logo
```

## 4. Dockerfile Evolution

The Dockerfile went through **5 major iterations**. This is the most instructive part of the project.

### Iteration 1: Compile from source (failed)

```dockerfile
FROM rust:1.82-alpine3.21 AS builder
RUN cargo build --release --bin nyxid
FROM ghcr.io/home-assistant/amd64-base:3.21
COPY --from=builder /target/release/nyxid /usr/local/bin/nyxid
```

**Problems encountered (in order)**:
1. `rust:1.82-alpine3.21` doesn't exist → Changed to `rust:1-alpine`
2. Missing `dbus-dev` → `libdbus-sys` crate needs D-Bus headers at compile time
3. aarch64 build via QEMU took 40+ minutes
4. `ARG BUILD_FROM` between stages doesn't work in Docker BuildKit → Must be declared before the first `FROM`

**Lesson**: Compiling Rust in CI is expensive. If pre-built binaries exist, use them.

### Iteration 2: Pre-built binary from NyxID image (current)

```dockerfile
FROM ghcr.io/chronoaiproject/nyxid/node-agent:0.2.0 AS nyxid-bin
FROM debian:bookworm-slim
COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid
```

Build time dropped from 40 minutes to ~1 minute.

**But**: The NyxID image is Debian (glibc). We tried Alpine base images first:

### Iteration 2a: Alpine + gcompat (failed)

```dockerfile
FROM ghcr.io/home-assistant/amd64-base:3.21  # Alpine
RUN apk add gcompat  # glibc compatibility layer
COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid
```

**Problem**: `gcompat` doesn't implement `__res_init` (glibc DNS resolver function). The nyxid binary crashes on startup.

**Lesson**: `gcompat` handles ~95% of glibc symbols but not all. If the binary uses DNS functions or other edge-case glibc APIs, Alpine won't work.

### Iteration 2b: Debian + manual s6-overlay (current)

Since the HA Alpine base images include s6-overlay but Debian ones don't, we install s6-overlay manually:

```dockerfile
FROM debian:bookworm-slim

# Install s6-overlay
RUN curl -fsSL ".../s6-overlay-noarch.tar.xz" | tar Jxpf - -C / \
    && curl -fsSL ".../s6-overlay-${S6_ARCH}.tar.xz" | tar Jxpf - -C /

# Install bashio (HA's bash helper library)
RUN curl -fsSL ".../bashio-v0.16.2.tar.gz" | tar xzf - -C /tmp \
    && cp -r /tmp/bashio-0.16.2/lib/* /usr/lib/bashio/

# Runtime deps
RUN apt-get install -y libdbus-1-3 curl jq bash

COPY --from=nyxid-bin /usr/local/bin/nyxid /usr/local/bin/nyxid
COPY rootfs /
ENTRYPOINT ["/init"]
```

**Key details**:
- `ENTRYPOINT ["/init"]` — s6-overlay's init must be PID 1
- `config.yaml` needs `init: false` — prevents HA Supervisor from adding Docker `--init` (tini), which would steal PID 1 from s6-overlay
- `bashio` needs a wrapper script at `/usr/bin/bashio` because symlinking causes path resolution issues (`bashio.sh` sources siblings via relative paths)
- `curl` must stay at runtime — bashio uses it to communicate with the HA Supervisor API
- `libdbus-1-3` — runtime dependency for nyxid's keyring crate

### Multi-arch support

Instead of per-arch base images, we use Docker's `TARGETARCH`:

```dockerfile
FROM ghcr.io/home-assistant/amd64-base:3.21 AS base-amd64
FROM ghcr.io/home-assistant/aarch64-base:3.21 AS base-arm64

ARG TARGETARCH
FROM base-${TARGETARCH}
```

This was used in the Alpine attempts. The Debian version doesn't need this since `debian:bookworm-slim` is already multi-arch.

## 5. s6-overlay Service Management

### Failed attempt: s6-rc.d (v3 native)

We first tried the s6-overlay v3 native structure:

```
s6-rc.d/
  nyxid-node-setup/
    type        # "oneshot"
    up          # Setup script
  nyxid-node/
    type        # "longrun"
    run         # Node agent
  user/contents.d/
    nyxid-node
    nyxid-node-setup
```

**Problem**: The `up` file in oneshot services is parsed as execlineb, not bash. Our bash script's `declare` statements were interpreted as execlineb commands, causing `unable to exec declare: No such file or directory`.

### Working approach: Legacy cont-init.d + services.d

```
cont-init.d/
  setup.sh          # Bash script with #!/command/with-contenv bashio
services.d/
  nyxid-node/
    run             # exec nyxid node start
    finish          # Log exit code
```

**Lesson**: HA Add-ons almost universally use the legacy s6-overlay structure. s6-rc.d v3 is more powerful but requires execlineb knowledge.

## 6. CI/CD Pipeline

### Initial approach: HA Builder (failed)

```yaml
- uses: home-assistant/builder@master
  with:
    args: --amd64 --target nyxid-node --docker-hub "ghcr.io/..."
```

**Problem**: `home-assistant/builder@master` is deprecated. It also failed to pass `BUILD_FROM` correctly.

### Current approach: Standard Docker Buildx

```yaml
- uses: docker/build-push-action@v6
  with:
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/chronoaiproject/nyx-homeassistant-node:${{ version }}
```

**Key details**:
- Single job builds both architectures → single multi-arch manifest
- One image name: `ghcr.io/chronoaiproject/nyx-homeassistant-node`
- Version read from `config.yaml` automatically
- Triggered on `release` (published) and `workflow_dispatch`

### Image naming

Initially we published per-arch images (`/amd64:0.1.0`, `/aarch64:0.1.0`). This creates messy GHCR package listings. Switched to a single multi-arch manifest under one name.

### Version management

Every code change that affects the Docker image requires a version bump in `config.yaml`. HA only pulls a new image when the version changes. Forgetting to bump = users stay on the old image.

## 7. NyxID Auth Model Discovery

This was the biggest unexpected challenge. Understanding it took multiple failed attempts.

### The two-service-model

NyxID has two service storage models:

| Model | Created by | Proxy visible |
|-------|-----------|---------------|
| `DownstreamService` | JWT session (`nyxid service add`) | Yes |
| `UserService` | API key (`POST /api/v1/keys`) | No |

**Discovery process**:
1. We tried auto-creating services from the setup script using an API key
2. Services appeared in `nyxid service list` but returned 404 from the proxy
3. We investigated the NyxID backend source code
4. Found that the proxy endpoint only queries `DownstreamService`
5. Realized this is by design: service creation is a privileged operation requiring JWT

### The slug matching problem

NyxID auto-generates slugs with random suffixes (e.g., `home-assistant-zrdc`). The node credential slug must match exactly. We tried:

1. **Specifying exact slug via API** — The backend supports a `slug` field in `POST /api/v1/keys`, but this creates `UserService` (not proxy-visible)
2. **Auto-creating from setup script** — API key can't create `DownstreamService`
3. **Final solution** — User creates the service on their machine (gets the slug), fills it into the add-on config

### The correct auth boundary

```
JWT (user's machine)     →  Creates services (one-time)
API Key (HA add-on)      →  Registers nodes, binds services, manages credentials
SUPERVISOR_TOKEN (HA)    →  Injected locally, never leaves the container
```

**Lesson**: Understand the auth model of the platform you're integrating with BEFORE designing the automation flow. We spent significant time trying to work around constraints that were intentional security boundaries.

## 8. Final Architecture

See `docs/superpowers/specs/2026-04-15-nyxid-node-addon-v2-design.md` for the full spec.

**User setup**: 2 commands on their machine + 2 fields in HA config.

**Setup script flow**:
1. Check if node is registered → if not, use API key to create reg token and register
2. Check if `ha_service_slug` is configured → if not, show help message with the command to run
3. Bind service to node (`nyxid service update --node-id`, idempotent)
4. Create/update HA credential with SUPERVISOR_TOKEN (every start)
5. Sync additional services from config
6. Start node agent

## 9. Development Workflow

### Local development cycle

```bash
# 1. Edit files
vim nyxid-node/rootfs/etc/cont-init.d/setup.sh

# 2. Bump version in config.yaml
#    (HA won't pull new image without version change)

# 3. Commit and push
git add -A && git commit -m "fix: ..." && git push

# 4. Trigger CI build
gh workflow run build.yaml --repo ChronoAIProject/nyx-homeassistant-node

# 5. Wait for build (~1 min with pre-built binary)
gh run watch <run_id> --exit-status

# 6. Update on HA (via proxy or UI)
#    Refresh → Install update → Start → Check logs
```

### Testing via NyxID proxy

If you have an existing node proxying HA, you can manage the add-on remotely:

```bash
# Refresh version detection
nyxid proxy request <ha-slug> "api/services/homeassistant/update_entity" -m POST \
  -d '{"entity_id":["update.nyxid_node_update"]}' -H "Content-Type: application/json"

# Install update
nyxid proxy request <ha-slug> "api/services/update/install" -m POST \
  -d '{"entity_id":"update.nyxid_node_update"}' -H "Content-Type: application/json"

# Start/stop/restart
nyxid proxy request <ha-slug> "api/services/hassio/addon_start" -m POST \
  -d '{"addon":"8404a721_nyxid-node"}' -H "Content-Type: application/json"

# Check logs
nyxid proxy request <ha-slug> "api/hassio/addons/8404a721_nyxid-node/logs"
```

**Note**: The HA Supervisor admin API (`/api/hassio/addons/.../options`, `/api/hassio/addons/.../uninstall`) returns 401 with long-lived access tokens. Configuration changes must be done through the HA web UI.

### Testing the setup script locally

You can test NyxID CLI commands without the container:

```bash
# Test credential operations
nyxid node credentials --config /tmp/test-config add \
  --service "test" --header "Authorization" \
  --secret-format bearer --value "test-token" \
  --url "http://localhost:8123"

nyxid node credentials --config /tmp/test-config list
```

**Important**: The `--config` flag on `credentials` goes BEFORE the subcommand:
```bash
nyxid node credentials --config /path add ...    # correct
nyxid node credentials add --config /path ...    # wrong!
```

## 10. Lessons Learned

### Architecture

1. **Understand the auth model first.** We spent hours trying to auto-create services with API keys before discovering that NyxID intentionally separates JWT (management) from API key (operations).

2. **Pre-built binaries over source compilation.** Compiling Rust in CI took 40 minutes per arch. Copying from an existing image takes seconds.

3. **glibc vs musl is a real boundary.** If your binary is linked against glibc, you need a glibc-based runtime. Alpine's `gcompat` covers most cases but fails on edge-case symbols like `__res_init`.

### Home Assistant Add-on specifics

4. **`init: false` in config.yaml** is required when using s6-overlay. Without it, HA adds Docker `--init` (tini) as PID 1, preventing s6-overlay from functioning.

5. **Use legacy `cont-init.d` + `services.d`**, not `s6-rc.d`. The v3 native structure parses scripts as execlineb, not bash.

6. **bashio needs curl at runtime.** Don't `apt-get purge curl` in the Dockerfile cleanup.

7. **bashio symlinks break path resolution.** Use a wrapper script at `/usr/bin/bashio` instead of `ln -s /usr/lib/bashio/bashio.sh /usr/bin/bashio`.

8. **Version bumps are mandatory.** HA caches images by version tag. Same version = same image, even if the tag was overwritten on GHCR.

### CI/CD

9. **Use `docker/build-push-action`**, not `home-assistant/builder`. The HA builder is deprecated and has build arg issues.

10. **Single multi-arch manifest** is cleaner than per-arch image names. Use `platforms: linux/amd64,linux/arm64` in one build job.

### NyxID integration

11. **`--config` flag position matters.** On `nyxid node credentials`, it's a parent-level arg: `credentials --config /path add`, not `credentials add --config /path`.

12. **Image tags don't have `v` prefix.** NyxID publishes `0.2.0`, not `v0.2.0`.

13. **Service slugs have random suffixes.** You cannot specify an exact slug through the CLI. The slug must be captured from the output and used as-is.

14. **Proxy path is relative to endpoint_url.** If endpoint is `http://supervisor/core/api`, request path `states` becomes `/api/states`. Don't prefix with `api/` or you get `/api/api/states`.
