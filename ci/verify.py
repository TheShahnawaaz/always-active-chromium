#!/usr/bin/env python3
"""Run all native-browser modes with isolated fixture profiles and bounded time."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from build import PROJECT


def executable_identity(file):
    original = Path(file)
    canonical = original.resolve(strict=True)
    if original.is_symlink() or not canonical.is_file():
        raise ValueError('A regular delivered browser executable is required')
    digest = hashlib.sha256()
    with canonical.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'executable': str(canonical), 'sha256': digest.hexdigest(), 'size': canonical.stat().st_size}


def cleanup_timeout(process, variant, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    report = {'controller_exited': False, 'detached_browser_cleanup_uncertain': variant == 'no-debug'}
    if variant == 'no-debug' and not windows:
        # This controller owns detached browser groups and traps SIGTERM to run
        # verified PID/profile cleanup. Killing its group first would orphan them.
        report['method'] = 'controller-sigterm'
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=30)
            report['controller_exited'] = True
            report['note'] = 'Timed-out run remains a failure; inspect the harness owned-process cleanup evidence.'
            return report
        except ProcessLookupError:
            report['controller_exited'] = True
            return report
        except subprocess.TimeoutExpired:
            report['method'] = 'forced-controller-group-after-sigterm'
    else:
        report['method'] = 'windows-process-tree' if windows else 'process-group'
    try:
        if windows:
            result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                    check=False, timeout=30)
            if result.returncode:
                report['cleanup_error'] = f'taskkill returned {result.returncode}'
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=30)
        report['controller_exited'] = True
    except (OSError, subprocess.TimeoutExpired) as problem:
        report['cleanup_error'] = str(problem)
    if variant == 'no-debug':
        report['note'] = 'Detached browser cleanup after a late timeout is uncertain; this run cannot verify native operation.'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    initial_executable = executable_identity(args.browser)
    args.browser = initial_executable['executable']
    args.output.mkdir(parents=True, exist_ok=True)
    modes = [
        ('baseline', 'run.mjs', ['--mode', 'baseline', '--disable-features', 'AlwaysActive'], 240),
        ('native', 'run.mjs', ['--mode', 'native'], 240),
        ('optional', 'run.mjs', ['--mode', 'native', '--features', 'AlwaysActiveFullscreen,AlwaysActiveBlockBackgroundReload'], 240),
        ('no-debug', 'no-debug.mjs', [], 180),
    ]
    variants = {}
    logs = []
    failed = False
    for name, entrypoint, flags, limit in modes:
        destination = args.output / name
        command = ['node', str(PROJECT / 'tests' / entrypoint), '--browser', args.browser,
                   *flags, '--output', str(destination)]
        print(f'Running built-browser verification: {name}', flush=True)
        try:
            # Each output directory owns a distinct temporary browser profile.
            # 3x4min + 3min paired no-debug = 15min, with bounded cleanup
            # reserved for timeout process-tree cleanup inside the 20min step.
            process = subprocess.Popen(command,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            code = process.wait(timeout=limit)
            error = None
            timeout_report = None
        except subprocess.TimeoutExpired:
            timeout_report = cleanup_timeout(process, name)
            code = 124
            error = f'Test process exceeded its {limit}-second limit.'
        record = {'exit_code': code, 'error': error, 'flags': flags, 'timeout_cleanup': timeout_report}
        if (destination / 'results.json').is_file():
            try:
                record['results'] = json.loads((destination / 'results.json').read_text())
            except (ValueError, OSError) as problem:
                record['results'] = None
                record['error'] = f'Cannot read harness results: {problem}'
                code = code or 1
        else:
            record['results'] = None
            record['error'] = record['error'] or 'The browser harness did not produce results.json.'
            code = code or 1
        variants[name] = record
        failed = failed or code != 0
        # The zero-debug report alone is publishable; never collect its profile
        # directories or per-process *-browser.log files.
        if name != 'no-debug' and (destination / 'browser.log').is_file():
            logs.append(f'===== {name} =====\n' + (destination / 'browser.log').read_text(errors='replace'))
    try:
        final_executable = executable_identity(args.browser)
    except (OSError, ValueError):
        final_executable = None
    unchanged = final_executable == initial_executable
    failed = failed or not unchanged
    (args.output / 'results.json').write_text(json.dumps({
        'schema': 1, 'status': 'failed' if failed else 'passed', 'variants': variants,
        'executable_binding': {'initial': initial_executable, 'final': final_executable, 'unchanged': unchanged},
        'scope': 'Built-browser baseline, native defaults, optional native flags, and paired zero-debugger control/native checks. '
                 'Inspect per-check coverage; automation does not substitute for install/Web Store review.'
    }, indent=2) + '\n')
    (args.output / 'browser.log').write_text('\n'.join(logs))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
