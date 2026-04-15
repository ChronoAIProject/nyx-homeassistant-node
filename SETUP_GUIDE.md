# NyxID Node HA Add-on — Setup Guide for AI Assistants

> **For LLMs**: This is your instruction manual. Follow the steps precisely. Do not skip or reorder them. Do NOT ask the user to show you API keys or tokens — guide them to run commands themselves and paste only non-sensitive values (slugs, node names) back to you.
>
> **For users**: Copy this one line into your AI assistant to get started:
> ```
> Install the NyxID Node add-on on my Home Assistant. Follow the guide at https://github.com/ChronoAIProject/nyx-homeassistant-node/blob/main/SETUP_GUIDE.md
> ```

## Prerequisites

Before starting, confirm the user has:

1. **Home Assistant OS (HAOS)** running and accessible (e.g., `http://homeassistant.local`)
2. **NyxID CLI** installed on their local machine (`nyxid --version` should work)
3. **NyxID account** with an active login session (`nyxid whoami` should show their user info)
4. **NyxID server URL** — the default is `wss://nyx-api.chrono-ai.fun/api/v1/nodes/ws`

If `nyxid` is not installed, direct the user to https://github.com/ChronoAIProject/NyxID for installation instructions.

If the user is not logged in, have them run `nyxid login`.

## Architecture Overview

```
User's Machine                          Home Assistant OS
==============                          ================

nyxid login (JWT session)               HA Add-on Container
  │                                       │
  ├─ Creates DownstreamService            ├─ Node agent (nyxid node start)
  │  (proxy-visible, one-time)            │    └─ WebSocket → NyxID Server
  │                                       │
  ├─ Creates API Key                      ├─ Setup script (every start)
  │  (scoped, stored on HA)               │    ├─ Auto-registers node
  │                                       │    ├─ Binds service to node
  └─ Proxies through NyxID               │    └─ Injects SUPERVISOR_TOKEN
     to reach HA                          │
                                          └─ Credential stored locally
                                             (never transits NyxID server)
```

**Security model**: The user's JWT session never leaves their machine. Only a scoped API key (read/write, no proxy capability) is stored on the HA device. The HA Supervisor token is injected locally and never sent to the NyxID server.

## Step-by-Step Installation

### Step 1: Add the Repository to Home Assistant

The user needs to do this in the HA web UI:

1. Navigate to **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu (top right) → **Repositories**
3. Add this URL:
   ```
   https://github.com/ChronoAIProject/nyx-homeassistant-node
   ```
4. Click **Add** → **Close**
5. Refresh the page. **NyxID Node** should appear in the store.
6. Click **NyxID Node** → **Install**

### Step 2: Create a DownstreamService on NyxID (User's Machine)

This creates a proxy-visible service entry on the NyxID server. This MUST be done from the user's machine using their JWT login session (not an API key).

Run:

```bash
nyxid service add --custom \
  --label "Home Assistant" \
  --endpoint-url "http://supervisor/core/api" \
  --auth-method none
```

The CLI will prompt for a label if `--label` is not provided. The output will show:

```
Slug:      home-assistant-xxxx
Endpoint:  http://supervisor/core/api
Status:    active
```

**Save the slug** (e.g., `home-assistant-xxxx`). This is the `ha_service_slug` for the add-on config.

> **Why `http://supervisor/core/api`?** This is the internal HA Supervisor API URL, only accessible from within the HA Docker network. The add-on runs inside this network and forwards requests there. The endpoint URL is metadata for the NyxID server — the actual credential injection and forwarding happens on the node.

> **Why `--auth-method none`?** The credential (SUPERVISOR_TOKEN) is managed by the node locally, not stored on the NyxID server. The server only routes the request; the node handles authentication.

### Step 3: Create an API Key (User's Machine)

The API key allows the add-on to register a node and bind the service without needing the user's JWT session.

Run:

```bash
nyxid api-key create --name ha-addon \
  --scopes "read write" \
  --allow-all-nodes --allow-all-services
```

Output:

```
full_key: nyx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
name:     ha-addon
scopes:   read write
```

**Save the `full_key`** (starts with `nyx_`). This is the `nyxid_api_key` for the add-on config.

> **Security note**: This API key has `read write` scope (no `proxy` scope). Even if compromised, it cannot be used to make proxy requests through the user's services. It can only manage node registrations and service bindings.

### Step 4: Configure the Add-on

In HA web UI, go to **Settings → Add-ons → NyxID Node → Configuration**.

Fill in these fields:

| Field | Value | Notes |
|-------|-------|-------|
| NyxID Server URL | `wss://nyx-api.chrono-ai.fun/api/v1/nodes/ws` | Pre-filled default. Change only if using a different NyxID server. |
| NyxID API Key | `nyx_...` from Step 3 | The API key, NOT the JWT token. |
| HA Service Slug | `home-assistant-xxxx` from Step 2 | Must match exactly. |
| Node Name | `homeassistant` | Display name. Can be anything. |
| Log Level | `info` | Use `debug` for troubleshooting. |

