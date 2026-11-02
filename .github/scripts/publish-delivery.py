"""Publish a fixed allowlist of finite real-delivery JSON; never profiles/logs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def same_executable(left, right, target):
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    if target == 'win-x64':
        return left.replace('\\', '/').lower() == right.replace('\\', '/').lower()
    return left == right


def passed_checks(items):
    return isinstance(items, list) and bool(items) and all(isinstance(item, dict) and item.get('status') == 'passed' for item in items)


def matching_version(value, provenance):
    return (isinstance(value, dict) and value.get('revision', '').lstrip('@') == provenance.get('revision') and
            value.get('product', '').rsplit('/', 1)[-1] == provenance.get('version'))


def normal_close(value):
    return isinstance(value, dict) and all(value.get(key) is True for key in ['closedNormally', 'rootGone', 'processGroupGone'])


def paired_no_debug(result, provenance, target):
    runs = result.get('runs', [])
    if result.get('interrupted', 'missing') is not None or result.get('mode') != 'paired' or result.get('expectedVersion') != provenance.get('version') or len(runs) != 2 or {item.get('mode') for item in runs} != {'control', 'native'}:
        return False
    required = {'both websites provide stable later reports', 'websites report no WebDriver automation',
        'website full versions match expected browser pin', 'owned profile exposes no remote debugging port file',
        'normal launch has no debugging, automation, extension, or emulation flags', 'verified owned browser process cleanup completes'}
    for run in runs:
        tests, cleanup = run.get('tests', []), run.get('cleanup', {})
        names = [item.get('name') for item in tests]
        evaluation = run.get('evaluation', {})
        if (run.get('status') != 'passed' or not passed_checks(tests) or len(names) != len(set(names)) or not required.issubset(names) or
                not same_executable(run.get('command', {}).get('executable'), provenance.get('browser'), target) or
                run.get('processIdentity', {}).get('owned') is not True or cleanup.get('rootGone') is not True or cleanup.get('error') or
                evaluation.get('reportsStable') is not True or evaluation.get('behaviorPassed') is not True):
            return False
        if target == 'mac-arm64' and cleanup.get('processGroupGone') is not True:
            return False
        if target == 'win-x64' and ('taskkill /T /F' not in cleanup.get('signals', []) or cleanup.get('initialIdentity', {}).get('owned') is not True):
            return False
        if run['mode'] == 'control':
            if 'at least one control website is genuinely hidden and unfocused' not in names or not evaluation.get('genuinelyHidden') or '--disable-features=AlwaysActive' not in run.get('command', {}).get('args', []):
                return False
        elif 'both websites stably report native visible and focused aliases' not in names or not all(evaluation.get('protectedPages', {}).get(page, {}).get('passed') is True for page in ['alpha', 'beta']):
            return False
    return True


def store_complete(store, provenance, target):
    required = {'helpers', 'launch', 'listing', 'installPrompt', 'acceptInstall', 'installedRegistry',
        'closeForSourceAudit', 'installedSourceAudit', 'resumeForExecution', 'executionInitial', 'restartPersistence',
        'executionAfterRestart', 'ordinaryUpdateCheck', 'removeUi', 'removePrompt', 'confirmRemove', 'registryAbsent',
        'restartRemovalAbsence', 'finalNormalClose', 'persistedRegistrationAbsent'}
    phases = store.get('phases', [])
    names = [item.get('name') for item in phases]
    observations = store.get('observations', {})
    if (store.get('status') != 'passed' or store.get('interrupted', 'missing') is not None or store.get('error') or
            len(names) != len(required) or set(names) != required or not passed_checks(phases) or
            not matching_version(observations.get('browserVersion'), provenance) or not normal_close(store.get('cleanup')) or
            not normal_close(observations.get('finalNormalClose')) or not normal_close(observations.get('closeForSourceAudit'))):
        return False
    generations = store.get('generations', [])
    if len(generations) != 4 or len({item.get('ownedPid') for item in generations}) != 4:
        return False
    for generation in generations:
        identity = generation.get('identity', {})
        if (not same_executable(generation.get('command', {}).get('executable'), provenance.get('browser'), target) or
                identity.get('verified') is not True or identity.get('pid') != generation.get('ownedPid') or not identity.get('started')):
            return False
    actions = store.get('actions', [])
    if len(actions) != 2 or {item.get('operation') for item in actions} != {'accept-install', 'confirm-remove'}:
        return False
    for action in actions:
        identity, prompt = action.get('identity', {}), action.get('prompt', {})
        if (action.get('schema') != 1 or action.get('status') != 'acted' or action.get('target') != 'ubol' or action.get('actionAttempted') is not True or
                action.get('actionPerformed') is not True or action.get('actionOutcomeUncertain') is not False or action.get('error') or action.get('errors') != [] or
                action.get('actionType') not in ('AXPress', 'UIA.Invoke', 'native-mouse-click') or
                identity.get('verified') is not True or identity.get('immediatelyRevalidated') is not True or
                not same_executable(identity.get('executable'), provenance.get('browser'), target) or
                not any(identity.get('pid') == item.get('ownedPid') and identity.get('started') == item.get('identity', {}).get('started') for item in generations) or
                not all(prompt.get(key) is True for key in ['nativeDialogVerified', 'targetMatched', 'affirmativeEnabled', 'affirmativeUnique'])):
            return False
        if action['operation'] == 'accept-install':
            if prompt.get('permissionTextMatched') is not True or prompt.get('affirmativeLabel') != 'Add extension':
                return False
        elif prompt.get('reportAbuseUncheckedOrAbsent') is not True or prompt.get('affirmativeLabel') != 'Remove':
            return False
    audit = observations.get('installedAudit', {})
    if audit.get('manifest', {}).get('semanticVerified') is not True or not audit.get('sources') or not all(item.get('verified') is True for item in audit['sources']):
        return False
    for key in ['initialExecution', 'executionAfterRestart']:
        execution = observations.get(key, {})
        rulesets = execution.get('rulesets', [])
        if (execution.get('identity', {}).get('ready') is not True or execution.get('identity', {}).get('id') != 'ddkjiahejlhfcafbddmgiahcphecmpfh' or
                execution.get('identity', {}).get('version') != audit.get('version') or not rulesets or len(rulesets) != len(set(rulesets)) or
                not set(rulesets).issubset(audit.get('declaredRulesets', []))):
            return False
    persisted = observations.get('persistedRegistration', {})
    if (persisted.get('targetRegistrationAbsent') is not True or not persisted.get('parsedFiles') or persisted.get('errors') != [] or
            persisted.get('registrationShapeUncertainty') != []):
        return False
    for entry in persisted.get('entries', []):
        shape = entry.get('shape', {})
        if not (shape.get('type') == 'object' and shape.get('status') == 'complete' and shape.get('keyCount') == 0 and
                shape.get('fields') == [] and shape.get('keySetComplete') is True and shape.get('truncated') is False):
            return False
    coverage = store.get('coverage', {})
    return all(coverage.get(key) is True for key in ['normalInstall', 'workerExecution', 'restartPersistence', 'ordinaryUpdateCheck', 'normalRemovalWithPersistedRegistrationAbsence'])


def verification_checks(reports, target):
    provenance = reports.get('provenance', {})
    behavior, store = reports.get('behavior', {}), reports.get('store', {})
    expected_os = 'darwin' if target == 'mac-arm64' else 'win32'
    delivered = (provenance.get('status') == 'delivered' and
        re.fullmatch(r'[0-9a-f]{40}', provenance.get('source_commit', '')) is not None and
        re.fullmatch(r'[0-9a-f]{64}', provenance.get('fingerprint', '')) is not None and
        len(provenance.get('assets', [])) == 3 and
        provenance.get('delivery', {}).get('method') == ('ditto-zip-extraction' if target == 'mac-arm64' else 'real-mini-installer-default-per-user'))
    variants = behavior.get('variants', {})
    flags = {'baseline': ['--mode', 'baseline', '--disable-features', 'AlwaysActive'],
        'native': ['--mode', 'native'],
        'optional': ['--mode', 'native', '--features', 'AlwaysActiveFullscreen,AlwaysActiveBlockBackgroundReload'],
        'no-debug': []}
    binding = behavior.get('executable_binding', {})
    initial = binding.get('initial', {}) or {}
    bound = (binding.get('unchanged') is True and initial == binding.get('final') and
        re.fullmatch(r'[0-9a-f]{64}', initial.get('sha256', '')) is not None and
        isinstance(initial.get('size'), int) and initial['size'] > 0 and
        same_executable(initial.get('executable'), provenance.get('browser'), target) and
        initial.get('sha256') == provenance.get('delivery', {}).get('executable_sha256') and
        initial.get('size') == provenance.get('delivery', {}).get('executable_size'))
    modes = behavior.get('status') == 'passed' and bound and set(variants) == set(flags)
    for name in flags:
        variant = variants.get(name, {})
        result = variant.get('results', {}) or {}
        modes = modes and variant.get('exit_code') == 0 and variant.get('error') is None and variant.get('timeout_cleanup') is None and variant.get('flags') == flags[name] and result.get('schema') == 1 and result.get('status') == 'passed' and result.get('platform') == expected_os and result.get('architecture') == ('arm64' if target == 'mac-arm64' else 'x64')
        if name == 'no-debug':
            modes = modes and paired_no_debug(result, provenance, target)
        else:
            tests = result.get('tests', [])
            modes = modes and result.get('mode') == ('baseline' if name == 'baseline' else 'native') and passed_checks(tests) and matching_version(result.get('observations', {}).get('browserVersion'), provenance) and not any('cleanup:' in str(item).lower() for item in result.get('limitations', []))
    normal_store = store_complete(store, provenance, target)
    return {'real_package_delivered': bool(delivered), 'four_behavior_modes_complete': bool(modes),
            'executable_binding_complete': bool(bound), 'normal_store_complete': bool(normal_store)}


def collect(project, env):
    target, repository = env['AA_PLATFORM'], env['GITHUB_REPOSITORY']
    run_id, attempt = env['GITHUB_RUN_ID'], env.get('GITHUB_RUN_ATTEMPT', '1')
    if (target not in ('mac-arm64', 'win-x64') or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or
            not run_id.isdigit() or not attempt.isdigit() or not re.fullmatch(r'ci-source-[0-9a-f]{12}', env['AA_PACKAGE_SOURCE_TAG'])):
        raise ValueError('Invalid delivery evidence identity')
    destination = project / 'packages/delivery-verification'
    destination.mkdir(parents=True, exist_ok=True)
    selected, reports, report_errors = [], {}, []
    entries = [('.runtime/delivery/delivery-provenance.json', 'provenance'),
               ('reports/delivery-behavior/results.json', 'behavior'),
               ('reports/delivery-store/results.json', 'store')]
    for relative, kind in entries:
        source = project / relative
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(project.resolve()) or source.stat().st_size > 4 * (1 << 20):
            report_errors.append({'kind': kind, 'reason': 'unsafe_or_oversized_evidence_file'})
            continue
        try:
            payload = source.read_bytes()
            data = json.loads(payload)
        except (OSError, ValueError):
            report_errors.append({'kind': kind, 'reason': 'unreadable_or_invalid_json'})
            continue
        if not isinstance(data, dict) or data.get('schema') != 1:
            report_errors.append({'kind': kind, 'reason': 'invalid_report_schema'})
            continue
        if kind == 'provenance' and (data.get('stage') != 'real-package-delivery' or data.get('platform') != target or data.get('source_tag') != env['AA_PACKAGE_SOURCE_TAG']):
            report_errors.append({'kind': kind, 'reason': 'delivery_identity_mismatch'})
            continue
        if kind == 'store' and (data.get('stage') != 'normal-store-compatibility' or data.get('platform') != ('darwin' if target == 'mac-arm64' else 'win32') or not isinstance(data.get('target'), dict) or data['target'].get('id') != 'ddkjiahejlhfcafbddmgiahcphecmpfh'):
            report_errors.append({'kind': kind, 'reason': 'store_identity_mismatch'})
            continue
        reports[kind] = data
        copied = destination / f'{target}-delivery-{kind}.json'
        copied.write_bytes(payload)
        selected.append(copied)
    try:
        checks = verification_checks(reports, target)
    except (TypeError, ValueError, AttributeError, KeyError):
        report_errors.append({'kind': 'combined', 'reason': 'malformed_nested_report_structure'})
        checks = {'real_package_delivered': False, 'four_behavior_modes_complete': False,
                  'executable_binding_complete': False, 'normal_store_complete': False}
    passed = not report_errors and all(checks.values()) and all(env.get(key) == 'success' for key in ['AA_ACQUIRE_OUTCOME', 'AA_BEHAVIOR_OUTCOME', 'AA_STORE_OUTCOME'])
    status = {'schema': 1, 'platform': target, 'source_tag': env['AA_PACKAGE_SOURCE_TAG'],
        'controller_commit': env['GITHUB_SHA'], 'run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'custom_native_browser_verified': passed, 'status': 'passed' if passed else 'failed',
        'verification_checks': checks,
        'report_errors': report_errors,
        'outcomes': {key: env.get('AA_' + key.upper() + '_OUTCOME', '') for key in ['acquire', 'behavior', 'store']},
        'scope': 'Real draft package provenance and installed/extracted browser behavior plus normal Store compatibility. '
                 'Inspect individual limits; no Developer ID/notarization/Authenticode or genuine Store version upgrade is established.'}
    metadata = destination / f'{target}-delivery-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{target}-delivery-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n' for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nFinite JSON/checksum evidence only. No profiles, browser logs, native UI trees, '
                     'extension sources/packages or browser binaries are uploaded by this verifier.\n', encoding='utf-8')
    return f'delivery-verification-{target}-{run_id}-{attempt}', notes, selected


def main():
    tag, notes, selected = collect(Path(__file__).resolve().parents[2], os.environ)
    subprocess.run(['gh', 'release', 'create', tag, '--repo', os.environ['GITHUB_REPOSITORY'], '--draft',
        '--title', f'Real package verification: {os.environ["AA_PLATFORM"]}', '--notes-file', notes], check=True, timeout=120)
    for item in selected:
        subprocess.run(['gh', 'release', 'upload', tag, item, '--repo', os.environ['GITHUB_REPOSITORY']], check=True, timeout=120)
    status = next(item for item in selected if item.name.endswith('-delivery-status.json'))
    return 0 if json.loads(status.read_text(encoding='utf-8'))['custom_native_browser_verified'] is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
