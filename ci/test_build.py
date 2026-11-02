"""Small archive-hydration regressions; no Chromium checkout or compilation."""
import contextlib
import base64
import hashlib
import io
from pathlib import Path
import json
import os
import shutil
import stat
import tempfile
import tarfile
from types import SimpleNamespace
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

    @unittest.skipUnless(os.name == 'nt', 'The exact Windows GNU tar integration requires its hosted image')
    def test_windows_source_helper_extracts_unicode_xz(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'source.tar.xz'
            relative = 'resources/caf\u00e9-\u65e5\u672c-\U0001f680.txt'
            content = b'UTF-8 source archive fixture\n'
            member = tarfile.TarInfo('chromium-fixture/' + relative)
            member.size = len(content)
            with tarfile.open(archive, 'w:xz', format=tarfile.PAX_FORMAT, preset=1) as package:
                package.addfile(member, io.BytesIO(content))
            destination = root / 'src'
            metadata = unpack(archive, destination, strip=1, source_archive=True)
            self.assertIn('GNU tar', metadata['version'])
            self.assertEqual((destination / relative).read_bytes(), content)


class DawnGoTests(unittest.TestCase):
    def dawn_fixture(self, root, version=build.DAWN_GO_VERSION):
        dawn = root / 'third_party/dawn'
        dawn.mkdir(parents=True)
        dependencies = {}
        for host, condition in (('mac-arm64', 'checkout_mac and non_git_source'),
                                ('windows-amd64', 'checkout_win and non_git_source')):
            dependencies[f'tools/golang/{host}'] = {
                'dep_type': 'cipd', 'condition': condition,
                'packages': [{'package': f'infra/3pp/tools/go/{host}', 'version': version}]}
        (dawn / 'DEPS').write_text(f'vars = {{"dawn_go_version": {version!r}}}\n'
                                  f'deps = {dependencies!r}\n', encoding='utf-8')
        return dawn

    def test_host_go_uses_nested_pin_checksum_and_absolute_executable(self):
        for platform, host, binary, version in (
                ('mac-arm64', 'mac-arm64', 'go', 'darwin/arm64'),
                ('win-x64', 'windows-amd64', 'go.exe', 'windows/amd64')):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                dawn = self.dawn_fixture(root)
                hydrate = mock.Mock()
                with mock.patch.object(build, 'run', return_value=SimpleNamespace(
                        stdout=f'go version go1.26.6 {version}\n')) as run:
                    build.hydrate_dawn_go(root, platform, hydrate)
                entries, base, selected, enabled, checksums = hydrate.call_args.args
                relative = f'tools/golang/{host}'
                package = f'infra/3pp/tools/go/{host}'
                self.assertEqual(base, dawn)
                self.assertEqual(selected, {relative})
                self.assertTrue(enabled(entries[relative]['condition']))
                other = 'windows-amd64' if host == 'mac-arm64' else 'mac-arm64'
                self.assertFalse(enabled(entries[f'tools/golang/{other}']['condition']))
                self.assertEqual(checksums, {package: build.DAWN_GO_SHA256[package]})
                run.assert_called_once_with([dawn / relative / 'bin' / binary, 'version'],
                                            cwd=dawn, capture_output=True, text=True)

    def test_unexpected_nested_go_pin_is_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.dawn_fixture(root, 'version:3@1.26.7')
            hydrate = mock.Mock()
            with mock.patch.object(build, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'pinned nested DEPS'):
                    build.hydrate_dawn_go(root, 'mac-arm64', hydrate)
            hydrate.assert_not_called()
            run.assert_not_called()

    def test_wrong_go_version_or_host_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.dawn_fixture(root)
            for output in ('go version go1.26.5 darwin/arm64\n',
                           'go version go1.26.6 darwin/amd64\n'):
                with self.subTest(output=output), mock.patch.object(build, 'run',
                        return_value=SimpleNamespace(stdout=output)):
                    with self.assertRaisesRegex(RuntimeError, 'version/host mismatch'):
                        build.hydrate_dawn_go(root, 'mac-arm64', mock.Mock())


class WindowsGperfTests(unittest.TestCase):
    def gperf_fixture(self):
        contents = {'bin/gperf.exe': b'pinned Windows executable fixture',
                    'README.chromium': b'License File: src/gperf/3.0.1/gperf-3.0.1-src/COPYING\n',
                    'src/gperf/3.0.1/gperf-3.0.1-src/COPYING': b'pinned license fixture'}
        pin = dict(build.WINDOWS_GPERF, files={relative: {
            'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
            'blob': hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()}
            for relative, content in contents.items()})
        scope = {'deps': {'src/third_party/gperf': {
            'url': f'{pin["repository"]}.git@{pin["revision"]}', 'condition': 'checkout_win'}}}
        return contents, pin, scope

    def test_exact_git_blob_is_verified_and_reused_without_touching_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents, pin, scope = self.gperf_fixture()
            with mock.patch.object(build, 'WINDOWS_GPERF', pin), mock.patch.object(build, 'fetch') as fetch, \
                    mock.patch.object(build, 'run', return_value=SimpleNamespace(stdout=pin['version'] + '\n')) as run:
                def download(url, path, **_kwargs):
                    relative = url.split(f'/{pin["revision"]}/', 1)[1].split('?', 1)[0]
                    path.write_bytes(base64.b64encode(contents[relative]))
                fetch.side_effect = download
                records = build.hydrate_windows_gperf(root, scope, lambda _condition: True)
                executable = root / 'third_party/gperf/bin/gperf.exe'
                stamps = {}
                for relative, content in contents.items():
                    target = root / 'third_party/gperf' / relative
                    self.assertEqual(target.read_bytes(), content)
                    stamps[relative] = target.stat().st_mtime_ns
                self.assertEqual(build.hydrate_windows_gperf(root, scope, lambda _condition: True), records)
                for relative, stamp in stamps.items():
                    self.assertEqual((root / 'third_party/gperf' / relative).stat().st_mtime_ns, stamp)
                self.assertEqual(fetch.call_count, 3)
                self.assertTrue(all(pin['revision'] in call.args[0] for call in fetch.call_args_list))
                self.assertEqual(records[0]['sha256'], pin['files']['bin/gperf.exe']['sha256'])
                self.assertEqual(records[0]['git_blob'], pin['files']['bin/gperf.exe']['blob'])
                self.assertEqual(run.call_args.args[0], [executable, '--version'])

    def test_wrong_git_revision_is_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            _content, pin, scope = self.gperf_fixture()
            scope['deps']['src/third_party/gperf']['url'] += 'foreign'
            with mock.patch.object(build, 'WINDOWS_GPERF', pin), mock.patch.object(build, 'fetch') as fetch:
                with self.assertRaisesRegex(RuntimeError, 'pinned source DEPS'):
                    build.hydrate_windows_gperf(Path(temporary), scope, lambda _condition: True)
                fetch.assert_not_called()

    def test_corrupt_download_cannot_install_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _content, pin, scope = self.gperf_fixture()
            with mock.patch.object(build, 'WINDOWS_GPERF', pin), mock.patch.object(build, 'fetch') as fetch:
                fetch.side_effect = lambda _url, path, **_kwargs: path.write_bytes(base64.b64encode(b'foreign'))
                with self.assertRaisesRegex(RuntimeError, 'Downloaded Windows gperf'):
                    build.hydrate_windows_gperf(root, scope, lambda _condition: True)
            self.assertEqual(list((root / 'third_party/gperf/bin').iterdir()), [])

    def test_unknown_existing_binary_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _content, pin, scope = self.gperf_fixture()
            executable = root / 'third_party/gperf/bin/gperf.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'foreign')
            with mock.patch.object(build, 'WINDOWS_GPERF', pin), mock.patch.object(build, 'fetch') as fetch:
                with self.assertRaisesRegex(RuntimeError, 'Existing Windows gperf'):
                    build.hydrate_windows_gperf(root, scope, lambda _condition: True)
                fetch.assert_not_called()
            self.assertEqual(executable.read_bytes(), b'foreign')


class CrubitFormatterTests(unittest.TestCase):
    def test_windows_uses_exact_gcs_entry_and_checks_pinned_executable(self):
        source = Path('/fixture/src')
        dependency = {'dep_type': 'gcs', 'condition': 'checkout_win and non_git_source',
                      'bucket': 'chromium-clang-format', 'objects': [{
                          'object_name': 'fb0bcaf406ad6f0bd6b4a6347d2abe78a94fb13e',
                          'generation': 1779297371701340, 'size_bytes': 3799552,
                          'sha256sum': 'ee7a1f89733de23daf8ee035f8aebafa52410c9f4dd1f05ee12a95ce517a0953',
                          'output_file': 'clang-format.exe'}]}
        scope = {'deps': {'src/buildtools/win-format': dependency}}
        enabled = mock.Mock(return_value=True)
        hydrate = mock.Mock()
        with mock.patch.object(build, 'run') as run:
            build.hydrate_crubit_formatter(source, 'win-x64', scope, enabled, hydrate)
        hydrate.assert_called_once_with(scope['deps'], source.parent, {'src/buildtools/win-format'}, enabled)
        run.assert_called_once_with([source / 'buildtools/win-format/clang-format.exe', '--version'], cwd=source)

    def test_mac_does_not_hydrate_formatter_unused_by_this_crubit_action(self):
        hydrate = mock.Mock()
        with mock.patch.object(build, 'run') as run:
            build.hydrate_crubit_formatter(Path('/fixture/src'), 'mac-arm64', {}, mock.Mock(), hydrate)
        hydrate.assert_not_called()
        run.assert_not_called()

    def test_missing_pinned_windows_formatter_fails_before_hydration(self):
        hydrate = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'pinned DEPS'):
            build.hydrate_crubit_formatter(Path('/fixture/src'), 'win-x64', {'deps': {}},
                                           mock.Mock(return_value=True), hydrate)
        hydrate.assert_not_called()


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
