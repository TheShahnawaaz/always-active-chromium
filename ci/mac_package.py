"""Seal a fresh copy of a nonofficial ARM64 Chromium app, preserving its baseline."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import struct
import subprocess
import sys
import tempfile
import time

STRUCTURAL_FLAGS = 0x2 | 0x20000  # CS_ADHOC and CS_LINKER_SIGNED, not enforcement.
SCOPE = ('CI-only staged ad-hoc bundle sealing; existing entitlements and enforcement '
         'flags preserved. No Developer ID, notarization, Gatekeeper approval or runtime proof.')


class MacPackageError(RuntimeError):
    def __init__(self, code, stage):
        super().__init__(f'Mac package {code} at {stage}')
        self.code, self.stage = code, stage


def _fail(code):
    raise MacPackageError(code, 'pending')


def _bounded_string(value, maximum):
    return isinstance(value, str) and 0 < len(value.encode('utf-8')) <= maximum and not any(ord(c) < 32 for c in value)


def _hash(file, deadline):
    result = hashlib.sha256()
    with file.open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            if time.monotonic() >= deadline:
                _fail('deadline')
            result.update(data)
    return result.hexdigest()


def _tree(root, deadline):
    """Never follow tree links; require relative links to remain within this app."""
    root_info = root.stat()
    result = {'.': {'kind': 'directory', 'mode': stat.S_IMODE(root_info.st_mode), 'mtime_ns': root_info.st_mtime_ns}}
    bytes_seen = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            file = Path(directory) / name
            relative = file.relative_to(root).as_posix()
            if len(result) >= 100000 or not _bounded_string(relative, 4096):
                _fail('tree_limit')
            info = file.lstat()
            value = {'mode': stat.S_IMODE(info.st_mode), 'mtime_ns': info.st_mtime_ns}
            if file.is_symlink():
                link = os.readlink(file)
                if Path(link).is_absolute() or not file.resolve().is_relative_to(root):
                    _fail('escaping_or_absolute_symlink')
                if not file.resolve().exists():
                    _fail('broken_symlink')
                value.update(kind='symlink', target=link)
            elif stat.S_ISDIR(info.st_mode):
                value.update(kind='directory')
            elif stat.S_ISREG(info.st_mode):
                bytes_seen += info.st_size
                if info.st_size > 4 * (1 << 30) or bytes_seen > 10 * (1 << 30):
                    _fail('tree_byte_limit')
                value.update(kind='file', size=info.st_size, sha256=_hash(file, deadline))
            else:
                _fail('unsupported_filesystem_member')
            result[relative] = value
    return result


def _invoke(command, deadline, allow_failure=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _fail('deadline')
    try:
        result = subprocess.run([str(part) for part in command], capture_output=True,
                                timeout=min(20, remaining), check=False)
    except (OSError, subprocess.SubprocessError):
        _fail('tool_execution_failed')
    if len(result.stdout) > 65536 or len(result.stderr) > 65536:
        _fail('tool_output_limit')
    if result.returncode and not allow_failure:
        _fail('tool_failed')
    return result


def _macho(file):
    with file.open('rb') as stream:
        header = stream.read(32)
        if header[:4] not in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
                              b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce',
                              b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                              b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'):
            return None
        # This delivery target requires one arm64 slice, not a foreign/fat binary.
        if len(header) != 32 or header[:4] != b'\xcf\xfa\xed\xfe' or struct.unpack_from('<I', header, 4)[0] != 0x100000c:
            _fail('non_arm64_macho')
        count, size = struct.unpack_from('<II', header, 16)
        if count > 4096 or size > 1048576:
            _fail('invalid_macho_commands')
        data = stream.read(size)
        if len(data) != size:
            _fail('invalid_macho_commands')
    offset, signature = 0, False
    for _ in range(count):
        if offset + 8 > len(data):
            _fail('invalid_macho_commands')
        command, length = struct.unpack_from('<II', data, offset)
        if length < 8 or offset + length > len(data):
            _fail('invalid_macho_commands')
        signature |= command == 0x1d  # LC_CODE_SIGNATURE
        offset += length
    return signature


def _entitlement_digest(value):
    return hashlib.sha256(plistlib.dumps(value, sort_keys=True)).hexdigest()


def _metadata(executable, has_signature, deadline):
    result = _invoke(['codesign', '--display', '--verbose=4', '--entitlements', ':-', executable],
                     deadline, allow_failure=True)
    if result.returncode:
        if has_signature:
            _fail('signature_metadata_unavailable')
        return {'signature': 'unsigned', 'flags': 0, 'enforcement_flags': 0,
                'entitlements_sha256': _entitlement_digest({})}, {}, None
    text = result.stderr.decode('utf-8', errors='replace')
    flags = re.search(r'^CodeDirectory .*\bflags=0x([0-9a-fA-F]{1,8})\b', text, re.M)
    identifier = re.search(r'^Identifier=(.+)$', text, re.M)
    team = re.search(r'^TeamIdentifier=(.+)$', text, re.M)
    if not flags or not identifier or not _bounded_string(identifier[1], 255):
        _fail('signature_metadata_shape')
    value = int(flags[1], 16)
    signature = 'adhoc' if re.search(r'^Signature=adhoc$', text, re.M) and team and team[1] == 'not set' else 'non-adhoc'
    try:
        entitlements = plistlib.loads(result.stdout) if result.stdout.strip() else {}
    except (ValueError, plistlib.InvalidFileException):
        _fail('invalid_entitlements')
    if not isinstance(entitlements, dict):
        _fail('invalid_entitlements')
    return {'signature': signature, 'flags': value, 'enforcement_flags': value & ~STRUCTURAL_FLAGS,
            'entitlements_sha256': _entitlement_digest(entitlements)}, entitlements, identifier[1]


def _bundle(bundle, root):
    plist = bundle / ('Resources/Info.plist' if bundle.suffix == '.framework' else 'Contents/Info.plist')
    if not plist.is_file() or plist.stat().st_size > 1048576 or not plist.resolve().is_relative_to(root):
        _fail('bundle_info_unavailable')
    try:
        info = plistlib.loads(plist.read_bytes())
    except (ValueError, plistlib.InvalidFileException):
        _fail('bundle_info_invalid')
    if not isinstance(info, dict) or not _bounded_string(info.get('CFBundleIdentifier'), 255):
        _fail('bundle_identifier_invalid')
    name = info.get('CFBundleExecutable')
    if not _bounded_string(name, 255) or '/' in name or '\\' in name or name in ('.', '..'):
        _fail('bundle_executable_invalid')
    executable = bundle / name if bundle.suffix == '.framework' else bundle / 'Contents/MacOS' / name
    if not executable.is_file() or not executable.resolve().is_relative_to(root):
        _fail('bundle_executable_unavailable')
    return info, executable.resolve()


def _verify_signed_layout(before, after, macho_files):
    for relative, entry in after.items():
        signature_resource = '_CodeSignature' in Path(relative).parts
        if relative not in before:
            if not signature_resource or Path(relative).name not in ('_CodeSignature', 'CodeResources'):
                _fail('unexpected_staged_member')
            continue
        if relative in macho_files or signature_resource:
            continue
        original = before[relative]
        if {key: value for key, value in entry.items() if key != 'mtime_ns'} != {key: value for key, value in original.items() if key != 'mtime_ns'}:
            _fail('staged_resource_or_layout_changed')
    if set(before) - set(after):
        _fail('staged_member_missing')


def stage_signed_app(source_app, destination_app, version, report_path):
    """Return app/browser/signing; write a <=64KiB receipt even on refusal.

    A failure preserves the staged copy for inspection and raises MacPackageError.
    The compiled source is never passed to a signing operation.
    """
    source, destination, report_path = map(Path, (source_app, destination_app, report_path))
    if (not report_path.is_absolute() or report_path.resolve().is_relative_to(source.absolute()) or
            report_path.resolve().is_relative_to(destination.absolute())):
        raise MacPackageError('unsafe_report_path', 'receipt')
    deadline = time.monotonic() + 600
    receipt = {'schema': 1, 'platform': 'mac-arm64', 'status': 'failed', 'stage': 'validate_source',
               'code': None, 'scope': SCOPE, 'counts': dict.fromkeys(['files', 'macho', 'bundles', 'planned', 'signed', 'verified'], 0),
               'parts': [], 'source_unchanged': None}
    before, failure, root_executable = None, None, None
    try:
        if sys.platform != 'darwin' or platform.machine() != 'arm64':
            _fail('mac_arm64_host_required')
        if (not source.is_absolute() or source.is_symlink() or not source.is_dir() or
                source.name != 'Chromium.app' or source.resolve() != source):
            _fail('source_app_invalid')
        if (not destination.is_absolute() or destination.name != 'Chromium.app' or
                destination.exists() or destination.is_symlink() or not destination.parent.is_dir() or
                destination.parent.resolve() != destination.parent or destination.is_relative_to(source)):
            _fail('fresh_independent_destination_required')
        if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version):
            _fail('invalid_expected_version')
        before = _tree(source, deadline)
        receipt['counts']['files'] = sum(value['kind'] == 'file' for value in before.values())
        receipt['stage'] = 'inventory'
        info, root_executable = _bundle(source, source)
        if info['CFBundleIdentifier'] != 'org.chromium.Chromium' or info.get('CFBundleShortVersionString') != version or info.get('CFBundleVersion') != '.'.join(version.split('.')[2:]):
            _fail('source_bundle_identity_mismatch')
        bundles = [source]
        bundles += [source / relative for relative, value in before.items() if value['kind'] == 'directory' and Path(relative).suffix in ('.app', '.framework', '.xpc', '.appex', '.bundle')]
        mapped, plans = {}, []
        for bundle in bundles:
            metadata, executable = _bundle(bundle, source)
            if executable in mapped:
                _fail('ambiguous_bundle_executable')
            mapped[executable] = (bundle, metadata['CFBundleIdentifier'])
        receipt['counts']['bundles'] = len(bundles)
        for relative, entry in before.items():
            if entry['kind'] != 'file':
                continue
            file = source / relative
            signature = _macho(file)
            if signature is None:
                continue
            receipt['counts']['macho'] += 1
            baseline, entitlements, existing_id = _metadata(file, signature, deadline)
            bundle = mapped.get(file)
            target, identifier = bundle if bundle else (file, existing_id)
            path = target.relative_to(source).as_posix()
            if len(plans) >= 48 or not _bounded_string(path, 384) or not _bounded_string(identifier, 255):
                _fail('part_or_identifier_limit')
            part = {'path': path, 'kind': 'bundle' if bundle else 'macho',
                    'identifier': identifier, 'baseline': baseline}
            receipt['parts'].append(part)
            if baseline['signature'] not in ('unsigned', 'adhoc'):
                _fail('non_adhoc_baseline')
            if baseline['enforcement_flags']:
                _fail('unsupported_baseline_enforcement_flags')
            plans.append((part, relative, entitlements))
        if set(mapped) - {source / relative for _part, relative, _entitlements in plans}:
            _fail('bundle_main_is_not_arm64_macho')
        receipt['counts']['planned'] = len(plans)
        if not plans:
            _fail('no_macho_parts')
        receipt['stage'] = 'copy'
        _invoke(['ditto', source, destination], deadline)
        copied = _tree(destination, deadline)
        if set(copied) != set(before) or any({key: value for key, value in copied[path].items() if key != 'mtime_ns'} != {key: value for key, value in expected.items() if key != 'mtime_ns'} for path, expected in before.items()):
            _fail('staged_copy_mismatch')
        for relative, entry in before.items():
            if entry['kind'] == 'file' and os.path.samestat((source / relative).stat(), (destination / relative).stat()):
                _fail('source_destination_hardlink')
        receipt['stage'] = 'sign'
        plans.sort(key=lambda value: len(Path(value[0]['path']).parts) if value[0]['path'] != '.' else 0, reverse=True)
        with tempfile.TemporaryDirectory(prefix='.mac-signing-', dir=destination.parent) as temporary:
            for index, (part, relative, entitlements) in enumerate(plans):
                target = destination / part['path']
                command = ['codesign', '--force', '--sign', '-', '--timestamp=none', '--identifier', part['identifier']]
                if entitlements:
                    file = Path(temporary) / f'{index}.plist'
                    file.write_bytes(plistlib.dumps(entitlements, sort_keys=True))
                    command += ['--entitlements', file]
                _invoke([*command, target], deadline)
                receipt['counts']['signed'] += 1
                after, _entitlements, identifier = _metadata(destination / relative, True, deadline)
                part['after'] = after
                if (after['signature'] != 'adhoc' or after['enforcement_flags'] != part['baseline']['enforcement_flags'] or
                        after['entitlements_sha256'] != part['baseline']['entitlements_sha256'] or identifier != part['identifier']):
                    _fail('signed_metadata_changed')
                _invoke(['codesign', '--verify', '--strict', target], deadline)
                receipt['counts']['verified'] += 1
        receipt['stage'] = 'verify'
        _invoke(['codesign', '--verify', '--deep', '--strict', destination], deadline)
        _verify_signed_layout(before, _tree(destination, deadline), {relative for _part, relative, _entitlements in plans})
        final_info, final_executable = _bundle(destination, destination)
        if final_info != info or final_executable.relative_to(destination) != root_executable.relative_to(source):
            _fail('staged_bundle_identity_changed')
        receipt.update(status='complete', stage='complete')
    except Exception as error:
        failure = MacPackageError(error.code if isinstance(error, MacPackageError) else 'operation_failed', receipt['stage'])
        receipt.update(status='failed', code=failure.code)
        failure.stage = receipt['stage']
    finally:
        if before is not None:
            try:
                receipt['source_unchanged'] = _tree(source, deadline) == before
            except Exception:
                receipt['source_unchanged'] = False
            if not receipt['source_unchanged']:
                receipt.update(status='failed', stage='source_verify', code='source_changed_or_unverified')
                failure = MacPackageError(receipt['code'], receipt['stage'])
        encoded = (json.dumps(receipt, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        if len(encoded) > 65536:
            receipt.update(status='failed', stage='receipt', code='receipt_limit')
            failure = MacPackageError('receipt_limit', 'receipt')
            # Keep the bounded baseline evidence; never publish oversized or
            # incomplete metadata as successful packaging.
            for part in receipt['parts']:
                part.pop('after', None)
            while True:
                encoded = (json.dumps(receipt, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
                if len(encoded) <= 65536:
                    break
                receipt['parts'].pop()
        if report_path.is_symlink() or report_path.exists() and not report_path.is_file():
            raise MacPackageError('unsafe_report_path', 'receipt')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(encoded)
    if failure:
        raise failure
    return {'app': str(destination), 'browser': str(destination / root_executable.relative_to(source)), 'signing': receipt}
