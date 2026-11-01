"""Exercise the identity change on actual nested archives, including full state."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).parents[1] / 'scripts/migrate_monitor_backup.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class BackupMigrationTests(unittest.TestCase):
    def backup(self, root, *, protected=False, extra_addon=False, unsafe=False):
        inner = io.BytesIO()
        payloads = {'data/options.json':b'{"worker_token":"synthetic-secret"}',
                    'data/state/monitoring.sqlite3':b'registry',
                    'data/state/rules/second/3/history.sqlite3':b'old revision',
                    'data/state/relay-ingest.sqlite3-wal':b'queued rows'}
        with tarfile.open(fileobj=inner, mode='w:gz') as archive:
            migration.add_json(archive, './addon.json', {'system':{'slug':migration.OLD_SLUG},
                'user':{'options':{'relay_token':'synthetic-secret'}}, 'version':'0.3.0-alpha.3','state':'started'})
            for name, content in payloads.items():
                item = tarfile.TarInfo('../escape' if unsafe else name)
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
        source = root / 'source.tar'
        with tarfile.open(source, 'w') as archive:
            migration.add_json(archive, './backup.json', {'slug':'original','type':'partial','protected':protected,
                'homeassistant':False,'folders':[],'compressed':True,
                'addons':[{'slug':'example_' + migration.OLD_SLUG}] + ([{'slug':'unrelated'}] if extra_addon else [])})
            item = tarfile.TarInfo('example_' + migration.OLD_SLUG + '.tar.gz')
            item.size = len(inner.getvalue())
            archive.addfile(item, io.BytesIO(inner.getvalue()))
        return source, payloads

    def test_preserves_all_nested_state_and_options_and_restores_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, payloads = self.backup(root)
            original = source.read_bytes()
            target = root/'target.tar'
            report = migration.prepare(source,target,'0.3.0-alpha.4')
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(report['target_slug'],'example_video-event-monitor')
            with tarfile.open(target) as outer:
                metadata = json.load(outer.extractfile('./backup.json'))
                self.assertNotEqual(metadata['slug'],'original')
                with tarfile.open(fileobj=outer.extractfile('example_video-event-monitor.tar.gz'),mode='r:gz') as inner:
                    addon = json.load(inner.extractfile('./addon.json'))
                    self.assertEqual(addon['state'],'stopped')
                    self.assertEqual(addon['user']['options'],{'relay_token':'synthetic-secret'})
                    self.assertFalse(addon['user']['ingress_panel'])
                    self.assertEqual(addon['system']['slug'],'video-event-monitor')
                    for name,content in payloads.items():
                        self.assertEqual(inner.extractfile(name).read(),content)
            with self.assertRaises(FileExistsError):migration.prepare(source,target,'0.3.0-alpha.4')
            self.assertEqual(target.stat().st_mode & 0o777,0o600)

    def test_rejects_protected_or_multi_addon_or_unsafe_backups_without_output(self):
        for kwargs in ({'protected':True},{'extra_addon':True},{'unsafe':True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source,_=self.backup(root,**kwargs)
                with self.assertRaises(ValueError):migration.prepare(source,root/'target.tar','0.3.0-alpha.4')
                self.assertFalse((root/'target.tar').exists())


if __name__ == '__main__':
    unittest.main()
