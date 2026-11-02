"""Retain only the bounded input-audit JSON before saving a large checkpoint."""
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
        raise ValueError('Unexpected build diagnostic platform')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Unexpected repository identity')
    if not re.fullmatch(r'[0-9]+', run_id) or not re.fullmatch(r'[0-9]+', attempt):
        raise ValueError('Unexpected workflow run identity')
    source_commit = env['AA_SOURCE_COMMIT']
    workflow_commit = env['GITHUB_SHA']
    if any(not re.fullmatch(r'[0-9a-f]{40}', value)
           for value in (source_commit, workflow_commit)):
        raise ValueError('Unexpected source/workflow commit')
    outcome = env['AA_AUDIT_OUTCOME']
    if outcome not in ('success', 'failure', 'cancelled', 'skipped'):
        raise ValueError('Unexpected audit outcome')

    destination = project / 'packages/build-diagnostics'
    destination.mkdir(parents=True, exist_ok=True)
    selected = []
    source = project / 'reports' / platform / 'input-audit.json'
    audit_status = None
    if source.exists() or source.is_symlink():
        if source.is_symlink() or not source.is_file() or source.stat().st_size > (2 << 20):
            raise ValueError('Refusing nonregular or oversized input audit')
        payload = source.read_bytes()
        audit = json.loads(payload)
        if (not isinstance(audit, dict) or audit.get('schema') != 1
                or audit.get('platform') != platform
                or audit.get('status') not in ('pass', 'missing', 'incomplete', 'error')):
            raise ValueError('Unexpected input-audit schema or identity')
        audit_status = audit['status']
        target = destination / f'{platform}-input-audit.json'
        target.write_bytes(payload)
        selected.append(target)

    status = {
        'schema': 1,
        'source_commit': source_commit,
        'workflow_commit': workflow_commit,
        'platform': platform,
        'run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'audit_step_outcome': outcome,
        'audit_report_available': audit_status is not None,
        'audit_report_status': audit_status,
        'scope': 'Read-only existence audit of declared leaf inputs in selected Ninja target graphs. '
                 'This establishes neither compilation success nor native browser behavior. '
                 'Only finite JSON and checksums are retained; raw tool logs, profiles, '
                 'source archives and build outputs are excluded.',
    }
    metadata = destination / f'{platform}-diagnostic-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{platform}-diagnostic-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n'
                            for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nThis draft tag is a default-branch storage '
                     'anchor. Attached metadata records the immutable source and workflow commits.\n',
                     encoding='utf-8')
    return f'build-inputs-{platform}-{run_id}-{attempt}', notes, selected


def main():
    project = Path(__file__).resolve().parents[2]
    tag, notes, selected = collect(project, os.environ)
    repository = os.environ['GITHUB_REPOSITORY']
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft',
                    '--title', f'Build input audit: {os.environ["AA_PLATFORM"]}',
                    '--notes-file', str(notes)], check=True, timeout=120)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, str(item), '--repo', repository],
                       check=True, timeout=120)
    subprocess.run(['gh', 'release', 'view', tag, '--repo', repository, '--json', 'url'],
                   check=True, timeout=120)


if __name__ == '__main__':
    main()
