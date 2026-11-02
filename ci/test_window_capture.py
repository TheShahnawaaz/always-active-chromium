"""Synthetic raster/receipt policy guards only; no browser, UI or real capture."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


def publisher():
    file = Path(__file__).resolve().parents[1] / '.github/scripts/publish-delivery.py'
    spec = importlib.util.spec_from_file_location('window_capture_publication_fixture', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def fixture():
    width, height = 320, 240
    row = b'\0' + b'\x50\x50\x50' * 160 + b'\xdc\xdc\xdc' * 160
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(row * height)) + chunk(b'IEND', b''))
    identity = {'pid': 1234, 'profile': 'C:\\owned\\profile-native', 'executable': 'C:\\owned\\chrome.exe',
        'started': '2026-11-02T00:00:00.0000000Z', 'verified': True, 'immediatelyRevalidated': True,
        'afterCaptureRevalidated': True, 'ownerVerified': True, 'sessionVerified': True}
    receipt = {'schema': 1, 'purpose': 'owned-normal-browser-window-capture', 'platform': 'win32', 'status': 'captured',
        'method': 'PrintWindow-full-window-flags-0', 'captureAttempted': True, 'captureSucceeded': True,
        'captureOutcomeUncertain': False, 'nativeUiAccessed': True, 'visitedWindows': 1,
        'manualReview': 'pending', 'uiEquivalenceVerified': False, 'visualCompletenessVerified': False,
        'identity': identity, 'errors': [], 'window': {'handle': 'abc', 'ownerPID': 1234, 'width': width, 'height': height,
            'dpi': 96, 'foregroundVerified': True, 'visible': True, 'minimized': False, 'cloaked': False,
            'normalTopLevelVerified': True, 'fixtureTitleVerified': True, 'unchangedAfterCapture': True},
        'contentCheck': {'sampleCount': 768, 'uniqueSampleColors': 2, 'nonUniform': True, 'visualCompletenessVerified': False},
        'png': {'file': 'browser-window.png', 'width': width, 'height': height, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}
    return data, receipt


class CaptureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.png = self.root / 'browser-window.png'
        self.data, self.receipt = fixture()
        self.png.write_bytes(self.data)
        self.module = publisher()

    def validate(self, receipt=None, **kwargs):
        return self.module.validate_appearance_capture(receipt or self.receipt, self.png,
            expected_executable=kwargs.get('expected_executable', self.receipt['identity']['executable']),
            expected_pid=kwargs.get('expected_pid', 1234),
            expected_started=kwargs.get('expected_started', self.receipt['identity']['started']),
            expected_profile=kwargs.get('expected_profile', self.receipt['identity']['profile']),
            allow_startup_diagnostic=kwargs.get('allow_startup_diagnostic', False))

    def test_failed_startup_image_requires_explicit_context_and_cannot_be_behavior_proof(self):
        receipt = copy.deepcopy(self.receipt)
        receipt.update(captureContext='startup-diagnostic', behaviorVerified=False)
        receipt['window'].update(titleKind='untitled', fixtureTitleVerified=False,
                                 titleContextVerified=True, titleUnchangedAfterCapture=True)
        with self.assertRaises(ValueError):
            self.validate(receipt)
        result = self.validate(receipt, allow_startup_diagnostic=True)
        self.assertEqual(result['captureContext'], 'startup-diagnostic')
        self.assertIs(result['behaviorVerified'], False)
        self.assertEqual(result['window']['titleKind'], 'untitled')
        for change in [{'behaviorVerified': True}, {'captureContext': 'other'}]:
            with self.assertRaises(ValueError):
                self.validate(dict(receipt, **change), allow_startup_diagnostic=True)
        for title, verified in [('other', False), ('untitled', True), ('fixture', False)]:
            bad = copy.deepcopy(receipt)
            bad['window'].update(titleKind=title, fixtureTitleVerified=verified)
            with self.assertRaises(ValueError):
                self.validate(bad, allow_startup_diagnostic=True)
        for field in ['titleKind', 'titleContextVerified', 'titleUnchangedAfterCapture']:
            bad = copy.deepcopy(receipt)
            del bad['window'][field]
            with self.assertRaises(ValueError):
                self.validate(bad, allow_startup_diagnostic=True)

    def test_schema_fixture_remains_pending_manual_review_and_sanitized(self):
        self.receipt['identity']['unknown_private_field'] = 'excluded fixture text'
        result = self.validate()
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(result['manualReview'], 'pending')
        self.assertIs(result['uiEquivalenceVerified'], False)
        self.assertIs(result['visualCompletenessVerified'], False)
        self.assertNotIn('unknown_private_field', result['identity'])

    def test_pid_creation_profile_and_executable_bindings_are_required(self):
        for arguments in [{'expected_pid': 9}, {'expected_started': 'different'},
                          {'expected_profile': 'C:\\other'}, {'expected_executable': 'C:\\other.exe'}]:
            with self.assertRaises(ValueError):
                self.validate(**arguments)

    def test_uncertain_foreign_window_or_visual_equivalence_claim_refuses(self):
        for key, value in [('captureOutcomeUncertain', True), ('captureSucceeded', None),
                           ('uiEquivalenceVerified', True), ('visualCompletenessVerified', True)]:
            with self.assertRaises(ValueError):
                self.validate(dict(self.receipt, **{key: value}))
        receipt = copy.deepcopy(self.receipt)
        receipt['window']['ownerPID'] = 9
        with self.assertRaises(ValueError):
            self.validate(receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['window']['foregroundVerified'] = False
        with self.assertRaises(ValueError):
            self.validate(receipt)

    def test_png_hash_dimensions_type_crc_and_completeness_are_verified(self):
        receipt = copy.deepcopy(self.receipt)
        receipt['png']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.validate(receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['png']['width'] = 1
        with self.assertRaises(ValueError):
            self.validate(receipt)
        for data in [b'not PNG', self.data[:-12], self.data[:40] + bytes([self.data[40] ^ 1]) + self.data[41:]]:
            self.png.write_bytes(data)
            with self.assertRaises(ValueError):
                self.validate()

    def test_symlink_png_and_malformed_receipt_are_refused(self):
        self.png.unlink()
        actual = self.root / 'actual.png'
        actual.write_bytes(self.data)
        self.png.symlink_to(actual)
        with self.assertRaises(ValueError):
            self.validate()
        self.png.unlink()
        self.png.write_bytes(self.data)
        for key in ['identity', 'window', 'contentCheck', 'png']:
            with self.assertRaises(ValueError):
                self.validate(dict(self.receipt, **{key: None}))

    def test_capture_without_complete_runtime_store_evidence_cannot_verify_native_browser(self):
        project = self.root / 'project'
        output = project / 'reports/delivery-behavior/no-debug'
        output.mkdir(parents=True)
        (output / 'browser-window.png').write_bytes(self.data)
        (output / 'browser-window-capture.json').write_text(json.dumps(self.receipt))
        run = {'mode': 'native', 'ownedPid': 1234, 'processIdentity': {'owned': True, 'started': self.receipt['identity']['started']},
            'command': {'executable': self.receipt['identity']['executable'], 'args': ['--user-data-dir=' + self.receipt['identity']['profile']]},
            'appearance': {'status': 'captured', 'receipt': self.receipt}}
        (project / 'reports/delivery-behavior/results.json').write_text(json.dumps({'schema': 1, 'status': 'failed',
            'variants': {'no-debug': {'results': {'runs': [run]}}}}))
        acquisition = project / '.runtime/delivery'
        acquisition.mkdir(parents=True)
        (acquisition / 'delivery-provenance.json').write_text(json.dumps({'schema': 1, 'stage': 'real-package-delivery',
            'status': 'delivered', 'platform': 'win-x64', 'source_tag': 'ci-source-' + 'a'*12, 'browser': self.receipt['identity']['executable']}))
        environment = {'AA_PLATFORM': 'win-x64', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
            'GITHUB_SHA': 'b'*40, 'AA_PACKAGE_SOURCE_TAG': 'ci-source-' + 'a'*12}
        _, _, files = self.module.collect(project, environment)
        status = json.loads((project / 'packages/delivery-verification/win-x64-delivery-status.json').read_text())
        self.assertFalse(status['custom_native_browser_verified'])
        self.assertEqual(status['appearance']['manualReview'], 'pending')
        self.assertEqual(len([file for file in files if file.suffix == '.png']), 1)
        self.assertFalse(status['appearance']['uiEquivalenceVerified'])
        self.assertEqual(status['appearance']['png']['sha256'], hashlib.sha256(self.data).hexdigest())


if __name__ == '__main__':
    unittest.main()
