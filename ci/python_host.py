"""Clean exact-pinned Windows CPython host package, not a foreign-host overlay."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import subprocess
import tempfile
import zipfile

WINDOWS_HOST = os.name == 'nt'
PACKAGE = 'infra/3pp/tools/cpython3/windows-amd64'
VERSION = 'version:3@3.11.9.chromium.38'
INSTANCE = 'jIPRqg4ET-ICO_XkOuwSaW8mbwfYiWJ5CDb8Qu7q24kC'
SHA256 = '8c83d1aa0e044fe2023bf5e43aec12696f266f07d88962790836fc42eeeadb89'
SIZE = 19926225
MARKER = '.aacc-windows-python.json'
DOT_GN_SHA256 = '1c33e1726ea5b347730043bf1837fb17bedbeee4651ae9d8393f0d191fb0dd24'
TARGET = '//v8:v8_base_without_compiler(//build/toolchain/win:win_clang_x64)'
UNQUALIFIED_TARGET = '//v8:v8_base_without_compiler'
TOOLCHAIN = '//build/toolchain/win:win_clang_x64'
PROBE = '''import ctypes,encodings,json,ssl,sqlite3,struct,sys,zlib
print(json.dumps({"version":list(sys.version_info[:3]),"platform":sys.platform,"implementation":sys.implementation.name,"pointer_bits":struct.calcsize("P")*8,"executable":sys.executable,"prefix":sys.prefix}))
'''


class PythonHostError(RuntimeError):
    def __init__(self, code, stage, cause=None):
        super().__init__(f'Windows CPython {code} at {stage}')
        self.code, self.stage, self.tool = code, stage, 'windows_cpython'
        for name, source in [('exit_code', 'returncode'), ('errno', 'errno'), ('winerror', 'winerror')]:
            value = getattr(cause, source, None)
            if isinstance(value, int):
                setattr(self, name, value)


def digest(file):
    result = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def directory(file, absent=False):
    if (file.is_symlink() or getattr(file, 'is_junction', lambda: False)() or
            file.exists() and not file.is_dir() or not absent and not file.is_dir()):
        raise PythonHostError('unsafe_directory', 'path')


def regular(file):
    if file.is_symlink() or not file.is_file():
        raise PythonHostError('not_regular_file', 'path')


def headers(root):
    values = {}
    for relative in ['bin/python3', 'bin/python3.exe', 'bin/python.exe']:
        file = root / relative
        if file.parent.is_symlink() or getattr(file.parent, 'is_junction', lambda: False)():
            values[relative] = {'kind': 'unsafe_parent'}
        elif file.is_symlink():
            values[relative] = {'kind': 'symlink'}
        elif file.is_file():
            with file.open('rb') as stream:
                prefix = stream.read(8)
            values[relative] = {'kind': 'regular', 'size': file.stat().st_size, 'prefix_hex': prefix.hex()}
        else:
            values[relative] = {'kind': 'other' if file.exists() else 'absent'}
    return values


def pe(file):
    regular(file)
    with file.open('rb') as stream:
        initial = stream.read(64)
        if len(initial) != 64 or initial[:2] != b'MZ':
            raise PythonHostError('invalid_pe', 'validate')
        offset = struct.unpack_from('<I', initial, 60)[0]
        if not 64 <= offset <= 1048576:
            raise PythonHostError('invalid_pe', 'validate')
        stream.seek(offset)
        value = stream.read(26)
    if len(value) != 26 or value[:4] != b'PE\0\0' or struct.unpack_from('<H', value, 4)[0] != 0x8664 or struct.unpack_from('<H', value, 24)[0] != 0x20b:
        raise PythonHostError('wrong_pe_architecture', 'validate')


def extract(archive, payload):
    inventory, folded = {}, set()
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 256 * 1048576:
            raise PythonHostError('archive_limit', 'extract')
        for entry in entries:
            name = entry.filename.rstrip('/')
            path = PurePosixPath(name)
            if (not name or '\\' in name or ':' in name or path.is_absolute() or
                    '..' in path.parts or any(part.rstrip('. ') != part for part in path.parts) or
                    name.casefold() in folded or stat.S_ISLNK(entry.external_attr >> 16)):
                raise PythonHostError('unsafe_zip_member', 'extract')
            folded.add(name.casefold())
            target = payload.joinpath(*path.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as incoming, target.open('xb') as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1048576)
                inventory[name] = digest(target)
    return inventory


def check_inventory(root, inventory):
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= 10000:
        raise PythonHostError('invalid_installation_inventory', 'validate')
    seen = set()
    for index, file in enumerate(root.rglob('*')):
        if index >= 15000:
            raise PythonHostError('installed_file_limit', 'validate')
        if file.is_symlink() or getattr(file, 'is_junction', lambda: False)():
            raise PythonHostError('unsafe_installed_member', 'validate')
        if file.is_dir():
            continue
        regular(file)
        relative = file.relative_to(root).as_posix()
        if relative == MARKER:
            continue
        if relative not in inventory:
            # Ordinary interpreter use writes stdlib bytecode caches; these are
            # not package files and are never mistaken for host executables.
            parts = PurePosixPath(relative).parts
            if parts[:2] == ('bin', 'Lib') and '__pycache__' in parts and relative.endswith('.pyc'):
                continue
            raise PythonHostError('unexpected_installed_member', 'validate')
        if digest(file) != inventory[relative]:
            raise PythonHostError('installed_file_changed', 'validate')
        seen.add(relative)
    if seen != inventory.keys():
        raise PythonHostError('missing_package_member', 'validate')


def validate(root, inventory, runner):
    directory(root)
    directory(root / 'bin')
    if (root / 'bin/python3').exists() or (root / 'bin/python3').is_symlink():
        raise PythonHostError('unexpected_extensionless_binary', 'validate')
    check_inventory(root, inventory)
    for name in ['python3.exe', 'python.exe', 'python311.dll', 'python3.dll']:
        pe(root / 'bin' / name)
    receipts = []
    for name in ['python3.exe', 'python3']:
        try:
            result = runner([str(root / 'bin' / name), '-I', '-B', '-c', PROBE],
                            check=True, capture_output=True, text=True, timeout=20)
            if len(result.stdout) > 4096 or len(result.stderr) > 4096:
                raise ValueError('output limit')
            value = json.loads(result.stdout)
        except Exception as error:
            raise PythonHostError('interpreter_launch_failed', 'runtime', error) from error
        if (value.get('version') != [3, 11, 9] or value.get('platform') != 'win32' or
                value.get('implementation') != 'cpython' or value.get('pointer_bits') != 64 or
                Path(value.get('executable', '')).resolve() != (root / 'bin/python3.exe').resolve() or
                Path(value.get('prefix', '')).resolve() != (root / 'bin').resolve()):
            raise PythonHostError('interpreter_identity_mismatch', 'runtime')
        receipts.append(name)
    return {'version': '3.11.9', 'host': 'windows-amd64', 'package_files_verified': len(inventory),
            'python3_exe_sha256': inventory['bin/python3.exe'],
            'runtime_paths_verified': receipts, 'stdlib_native_imports_verified': True}


def ensure_windows_python(src, dependency, downloader, runner=None):
    if not WINDOWS_HOST:
        raise PythonHostError('windows_host_required', 'pin')
    expected = {'packages': [{'package': 'infra/3pp/tools/cpython3/${{platform}}', 'version': VERSION}],
                'condition': 'non_git_source', 'dep_type': 'cipd'}
    if dependency != expected:
        raise PythonHostError('unexpected_dependency_pin', 'pin')
    src = Path(src).absolute()
    for path in [src, src / 'third_party']:
        directory(path)
    parent = src / 'third_party/cpython3'
    directory(parent, absent=True)
    parent.mkdir(exist_ok=True)
    target = src / 'third_party/cpython3/host'
    directory(target, absent=True)
    invoke = runner or subprocess.run
    url = f'https://chrome-infra-packages.appspot.com/dl/{PACKAGE}/+/{INSTANCE}'
    provenance = {'url': url, 'package': PACKAGE, 'version': VERSION, 'instance_id': INSTANCE,
                  'sha256': SHA256, 'size': SIZE, 'clean_host_schema': 1}
    marker = target / MARKER
    if marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= 1048576:
        try:
            prior = json.loads(marker.read_text())
            if prior.get('schema') == 1 and prior.get('package_sha256') == SHA256:
                validation = validate(target, prior['inventory'], invoke)
                if validation == prior['validation']:
                    return [{**provenance, 'validation': validation, 'replaced_headers': prior['replaced_headers']}]
        except (OSError, ValueError, KeyError, PythonHostError):
            pass
    work = Path(tempfile.mkdtemp(prefix='.aacc-python-', dir=src.parent))
    archive, payload, backup = work / 'package.zip', work / 'payload', work / 'previous'
    payload.mkdir()
    moved_old = moved_new = False
    before = headers(target)
    print('Windows CPython prior headers: ' + json.dumps(before, sort_keys=True), flush=True)
    try:
        downloader(url, archive, expected_sha=SHA256, expected_size=SIZE)
        regular(archive)
        if archive.stat().st_size != SIZE or digest(archive) != SHA256:
            raise PythonHostError('archive_pin_mismatch', 'download')
        inventory = extract(archive, payload)
        validate(payload, inventory, invoke)
        directory(target, absent=True)
        if target.exists():
            target.rename(backup)
            moved_old = True
        payload.rename(target)
        moved_new = True
        validation = validate(target, inventory, invoke)
        (target / MARKER).write_text(json.dumps({'schema': 1, 'package_sha256': SHA256,
            'inventory': inventory, 'validation': validation, 'replaced_headers': before}, sort_keys=True) + '\n')
    except Exception as error:
        rollback = 'original_untouched'
        try:
            if moved_new:
                target.rename(work / 'failed-installation')
            if moved_old:
                backup.rename(target)
                rollback = 'previous_restored'
        except OSError:
            rollback = 'failed_preserved_in_stage'
        failure = error if isinstance(error, PythonHostError) else PythonHostError('staging_failed', 'stage', error)
        evidence = {'schema': 1, 'code': failure.code, 'stage': failure.stage,
                    'rollback': rollback, 'original_headers': before}
        for name in ['exit_code', 'errno', 'winerror']:
            if hasattr(failure, name):
                evidence[name] = getattr(failure, name)
        try:
            (work / 'failure.json').write_text(json.dumps(evidence) + '\n')
        except OSError:
            pass  # Preserve the work directory even if its receipt cannot be written.
        if failure is error:
            raise
        raise failure from error
    try:
        shutil.rmtree(work)
    except OSError as error:
        raise PythonHostError('stage_cleanup_failed', 'cleanup', error) from error
    return [{**provenance, 'validation': validation, 'replaced_headers': before}]


def preflight_gn_desc(src, runner=None):
    src = Path(src)
    if not WINDOWS_HOST:
        raise PythonHostError('windows_host_required', 'gn_desc')
    if digest(src / '.gn') != DOT_GN_SHA256:
        raise PythonHostError('unexpected_dot_gn', 'gn_desc')
    # EXACT V8 compile_flags.py invocation, deliberately no gen-only override.
    command = [str(src / 'buildtools/win/gn.exe'), 'desc', '-q', 'out\\AlwaysActive', TARGET, '--format=json']
    try:
        result = (runner or subprocess.run)(command, cwd=src, capture_output=True,
                                            text=True, check=True, timeout=180)
        if len(result.stdout) > 8 * 1048576 or len(result.stderr) > 65536:
            raise ValueError('output limit')
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or len(data) != 1 or next(iter(data)) not in [TARGET, UNQUALIFIED_TARGET]:
            raise ValueError('unexpected or ambiguous target label')
        target = next(iter(data.values()))
        if not isinstance(target, dict) or target.get('toolchain') != TOOLCHAIN or not all(isinstance(target.get(key), list) for key in ['cflags', 'cflags_cc', 'include_dirs', 'defines']):
            raise ValueError('unexpected target metadata')
    except Exception as error:
        raise PythonHostError('exact_v8_gn_desc_failed', 'gn_desc', error) from error
    return {'status': 'passed', 'target': TARGET, 'script_executable_override': False,
            'mechanism': 'exact-pinned-v8-compile-flags-gn-desc', 'dot_gn_sha256': DOT_GN_SHA256}
