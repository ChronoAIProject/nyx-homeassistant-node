"""A Supervisor restore can make all persisted files root-owned."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'app'))
from run import prepare_state


class StateOwnershipTests(unittest.TestCase):
    def test_repairs_every_nested_file_without_touching_options_or_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';nested=state/'rules'/'example'/'3'
            nested.mkdir(parents=True)
            database=nested/'relay-ingest.sqlite3';database.write_bytes(b'persisted history')
            registry=state/'monitoring.sqlite3';registry.write_bytes(b'persisted registry')
            options=root/'options.json';options.write_bytes(b'private options');options.chmod(0o600)
            with patch('run.os.chown') as chown:prepare_state(state)
            targets={call.args[0] for call in chown.call_args_list}
            self.assertEqual(targets,{state,state/'rules',state/'rules'/'example',nested,database,registry})
            self.assertNotIn(options,targets)
            self.assertEqual(database.read_bytes(),b'persisted history')
            self.assertEqual(registry.read_bytes(),b'persisted registry')
            self.assertEqual(database.stat().st_mode & 0o777,0o600)
            self.assertEqual(nested.stat().st_mode & 0o777,0o700)

    def test_rejects_links_before_changing_any_ownership(self):
        for kind in ('symbolic','hard'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);state=root/'state';state.mkdir()
                outside=root/'outside';outside.write_bytes(b'never change')
                if kind=='symbolic':(state/'link').symlink_to(outside)
                else:os.link(outside,state/'link')
                with patch('run.os.chown') as chown:
                    with self.assertRaises(ValueError):prepare_state(state)
                    chown.assert_not_called()
                self.assertEqual(outside.read_bytes(),b'never change')


if __name__=='__main__':unittest.main()
