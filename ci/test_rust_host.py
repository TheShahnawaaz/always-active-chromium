"""Tiny Rust package fixtures; no real toolchain/network/Windows action."""
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import rust_host as rust


class RustHostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.src = self.root / 'src'
        self.target = self.src / 'third_party/rust-toolchain'
        interpreter = self.src / 'third_party/cpython3/host/bin/python3.exe'
        interpreter.parent.mkdir(parents=True)
        interpreter.write_bytes(b'fixture interpreter, never executed')
        self.target.mkdir()
        (self.target / 'bin').mkdir()
        (self.target / 'bin/rustc').write_bytes(b'\x7fELFforeign-host-fixture')
        (self.target / 'foreign-only').write_bytes(b'original marker')
        self.archive = self.root / 'fixture.tar.xz'
        self.calls = []
        self.download = mock.Mock(side_effect=lambda _url, output, **kwargs: shutil.copyfile(self.archive, output))
        self.host_stage = self.host_final = rust.HOST
        self.fail_extensionless = False
        self.make_archive()
        platform = mock.patch.object(rust, 'WINDOWS_HOST', True)
        platform.start()
        self.addCleanup(platform.stop)

    def pe(self):
        data = bytearray(154)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 128)
        data[128:132] = b'PE\0\0'
        struct.pack_into('<H', data, 132, 0x8664)
        struct.pack_into('<H', data, 152, 0x20b)
        return bytes(data)

    def make_archive(self, bad_pe=False, traversal=False):
        files = {'VERSION': f'rustc {rust.RELEASE} {rust.RUST_REVISION} ({rust.PACKAGE_REVISION} chromium)\n'.encode(),
                 'bin/rustc.exe': b'not PE' if bad_pe else self.pe()}
        for crate in ['std', 'core', 'alloc']:
            files[f'lib/rustlib/{rust.HOST}/lib/lib{crate}-abcd.rlib'] = b'fixture rlib'
        if traversal:
            files['../escaped'] = b'not allowed'
        with tarfile.open(self.archive, 'w:xz') as archive:
            for name, contents in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                archive.addfile(member, io.BytesIO(contents))
        self.pin = dict(rust.WIN_OBJECT, sha256sum=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                        size_bytes=self.archive.stat().st_size)

    def runner(self, command, **kwargs):
        self.assertEqual(command[0], self.src / 'third_party/cpython3/host/bin/python3.exe')
        self.assertEqual(command[1:3], ['-c', rust.CHILD_SCRIPT])
        self.assertEqual(kwargs['timeout'], 20)
        self.calls.append(command)
        tool = Path(command[3])
        root = tool.parent.parent
        if command[4:] == ['-vV']:
            host = self.host_final if root == self.target else self.host_stage
            value = {'output': f'rustc {rust.RELEASE}\ncommit-hash: {rust.RUST_REVISION}\nhost: {host}\nrelease: {rust.RELEASE}\n'}
        else:
            self.assertEqual(command[4:], ['--print', 'target-libdir', '--target', rust.HOST])
            self.assertEqual(tool.name, 'rustc')
            value = {'error': {'winerror': 193, 'errno': 8}} if self.fail_extensionless else {'output': str(root / 'lib/rustlib' / rust.HOST / 'lib')}
        return SimpleNamespace(stdout=json.dumps(value), stderr='')

    def ensure(self, **kwargs):
        dependency = {'dep_type': 'gcs', 'bucket': 'chromium-browser-clang',
                      'condition': 'not rust_force_head_revision', 'objects': [copy.deepcopy(self.pin)]}
        with mock.patch.dict(rust.WIN_OBJECT, self.pin, clear=True):
            return rust.ensure_windows_rust(self.src, dependency, self.download, runner=self.runner, **kwargs)

    def failure(self):
        files = list(self.root.glob('.aacc-rust-*/failure.json'))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def test_clean_swap_removes_foreign_host_and_validates_exact_action_path(self):
        records = self.ensure()
        self.assertFalse((self.target / 'bin/rustc').exists())
        self.assertFalse((self.target / 'foreign-only').exists())
        self.assertEqual(records[0]['replaced_headers']['bin/rustc']['prefix_hex'], '7f454c46')
        self.assertEqual(len(self.calls), 4)  # staged and installed, exe + exact extensionless.
        self.assertEqual(self.download.call_args.kwargs, {'expected_sha': self.pin['sha256sum'], 'expected_size': self.pin['size_bytes']})
        self.assertFalse(list(self.root.glob('.aacc-rust-*')))

    def test_resume_revalidates_without_download_or_mutating_any_mtime(self):
        first = self.ensure()
        before = {p.relative_to(self.target): p.stat().st_mtime_ns for p in self.target.rglob('*')}
        self.assertEqual(self.ensure(), first)
        self.assertEqual({p.relative_to(self.target): p.stat().st_mtime_ns for p in self.target.rglob('*')}, before)
        self.download.assert_called_once()
        self.assertEqual(len(self.calls), 6)

    def test_archive_hash_mismatch_preserves_original_before_any_execution(self):
        self.pin['sha256sum'] = '0' * 64
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.code, 'archive_pin_mismatch')
        self.assertEqual(self.calls, [])
        self.assertEqual((self.target / 'foreign-only').read_bytes(), b'original marker')
        self.assertEqual(self.failure()['rollback'], 'original_untouched')

    def test_wrong_staged_host_never_replaces_original(self):
        self.host_stage = 'x86_64-unknown-linux-gnu'
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.code, 'wrong_host')
        self.assertEqual(found.exception.observed_host, self.host_stage)
        self.assertTrue((self.target / 'foreign-only').is_file())
        self.assertEqual(self.failure()['rollback'], 'original_untouched')

    def test_failed_final_validation_rolls_original_directory_back(self):
        self.host_final = 'aarch64-apple-darwin'
        with self.assertRaises(rust.RustHostError):
            self.ensure()
        self.assertEqual((self.target / 'foreign-only').read_bytes(), b'original marker')
        self.assertEqual(self.failure()['rollback'], 'previous_restored')
        self.assertTrue(list(self.root.glob('.aacc-rust-*/failed-installation/bin/rustc.exe')))

    def test_rollback_failure_preserves_both_candidates_and_reports_controlled_code(self):
        self.host_final = 'aarch64-apple-darwin'
        original = Path.rename

        def rename(file, destination):
            if file.name == 'previous' and destination == self.target:
                raise PermissionError(13, 'fixture restore denial')
            return original(file, destination)

        with mock.patch.object(Path, 'rename', rename):
            with self.assertRaises(rust.RustHostError) as found:
                self.ensure()
        self.assertEqual(found.exception.code, 'rollback_failed')
        self.assertEqual(self.failure()['initial_code'], 'wrong_host')
        self.assertEqual(self.failure()['rollback'], 'failed_preserved_in_stage')
        self.assertTrue(list(self.root.glob('.aacc-rust-*/previous/foreign-only')))
        self.assertTrue(list(self.root.glob('.aacc-rust-*/failed-installation/bin/rustc.exe')))

    def test_marker_publication_failure_restores_original(self):
        original = Path.write_text

        def write(file, *args, **kwargs):
            if file.name == rust.MARKER:
                raise PermissionError(13, 'fixture marker denial')
            return original(file, *args, **kwargs)

        with mock.patch.object(Path, 'write_text', write):
            with self.assertRaises(rust.RustHostError) as found:
                self.ensure()
        self.assertEqual(found.exception.code, 'staging_failed')
        self.assertTrue((self.target / 'foreign-only').is_file())
        self.assertEqual(self.failure()['rollback'], 'previous_restored')

    def test_bad_pe_is_rejected_before_tool_execution(self):
        self.make_archive(bad_pe=True)
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.code, 'invalid_pe')
        self.assertEqual(self.calls, [])

    def test_exact_extensionless_child_winerror_is_retained_without_streams(self):
        self.fail_extensionless = True
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.winerror, 193)
        self.assertEqual(found.exception.errno, 8)
        self.assertEqual(found.exception.tool, 'bin/rustc')
        evidence = self.failure()
        self.assertEqual(evidence['winerror'], 193)
        self.assertNotIn('stdout', evidence)
        self.assertNotIn('stderr', evidence)

    def test_tampered_cached_executable_is_never_executed_before_clean_repair(self):
        self.ensure()
        (self.target / 'bin/rustc.exe').write_bytes(b'changed')
        self.calls.clear()
        self.ensure()
        self.assertNotEqual(Path(self.calls[0][3]).parent.parent, self.target)
        self.assertEqual(self.download.call_count, 2)
        self.assertEqual((self.target / 'bin/rustc.exe').read_bytes(), self.pe())

    def test_traversal_archive_cannot_escape_private_stage(self):
        self.make_archive(traversal=True)
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.code, 'unsafe_archive_member')
        self.assertFalse(list(self.root.rglob('escaped')))
        self.assertTrue((self.target / 'foreign-only').is_file())

    def test_symlink_toolchain_root_refuses_before_download(self):
        shutil.rmtree(self.target)
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'kept').write_bytes(b'untouched')
        self.target.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(rust.RustHostError) as found:
            self.ensure()
        self.assertEqual(found.exception.code, 'unsafe_directory')
        self.download.assert_not_called()
        self.assertEqual((outside / 'kept').read_bytes(), b'untouched')

    def test_changed_pin_and_non_windows_platform_refuse_before_download(self):
        dependency = {'dep_type': 'gcs', 'bucket': 'different', 'objects': [self.pin]}
        with self.assertRaises(rust.RustHostError) as found:
            rust.ensure_windows_rust(self.src, dependency, self.download)
        self.assertEqual(found.exception.code, 'dependency_pin_mismatch')
        with mock.patch.object(rust, 'WINDOWS_HOST', False):
            with self.assertRaises(rust.RustHostError) as found:
                self.ensure()
        self.assertEqual(found.exception.code, 'wrong_execution_platform')
        self.download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
