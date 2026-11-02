"""Pinned Ninja progress/no-progress proofs and finite diagnostic privacy."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import build
import compile_diagnostics as diagnostic


class CompileDiagnosticsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ninja'), 'Real Ninja fixture required')
    def test_actual_compile_controller_writes_early_report_and_progress_output(self):
        ninja = Path(shutil.which('ninja')).resolve()
        if not diagnostic.verify_version(ninja):
            self.skipTest('Exact pinned Ninja1.12.1 required')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'build-root'
            source = root / 'src'
            out = source / 'out/AlwaysActive'
            out.mkdir(parents=True)
            platform = 'win-x64' if os.name == 'nt' else 'mac-arm64'
            binary = source / 'third_party/ninja' / ('ninja.exe' if os.name == 'nt' else 'ninja')
            binary.parent.mkdir(parents=True)
            shutil.copy2(ninja, binary)
            (out / 'build.ninja').write_text(f'rule bad\n  command = "{sys.executable}" -c "raise SystemExit(1)"\n'
                                           'build chrome: bad\nbuild mini_installer: phony chrome\n')
            (root / 'state.json').write_text('{}')
            project = Path(temporary) / 'project'
            with mock.patch.object(build, 'root_path', return_value=root), \
                    mock.patch.object(build, 'PROJECT', project), mock.patch.object(build, 'set_build_env'), \
                    mock.patch.object(build, 'output') as output, \
                    mock.patch.object(build.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(200 << 30, 50 << 30, 150 << 30)), \
                    mock.patch.dict(build.os.environ, {'AA_JOB_STARTED': str(time.time())}), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = build.compile_browser(platform, False)
            self.assertEqual(result, 1)
            self.assertIn(mock.call('status', 'failed'), output.call_args_list)
            self.assertIn(mock.call('no_new_completed_actions', 'true'), output.call_args_list)
            report = json.loads((project / 'reports' / platform / 'compile-diagnostics.json').read_text())
            self.assertTrue(report['checkpoint_reuse']['no_new_completed_actions'])
            self.assertEqual(report['status'], 'failed')

    @unittest.skipUnless(shutil.which('ninja'), 'Real Ninja fixture required')
    def test_real_pinned_ninja_absent_unchanged_and_successful_action_log_proofs(self):
        ninja = Path(shutil.which('ninja')).resolve()
        if not diagnostic.verify_version(ninja):
            self.skipTest('Exact pinned Ninja1.12.1 required')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'action.py').write_text('import pathlib,sys\n'
                'if sys.argv[1] == "ok": pathlib.Path(sys.argv[2]).write_text("success")\n'
                'else: print("ModuleNotFoundError: No module named \'fixture_module\'");sys.exit(1)\n')
            (root / 'build.ninja').write_text(
                f'rule ok\n  command = "{sys.executable}" action.py ok $out\n'
                f'rule bad\n  command = "{sys.executable}" action.py bad\n'
                'build good: ok\nbuild next_good: ok\nbuild failed: bad\n'
                'build before: bad absent_input\nbuild after_success: bad next_good\n')

            def attempt(target):
                before = diagnostic.snapshot_log(root / '.ninja_log')
                manifest = diagnostic.manifest_policy(root / 'build.ninja')
                process = subprocess.Popen([str(ninja), '-j', '1', target], cwd=root,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                collector = diagnostic.Collector(root)
                with contextlib.redirect_stdout(io.StringIO()) as console:
                    reader = diagnostic.start_capture(process, collector)
                    code = process.wait(timeout=10)
                    reader.join(timeout=5)
                self.assertTrue(collector.complete)
                after = diagnostic.snapshot_log(root / '.ninja_log')
                proof = diagnostic.no_completed_actions(before, after, manifest,
                    diagnostic.manifest_policy(root / 'build.ninja'), collector, 'failed', code, True)
                return before, after, proof, collector, console.getvalue()

            before, after, proof, _, _ = attempt('before')
            self.assertEqual(before['state'], 'absent')
            self.assertEqual(after['state'], 'absent')
            self.assertTrue(proof)
            before, after, proof, collector, output = attempt('failed')
            self.assertEqual((before['state'], after['state']), ('absent', 'absent'))
            self.assertTrue(proof)
            self.assertIn('fixture_module', output)  # normal console still forwarded
            self.assertIn({'kind': 'python_exception', 'exception': 'ModuleNotFoundError',
                           'module': 'fixture_module'}, collector.events)
            subprocess.run([str(ninja), 'good'], cwd=root, check=True, capture_output=True)
            before, after, proof, _, _ = attempt('failed')
            self.assertEqual(before['state'], 'valid')
            self.assertEqual(before, after)
            self.assertTrue(proof)
            before, after, proof, _, _ = attempt('after_success')
            self.assertEqual(after['state'], 'valid')
            self.assertNotEqual(before, after)
            self.assertFalse(proof)
            self.assertTrue((root / 'next_good').is_file())

    def test_missing_uncertain_logging_errors_and_nonfailure_stages_always_save(self):
        collector = diagnostic.Collector(Path('/fixture/src'))
        collector.feed(b'ninja: build stopped: subcommand failed.\n')
        collector.finish()
        manifest = {'valid': True, 'sha256': '1' * 64}
        absent = {'state': 'absent'}
        self.assertTrue(diagnostic.no_completed_actions(absent, absent, manifest, manifest,
                                                       collector, 'failed', 1, True))
        for status, code, version, state in [('pending', 1, True, absent), ('disk-blocked', 1, True, absent),
                                            ('failed', -9, True, absent), ('failed', 1, False, absent),
                                            ('failed', 1, True, {'state': 'uncertain'})]:
            self.assertFalse(diagnostic.no_completed_actions(state, state, manifest, manifest,
                                                             collector, status, code, version))
        collector.feed(b'ninja: build stopped: Error writing to build log: disk full\n')
        self.assertFalse(diagnostic.no_completed_actions(absent, absent, manifest, manifest,
                                                         collector, 'failed', 1, True))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.ninja_log').write_bytes(b'# ninja log v99\n')
            self.assertEqual(diagnostic.snapshot_log(root / '.ninja_log')['state'], 'uncertain')
            (root / 'build.ninja').write_text('builddir = elsewhere\n')
            self.assertFalse(diagnostic.manifest_policy(root / 'build.ninja')['valid'])

    def test_useful_structured_context_is_bounded_and_has_no_raw_secrets_or_urls(self):
        collector = diagnostic.Collector(Path('/fixture/src'))
        collector.feed(b'PRIVATE_TOKEN=super-private\nhttps://download.invalid/?token=super-private\n')
        collector.feed(b"FileNotFoundError: [Errno 2] No such file: '/fixture/src/tools/missing.exe'\n")
        collector.feed(b"FileNotFoundError: [Errno 2] No such file: 'https://download.invalid/?token=super-private'\n")
        collector.feed(b"../../third_party/example.cc:12:3: error: no member named 'MissingSymbol'\n")
        collector.feed(b'[1/58421] ACTION //build/rust/std:find_stdlib(//build/toolchain/win:win_clang_x64_for_rust_host_build_tools)\n')
        collector.feed(b'FAILED: obj/build/rust/libstd.rlib obj/build/rust/liballoc.rlib\n')
        collector.feed(b'  File "/fixture/src/build/rust/std/find_std_rlibs.py", line 64, in main\n')
        collector.feed(b'OSError: [WinError 193] %1 is not a valid Win32 application\n')
        for _ in range(100):
            collector.feed(b'RAW_PRIVATE_LONG=' + b'x' * 10000 + b'\n')
        collector.finish()
        text = json.dumps(collector.events)
        self.assertNotIn('super-private', text)
        self.assertNotIn('download.invalid', text)
        self.assertNotIn('PRIVATE_TOKEN', text)
        self.assertNotIn('RAW_PRIVATE_LONG', text)
        self.assertIn('tools/missing.exe', text)
        self.assertIn('MissingSymbol', text)
        self.assertIn('find_stdlib', text)
        self.assertIn('find_std_rlibs.py', text)
        self.assertIn('193', text)
        self.assertLess(len(text), 4096)
        self.assertLessEqual(len(collector.events), 24)
        self.assertEqual(collector.pending, b'')
        self.assertEqual(collector.oversized_lines, 100)

    def test_compile_publisher_selects_only_fixed_json_and_rejects_raw_fields(self):
        collect = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                    '.github/scripts/publish-build-diagnostics.py'))['collect']
        env = {'AA_DIAGNOSTIC_PHASE': 'compile', 'AA_PLATFORM': 'win-x64',
               'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
               'AA_SOURCE_COMMIT': '1' * 40, 'GITHUB_SHA': '1' * 40, 'AA_COMPILE_OUTCOME': 'failure'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'reports/win-x64/compile-diagnostics.json'
            report = {'schema': 1, 'platform': 'win-x64', 'status': 'failed', 'events': [],
                      'checkpoint_reuse': {'before': {'state': 'absent'}, 'after': {'state': 'absent'},
                                           'manifest_before': {'valid': True}, 'manifest_after': {'valid': True}}}
            diagnostic.write_report(path, report)
            (path.parent / 'raw.log').write_text('PRIVATE_RAW_LOG')
            tag, _, selected = collect(root, env)
            self.assertEqual(tag, 'build-compile-win-x64-123-1')
            self.assertEqual({item.name for item in selected}, {'win-x64-compile-diagnostics.json',
                'win-x64-compile-status.json', 'win-x64-compile-SHA256SUMS.txt'})
            self.assertTrue(all('PRIVATE_RAW_LOG' not in item.read_text() for item in selected))
            report['raw_log'] = 'PRIVATE_RAW_LOG'
            diagnostic.write_report(path, report)
            with self.assertRaises(ValueError):
                collect(root, env)

    def test_prepare_error_is_published_early_with_only_controlled_tool_detail(self):
        collect = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                    '.github/scripts/publish-build-diagnostics.py'))['collect']
        class ToolFailure(RuntimeError):
            code = 'rustc_host_mismatch'
            stage = 'validate_host'
            tool = 'rustc.exe'
            expected_host = 'x86_64-pc-windows-msvc'
            observed_host = 'x86_64-unknown-linux-gnu'
            exit_code = 193
        env = {'AA_DIAGNOSTIC_PHASE': 'prepare', 'AA_PLATFORM': 'win-x64',
               'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
               'AA_SOURCE_COMMIT': '1' * 40, 'GITHUB_SHA': '1' * 40, 'AA_PREPARE_OUTCOME': 'failure'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(build, 'PROJECT', root):
                build.prepare_diagnostic(root / 'src', 'win-x64', ToolFailure('PRIVATE_RAW_ENV=https://secret.invalid'))
            tag, _, selected = collect(root, env)
            self.assertEqual(tag, 'build-prepare-win-x64-123-1')
            self.assertEqual({item.name for item in selected}, {'win-x64-prepare-diagnostics.json',
                'win-x64-prepare-status.json', 'win-x64-prepare-SHA256SUMS.txt'})
            report = json.loads((root / 'reports/win-x64/prepare-diagnostics.json').read_text())
            self.assertEqual(report['events'][0]['code'], 'rustc_host_mismatch')
            self.assertEqual(report['events'][0]['exit_code'], 193)
            self.assertTrue(all('PRIVATE_RAW_ENV' not in item.read_text() and
                                'secret.invalid' not in item.read_text() for item in selected))


if __name__ == '__main__':
    unittest.main()
