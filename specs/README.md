# specs

OpenAPI documents that NyxID attaches to Home Assistant services so agents get one tool per operation instead of a generic proxy tool.

- `home-assistant-openapi.json` — minimal Home Assistant REST API subset (config, entity state, switch/light turn_on and turn_off). Attach its raw URL as `openapi_spec_url` on the NyxID `home-assistant` service. Paths are relative to a service base URL that already ends in `/api`.
