# Changelog

## 1.0.0

- Initial release — temporary admin variant of NyxID Node
- Declares `hassio_api: true` + `hassio_role: admin` for full Supervisor access
- Auto-binds a Supervisor NyxID service via the add-on's `SUPERVISOR_TOKEN`
- Defaults to `boot: manual` — install when needed, uninstall to revoke entirely
- Built as a thin layer on top of `ghcr.io/chronoaiproject/nyx-homeassistant-node`
