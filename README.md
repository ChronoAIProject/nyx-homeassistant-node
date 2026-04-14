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
