"""Publish only finite normal-Store results from official reference browsers."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def collect(project, env):
    platform = env['AA_PLATFORM']
    repository = env['GITHUB_REPOSITORY']
    run_id = env['GITHUB_RUN_ID']
    attempt = env.get('GITHUB_RUN_ATTEMPT', '1')
    if platform not in ('mac-arm64', 'win-x64'):
        raise ValueError('Unexpected reference platform')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Unexpected repository identity')
    if not run_id.isdigit() or not attempt.isdigit():
        raise ValueError('Unexpected run identity')
    destination = project / 'packages/store-compat-reference'
    destination.mkdir(parents=True, exist_ok=True)
    selected = []
    report_status = None
    sources = [
        (project / 'reports/store-compat/results.json', f'{platform}-store-compat-results.json', True),
        (project / env['AA_REFERENCE_ROOT'] / 'reference-provenance.json', f'{platform}-reference-provenance.json', False),
    ]
    for source, name, is_report in sources:
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink() or not source.is_file() or source.stat().st_size > (1 << 20):
            raise ValueError('Refusing nonregular or oversized Store evidence')
        payload = source.read_bytes()
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError('Expected JSON object')
        if is_report:
            expected_os = 'darwin' if platform == 'mac-arm64' else 'win32'
            if (data.get('schema') != 1 or data.get('stage') != 'normal-store-compatibility'
                    or data.get('platform') != expected_os
                    or data.get('target', {}).get('id') != 'ddkjiahejlhfcafbddmgiahcphecmpfh'
                    or data.get('status') not in ('passed', 'failed')):
                raise ValueError('Unexpected Store report identity or stage')
            report_status = data['status']
        target = destination / name
        target.write_bytes(payload)
        selected.append(target)
    status = {
        'schema': 1,
        'controller_commit': env['GITHUB_SHA'],
        'run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'platform': platform,
        'inspection_outcome': env['AA_STORE_OUTCOME'],
        'report_status': report_status,
        'browser_kind': 'official-chrome-for-testing-reference',
        'custom_native_browser_verified': False,
        'scope': 'Normal Store compatibility mechanics on the pinned official reference browser. '
                 'Read each phase and action receipt for actual outcomes. This is not custom '
                 'native-browser verification or evidence of a genuine newer Store version upgrade.',
        'provenance_limit': 'Reference acquisition metadata also describes the original Always Active CRX; '
                            'that CRX was not loaded. Installed uBOL identity/source checks are in the results.',
    }
    metadata = destination / f'{platform}-store-compat-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{platform}-store-compat-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n'
                            for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nDefault-branch draft storage anchor; attached metadata '
                     'records the controller commit and reference package identity. Only finite JSON '
                     'and checksums are uploaded. Profiles, logs, extension code/packages and browser '
                     'binaries are excluded.\n', encoding='utf-8')
    return f'store-compat-reference-{platform}-{run_id}-{attempt}', notes, selected


def main():
    tag, notes, selected = collect(Path(__file__).resolve().parents[2], os.environ)
    repository = os.environ['GITHUB_REPOSITORY']
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft',
                    '--title', f'Normal Store reference: {os.environ["AA_PLATFORM"]}',
                    '--notes-file', str(notes)], check=True, timeout=120)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, str(item), '--repo', repository],
                       check=True, timeout=120)


if __name__ == '__main__':
    main()
