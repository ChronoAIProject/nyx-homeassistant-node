# specs

OpenAPI documents that NyxID attaches to Home Assistant services so agents get one tool per operation instead of a generic proxy tool.

- `home-assistant-openapi.json` — minimal Home Assistant REST API subset (config, entity state, switch/light turn_on and turn_off). Attach its raw URL as `openapi_spec_url` on the NyxID `home-assistant` service. Paths are relative to a service base URL that already ends in `/api`.
- `frigate-openapi.json` — minimal Frigate NVR REST API subset for the office cameras (version, stats, events list and detail, camera and event snapshot JPEGs). Attach its raw URL as `openapi_spec_url` on the NyxID `frigate` service. Paths start with `/api` because the service base URL is the Frigate host root. The two `image/jpeg` operations are marked `binary_artifact` by NyxID, so Aevatar exposes them with `response_mode: file_artifact` (workflow runs only; channel bots get text operations).
