"""Publish only finite reference results; never profiles or extension packages."""
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
        raise RuntimeError('Unexpected reference platform')
    repo = os.environ['GITHUB_REPOSITORY']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    destination = project / 'packages/reference'
    destination.mkdir(parents=True, exist_ok=True)
    selected = []
    for mode in ('baseline', 'oracle'):
        for name in ('results.json', 'browser.log'):
            source = project / 'reports' / mode / name
            if source.is_file():
                target = destination / f'{platform}-{mode}-{name}'
                shutil.copy2(source, target)
                selected.append(target)
    source = Path(os.environ['AA_REFERENCE_ROOT']) / 'reference-provenance.json'
    if source.is_file():
        target = destination / f'{platform}-reference-provenance.json'
        shutil.copy2(source, target)
        selected.append(target)
    metadata = destination / f'{platform}-reference-status.json'
    status = {
        'repository_commit': os.environ['GITHUB_SHA'],
        'run_url': f'https://github.com/{repo}/actions/runs/{run_id}',
        'platform': platform,
        'baseline_outcome': os.environ['AA_BASELINE_OUTCOME'],
        'oracle_outcome': os.environ['AA_ORACLE_OUTCOME'],
        'scope': 'Official unmodified CFT and exact shipped reference extension, not a custom native build.'
    }
    metadata.write_text(json.dumps(status, indent=2) + '\n')
    selected.append(metadata)
    checksums = destination / f'{platform}-reference-SHA256SUMS.txt'
    checksums.write_text(''.join(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
        for path in sorted(selected)))
    selected.append(checksums)
    notes = destination / '.reference-notes.txt'
    notes.write_text(
        f'Reference measurements on {platform}.\n\n'
        f'Baseline: {status["baseline_outcome"]}; extension oracle: {status["oracle_outcome"]}.\n'
        'These reports measure official Chrome for Testing and the shipped extension. '
        f'The test controller commit is {status["repository_commit"]}. '
        'The release tag is a storage anchor on the default branch. '
        'They are not custom-browser artifacts or evidence of native implementation success. '
        'Failed or uncovered checks remain visible in the attached JSON. '
        'Profiles and extension/browser packages are excluded.\n')
    tag = f'reference-{platform}-{run_id}-{attempt}'
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repo, '--draft',
                    '--title', f'Reference behavior: {platform}',
                    '--notes-file', str(notes)], check=True)
    for path in selected:
        subprocess.run(['gh', 'release', 'upload', tag, str(path), '--repo', repo], check=True)
    subprocess.run(['gh', 'release', 'view', tag, '--repo', repo, '--json', 'url'], check=True)


if __name__ == '__main__':
    main()