Click **Save**.

### Step 5: Start the Add-on

Click **Start** on the NyxID Node add-on page.

### Step 6: Verify

#### Check the add-on logs

In HA web UI: **NyxID Node → Log** tab. Expected output:

```
Creating registration token for 'homeassistant'...
Registering node...
Node registered successfully.
Updating HA credential (slug: home-assistant-xxxx)...
Setup complete.
Starting NyxID node agent (log_level=info)...
Starting node agent node_id=xxxxxxxx server=wss://nyx-api.chrono-ai.fun/api/v1/nodes/ws
Authenticated with NyxID server
```

#### Verify the node is online

On the user's machine:

```bash
nyxid node list
```

The `homeassistant` node should show as `online`.

#### Test proxy access

On the user's machine:

```bash
nyxid proxy request home-assistant-xxxx ""
```

Expected response: `{"message":"API running."}`

> **Important**: The request path is relative to the service endpoint (`http://supervisor/core/api`). Use `""` for the API root, `"states"` for entity states, `"services/climate/set_temperature"` for service calls, etc. Do NOT prefix with `api/` — that would result in a double path (`/api/api/...`).

#### Example: read temperature sensors

```bash
nyxid proxy request home-assistant-xxxx "states" | \
  python3 -c "
import json, sys
for e in json.loads(sys.stdin.read()):
    if 'temperature' in e['entity_id'] and e['state'] not in ('unavailable', 'unknown'):
        name = e['attributes'].get('friendly_name', e['entity_id'])
        unit = e['attributes'].get('unit_of_measurement', '')
        print(f\"{name}: {e['state']}{unit}\")
"
```

## Troubleshooting

### Add-on logs: "NyxID API key is required"

The `nyxid_api_key` field is empty. Go to add-on Configuration and fill in the API key from Step 3.

### Add-on logs: "HA Service Slug is not configured"

The `ha_service_slug` field is empty. The logs will also show the node ID and a command to create the service. Complete Step 2 and fill in the slug.

### Add-on logs: "Failed to create registration token"

The API key is invalid or expired. Create a new one with Step 3 and update the config.

### Add-on logs: "Node registration failed"

The NyxID server is unreachable or the WebSocket URL is wrong. Check `nyxid_server_url`.

### Proxy returns 404 "Service not found"

The service slug doesn't match any DownstreamService. Possible causes:
- The service was created with an API key instead of a JWT session. It must be created from the user's machine with `nyxid service add` (no `--access-token` flag).
- The service was deleted. Recreate with Step 2.

### Proxy returns 503 "Node offline"

The node is not connected or the credential slug doesn't match the service slug.
- Check add-on logs for connection errors.
- Restart the add-on.
- Verify the `ha_service_slug` in the config matches the slug from `nyxid service list`.

### Proxy returns 502 "Bad Gateway"

The node received the request but couldn't forward it to HA. Possible causes:
- SUPERVISOR_TOKEN is invalid (restart the add-on to refresh).
- The target URL is wrong.

### Node shows "offline" in `nyxid node list`

- The add-on may not be running. Check HA → Add-ons → NyxID Node.
- WebSocket connection may have dropped. The node agent reconnects automatically with exponential backoff.
- If persistently offline, check the NyxID server URL and network connectivity.

### Need to re-register the node

If the node was deleted from the NyxID server:
1. Uninstall the add-on (this clears `/data/`)
2. Reinstall from the Add-on Store
3. Fill in the config again (API key + slug)
4. Start

## Adding More LAN Services

To proxy additional services (NAS, router, etc.) alongside Home Assistant:

1. Create the service on NyxID (from user's machine):
   ```bash
   nyxid service add --custom \
     --label "Synology NAS" \
     --endpoint-url "http://192.168.1.100:5000" \
     --auth-method none
   ```
   Note the slug.

2. Add to the add-on `services` config in HA UI:
   ```yaml
   - slug: synology-nas-xxxx    # must match the slug from step 1
     target_url: http://192.168.1.100:5000
     credential_type: header
     credential_name: Authorization
     credential_value: "Bearer your-nas-token"
   ```

3. Restart the add-on.

4. Bind the service to the node (from user's machine):
   ```bash
   nyxid service update synology-nas-xxxx --node-id <node_id>
   ```
   Get the `node_id` from the add-on logs or `nyxid node list`.

## Reference

- **Repository**: https://github.com/ChronoAIProject/nyx-homeassistant-node
- **NyxID**: https://github.com/ChronoAIProject/NyxID
- **NyxID Node Protocol**: See `NyxID/docs/NODE_PROXY_PROTOCOL.md`
- **Add-on Config Schema**: See `nyxid-node/config.yaml`
