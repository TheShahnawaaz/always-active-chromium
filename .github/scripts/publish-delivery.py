"""Publish a fixed allowlist of finite real-delivery JSON; never profiles/logs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import struct
import zlib


def validate_appearance_capture(receipt, png, expected_executable=None, expected_pid=None,
                                expected_started=None, expected_profile=None,
                                allow_startup_diagnostic=False, expected_platform='win32'):
    """Validate finite owned-window capture evidence, never visual equivalence."""
    method = {'win32': 'PrintWindow-full-window-flags-2',
              'darwin': 'screencapture-owned-window-no-shadow'}.get(expected_platform)
    target = 'mac-arm64' if expected_platform == 'darwin' else 'win-x64'
    if (not isinstance(receipt, dict) or receipt.get('schema') != 1 or receipt.get('purpose') != 'owned-normal-browser-window-capture' or
            method is None or receipt.get('platform') != expected_platform or receipt.get('status') != 'captured' or receipt.get('method') != method or
            receipt.get('captureAttempted') is not True or receipt.get('captureSucceeded') is not True or receipt.get('captureOutcomeUncertain') is not False or
            receipt.get('manualReview') != 'pending' or receipt.get('uiEquivalenceVerified') is not False or receipt.get('visualCompletenessVerified') is not False or
            receipt.get('nativeUiAccessed') is not True or receipt.get('errors') != []):
        raise ValueError('Unverified appearance receipt')
    identity, window, image = receipt.get('identity', {}), receipt.get('window', {}), receipt.get('png', {})
    context = receipt.get('captureContext', 'fixture')
    if expected_platform == 'darwin' and (context != 'fixture' or not isinstance(identity, dict) or
            type(identity.get('startSeconds')) is not int or identity['startSeconds'] <= 0 or
            type(identity.get('startMicroseconds')) is not int or not 0 <= identity['startMicroseconds'] <= 999999):
        raise ValueError('Mac capture creation identity/context missing')
    if context not in ['fixture', 'startup-diagnostic'] or (context == 'startup-diagnostic' and
            (allow_startup_diagnostic is not True or receipt.get('behaviorVerified') is not False)):
        raise ValueError('Capture context is not authorized')
    if context == 'startup-diagnostic' and (not isinstance(window, dict) or
            window.get('titleKind') not in ['fixture', 'untitled'] or
            window.get('titleContextVerified') is not True or window.get('titleUnchangedAfterCapture') is not True):
        raise ValueError('Diagnostic title was not reverified')
    title_kind = window.get('titleKind', 'fixture') if isinstance(window, dict) else None
    title_verified = (isinstance(window, dict) and
        (title_kind == 'fixture' and window.get('fixtureTitleVerified') is True or
         context == 'startup-diagnostic' and title_kind == 'untitled' and window.get('fixtureTitleVerified') is False))
    if (not isinstance(identity, dict) or not all(identity.get(key) is True for key in ['verified', 'immediatelyRevalidated', 'afterCaptureRevalidated', 'ownerVerified', 'sessionVerified']) or
            type(identity.get('pid')) is not int or identity['pid'] <= 1 or
            not isinstance(identity.get('started'), str) or not re.fullmatch(
                r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2} \d\d:\d\d:\d\d \d{4}'
                if expected_platform == 'darwin' else r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z', identity['started']) or
            any(not isinstance(identity.get(key), str) or not 1 <= len(identity[key]) <= 4096 or '\n' in identity[key] for key in ['profile', 'executable'])):
        raise ValueError('Unverified capture process identity')
    for observed, expected in [(identity['executable'], expected_executable), (identity['profile'], expected_profile)]:
        if expected is not None and not same_executable(observed, expected, target):
            raise ValueError('Capture executable/profile mismatch')
    if expected_pid is not None and identity['pid'] != expected_pid or expected_started is not None and identity['started'] != expected_started:
        raise ValueError('Capture PID/start mismatch')
    if (not isinstance(window, dict) or window.get('ownerPID') != identity['pid'] or
            not isinstance(window.get('handle'), str) or not re.fullmatch(r'[0-9a-f]{1,16}', window['handle']) or int(window['handle'], 16) == 0 or
            not all(window.get(key) is True for key in ['foregroundVerified', 'visible', 'normalTopLevelVerified', 'unchangedAfterCapture']) or not title_verified or
            window.get('minimized') is not False or expected_platform == 'win32' and window.get('cloaked') is not False or type(window.get('dpi')) is not int or not 48 <= window['dpi'] <= 768 or
            type(receipt.get('visitedWindows')) is not int or not 1 <= receipt['visitedWindows'] <= 8):
        raise ValueError('Unverified capture window')
    content = receipt.get('contentCheck', {})
    if (not isinstance(content, dict) or content.get('nonUniform') is not True or content.get('visualCompletenessVerified') is not False or
            content.get('sampleCount') != 768 or type(content.get('uniqueSampleColors')) is not int or not 2 <= content['uniqueSampleColors'] <= 768):
        raise ValueError('Capture blankness observation missing')
    png = Path(png)
    if png.is_symlink() or not png.is_file() or not 57 <= png.stat().st_size <= 3145728:
        raise ValueError('Invalid finite PNG file')
    data = png.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('PNG signature required')
    offset, width, height, channels, ended, compressed = 8, None, None, None, False, []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError('Truncated PNG')
        size = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset+4:offset+8]
        end = offset + 12 + size
        if end > len(data) or re.fullmatch(b'[A-Za-z]{4}', kind) is None or zlib.crc32(data[offset+4:end-4]) != struct.unpack_from('>I', data, end-4)[0]:
            raise ValueError('Invalid PNG chunk')
        body = data[offset+8:end-4]
        if offset == 8:
            if kind != b'IHDR' or size != 13:
                raise ValueError('PNG IHDR required')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            channels = 3 if color == 2 else 4 if color == 6 else None
            if not 320 <= width <= 2048 or not 240 <= height <= 1536 or width*height > 3145728 or depth != 8 or not channels or any([compression, filtering, interlace]):
                raise ValueError('Unsupported bounded PNG dimensions/format')
        elif kind == b'IHDR':
            raise ValueError('Duplicate PNG IHDR')
        if kind == b'IDAT':
            compressed.append(body)
        if kind == b'IEND':
            if size or end != len(data):
                raise ValueError('Invalid PNG ending')
            ended = True
            break
        offset = end
    if not ended or not compressed:
        raise ValueError('Incomplete PNG')
    stride = width * channels + 1
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(b''.join(compressed), stride*height+1)
    except zlib.error as error:
        raise ValueError('Invalid PNG compression') from error
    if len(pixels) != stride*height or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or any(pixels[row*stride] > 4 for row in range(height)):
        raise ValueError('Invalid PNG pixel stream')
    digest = hashlib.sha256(data).hexdigest()
    if (not isinstance(image, dict) or image.get('file') != 'browser-window.png' or image.get('sha256') != digest or image.get('bytes') != len(data) or
            image.get('width') != width or image.get('height') != height or window.get('width') != width or window.get('height') != height):
        raise ValueError('PNG/receipt binding mismatch')
    return {'status': 'captured', 'method': receipt['method'], 'manualReview': 'pending',
        'uiEquivalenceVerified': False, 'visualCompletenessVerified': False,
        'captureContext': context, 'behaviorVerified': False,
        'identity': {key: identity[key] for key in ['pid', 'executable', 'profile', 'started', 'verified', 'immediatelyRevalidated', 'afterCaptureRevalidated', 'ownerVerified', 'sessionVerified'] + (['startSeconds', 'startMicroseconds'] if expected_platform == 'darwin' else [])},
        'window': {**{key: window[key] for key in ['handle', 'ownerPID', 'width', 'height', 'dpi']}, 'titleKind': title_kind},
        'png': {'width': width, 'height': height, 'bytes': len(data), 'sha256': digest}}


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
    appearance = {'status': 'not-captured', 'manualReview': 'pending',
                  'uiEquivalenceVerified': False, 'visualCompletenessVerified': False}
    if target in ('mac-arm64', 'win-x64'):
        receipt_file = project / 'reports/delivery-behavior/no-debug/browser-window-capture.json'
        png_file = receipt_file.with_name('browser-window.png')
        try:
            if receipt_file.is_symlink() or not receipt_file.is_file() or not receipt_file.resolve().is_relative_to(project.resolve()) or receipt_file.stat().st_size > 65536 or not png_file.resolve().is_relative_to(project.resolve()):
                raise ValueError('Missing or unsafe appearance evidence')
            receipt = json.loads(receipt_file.read_bytes())
            provenance = reports.get('provenance', {})
            if provenance.get('status') != 'delivered' or not isinstance(provenance.get('browser'), str):
                raise ValueError('Appearance is not bound to an acquired delivery')
            runs = reports.get('behavior', {}).get('variants', {}).get('no-debug', {}).get('results', {}).get('runs', [])
            native = [item for item in runs if item.get('mode') == 'native']
            if len(native) != 1 or native[0].get('appearance', {}).get('status') != 'captured' or native[0].get('appearance', {}).get('receipt') != receipt:
                raise ValueError('Appearance receipt not bound to native no-debug run')
            run = native[0]
            profiles = [item[len('--user-data-dir='):] for item in run.get('command', {}).get('args', []) if item.startswith('--user-data-dir=')]
            if len(profiles) != 1 or run.get('processIdentity', {}).get('owned') is not True or not same_executable(run.get('command', {}).get('executable'), provenance['browser'], target):
                raise ValueError('Appearance run identity missing')
            appearance = validate_appearance_capture(receipt, png_file, expected_executable=reports.get('provenance', {}).get('browser'),
                expected_pid=run.get('ownedPid'), expected_started=run['processIdentity'].get('started'), expected_profile=profiles[0],
                expected_platform='darwin' if target == 'mac-arm64' else 'win32')
            for original, suffix in [(receipt_file, 'window-capture.json'), (png_file, 'browser-window.png')]:
                copied = destination / f'{target}-delivery-{suffix}'
                copied.write_bytes(original.read_bytes())
                selected.append(copied)
        except (OSError, TypeError, ValueError, AttributeError, KeyError):
            appearance['reason'] = 'capture_missing_uncertain_or_unverified'
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
        'appearance': appearance,
        'report_errors': report_errors,
        'outcomes': {key: env.get('AA_' + key.upper() + '_OUTCOME', '') for key in ['acquire', 'behavior', 'store']},
        'scope': 'Real draft package provenance and installed/extracted browser behavior plus normal Store compatibility. '
                 'Appearance remains pending manual review even if a window PNG was captured. '
                 'Inspect individual limits; no Developer ID/notarization/Authenticode or genuine Store version upgrade is established.'}
    metadata = destination / f'{target}-delivery-status.json'
    metadata.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    selected.append(metadata)
    sums = destination / f'{target}-delivery-SHA256SUMS.txt'
    sums.write_text(''.join(f'{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}\n' for item in sorted(selected)), encoding='utf-8')
    selected.append(sums)
    notes = destination / '.notes.txt'
    notes.write_text(status['scope'] + '\n\nFinite JSON/checksum evidence and at most one verified owned-window PNG. No profiles, browser logs, native UI trees, '
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
