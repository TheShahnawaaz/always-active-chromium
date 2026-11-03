"""Guards for using a real task-owned installation as the Windows core target."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from acquire_delivery import DeliveryError
import install_build


class InstallBuildTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        packages = self.root / 'packages'
        packages.mkdir()
        self.expected = {'source_commit': 'a' * 40, 'source_tag': 'ci-source-' + 'a' * 12,
                         'platform': 'win-x64', 'version': '156.0.8078.80',
                         'revision': 'f' * 40, 'fingerprint': 'b' * 64,
                         'pins': {'version': '156.0.8078.80'},
                         'package_name': 'fixture-installer.exe', 'manifest_name': 'fixture-build.json'}
        self.installer = packages / self.expected['package_name']
        self.installer.write_bytes(b'actual installer fixture bytes')
        self.manifest = packages / self.expected['manifest_name']
        self.manifest.write_text(json.dumps({
            'source': self.expected['pins'], 'repository_commit': self.expected['source_commit'],
            'source_tag': self.expected['source_tag'], 'workflow_run': '12345',
            'build': {key: self.expected[key] for key in ['platform', 'version', 'revision', 'fingerprint']} | {'status': 'complete'}}))
        self.browser = self.root / 'installed-chrome.exe'
        self.browser.write_bytes(b'installed executable fixture')
        self.installed = {'method': 'real-mini-installer-default-per-user',
                          'executable_sha256': hashlib.sha256(self.browser.read_bytes()).hexdigest()}
        self.env = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                    'GITHUB_RUN_ID': '12345', 'AA_SOURCE_TAG': self.expected['source_tag']}
        self.platform = mock.patch.object(install_build.sys, 'platform', 'win32')
        self.platform.start()
        self.addCleanup(self.platform.stop)
        expected_patch = mock.patch.object(install_build, 'expected_package', return_value=self.expected)
        self.expected_mock = expected_patch.start()
        self.addCleanup(expected_patch.stop)
        install_patch = mock.patch.object(install_build, 'windows_delivery',
                                         return_value=(self.browser, self.installed))
        self.install = install_patch.start()
        self.addCleanup(install_patch.stop)

    def test_unapproved_host_cannot_launch_an_installer(self):
        for key, value in [('GITHUB_ACTIONS', 'false'), ('RUNNER_ENVIRONMENT', 'self-hosted')]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(DeliveryError, 'hosted_windows_required'):
                    install_build.install_for_core(self.root, {**self.env, key: value})
        with mock.patch.object(install_build.sys, 'platform', 'darwin'):
            with self.assertRaisesRegex(DeliveryError, 'hosted_windows_required'):
                install_build.install_for_core(self.root, self.env)
        self.expected_mock.assert_not_called()
        self.install.assert_not_called()

    def test_foreign_workflow_is_rejected_before_install(self):
        with self.assertRaisesRegex(DeliveryError, 'unexpected_installation_workflow'):
            install_build.install_for_core(self.root, {**self.env, 'GITHUB_RUN_ID': '99999'})
        self.install.assert_not_called()

    def test_receipt_binds_the_installer_and_installed_executable(self):
        browser, receipt = install_build.install_for_core(self.root, self.env)
        self.assertEqual(browser, self.browser)
        self.install.assert_called_once_with(self.installer, self.expected, environ=self.env)
        self.assertEqual(receipt['installer_sha256'], hashlib.sha256(self.installer.read_bytes()).hexdigest())
        self.assertEqual(receipt['executable_sha256'], self.installed['executable_sha256'])
        self.assertEqual(json.loads(self.manifest.read_text())['windows_core_installation'], receipt)

    def test_installer_mutation_cannot_create_a_success_receipt(self):
        def changed(*args, **kwargs):
            self.installer.write_bytes(b'changed during installation')
            return self.browser, self.installed
        self.install.side_effect = changed
        with self.assertRaisesRegex(DeliveryError, 'installer_changed_during_install'):
            install_build.install_for_core(self.root, self.env)
        self.assertNotIn('windows_core_installation', json.loads(self.manifest.read_text()))


if __name__ == '__main__':
    unittest.main()
