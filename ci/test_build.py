"""Small archive-hydration regressions; no Chromium checkout or compilation."""
import contextlib
from pathlib import Path
import json
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

import build
from build import unpack


class HydrationTests(unittest.TestCase):
    def test_cipd_readonly_executable_can_replace_existing_host_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / 'payload'
            destination.mkdir()
            executable = destination / 'gn'
            executable.write_bytes(b'wrong-host executable')
            executable.chmod(0o500)
            archive = root / 'package.zip'
            member = zipfile.ZipInfo('gn')
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o500) << 16
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr(member, b'correct-host executable')
            unpack(archive, destination)
            self.assertEqual(executable.read_bytes(), b'correct-host executable')
            if os.name != 'nt':
                self.assertEqual(executable.stat().st_mode & 0o777, 0o500)
            # Leave the temporary-directory cleanup writable on Windows too.
            executable.chmod(0o700)

    def test_package_symlink_cannot_escape_dependency_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'package.zip'
            member = zipfile.ZipInfo('bin/python3')
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr(member, '../../outside')
            with self.assertRaisesRegex(RuntimeError, 'Unsafe package symlink'):
                unpack(archive, root / 'payload')
            self.assertFalse((root / 'outside').exists())


class SourceRetentionTests(unittest.TestCase):
    def prepare_mocks(self, root, source_error=None, check_error=None, hydration_error=None):
        def extract(_archive, destination, strip, source_archive=False):
            if source_error:
                raise source_error
            self.assertTrue(source_archive)
            destination.mkdir(parents=True)
            return {'tool': 'validated source fixture'}

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(build, 'root_path', return_value=root))
        stack.enter_context(mock.patch.object(build.shutil, 'disk_usage',
            return_value=shutil._ntuple_diskusage(200 << 30, 50 << 30, 150 << 30)))
        fetch = stack.enter_context(mock.patch.object(build, 'fetch'))
        # A successfully fetched archive is normally removed after extraction.
        fetch.side_effect = lambda _url, archive, *_pins: archive.touch()
        stack.enter_context(mock.patch.object(build, 'unpack', side_effect=extract))
        stack.enter_context(mock.patch.object(build, 'set_build_env'))
        check = stack.enter_context(mock.patch.object(build, 'run', side_effect=check_error))
        hydration = stack.enter_context(mock.patch.object(build, 'hydrate', side_effect=hydration_error))
        emitted = stack.enter_context(mock.patch.object(build, 'output'))
        return check, hydration, emitted

    def test_hydration_failure_retains_only_validated_source_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            check, hydration, emitted = self.prepare_mocks(root, hydration_error=RuntimeError('missing build tool'))
            with self.assertRaisesRegex(RuntimeError, 'missing build tool'):
                build.prepare('mac-arm64')
            self.assertIn('--check', check.call_args.args[0])
            hydration.assert_called_once()
            emitted.assert_called_once_with('source_checkpointable', 'true')
            state = json.loads((root / 'state.json').read_text())
            self.assertEqual(state['phase'], 'source-ready')
            self.assertEqual(state['status'], 'bootstrap-incomplete')

    def test_native_source_validation_failure_cannot_be_checkpointed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, hydration, emitted = self.prepare_mocks(root, check_error=RuntimeError('wrong source hash'))
            with self.assertRaisesRegex(RuntimeError, 'wrong source hash'):
                build.prepare('mac-arm64')
            hydration.assert_not_called()
            emitted.assert_not_called()
            self.assertFalse((root / 'state.json').exists())

    def test_partial_source_extraction_cannot_be_checkpointed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            check, hydration, emitted = self.prepare_mocks(root, source_error=RuntimeError('archive extraction failed'))
            with self.assertRaisesRegex(RuntimeError, 'archive extraction failed'):
                build.prepare('mac-arm64')
            check.assert_not_called()
            hydration.assert_not_called()
            emitted.assert_not_called()
            self.assertFalse((root / 'state.json').exists())


if __name__ == '__main__':
    unittest.main()
