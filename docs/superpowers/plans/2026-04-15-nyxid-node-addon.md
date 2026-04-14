# NyxID Node Home Assistant Add-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Home Assistant Add-on that runs the NyxID credential node agent, enabling secure reverse-proxy access to Home Assistant and LAN services through NyxID.

**Architecture:** Multi-stage Docker build compiles the Rust-based `nyxid` CLI from source, packages it into an HA Alpine base image with s6-overlay process management. A oneshot setup service handles node registration and credential sync on each start. A longrun service runs the node agent.

**Tech Stack:** Rust (NyxID CLI), Docker multi-stage build, s6-overlay v3, bashio (HA shell helpers), GitHub Actions + HA Builder for CI/CD, GHCR for image hosting.

**Spec:** `docs/superpowers/specs/2026-04-15-nyxid-node-addon-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `repository.yaml` | Add-on repository metadata (name, URL, maintainer) |
| `nyxid-node/config.yaml` | Add-on definition: name, arch, options schema, permissions |
| `nyxid-node/build.yaml` | Multi-arch base image mapping + build args |
| `nyxid-node/Dockerfile` | Multi-stage: compile nyxid from source → Alpine runtime |
| `nyxid-node/translations/en.yaml` | English labels/descriptions for config options in HA UI |
| `nyxid-node/CHANGELOG.md` | Version changelog |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/type` | s6 service type: oneshot |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up` | Setup script: register node + sync credentials |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/dependencies.d/base` | Depends on base services |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/type` | s6 service type: longrun |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run` | Start nyxid node agent |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish` | Cleanup on stop |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/dependencies.d/nyxid-node-setup` | Depends on setup completing |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node` | Register longrun in user bundle |
| `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node-setup` | Register oneshot in user bundle |
| `.github/workflows/build.yaml` | CI: multi-arch Docker build on tag push, push to GHCR |
| `README.md` | Repository README with installation and usage instructions |

---

### Task 1: Repository Metadata

**Files:**
- Create: `repository.yaml`

- [ ] **Step 1: Create repository.yaml**

```yaml
name: NyxID Add-ons
url: https://github.com/ChronoAIProject/nyx-homeassistant-node
maintainer: ChronoAI Project
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('repository.yaml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add repository.yaml
git commit -m "feat: add add-on repository metadata"
```

---

### Task 2: Add-on Configuration and Build Files

**Files:**
- Create: `nyxid-node/config.yaml`
- Create: `nyxid-node/build.yaml`
- Create: `nyxid-node/translations/en.yaml`
- Create: `nyxid-node/CHANGELOG.md`

- [ ] **Step 1: Create config.yaml**

```yaml
name: "NyxID Node"
description: "Run a NyxID credential node agent to securely reverse-proxy Home Assistant and LAN services through NyxID"
version: "0.1.0"
slug: "nyxid-node"
url: "https://github.com/ChronoAIProject/nyx-homeassistant-node"
startup: "application"
boot: "auto"
arch:
  - amd64
  - aarch64
homeassistant_api: true
host_network: true
image: "ghcr.io/chronoaiproject/nyx-homeassistant-node/{arch}"
options:
  nyxid_server_url: "wss://nyx-api.chrono-ai.fun/api/v1/nodes/ws"
  registration_token: ""
  node_name: "homeassistant"
  log_level: "info"
  services: []
schema:
  nyxid_server_url: url
  registration_token: "str?"
  node_name: str
  log_level: "list(debug|info|warn|error)"
  services:
    - slug: str
      target_url: url
      credential_type: "list(header|query_param)"
      credential_name: str
      credential_value: password
```

- [ ] **Step 2: Create build.yaml**

```yaml
build_from:
  amd64: "ghcr.io/home-assistant/amd64-base:3.21"
  aarch64: "ghcr.io/home-assistant/aarch64-base:3.21"
args:
  NYXID_VERSION: "main"
```

- [ ] **Step 3: Create translations/en.yaml**

```yaml
configuration:
  nyxid_server_url:
    name: "NyxID Server URL"
    description: "WebSocket URL of your NyxID server (e.g., wss://auth.example.com/api/v1/nodes/ws)"
  registration_token:
    name: "Registration Token"
    description: "One-time registration token from NyxID. Only needed for first setup; ignored after successful registration."
  node_name:
    name: "Node Name"
    description: "Display name for this node in logs"
  log_level:
    name: "Log Level"
    description: "Logging verbosity (debug, info, warn, error)"
  services:
    name: "Additional Services"
    description: "LAN services to reverse-proxy (Home Assistant is auto-configured)"
    slug:
      name: "Service Slug"
      description: "Unique identifier for this service (e.g., synology-nas)"
    target_url:
      name: "Target URL"
      description: "URL of the downstream service (e.g., http://192.168.1.100:5000)"
    credential_type:
      name: "Credential Type"
      description: "How to inject the credential: as an HTTP header or query parameter"
    credential_name:
      name: "Credential Name"
      description: "Header name (e.g., Authorization) or query parameter name (e.g., api_key)"
    credential_value:
      name: "Credential Value"
      description: "The secret value to inject (e.g., Bearer token or API key)"
```

- [ ] **Step 4: Create CHANGELOG.md**

```markdown
# Changelog

## 0.1.0

- Initial release
- NyxID credential node agent packaged as HA Add-on
- Auto-configured Home Assistant API access via SUPERVISOR_TOKEN
- Support for additional LAN service proxying
- Multi-arch support (amd64, aarch64)
```

- [ ] **Step 5: Verify YAML syntax**

Run: `for f in nyxid-node/config.yaml nyxid-node/build.yaml nyxid-node/translations/en.yaml; do echo "--- $f ---"; python3 -c "import yaml; yaml.safe_load(open('$f'))"; done`
Expected: Three `---` headers with no errors

- [ ] **Step 6: Commit**

```bash
git add nyxid-node/config.yaml nyxid-node/build.yaml nyxid-node/translations/en.yaml nyxid-node/CHANGELOG.md
git commit -m "feat: add add-on config, build, and translation files"
```

---

### Task 3: Dockerfile

**Files:**
- Create: `nyxid-node/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Stage 1: Compile nyxid CLI from source
FROM rust:1.82-alpine3.21 AS builder

RUN apk add --no-cache \
    musl-dev \
    openssl-dev \
    openssl-libs-static \
    pkgconf \
    git \
    perl \
    make

ARG NYXID_VERSION=main
RUN git clone --depth 1 --branch ${NYXID_VERSION} \
    https://github.com/ChronoAIProject/NyxID.git /build/nyxid

WORKDIR /build/nyxid

ENV OPENSSL_STATIC=1
RUN cargo build --release --bin nyxid \
    && strip target/release/nyxid

# Stage 2: Runtime image
ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache \
    ca-certificates \
    jq \
    bash

COPY --from=builder /build/nyxid/target/release/nyxid /usr/local/bin/nyxid

COPY rootfs /
```

- [ ] **Step 2: Verify Dockerfile syntax**

Run: `docker run --rm -i hadolint/hadolint < nyxid-node/Dockerfile || true`
Expected: No critical errors (warnings about pinning are acceptable)

- [ ] **Step 3: Commit**

```bash
git add nyxid-node/Dockerfile
git commit -m "feat: add multi-stage Dockerfile for nyxid node agent"
```

---

### Task 4: s6-overlay Service Structure

**Files:**
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/type`
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/dependencies.d/base` (empty)
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/type`
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/dependencies.d/nyxid-node-setup` (empty)
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node` (empty)
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node-setup` (empty)

- [ ] **Step 1: Create setup service type**

Write `oneshot` (no trailing newline) to:
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/type`

- [ ] **Step 2: Create setup service dependency**

Create empty file:
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/dependencies.d/base`

- [ ] **Step 3: Create longrun service type**

Write `longrun` (no trailing newline) to:
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/type`

- [ ] **Step 4: Create longrun service dependency on setup**

Create empty file:
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/dependencies.d/nyxid-node-setup`

- [ ] **Step 5: Register both services in user bundle**

Create empty files:
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node`
`nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node-setup`

- [ ] **Step 6: Verify directory structure**

Run: `find nyxid-node/rootfs -type f | sort`
Expected:
```
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/dependencies.d/base
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/type
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/dependencies.d/nyxid-node-setup
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/type
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node
nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node-setup
```

- [ ] **Step 7: Commit**

```bash
git add nyxid-node/rootfs/
git commit -m "feat: add s6-overlay service structure"
```

---

### Task 5: Setup Script (oneshot)

**Files:**
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up`

This script runs on every Add-on start. It handles:
1. Node registration (first run only)
2. HA credential injection (every run, because SUPERVISOR_TOKEN changes)
3. Services credential sync (every run, to pick up config changes)

**NyxID CLI reference for this script:**
- `nyxid node register --token <token> --url <ws_url> --config <dir>` — initial registration
- `nyxid node credentials add --config <dir> --service <slug> --header <name> --value <secret> --secret-format raw --url <target_url>` — add/update header credential
- `nyxid node credentials add --config <dir> --service <slug> --query-param <name> --value <secret> --url <target_url>` — add/update query param credential
- `nyxid node credentials remove --config <dir> --service <slug>` — remove a credential

- [ ] **Step 1: Create the setup script**

```bash
#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Setup (runs on every start)
# ==============================================================================

declare NYXID_CONFIG="/data/nyxid-node"
declare SERVICES_FILE="/data/configured-services.txt"

mkdir -p "${NYXID_CONFIG}"

# --------------------------------------------------------------------------
# 1. Node registration (first run only)
# --------------------------------------------------------------------------
if [ ! -f "${NYXID_CONFIG}/config.toml" ] || ! grep -q '\[node\]' "${NYXID_CONFIG}/config.toml" 2>/dev/null; then
    declare server_url
    declare reg_token
    server_url=$(bashio::config 'nyxid_server_url')
    reg_token=$(bashio::config 'registration_token')

    if bashio::var.is_empty "${reg_token}"; then
        bashio::log.fatal "Node is not registered and no registration token is configured."
        bashio::log.fatal "Please set 'registration_token' in the add-on configuration."
        exit 1
    fi

    if bashio::var.is_empty "${server_url}"; then
        bashio::log.fatal "NyxID server URL is not configured."
        bashio::log.fatal "Please set 'nyxid_server_url' in the add-on configuration."
        exit 1
    fi

    declare node_name
    node_name=$(bashio::config 'node_name')
    bashio::log.info "Registering node '${node_name}' with NyxID server at ${server_url}..."

    if ! nyxid node register \
        --token "${reg_token}" \
        --url "${server_url}" \
        --config "${NYXID_CONFIG}"; then
        bashio::log.fatal "Node registration failed. Check your registration token and server URL."
        exit 1
    fi

    bashio::log.info "Node registered successfully."
fi

# --------------------------------------------------------------------------
# 2. Determine desired service slugs
# --------------------------------------------------------------------------
declare -a desired_slugs=("homeassistant")

for index in $(bashio::config 'services|keys'); do
    declare slug
    slug=$(bashio::config "services[${index}].slug")
    desired_slugs+=("${slug}")
done

# --------------------------------------------------------------------------
# 3. Remove stale services (present in previous run but not in current config)
# --------------------------------------------------------------------------
if [ -f "${SERVICES_FILE}" ]; then
    while IFS= read -r old_slug; do
        [ -z "${old_slug}" ] && continue
        declare found=false
        for desired in "${desired_slugs[@]}"; do
            if [ "${desired}" = "${old_slug}" ]; then
                found=true
                break
            fi
        done
        if [ "${found}" = "false" ]; then
            bashio::log.info "Removing stale service credential: ${old_slug}"
            nyxid node credentials remove \
                --config "${NYXID_CONFIG}" \
                --service "${old_slug}" || true
        fi
    done < "${SERVICES_FILE}"
fi

# --------------------------------------------------------------------------
# 4. Update Home Assistant built-in credential (every start)
# --------------------------------------------------------------------------
bashio::log.info "Updating Home Assistant API credential..."

nyxid node credentials add \
    --config "${NYXID_CONFIG}" \
    --service "homeassistant" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor/core/api"

# --------------------------------------------------------------------------
# 5. Sync additional services from options
# --------------------------------------------------------------------------
for index in $(bashio::config 'services|keys'); do
    declare slug target_url cred_type cred_name cred_value
    slug=$(bashio::config "services[${index}].slug")
    target_url=$(bashio::config "services[${index}].target_url")
    cred_type=$(bashio::config "services[${index}].credential_type")
    cred_name=$(bashio::config "services[${index}].credential_name")
    cred_value=$(bashio::config "services[${index}].credential_value")

    bashio::log.info "Configuring service: ${slug} → ${target_url}"

    if [ "${cred_type}" = "header" ]; then
        nyxid node credentials add \
            --config "${NYXID_CONFIG}" \
            --service "${slug}" \
            --header "${cred_name}" \
            --secret-format raw \
            --value "${cred_value}" \
            --url "${target_url}"
    else
        nyxid node credentials add \
            --config "${NYXID_CONFIG}" \
            --service "${slug}" \
            --query-param "${cred_name}" \
            --value "${cred_value}" \
            --url "${target_url}"
    fi
done

# --------------------------------------------------------------------------
# 6. Save current service list for next-run diff
# --------------------------------------------------------------------------
printf '%s\n' "${desired_slugs[@]}" > "${SERVICES_FILE}"

bashio::log.info "Setup complete. ${#desired_slugs[@]} service(s) configured."
```

- [ ] **Step 2: Make the script executable**

Run: `chmod +x nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up`

- [ ] **Step 3: Verify script syntax**

Run: `bash -n nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up`
Expected: No output (valid syntax)

- [ ] **Step 4: Commit**

```bash
git add nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up
git commit -m "feat: add setup script for node registration and credential sync"
```

---

### Task 6: Run and Finish Scripts (longrun)

**Files:**
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run`
- Create: `nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish`

- [ ] **Step 1: Create the run script**

```bash
#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Run the node agent
# ==============================================================================

declare NYXID_CONFIG="/data/nyxid-node"
declare log_level

log_level=$(bashio::config 'log_level')

bashio::log.info "Starting NyxID node agent (log_level=${log_level})..."

exec nyxid node start \
    --config "${NYXID_CONFIG}" \
    --log-level "${log_level}"
```

- [ ] **Step 2: Create the finish script**

```bash
#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Finish (cleanup on stop/crash)
# ==============================================================================

declare exit_code=${1}
declare signal=${2}

if [ "${exit_code}" -ne 0 ]; then
    bashio::log.warning "NyxID node agent exited with code ${exit_code} (signal ${signal})"
fi
```

- [ ] **Step 3: Make scripts executable**

Run: `chmod +x nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish`

- [ ] **Step 4: Verify script syntax**

Run: `bash -n nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run && bash -n nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish`
Expected: No output (valid syntax)

- [ ] **Step 5: Commit**

```bash
git add nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish
git commit -m "feat: add run and finish scripts for nyxid node agent"
```

---

### Task 7: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/build.yaml`

- [ ] **Step 1: Create the build workflow**

```yaml
name: Build Add-on

on:
  release:
    types:
      - published
  workflow_dispatch:

jobs:
  build:
    name: Build ${{ matrix.arch }} image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      fail-fast: false
      matrix:
        arch:
          - amd64
          - aarch64
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Build and push
        uses: home-assistant/builder@master
        with:
          args: |
            --${{ matrix.arch }} \
            --target nyxid-node \
            --docker-hub "ghcr.io/chronoaiproject/nyx-homeassistant-node"
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build.yaml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build.yaml
git commit -m "ci: add multi-arch build workflow with HA Builder"
```

---

### Task 8: README and Final Verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# NyxID Node — Home Assistant Add-on

Run a [NyxID](https://github.com/ChronoAIProject/NyxID) credential node agent on Home Assistant OS. Securely reverse-proxy your Home Assistant instance and other LAN services through NyxID — credentials never leave your local network.

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click **⋮ → Repositories** and add:
   ```
   https://github.com/ChronoAIProject/nyx-homeassistant-node
   ```
3. Find **NyxID Node** in the store and click **Install**

## Configuration

### Required (first setup)

| Option | Description |
|--------|-------------|
| `nyxid_server_url` | WebSocket URL of your NyxID server (e.g., `wss://auth.example.com/api/v1/nodes/ws`) |
| `registration_token` | One-time registration token from NyxID (only needed for first start) |

### Optional

| Option | Default | Description |
|--------|---------|-------------|
| `node_name` | `homeassistant` | Display name for this node in logs |
| `log_level` | `info` | Logging verbosity: `debug`, `info`, `warn`, `error` |
| `services` | `[]` | Additional LAN services to reverse-proxy (see below) |

### Home Assistant API

Home Assistant is **automatically configured** as a built-in service. The add-on uses the Supervisor API token — no manual setup required. Access it through NyxID with the service slug `homeassistant`.

### Additional Services

To proxy other LAN services, add entries to the `services` list:

```yaml
services:
  - slug: synology-nas
    target_url: http://192.168.1.100:5000
    credential_type: header
    credential_name: Authorization
    credential_value: "Bearer your-token-here"
  - slug: router-api
    target_url: http://192.168.1.1/api
    credential_type: query_param
    credential_name: api_key
    credential_value: "your-api-key"
```

## How It Works

```
External Client → NyxID Server → WebSocket → This Add-on → Local Services
                                (outbound)     (credential    (HA, NAS, etc.)
                                               injection)
```

1. The add-on connects to your NyxID server via outbound WebSocket (no inbound ports needed)
2. When a proxy request arrives, the node agent injects the locally-stored credentials
3. The request is forwarded to the target service on your LAN
4. Credentials never leave your network — NyxID only sees the request metadata

## Architecture

- **amd64** and **aarch64** supported
- Persistent data stored in `/data/` (survives add-on updates)
- Process managed by s6-overlay with automatic restart on crash
- Node agent includes built-in WebSocket reconnection with exponential backoff
```

- [ ] **Step 2: Add placeholder icon and logo**

The Add-on needs `nyxid-node/icon.png` (128x128) and `nyxid-node/logo.png` (256x256). For now, create minimal placeholder SVGs converted to PNG, or copy existing NyxID branding assets from `/Users/auric/NyxID/` if available. These can be replaced with proper artwork later.

- [ ] **Step 3: Verify complete file structure**

Run: `find . -not -path './.git/*' -not -path './.git' -type f | sort`
Expected:
```
./.github/workflows/build.yaml
./README.md
./docs/superpowers/plans/2026-04-15-nyxid-node-addon.md
./docs/superpowers/specs/2026-04-15-nyxid-node-addon-design.md
./nyxid-node/CHANGELOG.md
./nyxid-node/Dockerfile
./nyxid-node/build.yaml
./nyxid-node/config.yaml
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/dependencies.d/base
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/type
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/dependencies.d/nyxid-node-setup
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/type
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node
./nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/nyxid-node-setup
./nyxid-node/translations/en.yaml
./repository.yaml
```

- [ ] **Step 4: Commit**

```bash
git add README.md nyxid-node/icon.png nyxid-node/logo.png
git commit -m "docs: add repository README, icon, and logo"
```

- [ ] **Step 5: Verify all scripts are executable**

Run: `ls -la nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node-setup/up nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/run nyxid-node/rootfs/etc/s6-overlay/s6-rc.d/nyxid-node/finish`
Expected: All three files show `-rwxr-xr-x` permissions
