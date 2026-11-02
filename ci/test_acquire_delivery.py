"""Small provenance, path and installer-failure guards; no real browser/install."""
import copy
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import acquire_delivery as delivery
import verify


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.trusted, self.source = self.root / 'trusted', self.root / 'source'
        for directory in [self.trusted, self.source]:
            for relative in ['ci', 'native', 'patches']:
                (directory / relative).mkdir(parents=True)
            (directory / 'ci/pins.json').write_text(json.dumps({'version': '156.0.8078.80', 'revision': 'f' * 40}))
            (directory / 'native/provenance.json').write_text(json.dumps({'patch': 'patches/native.patch'}))
            (directory / 'native/apply_patches.py').write_text('trusted applicator fixture')
            (directory / 'patches/native.patch').write_text('trusted native bytes fixture')
        self.git = mock.Mock(return_value=SimpleNamespace(stdout='a' * 40 + '\n'))
        self.expected = delivery.expected_package(self.source, 'ci-source-' + 'a' * 12, 'win-x64', self.trusted, self.git)

    def manifest(self):
        value = self.expected
        return {'source': value['pins'], 'repository_commit': value['source_commit'], 'source_tag': value['source_tag'],
                'workflow_run': '12345', 'build': {key: value[key] for key in ['fingerprint', 'platform', 'version', 'revision']} | {'status': 'complete'}}

    def test_wrong_source_tag_pins_and_native_patch_are_rejected(self):
        with self.assertRaises(delivery.DeliveryError):
            delivery.expected_package(self.source, 'main', 'win-x64', self.trusted, self.git)
        (self.source / 'ci/pins.json').write_text(json.dumps({'version': 'different', 'revision': 'f' * 40}))
        with self.assertRaisesRegex(delivery.DeliveryError, 'unexpected_source_pins'):
            delivery.expected_package(self.source, self.expected['source_tag'], 'win-x64', self.trusted, self.git)
        (self.source / 'ci/pins.json').write_bytes((self.trusted / 'ci/pins.json').read_bytes())
        (self.source / 'patches/native.patch').write_text('foreign patch')
        with self.assertRaisesRegex(delivery.DeliveryError, 'unexpected_native_fingerprint'):
            delivery.expected_package(self.source, self.expected['source_tag'], 'win-x64', self.trusted, self.git)

    def test_source_commit_must_match_the_exact_input_tag(self):
        git = mock.Mock(return_value=SimpleNamespace(stdout='b' * 40))
        with self.assertRaisesRegex(delivery.DeliveryError, 'source_tag_commit_mismatch'):
            delivery.expected_package(self.source, self.expected['source_tag'], 'win-x64', self.trusted, git)

    def test_partial_or_other_platform_build_cannot_be_delivered(self):
        delivery.validate_manifest(self.manifest(), self.expected)
        for field, value in [('status', 'pending'), ('platform', 'mac-arm64'), ('fingerprint', '0' * 64), ('revision', 'e' * 40)]:
            manifest = copy.deepcopy(self.manifest())
            manifest['build'][field] = value
            with self.assertRaisesRegex(delivery.DeliveryError, 'build_provenance_mismatch'):
                delivery.validate_manifest(manifest, self.expected)

    def test_checksums_reject_duplicate_foreign_and_path_names(self):
        stem = self.expected['stem']
        good = '0' * 64 + '  ' + stem + '-build.json\n'
        self.assertIn(stem + '-build.json', delivery.parse_sums(good, stem))
        for value in [good + good, '0' * 64 + '  ../escape\n', '0' * 64 + '  unrelated.exe\n']:
            with self.assertRaises(delivery.DeliveryError):
                delivery.parse_sums(value, stem)

    def test_real_asset_bytes_must_match_size_checksums_and_api_digest(self):
        file = self.root / 'package.exe'
        file.write_bytes(b'finite package fixture')
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        metadata = {'id': 12, 'size': file.stat().st_size, 'digest': 'sha256:' + digest}
        self.assertEqual(delivery.verify_asset(file, metadata, digest)['sha256'], digest)
        for changed in [dict(metadata, size=1), dict(metadata, digest='sha256:' + '0' * 64)]:
            with self.assertRaises(delivery.DeliveryError):
                delivery.verify_asset(file, changed, digest)
        with self.assertRaises(delivery.DeliveryError):
            delivery.verify_asset(file, metadata, '0' * 64)

    def test_wrong_remote_ref_and_published_release_are_rejected_before_download(self):
        runner = mock.Mock(return_value=SimpleNamespace(stdout=json.dumps({'object': {'type': 'commit', 'sha': 'b' * 40}})))
        with self.assertRaisesRegex(delivery.DeliveryError, 'remote_tag_mismatch'):
            delivery.verify_ref('owner/repo', self.expected['source_tag'], self.expected['source_commit'], runner)
        calls = [SimpleNamespace(stdout=json.dumps({'object': {'type': 'commit', 'sha': 'a' * 40}}))] * 2
        calls.append(SimpleNamespace(stdout=json.dumps({'tagName': self.expected['release_tag'], 'isDraft': False, 'assets': []})))
        runner = mock.Mock(side_effect=calls)
        with self.assertRaisesRegex(delivery.DeliveryError, 'real_draft_required'):
            delivery.download_package(self.expected, 'owner/repo', self.root, runner)
        self.assertEqual(runner.call_count, 3)

    def test_mac_package_rejects_escape_and_external_symlink(self):
        for name, link in [('Chromium.app/../escaped', None), ('Chromium.app/Contents/link', '/outside')]:
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                item = zipfile.ZipInfo(name)
                if link:
                    item.create_system = 3
                    item.external_attr = 0o120777 << 16
                output.writestr(item, link or 'not extracted')
            with self.assertRaises(delivery.DeliveryError):
                delivery.validate_zip(archive)

    def test_macos_zero_exit_without_extracted_browser_is_failure(self):
        archive = self.root / 'empty.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('Chromium.app/Contents/placeholder', 'fixture')
        runner = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=''))
        with self.assertRaisesRegex(delivery.DeliveryError, 'extracted_browser_missing'):
            delivery.mac_delivery(archive, self.root / 'delivered', self.expected, runner)

    def test_existing_chromium_identity_refuses_without_any_installer_action(self):
        environment = {key: str(self.root / key) for key in ['LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)']}
        keys = []
        def key_exists(hive, view, key):
            keys.append(key)
            return key == 'Software\\Chromium'
        with self.assertRaisesRegex(delivery.DeliveryError, 'existing_chromium_registration'):
            delivery.windows_clean_identity(environment, exists=lambda value: False, key_exists=key_exists)
        self.assertEqual(keys, ['Software\\Chromium'])
        with self.assertRaisesRegex(delivery.DeliveryError, 'existing_chromium_directory'):
            delivery.windows_clean_identity(environment, exists=lambda value: True, key_exists=mock.Mock())

    def test_failed_installer_and_zero_exit_without_real_browser_are_failures(self):
        browser = self.root / 'new/Chromium/Application/chrome.exe'
        clean = mock.Mock(return_value=browser)
        failed = mock.Mock(return_value=SimpleNamespace(returncode=7))
        with self.assertRaises(delivery.DeliveryError) as found:
            delivery.windows_delivery(self.root / 'real-installer.exe', self.expected, failed, {}, clean)
        self.assertEqual(found.exception.code, 'installer_failed')
        self.assertEqual(found.exception.exit_code, 7)
        self.assertEqual(failed.call_args.args[0][1:], ['--do-not-launch-chrome'])
        succeeded = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with self.assertRaisesRegex(delivery.DeliveryError, 'installed_browser_missing'):
            delivery.windows_delivery(self.root / 'real-installer.exe', self.expected, succeeded, {}, clean)

    def test_installed_wrong_architecture_never_launches_a_browser(self):
        browser = self.root / 'chrome.exe'
        data = bytearray(134)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 128)
        data[128:132] = b'PE\0\0'
        struct.pack_into('<H', data, 132, 0x14c)
        browser.write_bytes(data)
        runner = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with self.assertRaisesRegex(delivery.DeliveryError, 'wrong_installed_architecture_or_path'):
            delivery.windows_delivery(self.root / 'installer.exe', self.expected, runner, {}, lambda env: browser)
        self.assertEqual(runner.call_count, 1)

    def test_installer_timeout_never_means_delivered(self):
        runner = mock.Mock(side_effect=subprocess.TimeoutExpired('owned installer', 300))
        with self.assertRaisesRegex(delivery.DeliveryError, 'installer_timed_out'):
            delivery.windows_delivery(self.root / 'installer.exe', self.expected, runner, {}, lambda env: self.root / 'chrome.exe')

    def test_behavior_binding_changes_when_executable_bytes_change(self):
        file = self.root / 'browser-fixture'
        file.write_bytes(b'not a browser, never executed')
        original = verify.executable_identity(file)
        self.assertEqual(original['executable'], str(file.resolve()))
        self.assertEqual(original['size'], file.stat().st_size)
        file.write_bytes(b'different bytes')
        self.assertNotEqual(original, verify.executable_identity(file))


