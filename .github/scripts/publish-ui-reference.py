"""Retain one owned CFT window image for manual review; never native proof."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess


def collect(project, env):
    repository, run_id = env['GITHUB_REPOSITORY'], env['GITHUB_RUN_ID']
    attempt = env.get('GITHUB_RUN_ATTEMPT', '1')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not run_id.isdigit() or
            not attempt.isdigit() or not re.fullmatch(r'[0-9a-f]{40}', env['GITHUB_SHA'])):
        raise ValueError('Invalid reference evidence identity')
    policy = runpy.run_path(str(project / '.github/scripts/publish-delivery.py'))
    destination = project / 'packages/ui-reference'
    destination.mkdir(parents=True, exist_ok=True)
    sources = [
        ('reports/ui-reference/results.json', 'results', 1048576),
        ('reports/ui-reference/browser-window-capture.json', 'capture', 65536),
        ('.runtime/ui-reference/reference-provenance.json', 'provenance', 1048576),
    ]
    selected, records, errors = [], {}, []
    for relative, kind, maximum in sources:
        source = project / relative
        if not source.exists() and not source.is_symlink():
            continue
        try:
            if (source.is_symlink() or not source.is_file() or source.stat().st_size > maximum or
                    not source.resolve().is_relative_to(project.resolve())):
                raise ValueError('Unsafe evidence file')
            payload = source.read_bytes()
            data = json.loads(payload)
            if not isinstance(data, dict) or data.get('schema') != 1:
                raise ValueError('Invalid evidence schema')
        except (OSError, ValueError):
            errors.append({'kind': kind, 'reason': 'invalid_or_unsafe_json'})
            continue
        records[kind] = data
        copied = destination / f'win-x64-ui-reference-{kind}.json'
        copied.write_bytes(payload)
        selected.append(copied)
    result, capture, provenance = (records.get(key, {}) for key in ['results', 'capture', 'provenance'])
    expected = env.get('AA_REFERENCE_BROWSER', '')
    normal_control, diagnostic_capture, image_integrity, image_metadata = False, False, False, None
    try:
        runs = result.get('runs', [])
        run = runs[0] if len(runs) == 1 else {}
        names = {item.get('name') for item in run.get('tests', [])}
        owned_control = (result.get('mode') == 'control' and
            result.get('interrupted', 'missing') is None and result.get('platform') == 'win32' and
            result.get('architecture') == 'x64' and result.get('expectedVersion') == '156.0.8078.80' and
            run.get('mode') == 'control' and
            policy['same_executable'](run.get('command', {}).get('executable'), expected, 'win-x64') and
            type(run.get('ownedPid')) is int and run['ownedPid'] > 1 and
            run.get('processIdentity', {}).get('pid') == run['ownedPid'] and
            run.get('processIdentity', {}).get('owned') is True and run.get('cleanup', {}).get('rootGone') is True and
            provenance.get('platform') == 'win64' and provenance.get('version') == '156.0.8078.80' and
            provenance.get('expected_revision') == 'fb096c0011f9d50f0a264a9376420cdea9c421e3' and
            provenance.get('cft', {}).get('sha256') == '16edb57d6107bf1c48a7c149b8d78b155fe614410093796dd72441fd6640540f')
        guard_names = {'owned profile exposes no remote debugging port file',
            'normal launch has no debugging, automation, extension, or emulation flags',
            'verified owned browser process cleanup completes'}
        guards_passed = all(len(matches := [item for item in run.get('tests', []) if item.get('name') == name]) == 1 and
                            matches[0].get('status') == 'passed' for name in guard_names)
        normal_control = (owned_control and result.get('status') == 'passed' and run.get('status') == 'passed' and
            policy['passed_checks'](run.get('tests')) and guards_passed and
            'at least one control website is genuinely hidden and unfocused' in names)
        diagnostic_capture = (owned_control and guards_passed and env.get('AA_FAILED_STARTUP_CAPTURE') == '1' and
            result.get('status') == 'failed' and run.get('status') == 'failed' and
            any(item.get('status') == 'failed' for item in run.get('tests', [])) and
            capture.get('captureContext') == 'startup-diagnostic')
        png = project / 'reports/ui-reference/browser-window.png'
        if normal_control or diagnostic_capture:
            if run.get('appearance', {}).get('status') != 'captured' or run.get('appearance', {}).get('receipt') != capture:
                raise ValueError('Capture is not the selected normal-launch receipt')
            image_metadata = policy['validate_appearance_capture'](capture, png, expected_executable=expected,
                expected_pid=run['ownedPid'], expected_started=run.get('processIdentity', {}).get('started'),
                expected_profile=str((project / 'reports/ui-reference/profile-control').resolve()),
                allow_startup_diagnostic=diagnostic_capture)
            identity = capture.get('identity', {})
            if (identity.get('pid') != run.get('ownedPid') or
                    identity.get('started') != run.get('processIdentity', {}).get('started')):
                raise ValueError('Capture and normal-launch identities differ')
            copied = destination / 'win-x64-ui-reference-window.png'
            copied.write_bytes(png.read_bytes())
            selected.append(copied)
            image_integrity = True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        errors.append({'kind': 'capture', 'reason': 'normal_launch_or_image_binding_unverified'})
    verified = normal_control and image_integrity and not errors and env.get('AA_INSPECTION_OUTCOME') == 'success'
    status = {'schema': 1, 'platform': 'win-x64', 'controller_commit': env['GITHUB_SHA'],
        'run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'browser_kind': 'official-chrome-for-testing-reference',
        'status': 'retained-for-manual-review' if verified else 'failed',
        'normal_launch_observation_verified': bool(normal_control),
        'capture_context': 'startup-diagnostic' if diagnostic_capture and image_integrity else 'fixture' if image_integrity else None,
        'failed_startup_diagnostic_retained': bool(diagnostic_capture and image_integrity),
        'capture_file_and_identity_verified': bool(image_integrity), 'capture_metadata': image_metadata,
        'custom_native_browser_verified': False, 'appearance_equivalence_verified': False,
        'manual_review': 'pending' if image_integrity else 'unavailable', 'errors': errors,
        'reference_acquisition_limit': 'The original CRX described in acquisition metadata is not loaded by this normal-launch trial.',
        'scope': 'One bounded application-rendered owned reference window capture and passive normal-launch evidence. '
                 'File/API success does not prove complete rendered pixels or visual equivalence. '
                 'This is not custom-browser, real-package or native-feature verification.'}
    metadata = destination / 'win-x64-ui-reference-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / 'win-x64-ui-reference-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n'
                            for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nFixed finite JSON, one owned-window PNG and checksums only; '
                     'profiles, logs, source/extensions and browser packages are excluded.\n', encoding='utf-8')
    return f'ui-reference-win-x64-{run_id}-{attempt}', notes, selected, verified


def main():
    tag, notes, selected, verified = collect(Path(__file__).resolve().parents[2], os.environ)
    subprocess.run(['gh', 'release', 'create', tag, '--repo', os.environ['GITHUB_REPOSITORY'], '--draft',
                    '--title', 'Normal Windows reference window', '--notes-file', notes], check=True, timeout=120)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, item, '--repo', os.environ['GITHUB_REPOSITORY']],
                       check=True, timeout=120)
    return 0 if verified else 1


if __name__ == '__main__':
    raise SystemExit(main())
