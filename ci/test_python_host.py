"""Tiny mocked package/runtime guards. No real package, GN or interpreter runs."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import python_host as host


class PythonHostTests(unittest.TestCase):
    def fixture(self, temporary, extra=None):
        src = Path(temporary) / 'src'
        (src / 'third_party/cpython3/host/bin').mkdir(parents=True)
        binary = bytearray(128)
        binary[:2] = b'MZ';struct.pack_into('<I', binary, 60, 64)
        binary[64:68] = b'PE\0\0';struct.pack_into('<H', binary, 68, 0x8664)
        struct.pack_into('<H', binary, 88, 0x20b)
        files = {'bin/' + name: bytes(binary) for name in ['python3.exe', 'python.exe', 'python311.dll', 'python3.dll']}
        files['bin/Lib/os.py'] = b'# pinned stdlib fixture\n'
        files.update(extra or {})
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as package:
            for name, data in files.items():package.writestr(name, data)
        payload = archive.getvalue()
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(host, 'WINDOWS_HOST', True))
        stack.enter_context(mock.patch.object(host, 'SHA256', hashlib.sha256(payload).hexdigest()))
        stack.enter_context(mock.patch.object(host, 'SIZE', len(payload)))
        self.addCleanup(stack.close)
        dependency = {'packages': [{'package': 'infra/3pp/tools/cpython3/${{platform}}', 'version': host.VERSION}],
                      'condition': 'non_git_source', 'dep_type': 'cipd'}
        download = mock.Mock(side_effect=lambda _url, destination, **_kwargs: destination.write_bytes(payload))
        def runtime(command, **kwargs):
            self.assertEqual(command[1:4], ['-I', '-B', '-c'])
            self.assertTrue(kwargs['check'])
            binary = Path(command[0])
            return SimpleNamespace(stdout=json.dumps({'version': [3, 11, 9], 'platform': 'win32',
                'implementation': 'cpython', 'pointer_bits': 64,
                'executable': str(binary.parent / 'python3.exe'), 'prefix': str(binary.parent)}), stderr='')
        return src, dependency, download, runtime

    def test_clean_replacement_retains_prior_headers_and_unrelated_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            target = src / 'third_party/cpython3/host'
            (target / 'bin/python3').write_bytes(b'\x7fELF synthetic fixture only')
            output = src / 'out/AlwaysActive/progress.o';output.parent.mkdir(parents=True);output.write_bytes(b'compiler progress')
            stamp = output.stat().st_mtime_ns
            records = host.ensure_windows_python(src, dependency, download, runner=runtime)
            self.assertFalse((target / 'bin/python3').exists())
            self.assertTrue(records[0]['replaced_headers']['bin/python3']['prefix_hex'].startswith('7f454c46'))
            self.assertEqual(output.stat().st_mtime_ns, stamp)
            self.assertEqual(output.read_bytes(), b'compiler progress')
            self.assertEqual(records[0]['validation']['runtime_paths_verified'], ['python3.exe', 'python3'])
            self.assertIn(host.INSTANCE, download.call_args.args[0])

    def test_validated_reuse_keeps_payload_mtimes_and_accepts_normal_stdlib_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            first = host.ensure_windows_python(src, dependency, download, runner=runtime)
            target = src / 'third_party/cpython3/host'
            stamps = {file: file.stat().st_mtime_ns for file in target.rglob('*') if file.is_file()}
            cache = target / 'bin/Lib/__pycache__/os.cpython-311.pyc'
            cache.parent.mkdir();cache.write_bytes(b'ordinary cached bytecode fixture')
            self.assertEqual(host.ensure_windows_python(src, dependency, download, runner=runtime), first)
            self.assertEqual(download.call_count, 1)
            for file, stamp in stamps.items():self.assertEqual(file.stat().st_mtime_ns, stamp)

    def test_unexpected_dependency_rejects_before_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            dependency['packages'][0]['version'] = 'foreign'
            with self.assertRaisesRegex(host.PythonHostError, 'unexpected_dependency_pin'):
                host.ensure_windows_python(src, dependency, download, runner=runtime)
            download.assert_not_called()

    def test_corrupt_download_preserves_original_and_failure_headers(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            original = src / 'third_party/cpython3/host/bin/python3';original.write_bytes(b'original')
            download.side_effect = lambda _url, destination, **_kwargs: destination.write_bytes(b'wrong archive')
            with self.assertRaisesRegex(host.PythonHostError, 'archive_pin_mismatch'):
                host.ensure_windows_python(src, dependency, download, runner=runtime)
            self.assertEqual(original.read_bytes(), b'original')
            failure = json.loads(next(src.parent.glob('.aacc-python-*/failure.json')).read_text())
            self.assertEqual(failure['rollback'], 'original_untouched')
            self.assertEqual(failure['original_headers']['bin/python3']['size'], 8)

    def test_unsafe_zip_member_never_changes_original_root(self):
        for name in ['../outside', 'bin/foreign:stream', 'bin/trailing.']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                src, dependency, download, runtime = self.fixture(temporary, {name: b'foreign'})
                with self.assertRaisesRegex(host.PythonHostError, 'unsafe_zip_member'):
                    host.ensure_windows_python(src, dependency, download, runner=runtime)
                self.assertFalse((src / 'third_party/cpython3/host/bin/python3.exe').exists())

    def test_wrong_runtime_identity_cannot_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            def wrong(command, **kwargs):
                result = runtime(command, **kwargs);value = json.loads(result.stdout);value['platform'] = 'linux'
                return SimpleNamespace(stdout=json.dumps(value), stderr='')
            with self.assertRaisesRegex(host.PythonHostError, 'interpreter_identity_mismatch'):
                host.ensure_windows_python(src, dependency, download, runner=wrong)
            self.assertFalse((src / 'third_party/cpython3/host/bin/python3.exe').exists())

    def test_invalid_required_host_dll_rejects_even_a_hash_matching_fixture_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary, {'bin/python311.dll': b'foreign library'})
            with self.assertRaisesRegex(host.PythonHostError, 'invalid_pe'):
                host.ensure_windows_python(src, dependency, download, runner=runtime)
            self.assertFalse((src / 'third_party/cpython3/host/bin/python3.exe').exists())

    def test_final_extensionless_launch_failure_rolls_back_prior_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            original = src / 'third_party/cpython3/host/bin/python3';original.write_bytes(b'prior bytes')
            def fail(command, **kwargs):
                if Path(command[0]) == original:
                    raise subprocess.CalledProcessError(9, ['private command'])
                return runtime(command, **kwargs)
            with self.assertRaises(host.PythonHostError) as caught:
                host.ensure_windows_python(src, dependency, download, runner=fail)
            self.assertEqual(caught.exception.exit_code, 9)
            self.assertEqual(original.read_bytes(), b'prior bytes')
            failure = json.loads(next(src.parent.glob('.aacc-python-*/failure.json')).read_text())
            self.assertEqual(failure['rollback'], 'previous_restored')
            self.assertNotIn('private', json.dumps(failure))

    def test_changed_package_file_or_new_foreign_binary_forces_clean_reinstall(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, dependency, download, runtime = self.fixture(temporary)
            host.ensure_windows_python(src, dependency, download, runner=runtime)
            target = src / 'third_party/cpython3/host'
            (target / 'bin/Lib/os.py').write_bytes(b'changed stdlib')
            (target / 'bin/python3').write_bytes(b'foreign executable fixture')
            host.ensure_windows_python(src, dependency, download, runner=runtime)
            self.assertEqual(download.call_count, 2)
            self.assertFalse((target / 'bin/python3').exists())
            self.assertEqual((target / 'bin/Lib/os.py').read_bytes(), b'# pinned stdlib fixture\n')

    def test_exact_v8_desc_has_no_override_and_requires_real_target_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            src = Path(temporary);(src / '.gn').write_bytes(b'pinned dotfile fixture')
            with mock.patch.object(host, 'WINDOWS_HOST', True), mock.patch.object(host, 'DOT_GN_SHA256', host.digest(src / '.gn')):
                target = {'toolchain': host.TOOLCHAIN, 'cflags': [], 'cflags_cc': [], 'include_dirs': [], 'defines': []}
                runner = mock.Mock()
                for label in [host.TARGET, host.UNQUALIFIED_TARGET]:
                    runner.return_value = SimpleNamespace(stdout=json.dumps({label: target}), stderr='')
                    result = host.preflight_gn_desc(src, runner=runner)
                    self.assertFalse(result['script_executable_override'])
                    self.assertEqual(runner.call_args.args[0], [str(src / 'buildtools/win/gn.exe'), 'desc', '-q', 'out\\AlwaysActive', host.TARGET, '--format=json'])
                    self.assertEqual(runner.call_args.kwargs['cwd'], src)
                for response in [{}, {host.TARGET: target, host.UNQUALIFIED_TARGET: target},
                                 {'//v8:other': target}, {host.UNQUALIFIED_TARGET: dict(target, toolchain='//wrong:toolchain')},
                                 {host.TARGET: {key: value for key, value in target.items() if key != 'toolchain'}}]:
                    runner.return_value = SimpleNamespace(stdout=json.dumps(response), stderr='')
                    with self.assertRaises(host.PythonHostError):host.preflight_gn_desc(src, runner=runner)


if __name__ == '__main__':
    unittest.main()
