import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'app/options.py'
spec = importlib.util.spec_from_file_location('pipeline_addon_options', SOURCE)
options = importlib.util.module_from_spec(spec)
spec.loader.exec_module(options)


class OptionsTests(unittest.TestCase):
    def test_settings_cannot_override_storage_or_inject_unlisted_environment(self):
        result = options.environment({'pipeline_config': '{"version":1}', 'relay_token':'synthetic-secret',
                                      'tick_seconds':5,'frigate_url':'http://example-frigate:5000',
                                      'mongodb_uri':'must-not-be-used','data_dir':'/other',
                                      'processing_enabled':False,'pythonpath':'/injected'}, '/data/state')
        self.assertEqual(result['DATA_DIR'], '/data/state')
        self.assertEqual(result['RELAY_TOKEN'], 'synthetic-secret')
        self.assertEqual(result['TICK_SECONDS'], '5')
        self.assertEqual(result['FRIGATE_URL'], 'http://example-frigate:5000')
        self.assertEqual(json.loads(result['PIPELINE_CONFIG_JSON']), {'version':1})
        self.assertNotIn('MONGODB_URI', result)
        self.assertNotIn('PROCESSING_ENABLED', result)
        self.assertNotIn('PYTHONPATH', result)

    def test_rejects_missing_or_non_object_policy(self):
        for value in ({}, {'pipeline_config':{}}, {'pipeline_config':'[]'}, {'pipeline_config':'invalid'}):
            with self.subTest(value=value),self.assertRaises(ValueError):options.environment(value,'/data/state')
