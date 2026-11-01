#!/usr/bin/env python3
"""Bounded continuation using GitHub's workflow_dispatch token exception."""
import os
import subprocess

stage = int(os.environ['AA_STAGE'])
limit = int(os.environ['AA_MAX_STAGES'])
if not 1 <= limit <= 100 or not 0 <= stage < 100:
    raise RuntimeError('Stage bounds must be between 1 and 100')
if stage + 1 >= limit:
    print(f'Stopped automatically at {limit} stages; the complete checkpoint remains resumable.')
else:
    subprocess.run(['gh', 'workflow', 'run', 'build.yml', '--repo', os.environ['GITHUB_REPOSITORY'],
        '--ref', os.environ['GITHUB_REF_NAME'],
        '--field', f'platform={os.environ["AA_PLATFORM"]}',
        '--field', f'build_ref={os.environ.get("AA_SOURCE_TAG", os.environ["AA_BUILD_REF"])}',
        '--field', f'stage={stage + 1}', '--field', f'max_stages={limit}',
        '--field', 'auto_resume=true', '--field', 'bootstrap_only=false',
        '--field', f'migrate_native={os.environ.get("AA_MIGRATE_NATIVE", "false")}'], check=True)
