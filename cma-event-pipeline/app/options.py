"""Allowlisted add-on options; application credentials stay in private HA options."""
import json

NAMES = (
    'relay_token', 'api_token', 'provider_token', 'worker_token', 'worker_service',
    'cma_context_config', 'cma_context_token',
    'worker_name', 'cma_event_url', 'cma_hmac_key_id', 'cma_hmac_secret',
    'frigate_url', 'frigate_api_key', 'heartbeat_seconds', 'tick_seconds',
)


def environment(options, data_dir):
    if not isinstance(options, dict) or not isinstance(options.get('pipeline_config'), str):
        raise ValueError('pipeline_config must contain a JSON policy')
    pipeline = json.loads(options['pipeline_config'])
    if not isinstance(pipeline, dict):
        raise ValueError('pipeline_config must contain a JSON object')
    env = {name.upper(): str(options[name]) for name in NAMES if name in options and options[name] != ''}
    env.update(PIPELINE_CONFIG_JSON=json.dumps(pipeline, ensure_ascii=False), DATA_DIR=str(data_dir), HA_INGRESS="true")
    # This deployment always uses local durable SQLite. Options cannot override
    # MongoDB, data paths, arbitrary env, paused-source state or Python settings.
    return env
