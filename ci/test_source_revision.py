"""Offline exact upstream Python generators on tiny source snapshots, not a build."""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import build
import source_revision as revision


class SourceRevisionTests(unittest.TestCase):
    def fixture(self, temporary):
        root = Path(temporary).resolve() / 'src'
        root.mkdir()
        data = json.loads(revision.DATA.read_text())
        snapshot = base64.b64decode(data['test_sources_zip_base64'], validate=True)
        self.assertEqual(hashlib.sha256(snapshot).hexdigest(), data['test_sources_zip_sha256'])
        with zipfile.ZipFile(io.BytesIO(snapshot)) as files:
            self.assertEqual(set(files.namelist()), revision.SOURCE_PATHS)
            for name in files.namelist():
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(files.read(name))
        pins = json.loads((Path(__file__).parent / 'pins.json').read_text())
        return root, pins, data

    def test_authentic_commit_generates_exact_standard_files_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, data = self.fixture(temporary)
            unchanged_pins = copy.deepcopy(pins)
            dummy = root / 'build/util/LASTCHANGE.dummy'
            dummy_before = (dummy.read_bytes(), dummy.stat().st_mtime_ns)
            result = revision.ensure_source_revision(root, pins)
            self.assertEqual(result['revision'], pins['revision'])
            self.assertEqual(result['commit_position'], 'refs/branch-heads/8078@{#1705}')
            self.assertEqual(result['committer_epoch'], 1793220128)
            self.assertEqual(result['year'], 2026)
            self.assertEqual(result['metadata_gn_args'], {'use_dummy_lastchange': False})
            self.assertFalse(result['is_official_build']);self.assertFalse(result['is_chrome_branded'])
            lastchange = root / 'build/util/LASTCHANGE'
            self.assertEqual(lastchange.read_text(), 'LASTCHANGE=' + pins['revision'] + '-refs/branch-heads/8078@{#1705}\nLASTCHANGE_YEAR=2026\n')
            self.assertEqual((root / 'build/util/LASTCHANGE.committime').read_bytes(), b'1793220128')
            stamps = {entry['path']: (root / entry['path']).stat().st_mtime_ns for entry in result['outputs']}
            self.assertEqual(revision.ensure_source_revision(root, pins), result)
            for name, stamp in stamps.items():self.assertEqual((root / name).stat().st_mtime_ns, stamp)
            self.assertEqual((dummy.read_bytes(), dummy.stat().st_mtime_ns), dummy_before)
            self.assertEqual(pins, unchanged_pins)

    def test_real_pinned_generators_emit_exact_cdp_revision_without_official_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, _data = self.fixture(temporary)
            revision.ensure_source_revision(root, pins)
            output = Path(temporary).resolve() / 'generated';output.mkdir()
            script = root / 'build/util/version.py'
            cdp = output / 'chromium_git_revision.h'
            base = output / 'version_info_values.h'
            environment = dict(os.environ)
            environment.pop('CHROME_BUILD_TYPE', None)
            subprocess.run([sys.executable, str(script), '-e', "LASTCHANGE=LASTCHANGE[:LASTCHANGE.find('-')]",
                '-f', str(root / 'build/util/LASTCHANGE'), str(root / 'build/util/chromium_git_revision.h.in'), str(cdp)],
                check=True, capture_output=True, timeout=10, env=environment)
            subprocess.run([sys.executable, str(script), '-f', str(root / 'chrome/VERSION'),
                '-f', str(root / 'chrome/app/theme/chromium/BRANDING'), '-f', str(root / 'build/util/LASTCHANGE'),
                str(root / 'base/version_info/version_info_values.h.version'), str(base)],
                check=True, capture_output=True, timeout=10, env=environment)
            self.assertIn('#define CHROMIUM_GIT_REVISION "@' + pins['revision'] + '"', cdp.read_text())
            self.assertIn('#define IS_OFFICIAL_BUILD 0', base.read_text())
            self.assertIn('#define LAST_CHANGE "' + pins['revision'] + '-refs/branch-heads/8078@{#1705}"', base.read_text())
            self.assertIn('#define PRODUCT_VERSION "156.0.8078.80"', base.read_text())

    def test_production_gn_selects_authenticated_metadata_without_changing_compiler_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, _data = self.fixture(temporary)
            receipt = revision.ensure_source_revision(root, pins)
            for platform in ['mac-arm64', 'win-x64']:
                original = build.rendered_gn_args(platform)
                self.assertEqual(build.rendered_gn_args(platform, receipt),
                                 original + 'use_dummy_lastchange = false\n')
                for patch in [{'revision': '0' * 40}, {'status': 'failed'},
                              {'metadata_gn_args': {'use_dummy_lastchange': True}},
                              {'metadata_gn_args': {'is_official_build': True}}]:
                    with self.subTest(platform=platform, patch=patch), self.assertRaises(RuntimeError):
                        build.rendered_gn_args(platform, dict(receipt, **patch))

    def test_wrong_pins_or_corrupt_commit_cannot_write_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, data = self.fixture(temporary)
            for patch in [{'revision': '0' * 40}, {'version': '156.0.8078.81'}, {'source_sha256': '0' * 64}]:
                with self.subTest(patch=patch), self.assertRaises(revision.SourceRevisionError):
                    revision.ensure_source_revision(root, dict(pins, **patch))
            raw = bytearray(base64.b64decode(data['raw_commit_base64']));raw[-2] ^= 1
            data['raw_commit_base64'] = base64.b64encode(raw).decode()
            metadata = Path(temporary) / 'bad.json';metadata.write_text(json.dumps(data))
            with self.assertRaisesRegex(revision.SourceRevisionError, 'commit_object_hash_mismatch'):
                revision.ensure_source_revision(root, pins, metadata)
            self.assertFalse((root / 'build/util/LASTCHANGE').exists())

    def test_changed_source_version_or_generator_is_rejected_before_any_write(self):
        for name in ['chrome/VERSION', 'build/util/version.py', 'build/util/LASTCHANGE.dummy']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root, pins, _data = self.fixture(temporary)
                file = root / name;file.write_bytes(file.read_bytes() + b'changed source\n')
                with self.assertRaisesRegex(revision.SourceRevisionError, 'pinned_source_digest_mismatch'):
                    revision.ensure_source_revision(root, pins)
                self.assertFalse((root / 'build/util/LASTCHANGE').exists())

    def test_output_symlink_refuses_without_modifying_foreign_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, _data = self.fixture(temporary)
            foreign = Path(temporary) / 'foreign';foreign.write_bytes(b'keep')
            try:
                (root / 'build/util/LASTCHANGE.committime').symlink_to(foreign)
            except OSError:
                self.skipTest('Symlink creation unavailable on this host')
            with self.assertRaisesRegex(revision.SourceRevisionError, 'unsafe_source_file'):
                revision.ensure_source_revision(root, pins)
            self.assertFalse((root / 'build/util/LASTCHANGE').exists())
            self.assertEqual(foreign.read_bytes(), b'keep')

    def test_interrupted_atomic_pair_is_safely_resumed_without_retimestamping_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, pins, _data = self.fixture(temporary)
            replace = revision.os.replace
            def interrupt(source, destination):
                if Path(destination).name == 'LASTCHANGE.committime':raise OSError('interrupted fixture')
                return replace(source, destination)
            with mock.patch.object(revision.os, 'replace', side_effect=interrupt):
                with self.assertRaisesRegex(revision.SourceRevisionError, 'atomic_metadata_write_failed'):
                    revision.ensure_source_revision(root, pins)
            first = root / 'build/util/LASTCHANGE';stamp = first.stat().st_mtime_ns
            self.assertEqual(list((root / 'build/util').glob('*.tmp')), [])
            revision.ensure_source_revision(root, pins)
            self.assertEqual(first.stat().st_mtime_ns, stamp)
            self.assertEqual((root / 'build/util/LASTCHANGE.committime').read_bytes(), b'1793220128')


if __name__ == '__main__':
    unittest.main()
