#!/usr/bin/env python3
"""Upload genuine packages and narrowly selected test evidence to a draft release."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from build import PROJECT, PINS, final_release_tag, require_tag, sha256, source_commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True, choices=['mac-arm64', 'win-x64'])
    parser.add_argument('--test-outcome', required=True)
    args = parser.parse_args()
    repo = os.environ['GITHUB_REPOSITORY']
    packages = PROJECT / 'packages'
    stem = f'always-active-chromium-{PINS["version"]}-{args.platform}'
    tag = final_release_tag(args.platform)
    # The actual final tag is created by the authorized repository owner before
    # the build, never inferred from a moving storage anchor or workflow HEAD.
    require_tag(tag, source_commit())
    # Browser profiles, installed extension fixtures, cookies and local storage
    # are deliberately excluded from release assets.
    report = PROJECT / 'reports' / args.platform
    for name in ('results.json', 'browser.log'):
        if (report / name).is_file():
            shutil.copy2(report / name, packages / f'{stem}-{name}')
    (packages / f'{stem}-test-status.json').write_text(json.dumps({
        'workflow_test_outcome': args.test_outcome,
        'run_url': f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}',
        'scope': 'Automated test evidence only; install and interactive extension-store checks still require review.'
    }, indent=2) + '\n')
    sums = packages / f'{stem}-SHA256SUMS.txt'
    sums.write_text(''.join(f'{sha256(path)}  {path.name}\n' for path in sorted(packages.glob(stem + '*')) if path != sums))
    notes = packages / '.release-notes.txt'
    notes.write_text(f'Chromium {PINS["version"]}, {args.platform}, native always-active patch.\n\n'
        f'Automated test step: {args.test_outcome}. Inspect the attached results and build provenance.\n'
        'Unsigned development build: no Apple Developer ID/notarization or Windows Authenticode certificate.\n'
        'Standard Chromium UI and extension platform retained. This is Chromium, not Google Chrome.\n'
        'This release stays a draft for review; its existence is not proof of complete platform verification.\n')
    existing = subprocess.run(['gh', 'release', 'view', tag, '--repo', repo, '--json', 'isDraft'],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        if not json.loads(existing.stdout)['isDraft']:
            raise RuntimeError('Refusing to replace an already published release')
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', repo, '--notes-file', str(notes)], check=True)
    else:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', repo, '--draft', '--verify-tag',
            '--title', stem, '--notes-file', str(notes)], check=True)
    for path in sorted(packages.glob(stem + '*')):
        subprocess.run(['gh', 'release', 'upload', tag, str(path), '--repo', repo, '--clobber'], check=True)
    subprocess.run(['gh', 'release', 'view', tag, '--repo', repo, '--json', 'url'], check=True)


if __name__ == '__main__':
    main()
