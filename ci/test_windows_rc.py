"""Small hostile-input/closure guards; mocks never count as real Windows RC proof."""
import contextlib
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import windows_rc as rc


class WindowsRcTests(unittest.TestCase):
    def fixture(self, temporary, machine=0x8664):
        src = Path(temporary) / 'src'
        payload = bytearray(128)
        payload[:2] = b'MZ'
        struct.pack_into('<I', payload, 60, 64)
        payload[64:68] = b'PE\0\0'
        struct.pack_into('<H', payload, 68, machine)
        struct.pack_into('<H', payload, 88, 0x20b)
        payload = bytes(payload)
        pin = dict(rc.PIN, sha1=hashlib.sha1(payload).hexdigest(),
                   sha256=hashlib.sha256(payload).hexdigest(), size=len(payload))
        source = {'build/toolchain/win/rc/rc.py': b'pinned driver fixture\n',
                  'build/toolchain/win/tool_wrapper.py': b'pinned wrapper fixture\n',
                  rc.RC_RELATIVE + '.sha1': pin['sha1'].encode()}
        for relative, data in source.items():
            file = src / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        patches = contextlib.ExitStack()
        patches.enter_context(mock.patch.object(rc, 'WINDOWS_HOST', True))
        patches.enter_context(mock.patch.object(rc, 'PIN', pin))
        patches.enter_context(mock.patch.object(rc, 'SOURCES', {
            relative: hashlib.sha256(data).hexdigest() for relative, data in source.items()}))
        self.addCleanup(patches.close)
        fetch = mock.Mock(side_effect=lambda _url, file, **_kwargs: file.write_bytes(payload))
        return src, payload, pin, {'hooks': [dict(rc.HOOK)]}, fetch

    def test_verified_download_and_existing_reuse_preserve_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, payload, pin, scope, fetch = self.fixture(temporary)
            records = rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            target = src / rc.RC_RELATIVE
            self.assertEqual(target.read_bytes(), payload)
            stamp = target.stat().st_mtime_ns
            self.assertEqual(rc.ensure_windows_rc(src, scope, lambda _: True, fetch), records)
            self.assertEqual(target.stat().st_mtime_ns, stamp)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(fetch.call_args.kwargs, {'expected_sha': pin['sha256'], 'expected_size': pin['size']})
            self.assertIn('?generation=' + str(pin['generation']), fetch.call_args.args[0])

    def test_wrong_hook_or_source_rejects_before_any_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, _payload, _pin, scope, fetch = self.fixture(temporary)
            scope['hooks'][0]['action'] = ['foreign']
            with self.assertRaisesRegex(rc.WindowsRcError, 'unexpected_deps_hook'):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            scope['hooks'] = [dict(rc.HOOK)]
            (src / 'build/toolchain/win/rc/rc.py').write_bytes(b'changed source')
            with self.assertRaisesRegex(rc.WindowsRcError, 'unexpected_pinned_source'):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            fetch.assert_not_called()

    def test_corrupt_download_is_not_installed_or_left_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, _payload, _pin, scope, fetch = self.fixture(temporary)
            fetch.side_effect = lambda _url, file, **_kwargs: file.write_bytes(b'corrupt')
            with self.assertRaises(rc.WindowsRcError):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            self.assertFalse((src / rc.RC_RELATIVE).exists())
            self.assertEqual(list((src / rc.RC_RELATIVE).parent.glob('.aacc-rc-*')), [])

    def test_unknown_existing_binary_is_preserved_and_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, _payload, _pin, scope, fetch = self.fixture(temporary)
            target = src / rc.RC_RELATIVE
            target.write_bytes(b'unknown prior binary')
            with self.assertRaises(rc.WindowsRcError):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            self.assertEqual(target.read_bytes(), b'unknown prior binary')
            fetch.assert_not_called()

    def test_non_x64_pe_rejected_even_if_all_fixture_digests_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, _payload, _pin, scope, fetch = self.fixture(temporary, machine=0x14c)
            with self.assertRaisesRegex(rc.WindowsRcError, 'wrong_pe_architecture'):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            self.assertFalse((src / rc.RC_RELATIVE).exists())

    def test_symlink_target_or_parent_cannot_redirect_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            src, _payload, _pin, scope, fetch = self.fixture(temporary)
            target = src / rc.RC_RELATIVE
            foreign = Path(temporary) / 'foreign'
            foreign.write_bytes(b'foreign')
            try:
                target.symlink_to(foreign)
            except OSError:
                self.skipTest('Symlink creation unavailable on this host')
            with self.assertRaises(rc.WindowsRcError):
                rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
            self.assertEqual(foreign.read_bytes(), b'foreign')
            fetch.assert_not_called()

    def prepare_preflight(self, temporary):
        src, _payload, _pin, scope, fetch = self.fixture(temporary)
        rc.ensure_windows_rc(src, scope, lambda _: True, fetch)
        for relative in ['third_party/cpython3/host/bin/python3.exe', 'out/AlwaysActive/environment.x64']:
            file = src / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'fixture\0\0')
        return src

    def test_preflight_uses_real_wrapper_generated_env_and_compares_both_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            src = self.prepare_preflight(temporary)
            resource_data = struct.pack('<II', 0, 32) + b'\0' * 24 + b'\x34\x12\xcd\xab'
            def run(command, **kwargs):
                self.assertEqual(command[:5], [str(src / 'third_party/cpython3/host/bin/python3.exe'),
                    str(src / 'build/toolchain/win/tool_wrapper.py'), 'rc-wrapper', 'environment.x64', 'rc.exe'])
                self.assertEqual(kwargs['cwd'], src / 'out/AlwaysActive')
                self.assertEqual(kwargs['timeout'], 30)
                self.assertTrue(kwargs['check'])
                self.assertIn('#define AACC_RC_WORD', Path(command[-1]).read_text())
                output = Path(command[-2][3:])
                output.write_bytes(resource_data)
                Path(str(output) + '_ms_rc').write_bytes(resource_data)
                return SimpleNamespace(stdout='', stderr='')
            result = rc.preflight_windows_rc(src, runner=run)
            self.assertEqual(result['resource_sha256'], hashlib.sha256(resource_data).hexdigest())
            self.assertEqual(json.loads((src.parent / 'windows-rc-preflight.json').read_text()), result)
            self.assertEqual(list(src.parent.glob('.aacc-rc-preflight-*')), [])

    def test_sdk_or_subprocess_failure_retains_safe_error_and_clears_stale_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            src = self.prepare_preflight(temporary)
            prior = src.parent / 'windows-rc-preflight.json'
            prior.write_text('{"status":"passed"}')
            failure = subprocess.CalledProcessError(7, ['private command'], output='private output')
            with self.assertRaises(rc.WindowsRcError) as caught:
                rc.preflight_windows_rc(src, runner=mock.Mock(side_effect=failure))
            self.assertEqual(caught.exception.exit_code, 7)
            self.assertNotIn('private', str(caught.exception))
            self.assertFalse(prior.exists())
            self.assertEqual(list(src.parent.glob('.aacc-rc-preflight-*')), [])

    def test_disagreeing_resource_outputs_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            src = self.prepare_preflight(temporary)
            def run(command, **_kwargs):
                output = Path(command[-2][3:])
                output.write_bytes(struct.pack('<II', 0, 32) + b'\0' * 24 + b'\x34\x12\xcd\xab')
                Path(str(output) + '_ms_rc').write_bytes(b'different data' * 3)
                return SimpleNamespace(stdout='', stderr='')
            with self.assertRaisesRegex(rc.WindowsRcError, 'resource_comparison_failed'):
                rc.preflight_windows_rc(src, runner=run)
            self.assertFalse((src.parent / 'windows-rc-preflight.json').exists())


if __name__ == '__main__':
    unittest.main()
