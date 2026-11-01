#!/usr/bin/env python3
"""Run all native-browser modes with isolated fixture profiles and bounded time."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from build import PROJECT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    modes = [
        ('baseline', ['--mode', 'baseline', '--disable-features', 'AlwaysActive']),
        ('native', ['--mode', 'native']),
        ('optional', ['--mode', 'native', '--features', 'AlwaysActiveFullscreen,AlwaysActiveBlockBackgroundReload']),
    ]
    variants = {}
    logs = []
    failed = False
    for name, flags in modes:
        destination = args.output / name
        command = ['node', str(PROJECT / 'tests/run.mjs'), '--browser', args.browser,
                   *flags, '--output', str(destination)]
        print(f'Running built-browser verification: {name}', flush=True)
        try:
            # Each output directory owns a distinct temporary browser profile.
            # Three five-minute bounds leave room inside the workflow's 20min step.
            process = subprocess.Popen(command,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            code = process.wait(timeout=300)
            error = None
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               check=False, timeout=30)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
            code = 124
            error = 'Test process exceeded its five-minute limit.'
        record = {'exit_code': code, 'error': error, 'flags': flags}
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
        if (destination / 'browser.log').is_file():
            logs.append(f'===== {name} =====\n' + (destination / 'browser.log').read_text(errors='replace'))
    (args.output / 'results.json').write_text(json.dumps({
        'schema': 1, 'status': 'failed' if failed else 'passed', 'variants': variants,
        'scope': 'Built-browser baseline, native defaults and optional native flags. '
                 'Inspect per-check coverage; automation does not substitute for install/Web Store review.'
    }, indent=2) + '\n')
    (args.output / 'browser.log').write_text('\n'.join(logs))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
