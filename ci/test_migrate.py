"""Bounded migration rejection, transaction, timestamp and incremental-build tests."""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import build
import migrate


def make_bundle(originals, outputs):
    pieces = []
    records = []
    for relative in sorted(outputs):
        pieces.append(f'diff --git a/{relative} b/{relative}\n')
        pieces.extend(difflib.unified_diff(originals[relative].decode().splitlines(True),
            outputs[relative].decode().splitlines(True), fromfile='a/' + relative, tofile='b/' + relative))
        records.append({'path': relative, 'upstream_sha256': migrate.digest(originals[relative]),
                        'patched_sha256': migrate.digest(outputs[relative])})
    patch = ''.join(pieces).encode()
    provenance = json.dumps({'schema_version': 1, 'upstream_tag': build.PINS['version'],
        'upstream_revision': build.PINS['revision'], 'patch': 'patches/test.patch',
        'patch_sha256': migrate.digest(patch), 'files': records}).encode()
    return migrate.bundle(provenance, patch, 'Fixture'), provenance, patch


class MigrationTests(unittest.TestCase):
    platform = 'win-x64' if os.name == 'nt' else 'mac-arm64'

    def setup_tree(self, root, second_change=False, partial=False):
        originals = {'one.cc': b'original one\n', 'two.h': b'original two\n'}
        old_outputs = {'one.cc': b'old one\n', 'two.h': b'stable patched two\n'}
        new_outputs = {'one.cc': b'new one\n', 'two.h': b'new two\n' if second_change else old_outputs['two.h']}
        old, provenance, patch = make_bundle(originals, old_outputs)
        new, _, _ = make_bundle(originals, new_outputs)
        old_ref, old_commit = migrate.APPROVED_SEEDS[self.platform]
        proof = migrate.Proof(old, new, '1' * 64, '2' * 64, old_commit, old_ref,
            f'checkpoint-{self.platform}-' + '1' * 20 + '-fixture', self.platform, 'a' * 40)
        source = root / 'src'
        source.mkdir()
        for relative, data in old_outputs.items():
            file = source / relative
            file.write_bytes(originals[relative] if partial and relative == 'one.cc' else data)
            os.utime(file, ns=(1712345678123456000, 1712345678123456000))
        out = source / 'out/AlwaysActive'
        out.mkdir(parents=True)
        (out / 'args.gn').write_text(build.rendered_gn_args(self.platform), encoding='utf-8')
        state = {'schema': 1, 'platform': self.platform, 'root': str(root), 'version': build.PINS['version'],
            'revision': build.PINS['revision'], 'fingerprint': proof.old_fingerprint,
            'repository_commit': old_commit, 'phase': 'source-ready' if partial else 'build-ready',
            'status': 'bootstrap-incomplete' if partial else 'pending'}
        (root / 'state.json').write_text(json.dumps(state))
        return proof, originals, old_outputs, new_outputs, provenance, patch

    def verify_outputs(self, root, expected):
        for name, data in expected.items():
            self.assertEqual((root / 'src' / name).read_bytes(), data)

    def test_unchanged_mtime_and_strict_newer_changed_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, expected, _, _ = self.setup_tree(root)
            unchanged = (root / 'src/two.h').stat().st_mtime_ns
            latest_output = time.time_ns()
            state = migrate.migrate_source(root, proof, latest_output,
                verifier=lambda: self.verify_outputs(root, expected))
            self.assertEqual((root / 'src/two.h').stat().st_mtime_ns, unchanged)
            self.assertGreaterEqual((root / 'src/one.cc').stat().st_mtime_ns - latest_output, 100_000_000)
            self.assertEqual(state['fingerprint'], proof.new_fingerprint)
            self.assertEqual((state['phase'], state['status']), ('source-ready', 'bootstrap-incomplete'))

    def test_unknown_second_file_edit_rejects_before_first_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, old, _, _, _ = self.setup_tree(root, second_change=True)
            first_ns = (root / 'src/one.cc').stat().st_mtime_ns
            (root / 'src/two.h').write_bytes(b'foreign edit\n')
            with self.assertRaisesRegex(RuntimeError, 'Unknown native source edit'):
                migrate.migrate_source(root, proof, 0, verifier=lambda: None)
            self.assertEqual((root / 'src/one.cc').read_bytes(), old['one.cc'])
            self.assertEqual((root / 'src/one.cc').stat().st_mtime_ns, first_ns)

    def test_write_failure_rolls_back_bytes_mtimes_and_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, old, _, _, _ = self.setup_tree(root, second_change=True)
            state_before = (root / 'state.json').read_bytes()
            times = {name: (root / 'src' / name).stat().st_mtime_ns for name in old}
            calls = 0
            def fail_second(*arguments):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated second rename failure')
                migrate.replace_file(*arguments)
            with self.assertRaisesRegex(OSError, 'simulated second'):
                migrate.migrate_source(root, proof, 0, replacer=fail_second, verifier=lambda: None)
            self.verify_outputs(root, old)
            self.assertEqual((root / 'state.json').read_bytes(), state_before)
            self.assertEqual({name: (root / 'src' / name).stat().st_mtime_ns for name in old}, times)

    def test_verification_failure_rolls_back_all_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, old, _, _, _ = self.setup_tree(root, second_change=True)
            with self.assertRaisesRegex(RuntimeError, 'verify failed'):
                migrate.migrate_source(root, proof, 0,
                    verifier=lambda: (_ for _ in ()).throw(RuntimeError('verify failed')))
            self.verify_outputs(root, old)
            self.assertEqual(json.loads((root / 'state.json').read_text())['fingerprint'], proof.old_fingerprint)

    def test_known_upstream_partial_state_is_completed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, expected, _, _ = self.setup_tree(root, partial=True)
            migrate.migrate_source(root, proof, 0, verifier=lambda: self.verify_outputs(root, expected))
            self.verify_outputs(root, expected)

    def test_strict_source_only_seed_without_output_tree_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, expected, _, _ = self.setup_tree(root, partial=True)
            shutil.rmtree(root / 'src/out/AlwaysActive')
            migrated = migrate.migrate_source(root, proof, 0,
                verifier=lambda: self.verify_outputs(root, expected))
            self.assertEqual(migrated['fingerprint'], proof.new_fingerprint)
            self.assertFalse((root / 'src/out/AlwaysActive').exists())

    def test_missing_args_with_existing_outputs_rejects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, old, _, _, _ = self.setup_tree(root, partial=True)
            out = root / 'src/out/AlwaysActive'
            (out / 'args.gn').unlink()
            (out / 'retained.o').write_bytes(b'real output tree')
            with self.assertRaisesRegex(RuntimeError, 'GN arguments'):
                migrate.migrate_source(root, proof, 0, verifier=lambda: None)
            self.verify_outputs(root, {'one.cc': b'original one\n', 'two.h': old['two.h']})

    def test_source_only_seed_rejects_nonzero_restored_output_timestamp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, _, _, _ = self.setup_tree(root, partial=True)
            shutil.rmtree(root / 'src/out/AlwaysActive')
            with self.assertRaisesRegex(RuntimeError, 'strict source-only'):
                migrate.migrate_source(root, proof, 1, verifier=lambda: None)

    def test_args_change_and_future_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, old, _, _, _ = self.setup_tree(root)
            args = root / 'src/out/AlwaysActive/args.gn'
            args.write_text('is_debug = true\n')
            with self.assertRaisesRegex(RuntimeError, 'GN arguments'):
                migrate.migrate_source(root, proof, 0, verifier=lambda: None)
            args.write_text(build.rendered_gn_args(self.platform))
            with self.assertRaisesRegex(RuntimeError, 'future compiler-output'):
                migrate.migrate_source(root, proof, time.time_ns() + 600_000_000_000, verifier=lambda: None)
            self.verify_outputs(root, old)

    def test_config_paths_are_forbidden(self):
        for name in ('build/config/test.h', 'DEPS', 'chrome/BUILD.gn', 'third_party/llvm-build/bin/test.cc'):
            with self.assertRaises(RuntimeError):
                migrate.native_path(name)

    def test_old_pins_fingerprint_and_allowlist_are_independent_proofs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, _, provenance, patch = self.setup_tree(root)
            state = json.loads((root / 'state.json').read_text())
            state['repository_commit'] = 'f' * 40
            with self.assertRaisesRegex(RuntimeError, 'allowlist'):
                migrate.prove_seed(state, self.platform, root, proof.seed_tag,
                    fetch_blob=lambda *args: b'', verify_ref=lambda *args: None)
            state['repository_commit'] = proof.old_commit
            with self.assertRaisesRegex(RuntimeError, 'PINS/configuration'):
                migrate.prove_seed(state, self.platform, root, proof.seed_tag,
                    fetch_blob=lambda *args: b'wrong configuration', verify_ref=lambda *args: None)
            blobs = {'ci/pins.json': (build.PROJECT / 'ci/pins.json').read_bytes(),
                'native/provenance.json': provenance, 'native/apply_patches.py': b'raise RuntimeError("must never execute old Python")',
                'patches/test.patch': patch}
            with self.assertRaisesRegex(RuntimeError, 'independent Git-blob proof'):
                migrate.prove_seed(state, self.platform, root, proof.seed_tag,
                    fetch_blob=lambda _commit, path, _limit: blobs[path], verify_ref=lambda *args: None)

    def test_prior_native14_source_refs_are_not_fallback_seeds(self):
        for platform, old_commit in [('mac-arm64', '67dea4dbe7e2df2f21394efbe8f0346fee3af2f4'),
                                     ('win-x64', 'f2f4e1335f61d63f7b9abc4d44dbcfa5e0a9034d')]:
            with self.subTest(platform=platform), self.assertRaisesRegex(RuntimeError, 'allowlist'):
                migrate.prove_seed({'repository_commit': old_commit}, platform, Path('/fixture'),
                    'checkpoint-old', fetch_blob=lambda *args: self.fail('unapproved metadata fetch'),
                    verify_ref=lambda *args: self.fail('unapproved source ref'))

    @unittest.skipUnless(shutil.which('ninja'), 'Ninja not available')
    def test_ninja_rebuilds_only_changed_source_then_is_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof, _, _, expected, _, _ = self.setup_tree(root)
            out = root / 'src/out/AlwaysActive'
            (out / 'copy.py').write_text('from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes())\n')
            (out / 'build.ninja').write_text(f'rule copy\n  command = "{sys.executable}" copy.py $in $out\n'
                'build one.o: copy ../../one.cc\nbuild two.o: copy ../../two.h\ndefault one.o two.o\n')
            subprocess.run(['ninja', '-C', str(out)], check=True, capture_output=True)
            quiet = subprocess.check_output(['ninja', '-C', str(out)], text=True)
            self.assertIn('no work to do', quiet)
            other_mtime = (out / 'two.o').stat().st_mtime_ns
            maximum = max((out / name).stat().st_mtime_ns for name in ('one.o', 'two.o'))
            time.sleep(0.15)
            migrate.migrate_source(root, proof, maximum, verifier=lambda: self.verify_outputs(root, expected))
            rebuilt = subprocess.check_output(['ninja', '-C', str(out)], text=True)
            self.assertIn('one.o', rebuilt)
            self.assertNotIn('two.o', rebuilt)
            self.assertEqual((out / 'two.o').stat().st_mtime_ns, other_mtime)
            self.assertIn('no work to do', subprocess.check_output(['ninja', '-C', str(out)], text=True))

    def test_selected_real_seed_to_current_native_sources(self):
        for platform in ('mac-arm64', 'win-x64'):
            with self.subTest(platform=platform):
                self.check_selected_real_seed_to_current_native_sources(platform)

    def check_selected_real_seed_to_current_native_sources(self, platform):
        cache = build.PROJECT / 'native/.cache/upstream'
        if not cache.is_dir():
            self.skipTest('Selected-file authoring snapshot is local only; no full source download')
        old_ref, old_commit = migrate.APPROVED_SEEDS[platform]
        def git_blob(commit, relative, _limit):
            return subprocess.check_output(['git', '-C', str(build.PROJECT), 'show', commit + ':' + relative])
        old_provenance = git_blob(old_commit, 'native/provenance.json', 0)
        relative = json.loads(old_provenance)['patch']
        old_patch = git_blob(old_commit, relative, 0)
        old_pins = git_blob(old_commit, 'ci/pins.json', 0)
        if old_pins != (build.PROJECT / 'ci/pins.json').read_bytes():
            self.skipTest('The approved seed does not have the current build configuration')
        old_fp = migrate.fingerprint_blobs(platform, old_pins, old_provenance,
            git_blob(old_commit, 'native/apply_patches.py', 0), old_patch, relative)
        self.assertEqual(old_fp, migrate.APPROVED_FINGERPRINTS[platform])
        current = json.loads((build.PROJECT / 'native/provenance.json').read_text())
        old_manifest = json.loads(old_provenance)
        union = {item['path'] for item in current['files']} | {item['path'] for item in old_manifest['files']}
        if not all((cache / path).is_file() for path in union):
            self.skipTest('Selected-file authoring snapshot is incomplete')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'src'
            for path in union:
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((cache / path).read_bytes())
            old = migrate.bundle(old_provenance, old_patch, 'Old real seed')
            for path, record in old['records'].items():
                target = source / path
                self.assertEqual(migrate.digest(target.read_bytes()), record['upstream_sha256'])
                target.write_bytes(migrate.CURRENT.transform(target.read_bytes(), old['hunks'][path]))
            for path in union:
                os.utime(source / path, ns=(1712345678123456000, 1712345678123456000))
            (source / 'chrome/VERSION').write_text('MAJOR=156\nMINOR=0\nBUILD=8078\nPATCH=80\n')
            out = source / 'out/AlwaysActive'
            out.mkdir(parents=True)
            (out / 'args.gn').write_text(build.rendered_gn_args(platform))
            object_file = out / 'seed.o'
            object_file.write_bytes(b'unchanged seed object')
            object_mtime = object_file.stat().st_mtime_ns
            state = {'schema': 1, 'platform': platform, 'root': str(root), 'version': build.PINS['version'],
                'revision': build.PINS['revision'], 'repository_commit': old_commit, 'fingerprint': old_fp,
                'phase': 'build-ready', 'status': 'failed'}
            (root / 'state.json').write_text(json.dumps(state))
            tag = f'checkpoint-{platform}-{old_fp[:20]}-real-fixture'
            proof = migrate.prove_seed(state, platform, root, tag, fetch_blob=git_blob, verify_ref=lambda *args: None)
            before = {path: ((source / path).read_bytes(), (source / path).stat().st_mtime_ns) for path in union}
            migrated = migrate.migrate_source(root, proof, object_mtime)
            for path, record in proof.new['records'].items():
                self.assertEqual(migrate.digest((source / path).read_bytes()), record['patched_sha256'])
                if before[path][0] == (source / path).read_bytes():
                    self.assertEqual((source / path).stat().st_mtime_ns, before[path][1])
            self.assertEqual(object_file.read_bytes(), b'unchanged seed object')
            self.assertEqual(object_file.stat().st_mtime_ns, object_mtime)
            self.assertEqual(migrated['fingerprint'], build.fingerprint(platform))
            self.assertEqual(migrated['native_migrations'][-1]['changed_paths'],
                             ['third_party/blink/renderer/core/dom/document.cc'])


if __name__ == '__main__':
    unittest.main()