class DeliveryPublicationTests(unittest.TestCase):
    def publisher(self):
        file = Path(__file__).resolve().parents[1] / '.github/scripts/publish-delivery.py'
        spec = importlib.util.spec_from_file_location('delivery_publication_fixture', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cli_retains_receipt_then_reports_its_verification_outcome(self):
        module = self.publisher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = root / 'fixture-delivery-status.json'
            for verified in [False, True]:
                status.write_text(json.dumps({'custom_native_browser_verified': verified}))
                with mock.patch.object(module, 'collect', return_value=('fixture-tag', root / 'notes', [status])), \
                        mock.patch.dict(module.os.environ, {'GITHUB_REPOSITORY': 'owner/repo', 'AA_PLATFORM': 'win-x64'}), \
                        mock.patch.object(module.subprocess, 'run') as publish:
                    self.assertEqual(module.main(), 0 if verified else 1)
                    self.assertEqual(publish.call_count, 2)  # Retain even the failed receipt first.

    def test_empty_pass_labels_cannot_claim_native_delivery_verification(self):
        checks = self.publisher().verification_checks({'provenance': {'status': 'delivered'},
            'behavior': {'status': 'passed'}, 'store': {'status': 'passed'}}, 'win-x64')
        self.assertFalse(any(checks.values()))

    def test_missing_or_different_executable_hash_cannot_bind_success(self):
        provenance = {'browser': '/owned/Chromium', 'delivery': {'executable_sha256': 'a' * 64, 'executable_size': 3}}
        original = {'executable': '/owned/Chromium', 'sha256': 'b' * 64, 'size': 3}
        reports = {'provenance': provenance, 'behavior': {'executable_binding': {'initial': original, 'final': original, 'unchanged': True}}}
        self.assertFalse(self.publisher().verification_checks(reports, 'mac-arm64')['executable_binding_complete'])
        original.pop('sha256')
        self.assertFalse(self.publisher().verification_checks(reports, 'mac-arm64')['executable_binding_complete'])

    def test_uncertain_native_action_and_missing_phases_cannot_complete_store(self):
        store = {'status': 'passed', 'phases': [], 'coverage': {key: True for key in ['normalInstall', 'workerExecution', 'restartPersistence', 'ordinaryUpdateCheck', 'normalRemovalWithPersistedRegistrationAbsence']}}
        self.assertFalse(self.publisher().store_complete(store, {}, 'win-x64'))
        store['actions'] = [{'operation': 'accept-install', 'status': 'acted', 'actionOutcomeUncertain': True}]
        self.assertFalse(self.publisher().store_complete(store, {}, 'win-x64'))

    def test_publication_allowlist_excludes_profiles_and_browser_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / '.runtime/delivery'
            output.mkdir(parents=True)
            (output / 'delivery-provenance.json').write_text(json.dumps({'schema': 1, 'stage': 'real-package-delivery',
                'status': 'failed', 'platform': 'win-x64', 'source_tag': 'ci-source-' + 'a' * 12}))
            (output / 'browser.log').write_text('excluded raw log fixture')
            (output / 'profile').mkdir()
            (output / 'profile/Preferences').write_text('excluded profile fixture')
            environment = {'AA_PLATFORM': 'win-x64', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
                'AA_PACKAGE_SOURCE_TAG': 'ci-source-' + 'a' * 12, 'GITHUB_SHA': 'b' * 40,
                'AA_ACQUIRE_OUTCOME': 'failure', 'AA_BEHAVIOR_OUTCOME': 'skipped', 'AA_STORE_OUTCOME': 'skipped'}
            _, _, selected = self.publisher().collect(root, environment)
            self.assertEqual({file.name for file in selected}, {'win-x64-delivery-provenance.json',
                'win-x64-delivery-status.json', 'win-x64-delivery-SHA256SUMS.txt'})
            status = json.loads((root / 'packages/delivery-verification/win-x64-delivery-status.json').read_text())
            self.assertFalse(status['custom_native_browser_verified'])

    def test_publisher_refuses_symlink_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / '.runtime/delivery'
            source.mkdir(parents=True)
            outside = root / 'outside.json'
            outside.write_text('{}')
            (source / 'delivery-provenance.json').symlink_to(outside)
            environment = {'AA_PLATFORM': 'win-x64', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
                'AA_PACKAGE_SOURCE_TAG': 'ci-source-' + 'a' * 12, 'GITHUB_SHA': 'b' * 40}
            _, _, selected = self.publisher().collect(root, environment)
            self.assertNotIn('win-x64-delivery-provenance.json', [file.name for file in selected])
            status = json.loads((root / 'packages/delivery-verification/win-x64-delivery-status.json').read_text())
            self.assertFalse(status['custom_native_browser_verified'])
            self.assertEqual(status['report_errors'], [{'kind': 'provenance', 'reason': 'unsafe_or_oversized_evidence_file'}])

    def test_malformed_nested_reports_retain_failed_status_without_publisher_crash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'reports/delivery-behavior'
            source.mkdir(parents=True)
            (source / 'results.json').write_text(json.dumps({'schema': 1, 'status': 'passed', 'variants': ['malformed']}))
            environment = {'AA_PLATFORM': 'win-x64', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
                'AA_PACKAGE_SOURCE_TAG': 'ci-source-' + 'a' * 12, 'GITHUB_SHA': 'b' * 40}
            self.publisher().collect(root, environment)
            status = json.loads((root / 'packages/delivery-verification/win-x64-delivery-status.json').read_text())
            self.assertFalse(status['custom_native_browser_verified'])
            self.assertIn({'kind': 'combined', 'reason': 'malformed_nested_report_structure'}, status['report_errors'])


if __name__ == '__main__':
    unittest.main()
