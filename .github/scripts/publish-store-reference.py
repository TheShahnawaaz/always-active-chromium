"""Publish a fixed allowlist of bounded, non-profile Store inspection evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    project = Path(__file__).resolve().parents[2]
    platform = os.environ['AA_PLATFORM']
    if platform not in ('mac-arm64', 'win-x64'):
        raise RuntimeError('Unexpected Store preflight platform')
    repository = os.environ['GITHUB_REPOSITORY']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    phase = os.environ.get('AA_STORE_PHASE', 'preflight')
    if phase not in ('preflight', 'permission-dialog'):
        raise RuntimeError('Unexpected Store inspection phase')
    destination = project / 'packages/store-reference'
    destination.mkdir(parents=True, exist_ok=True)
    selected = []
    sources = [
        (project / 'reports/store/results.json', f'{platform}-store-results.json'),
        (project / os.environ['AA_REFERENCE_ROOT'] / 'reference-provenance.json',
         f'{platform}-reference-provenance.json'),
    ]
    for source, name in sources:
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file() or source.stat().st_size > (1 << 20):
            raise RuntimeError('Refusing nonregular or oversized preflight evidence')
        json.loads(source.read_text(encoding='utf-8'))
        target = destination / name
        shutil.copy2(source, target)
        selected.append(target)
    status = {
        'schema': 1,
        'repository_commit': os.environ['GITHUB_SHA'],
        'run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'platform': platform,
        'inspection_outcome': os.environ['AA_STORE_OUTCOME'],
        'phase': phase,
        'scope': ('Read-only official CFT Store page and owned native UI prerequisites. '
                  if phase == 'preflight' else
                  'Official CFT Store Add click and inspection of the unaccepted native permission dialog. ')
                 + 'No permission acceptance, completed extension installation, update, removal, '
                   'or custom native-browser verification is established.',
    }
    metadata = destination / f'{platform}-store-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{platform}-store-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n'
                            for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nThe draft tag is a default-branch storage anchor. '
        'Actual controller commit and exact reference package hashes are attached. '
        'Only finite JSON and checksums are uploaded; profiles, logs, binaries, '
        'browser packages and extension source are excluded.\n', encoding='utf-8')
    kind = 'store-reference' if phase == 'preflight' else 'store-dialog'
    tag = f'{kind}-{platform}-{run_id}-{attempt}'
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft',
        '--title', f'Store {phase}: {platform}', '--notes-file', str(notes)], check=True)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, str(item), '--repo', repository], check=True)
    subprocess.run(['gh', 'release', 'view', tag, '--repo', repository, '--json', 'url'], check=True)


if __name__ == '__main__':
    main()
