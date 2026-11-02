"""Reference capture failure receipts must not become native/UI claims."""
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest


class UiReferencePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        original = Path(__file__).resolve().parents[1]
        (self.root / '.github/scripts').mkdir(parents=True)
        shutil.copy2(original / '.github/scripts/publish-delivery.py', self.root / '.github/scripts/publish-delivery.py')
        self.collect = runpy.run_path(str(original / '.github/scripts/publish-ui-reference.py'))['collect']
        self.env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123', 'GITHUB_SHA': 'a' * 40,
                    'AA_INSPECTION_OUTCOME': 'success', 'AA_REFERENCE_BROWSER': '/owned/reference.exe'}

    def status(self):
        return json.loads((self.root / 'packages/ui-reference/win-x64-ui-reference-status.json').read_text())

    def test_pass_labels_without_complete_capture_never_publish_image_or_native_proof(self):
        report = self.root / 'reports/ui-reference'
        report.mkdir(parents=True)
        (report / 'results.json').write_text(json.dumps({'schema': 1, 'status': 'passed', 'mode': 'control', 'runs': []}))
        (report / 'browser-window.png').write_bytes(b'unverified image must not be published')
        (report / 'browser.log').write_text('excluded raw log')
        (report / 'profile').mkdir()
        (report / 'profile/Preferences').write_text('excluded owned profile')
        _, _, selected, verified = self.collect(self.root, self.env)
        self.assertFalse(verified)
        self.assertTrue(all(file.suffix in ('.json', '.txt') for file in selected))
        self.assertFalse(self.status()['custom_native_browser_verified'])
        self.assertFalse(self.status()['appearance_equivalence_verified'])
        self.assertFalse(self.status()['capture_file_and_identity_verified'])

    def test_unsafe_capture_receipt_is_not_copied_and_failure_is_retained(self):
        report = self.root / 'reports/ui-reference'
        report.mkdir(parents=True)
        outside = self.root / 'outside.json'
        outside.write_text('{"schema":1}')
        (report / 'browser-window-capture.json').symlink_to(outside)
        _, _, selected, verified = self.collect(self.root, self.env)
        self.assertFalse(verified)
        self.assertNotIn('win-x64-ui-reference-capture.json', [file.name for file in selected])
        self.assertIn({'kind': 'capture', 'reason': 'invalid_or_unsafe_json'}, self.status()['errors'])


if __name__ == '__main__':
    unittest.main()
