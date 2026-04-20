# NyxID Node — Home Assistant Add-on

Run a [NyxID](https://github.com/ChronoAIProject/NyxID) credential node agent on Home Assistant OS. Securely reverse-proxy your Home Assistant instance and other LAN services through NyxID — credentials never leave your local network.

## Quick Start — Give This to Your AI Assistant

Copy this one line into Claude Code, Codex, Cursor, or any AI coding assistant:

```
Install the NyxID Node add-on on my Home Assistant. Follow the guide at https://github.com/ChronoAIProject/nyx-homeassistant-node/blob/main/SETUP_GUIDE.md
```

The AI will walk you through the setup step by step.

## How It Works

```
External Client → NyxID Server → WebSocket → This Add-on → Local Services
                                (outbound)    (credential    (HA, NAS, etc.)
                                              injection)
```

1. The add-on connects to your NyxID server via outbound WebSocket (no inbound ports needed)
2. When a proxy request arrives, the node agent injects the locally-stored credentials
3. The request is forwarded to the target service on your LAN
4. Credentials never leave your network — NyxID only sees the request metadata

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click **⋮ → Repositories** and add:
   ```
   https://github.com/ChronoAIProject/nyx-homeassistant-node
   ```
3. Find **NyxID Node** in the store and click **Install**

## Setup

### Step 1: Create the HA service (on your machine, one-time)

```bash
nyxid service add --custom \
  --label "Home Assistant" \
  --endpoint-url "http://supervisor/core/api" \
  --auth-method none
```

Note the **Slug** from the output (e.g., `home-assistant-xxxx`).

### Step 2: Create an API key (on your machine, one-time)

```bash
nyxid api-key create --name ha-addon \
  --scopes "read write" \
  --allow-all-nodes --allow-all-services
```

Note the **key** (starts with `nyx_`).

### Step 3: Configure the Add-on

In Home Assistant, go to **NyxID Node → Configuration** and fill in:

| Field | Value |
|-------|-------|
| **NyxID API Key** | The `nyx_...` key from Step 2 |
| **HA Service Slug** | The slug from Step 1 |

Click **Save**, then **Start**.

### Verify

After starting, check the add-on logs. You should see:

```
Node registered successfully.
Updating HA credential (slug: home-assistant-xxxx)...
Setup complete.
Starting NyxID node agent...
Authenticated with NyxID server
```

Test from your machine:

```bash
nyxid proxy request home-assistant-xxxx "api/"
# Should return: {"message":"API running."}
```

## Additional Services

To proxy other LAN services, add entries to the `services` list in the add-on config:

```yaml
services:
  - slug: synology-nas
    target_url: http://192.168.1.100:5000
    credential_type: header
    credential_name: Authorization
    credential_value: "Bearer your-token-here"
```

## Temporary admin mode — `NyxID Node (Admin)`

The main add-on only has Core API access, so it cannot install/manage add-ons remotely. For that, install the sibling add-on **NyxID Node (Admin)** from the same repository *only when you need it*, then **uninstall** to fully revoke the elevated capability.

### How it differs

| | NyxID Node | NyxID Node (Admin) |
|---|---|---|
| `hassio_role` | (none) | **admin** |
| `/api/*` (Core API) | ✅ | ✅ |
| `/supervisor/*`, `/addons/*`, `/store/*` | ❌ 403 | ✅ |
| `boot` | auto | **manual** |
| Use case | always-on | install → use → uninstall |

### Usage

```bash
# On your machine — one-time: register a Supervisor service slug
nyxid service add --custom \
  --label "HA Supervisor" \
  --endpoint-url "http://supervisor" \
  --auth-method none
```

In HA: install **NyxID Node (Admin)**, paste the slug into `Supervisor Service Slug`, start.

Now you can drive the Supervisor API via NyxID:

```bash
# Add Frigate repository
nyxid proxy request supervisor-xxxx "store/repositories" \
  --method POST \
  --body '{"repository":"https://github.com/blakeblackshear/frigate-hass-addons"}'

# Install Frigate
nyxid proxy request supervisor-xxxx \
  "store/addons/blakeblackshear_frigate_hass-addons_frigate/install" \
  --method POST
```

When done: **uninstall the admin add-on**. The container is destroyed, the `SUPERVISOR_TOKEN` is invalidated, and `hassio_role: admin` is no longer declared anywhere. Stopping (without uninstalling) also works but is weaker — the permission declaration stays on disk.

### Security note

`hassio_role: admin` grants root-equivalent control over your HA system. Anyone who obtains the NyxID API key while the admin add-on is running can install/remove any add-on, read `/data`, and modify Supervisor state. Keep the admin add-on uninstalled by default.

## Architecture

- **amd64** and **aarch64** supported
- Persistent data stored in `/data/` (survives add-on updates)
- Process managed by s6-overlay with automatic restart on crash
- Node agent includes built-in WebSocket reconnection with exponential backoff
- JWT session never leaves your machine — only a scoped API key is stored on HA
