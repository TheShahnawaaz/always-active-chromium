"""Verify the final publisher's token path without creating a browser release."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('This probe is restricted to an ephemeral hosted runner.')
    tag = os.environ['AA_PROBE_TAG']
    if not re.fullmatch(r'ci-auth-probe-[0-9a-f]{12}', tag):
        raise RuntimeError('Only an explicitly pre-created auth-probe tag is allowed.')
    repo = os.environ['GITHUB_REPOSITORY']
    reference = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{repo}/git/ref/tags/{tag}'], text=True))
    present = subprocess.run(['gh', 'release', 'view', tag, '--repo', repo],
                             capture_output=True, text=True)
    if present.returncode == 0:
        raise RuntimeError('Refusing to replace an existing release during this probe.')
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='aacc-release-probe-') as temporary:
            directory = Path(temporary)
            payload = directory / 'auth-probe.json'
            payload.write_text(json.dumps({
                'purpose': 'Permission test only; no browser binary or user profile.',
                'source_ref': reference,
                'workflow_commit': os.environ['GITHUB_SHA'],
                'run_id': os.environ['GITHUB_RUN_ID']
            }, indent=2) + '\n', encoding='utf-8')
            subprocess.run(['gh', 'release', 'create', tag, '--repo', repo,
                '--draft', '--verify-tag', '--title', 'Temporary release permission probe',
                '--notes', 'Temporary CI permission check. Not an installable browser. '
                'This draft is deleted after the upload/download test.'], check=True)
            created = True
            subprocess.run(['gh', 'release', 'upload', tag, str(payload), '--repo', repo], check=True)
            downloaded = directory / 'downloaded'
            subprocess.run(['gh', 'release', 'download', tag, '--repo', repo,
                '--pattern', payload.name, '--dir', str(downloaded)], check=True)
            expected = hashlib.sha256(payload.read_bytes()).hexdigest()
            actual = hashlib.sha256((downloaded / payload.name).read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError('Draft asset roundtrip SHA-256 mismatch.')
            print(json.dumps({'status': 'passed', 'existing_tag': tag,
                'source_ref': reference['object'], 'asset_sha256': actual,
                'publisher_arguments': 'draft + verify-tag, no target override'}), flush=True)
    finally:
        if created:
            subprocess.run(['gh', 'release', 'delete', tag, '--repo', repo, '--yes'], check=True)
            print('Temporary draft deleted; pre-created Git tag preserved.', flush=True)


if __name__ == '__main__':
    main()
