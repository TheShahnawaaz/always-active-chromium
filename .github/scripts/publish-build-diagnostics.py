"""Retain fixed bounded build/signing JSON before a large checkpoint."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


def validate_package_report(report):
    allowed = {'schema', 'platform', 'status', 'stage', 'code', 'scope', 'counts', 'parts', 'source_unchanged'}
    if (set(report) - allowed or report.get('platform') != 'mac-arm64' or
            report.get('status') not in ('complete', 'failed') or
            not isinstance(report.get('stage'), str) or not re.fullmatch(r'[a-z0-9_-]{1,80}', report['stage']) or
            report.get('code') is not None and (not isinstance(report['code'], str) or not re.fullmatch(r'[a-z0-9_]{1,100}', report['code'])) or
            not isinstance(report.get('scope'), str) or len(report['scope']) > 1024 or
            report.get('source_unchanged') is not None and type(report['source_unchanged']) is not bool):
        raise ValueError('Unexpected Mac package diagnostic fields')
    counts = report.get('counts')
    if (not isinstance(counts, dict) or set(counts) != {'files', 'macho', 'bundles', 'planned', 'signed', 'verified'} or
            any(type(value) is not int or not 0 <= value <= 1000000 for value in counts.values())):
        raise ValueError('Unexpected Mac package counts')
    parts = report.get('parts')
    if not isinstance(parts, list) or len(parts) > 48:
        raise ValueError('Unexpected Mac package inventory')
    for part in parts:
        if not isinstance(part, dict) or set(part) - {'path', 'kind', 'identifier', 'baseline', 'after'}:
            raise ValueError('Unexpected package part fields')
        path = part.get('path')
        identifier = part.get('identifier')
        if (not isinstance(path, str) or not 1 <= len(path) <= 1024 or
                any(char in path for char in ['\\', '\n', '\r', '\0']) or PurePosixPath(path).is_absolute() or
                '..' in PurePosixPath(path).parts or part.get('kind') not in ('bundle', 'macho') or
                identifier is not None and (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_. -]{1,256}', identifier))):
            raise ValueError('Unexpected package part identity')
        for field in ('baseline', 'after'):
            value = part.get(field)
            if field == 'after' and value is None:
                continue
            if (not isinstance(value, dict) or set(value) != {'signature', 'flags', 'enforcement_flags', 'entitlements_sha256'} or
                    value.get('signature') not in ('unsigned', 'adhoc', 'non-adhoc') or
                    any(type(value.get(key)) is not int or not 0 <= value[key] <= 0xffffffff for key in ('flags', 'enforcement_flags')) or
                    not isinstance(value.get('entitlements_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', value['entitlements_sha256'])):
                raise ValueError('Unexpected package signature metadata')


def collect(project, env):
    phase = env.get('AA_DIAGNOSTIC_PHASE', 'audit')
    if phase not in ('audit', 'compile', 'prepare', 'package'):
        raise ValueError('Unexpected diagnostic phase')
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
    outcome = env[{'audit': 'AA_AUDIT_OUTCOME', 'compile': 'AA_COMPILE_OUTCOME', 'prepare': 'AA_PREPARE_OUTCOME', 'package': 'AA_PACKAGE_OUTCOME'}[phase]]
    if outcome not in ('success', 'failure', 'cancelled', 'skipped'):
        raise ValueError('Unexpected audit outcome')

    destination = project / 'packages/build-diagnostics'
    destination.mkdir(parents=True, exist_ok=True)
    selected = []
    report_name = 'input-audit' if phase == 'audit' else f'{phase}-diagnostics'
    source = project / 'reports' / platform / f'{report_name}.json'
    audit_status = None
    if source.exists() or source.is_symlink():
        maximum = (2 << 20) if phase == 'audit' else 65536
        if source.is_symlink() or not source.is_file() or source.stat().st_size > maximum:
            raise ValueError('Refusing nonregular or oversized input audit')
        payload = source.read_bytes()
        audit = json.loads(payload)
        statuses = ('pass', 'missing', 'incomplete', 'error') if phase == 'audit' else ('pending', 'complete', 'failed', 'disk-blocked')
        if (not isinstance(audit, dict) or audit.get('schema') != 1
                or audit.get('platform') != platform
                or audit.get('status') not in statuses):
            raise ValueError('Unexpected input-audit schema or identity')
        if phase in ('compile', 'prepare'):
            allowed = {'schema', 'platform', 'status', 'exit_code', 'scope', 'events', 'console_bytes',
                       'capture_complete', 'oversized_context_lines', 'checkpoint_reuse'} if phase == 'compile' else {
                       'schema', 'platform', 'status', 'scope', 'events', 'stage'}
            if set(audit) - allowed or not isinstance(audit.get('events'), list) or len(audit['events']) > 24:
                raise ValueError('Unexpected compile diagnostic fields')
            for event in audit['events']:
                if not isinstance(event, dict) or set(event) - {'kind', 'exception', 'module', 'path', 'needed_by',
                                                               'line', 'column', 'code', 'symbol', 'header', 'action', 'family',
                                                               'stage', 'tool', 'expected_host', 'observed_host', 'errno', 'winerror', 'exit_code'}:
                    raise ValueError('Unexpected compile event fields')
        if phase == 'compile':
            proof = audit.get('checkpoint_reuse')
            if (not isinstance(proof, dict) or set(proof) - {'no_new_completed_actions', 'basis',
                    'version_verified', 'normal_failure', 'logging_error', 'before', 'after',
                    'manifest_before', 'manifest_after'}):
                raise ValueError('Unexpected compile proof fields')
            for name in ('before', 'after'):
                if not isinstance(proof.get(name), dict) or set(proof[name]) - {'state', 'reason', 'size', 'sha256'}:
                    raise ValueError('Unexpected Ninja log proof fields')
            for name in ('manifest_before', 'manifest_after'):
                if not isinstance(proof.get(name), dict) or set(proof[name]) - {'valid', 'sha256'}:
                    raise ValueError('Unexpected Ninja manifest proof fields')
        if phase == 'package':
            validate_package_report(audit)
        audit_status = audit['status']
        target = destination / f'{platform}-{report_name}.json'
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
    if phase in ('compile', 'prepare', 'package'):
        status[f'{phase}_step_outcome'] = status.pop('audit_step_outcome')
        status[f'{phase}_report_available'] = status.pop('audit_report_available')
        status[f'{phase}_report_status'] = status.pop('audit_report_status')
        status.update(phase=phase, scope='Finite structured build tool/action diagnostics. '
                            'Raw logs, commands, environment, signed URLs and profiles are excluded. '
                            'No browser behavior or package success is established.')
    prefix = 'diagnostic' if phase == 'audit' else phase
    metadata = destination / f'{platform}-{prefix}-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{platform}-{prefix}-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n'
                            for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nThis draft tag is a default-branch storage '
                     'anchor. Attached metadata records the immutable source and workflow commits.\n',
                     encoding='utf-8')
    tag_prefix = 'build-inputs' if phase == 'audit' else f'build-{phase}'
    return f'{tag_prefix}-{platform}-{run_id}-{attempt}', notes, selected


def main():
    project = Path(__file__).resolve().parents[2]
    tag, notes, selected = collect(project, os.environ)
    repository = os.environ['GITHUB_REPOSITORY']
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft',
                    '--title', f'Build {os.environ.get("AA_DIAGNOSTIC_PHASE", "audit")} diagnostics: {os.environ["AA_PLATFORM"]}',
                    '--notes-file', str(notes)], check=True, timeout=120)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, str(item), '--repo', repository],
                       check=True, timeout=120)
    subprocess.run(['gh', 'release', 'view', tag, '--repo', repository, '--json', 'url'],
                   check=True, timeout=120)


if __name__ == '__main__':
    main()
