"""Real tiny ARM64 app/framework fixtures only; never a local Chromium build."""
import contextlib
import io
import json
from pathlib import Path
import platform
import plistlib
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import mac_package as package
import build
import acquire_delivery


@unittest.skipUnless(sys.platform == 'darwin' and platform.machine() == 'arm64', 'Real Mac ARM64 codesign fixture')
class MacPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix='tiny-mac-signing-')
        root = Path(cls.work.name).resolve()
        cls.base = root / 'Chromium.app'
        contents = cls.base / 'Contents'
        framework = contents / 'Frameworks/Fixture.framework'
        current = framework / 'Versions/A'
        helper = current / 'Helpers/Fixture Helper.app'
        for directory in [contents / 'MacOS', current / 'Resources', current / 'Libraries', helper / 'Contents/MacOS']:
            directory.mkdir(parents=True, exist_ok=True)
        (framework / 'Versions/Current').symlink_to('A')
        (framework / 'Fixture').symlink_to('Versions/Current/Fixture')
        (framework / 'Resources').symlink_to('Versions/Current/Resources')
        def info(file, identifier, executable, kind):
            file.write_bytes(plistlib.dumps({'CFBundleIdentifier': identifier, 'CFBundleExecutable': executable,
                'CFBundlePackageType': kind, 'CFBundleVersion': '3.4', 'CFBundleShortVersionString': '1.2.3.4'}))
        info(contents / 'Info.plist', 'org.chromium.Chromium', 'Chromium', 'APPL')
        info(current / 'Resources/Info.plist', 'org.chromium.Chromium.fixture', 'Fixture', 'FMWK')
        info(helper / 'Contents/Info.plist', 'org.chromium.Chromium.helper', 'Fixture Helper', 'APPL')
        library, main, trivial = root / 'library.c', root / 'main.c', root / 'trivial.c'
        library.write_text('int fixture_value(void) { return 42; }\n')
        main.write_text('extern int fixture_value(void); int main(void) { return fixture_value() == 42 ? 0 : 1; }\n')
        trivial.write_text('int main(void) { return 0; }\n')
        cls.run_tool(['xcrun', 'clang', '-arch', 'arm64', '-dynamiclib', library, '-o', current / 'Fixture',
                      '-Wl,-install_name,@rpath/Fixture.framework/Versions/A/Fixture'])
        cls.run_tool(['xcrun', 'clang', '-arch', 'arm64', main, '-F' + str(contents / 'Frameworks'),
                      '-framework', 'Fixture', '-Wl,-rpath,@executable_path/../Frameworks', '-o', contents / 'MacOS/Chromium'])
        cls.run_tool(['xcrun', 'clang', '-arch', 'arm64', trivial, '-o', helper / 'Contents/MacOS/Fixture Helper'])
        cls.run_tool(['xcrun', 'clang', '-arch', 'arm64', '-dynamiclib', library, '-o', current / 'Libraries/Standalone.dylib'])
        entitlements = root / 'existing.plist'
        entitlements.write_bytes(plistlib.dumps({'com.apple.security.cs.allow-jit': True}))
        cls.run_tool(['codesign', '--force', '--sign', '-', '--timestamp=none', '--entitlements', entitlements, helper])

    @staticmethod
    def run_tool(command):
        return subprocess.run([str(part) for part in command], check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='tiny-mac-case-')
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name).resolve()
        self.source = self.root / 'source/Chromium.app'
        self.source.parent.mkdir()
        shutil.copytree(self.base, self.source, symlinks=True)
        self.destination = self.root / 'destination/Chromium.app'
        self.destination.parent.mkdir()
        self.report = self.root / 'receipt.json'

    def seal(self):
        return package.stage_signed_app(self.source, self.destination, '1.2.3.4', self.report)

    def failure(self, expected):
        with self.assertRaises(package.MacPackageError) as caught:
            self.seal()
        self.assertEqual(caught.exception.code, expected)
        receipt = json.loads(self.report.read_bytes())
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['code'], expected)
        self.assertLessEqual(self.report.stat().st_size, 65536)
        return receipt

    def test_real_inside_out_sealing_preserves_jit_entitlements_identity_and_source(self):
        commands = []
        invoke = package._invoke
        def observe(command, *args, **kwargs):
            commands.append([str(part) for part in command])
            return invoke(command, *args, **kwargs)
        with mock.patch.object(package, '_invoke', side_effect=observe):
            result = self.seal()
        receipt = result['signing']
        self.assertEqual(receipt['status'], 'complete')
        self.assertTrue(receipt['source_unchanged'])
        self.assertEqual(receipt['counts']['planned'], 4)
        self.assertEqual(receipt['counts']['signed'], 4)
        self.assertEqual(receipt['counts']['verified'], 4)
        self.assertEqual(receipt['counts']['bundles'], 3)
        self.assertNotIn(str(self.root), self.report.read_text())
        for part in receipt['parts']:
            self.assertEqual(part['baseline']['entitlements_sha256'], part['after']['entitlements_sha256'])
            self.assertEqual(part['after']['enforcement_flags'], 0)
        sign_commands = [command for command in commands if '--sign' in command]
        self.assertEqual(Path(sign_commands[-1][-1]), self.destination)
        self.assertTrue(all('--deep' not in command and '--options' not in command for command in sign_commands))
        self.run_tool(['codesign', '--verify', '--deep', '--strict', self.destination])
        # Executing this 1-line C fixture is not browser/runtime verification.
        self.run_tool([result['browser']])

    def test_existing_destination_is_never_overwritten(self):
        self.destination.mkdir();sentinel = self.destination / 'sentinel';sentinel.write_bytes(b'keep')
        self.failure('fresh_independent_destination_required')
        self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_build_zip_roundtrip_uses_the_same_sealed_executable(self):
        build_root = self.root / 'build'
        out = build_root / 'src/out/AlwaysActive'
        out.mkdir(parents=True)
        shutil.copytree(self.source, out / 'Chromium.app', symlinks=True)
        (build_root / 'state.json').write_text(json.dumps({'status': 'complete'}))
        project = self.root / 'project'
        project.mkdir()
        with mock.patch.object(build, 'root_path', return_value=build_root), \
                mock.patch.object(build, 'PROJECT', project), \
                mock.patch.object(build, 'PINS', {'version': '1.2.3.4'}), \
                mock.patch.object(build, 'source_commit', return_value='a' * 40), \
                mock.patch.object(build, 'output') as output, contextlib.redirect_stdout(io.StringIO()):
            build.package('mac-arm64')
            browser = Path(next(call.args[1] for call in output.call_args_list if call.args[0] == 'browser'))
            archive = project / 'packages/always-active-chromium-1.2.3.4-mac-arm64.zip'
            delivered, evidence = acquire_delivery.mac_delivery(archive, self.root / 'delivered', {'version': '1.2.3.4'})
        manifest = json.loads((project / 'packages/always-active-chromium-1.2.3.4-mac-arm64-build.json').read_text())
        self.assertTrue(manifest['mac_signing']['source_unchanged'])
        self.assertEqual(manifest['mac_signing']['status'], 'complete')
        self.assertEqual(build.sha256(browser), build.sha256(delivered))
        self.assertTrue(evidence['codesign_structure_verified'])
        collect = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                    '.github/scripts/publish-build-diagnostics.py'))['collect']
        _, _, selected = collect(project, {'AA_DIAGNOSTIC_PHASE': 'package', 'AA_PLATFORM': 'mac-arm64',
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123', 'AA_SOURCE_COMMIT': 'a' * 40,
            'GITHUB_SHA': 'a' * 40, 'AA_PACKAGE_OUTCOME': 'success'})
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(file.suffix in ('.json', '.txt') for file in selected))
        status = json.loads((project / 'packages/build-diagnostics/mac-arm64-package-status.json').read_text())
        self.assertEqual(status['package_report_status'], 'complete')
        self.run_tool([delivered])

    def test_external_symlink_refuses_before_copy_or_sign(self):
        (self.source / 'Contents/escape').symlink_to('../../outside')
        receipt = self.failure('escaping_or_absolute_symlink')
        self.assertEqual(receipt['counts']['signed'], 0)
        self.assertFalse(self.destination.exists())

    def test_wrong_bundle_identity_refuses_before_copy(self):
        file = self.source / 'Contents/Info.plist';value = plistlib.loads(file.read_bytes())
        value['CFBundleIdentifier'] = 'org.example.wrong';file.write_bytes(plistlib.dumps(value))
        receipt = self.failure('source_bundle_identity_mismatch')
        self.assertTrue(receipt['source_unchanged'])
        self.assertFalse(self.destination.exists())

    def test_hardened_baseline_is_reported_and_never_downgraded(self):
        helper = self.source / 'Contents/Frameworks/Fixture.framework/Versions/A/Helpers/Fixture Helper.app'
        self.run_tool(['codesign', '--force', '--sign', '-', '--timestamp=none', '--options', 'runtime', helper])
        receipt = self.failure('unsupported_baseline_enforcement_flags')
        self.assertTrue(any(part['baseline']['enforcement_flags'] & 0x10000 for part in receipt['parts']))
        self.assertTrue(receipt['source_unchanged']);self.assertEqual(receipt['counts']['signed'], 0)
        self.assertFalse(self.destination.exists())

    def test_concurrent_source_mutation_cannot_produce_a_success_receipt(self):
        invoke = package._invoke;changed = False
        def mutate(command, *args, **kwargs):
            nonlocal changed
            result = invoke(command, *args, **kwargs)
            if '--sign' in command and not changed:
                (self.source / 'Contents/concurrent-change').write_bytes(b'external mutation fixture')
                changed = True
            return result
        with mock.patch.object(package, '_invoke', side_effect=mutate):
            receipt = self.failure('source_changed_or_unverified')
        self.assertFalse(receipt['source_unchanged'])


if __name__ == '__main__':
    unittest.main()
