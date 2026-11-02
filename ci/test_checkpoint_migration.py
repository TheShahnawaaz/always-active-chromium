"""Exact native15 seed selection; no source download or external mutation."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import checkpoint
import migrate
from build import fingerprint


class Native15CheckpointSelectionTests(unittest.TestCase):
    def test_latest_complete_exact15_seed_wins_after_incomplete_and_foreign_entries(self):
        for platform in ('mac-arm64', 'win-x64'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                commit = migrate.APPROVED_SEEDS[platform][1]
                old_fp = migrate.APPROVED_FINGERPRINTS[platform]
                def release(label):
                    return {'draft': True, 'tag_name': f'checkpoint-{platform}-{old_fp[:20]}-{label}'}
                entries = [release(name) for name in ('incomplete-newest', 'wrong-fingerprint', 'wrong-source',
                                                       'latest-complete15', 'older-complete15')]
                state = {'repository_commit': commit, 'fingerprint': old_fp}
                manifests = {
                    entries[0]['tag_name']: None,
                    entries[1]['tag_name']: {'state': dict(state, fingerprint='1' * 64)},
                    entries[2]['tag_name']: {'state': dict(state, repository_commit='f' * 40)},
                    entries[3]['tag_name']: {'state': state},
                    entries[4]['tag_name']: {'state': state},
                }
                proof = SimpleNamespace(old_fingerprint=old_fp)
                with mock.patch.object(checkpoint, 'root_path', return_value=root), \
                        mock.patch.object(checkpoint, 'releases', return_value=entries), \
                        mock.patch.object(checkpoint, 'ready_manifest', side_effect=lambda r: (manifests[r['tag_name']], {})), \
                        mock.patch.object(checkpoint, 'restore_candidate', return_value=123) as restore, \
                        mock.patch.object(checkpoint, 'output') as output, \
                        mock.patch.object(migrate, 'prove_seed', return_value=proof) as prove, \
                        mock.patch.object(migrate, 'migrate_source', return_value={'fingerprint': fingerprint(platform)}) as apply:
                    checkpoint.restore(platform, migrate_native=True)
                self.assertEqual(restore.call_args.args[1]['tag_name'], entries[3]['tag_name'])
                self.assertEqual(prove.call_count, 1)
                apply.assert_called_once_with(root, proof, 123)
                self.assertIn(mock.call('native_migration_from', old_fp), output.call_args_list)

    def test_unready_native15_cannot_fall_back_to_native14_or_cold_source(self):
        platform = 'mac-arm64'
        with tempfile.TemporaryDirectory() as temporary:
            entries = [{'draft': True, 'tag_name': 'checkpoint-mac-arm64-unready15'},
                       {'draft': True, 'tag_name': 'checkpoint-mac-arm64-old14'}]
            def manifest(release):
                if release is entries[0]:
                    return None, {}
                return {'state': {'repository_commit': '67dea4dbe7e2df2f21394efbe8f0346fee3af2f4',
                                  'fingerprint': '7e08baa8b9ce4a8216f86aaa745fa3d028ff58ccd5e58baca3c78b775730142c'}}, {}
            with mock.patch.object(checkpoint, 'root_path', return_value=Path(temporary)), \
                    mock.patch.object(checkpoint, 'releases', return_value=entries), \
                    mock.patch.object(checkpoint, 'ready_manifest', side_effect=manifest), \
                    mock.patch.object(checkpoint, 'restore_candidate') as restore, \
                    mock.patch.object(checkpoint, 'output') as output:
                with self.assertRaisesRegex(RuntimeError, 'No complete approved seed'):
                    checkpoint.restore(platform, migrate_native=True)
            restore.assert_not_called()
            output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
