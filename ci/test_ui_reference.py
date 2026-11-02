"""Reference capture failure receipts must not become native/UI claims."""
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from test_window_capture import fixture


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

    def failed_startup(self):
        report = self.root / 'reports/ui-reference'
        report.mkdir(parents=True)
        data, receipt = fixture()
        receipt.update(captureContext='startup-diagnostic', behaviorVerified=False)
        receipt['identity'].update(executable=self.env['AA_REFERENCE_BROWSER'], profile=str((report / 'profile-control').resolve()))
        receipt['window'].update(titleKind='untitled', fixtureTitleVerified=False,
                                titleContextVerified=True, titleUnchangedAfterCapture=True)
        guards = ['owned profile exposes no remote debugging port file',
                  'normal launch has no debugging, automation, extension, or emulation flags',
                  'verified owned browser process cleanup completes']
        run = {'mode': 'control', 'status': 'failed', 'ownedPid': receipt['identity']['pid'],
            'processIdentity': {'pid': receipt['identity']['pid'], 'owned': True, 'started': receipt['identity']['started']},
            'cleanup': {'rootGone': True}, 'command': {'executable': self.env['AA_REFERENCE_BROWSER']},
            'appearance': {'status': 'captured', 'receipt': receipt},
            'tests': [{'name': name, 'status': 'passed'} for name in guards] +
                     [{'name': 'both websites provide stable later reports', 'status': 'failed'}]}
        result = {'schema': 1, 'mode': 'control', 'status': 'failed', 'interrupted': None,
                  'platform': 'win32', 'architecture': 'x64', 'expectedVersion': '156.0.8078.80', 'runs': [run]}
        provenance = self.root / '.runtime/ui-reference'
        provenance.mkdir(parents=True)
        (provenance / 'reference-provenance.json').write_text(json.dumps({'schema': 1, 'platform': 'win64',
            'version': '156.0.8078.80', 'expected_revision': 'fb096c0011f9d50f0a264a9376420cdea9c421e3',
            'cft': {'sha256': '16edb57d6107bf1c48a7c149b8d78b155fe614410093796dd72441fd6640540f'}}))
        (report / 'results.json').write_text(json.dumps(result))
        (report / 'browser-window-capture.json').write_text(json.dumps(receipt))
        (report / 'browser-window.png').write_bytes(data)
        self.env.update(AA_FAILED_STARTUP_CAPTURE='1', AA_INSPECTION_OUTCOME='failure')
        return report, result

    def test_owned_failed_startup_image_is_retained_without_passing_behavior_or_native_claims(self):
        self.failed_startup()
        _, _, selected, verified = self.collect(self.root, self.env)
        status = self.status()
        self.assertFalse(verified)
        self.assertEqual(status['status'], 'failed')
        self.assertTrue(status['capture_file_and_identity_verified'])
        self.assertTrue(status['failed_startup_diagnostic_retained'])
        self.assertFalse(status['normal_launch_observation_verified'])
        self.assertFalse(status['custom_native_browser_verified'])
        self.assertFalse(status['appearance_equivalence_verified'])
        self.assertEqual(status['capture_context'], 'startup-diagnostic')
        self.assertEqual(len([file for file in selected if file.suffix == '.png']), 1)

    def test_failed_startup_image_requires_opt_in_and_all_ownership_launch_cleanup_guards(self):
        report, result = self.failed_startup()
        cases = [('opt_in', None), ('rootGone', False), ('owned', False), ('executable', '/other.exe')]
        for field, value in cases:
            with self.subTest(field=field):
                changed = json.loads(json.dumps(result))
                environment = dict(self.env)
                if field == 'opt_in':environment.pop('AA_FAILED_STARTUP_CAPTURE')
                elif field == 'rootGone':changed['runs'][0]['cleanup'][field] = value
                elif field == 'owned':changed['runs'][0]['processIdentity'][field] = value
                else:changed['runs'][0]['command'][field] = value
                (report / 'results.json').write_text(json.dumps(changed))
                _, _, selected, verified = self.collect(self.root, environment)
                self.assertFalse(verified)
                self.assertFalse(self.status()['capture_file_and_identity_verified'])
                self.assertFalse(any(file.suffix == '.png' for file in selected))
        for index in range(3):
            changed = json.loads(json.dumps(result))
            changed['runs'][0]['tests'][index]['status'] = 'failed'
            (report / 'results.json').write_text(json.dumps(changed))
            _, _, selected, _ = self.collect(self.root, self.env)
            self.assertFalse(self.status()['capture_file_and_identity_verified'])
            self.assertFalse(any(file.suffix == '.png' for file in selected))

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
