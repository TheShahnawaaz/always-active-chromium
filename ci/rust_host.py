"""Clean Windows Rust host hydration; never overlays another host's package."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile

WINDOWS_HOST = os.name == 'nt'
HOST = 'x86_64-pc-windows-msvc'
RUST_REVISION = '1edd55dcfcd573872c727fa3e086369a71661ee0'
PACKAGE_REVISION = RUST_REVISION + '-2-llvmorg-24-init-7747-g62397f8b'
RELEASE = '1.100.0'
WIN_OBJECT = {
    'object_name': f'Win/rust-toolchain-{PACKAGE_REVISION}.tar.xz',
    'sha256sum': '487387d6c7cfec69b06d613eb0f68331a3b56b1081f73bc673a1b26299865379',
    'size_bytes': 416611108,
    'generation': 1789143395284107,
    'condition': 'host_os == "win"',
}
SCHEMA = 1
MARKER = '.aacc-windows-rust.json'
CHILD_SCRIPT = '''import json,subprocess,sys
try:
 value=subprocess.check_output(sys.argv[1:],stderr=subprocess.STDOUT,timeout=15,text=True)
 print(json.dumps({"output":value}))
except Exception as error:
 details={key:getattr(error,key) for key in ["errno","winerror","returncode"] if isinstance(getattr(error,key,None),int)}
 print(json.dumps({"error":details}))
'''


class RustHostError(RuntimeError):
    """Only controlled fields are exposed to structured prepare diagnostics."""
    def __init__(self, code, stage, tool='', cause=None, observed_host=None):
        super().__init__(f'Windows Rust {code} at {stage}' + (f' ({tool})' if tool else ''))
        self.code, self.stage, self.tool = code, stage, tool
        self.expected_host = HOST
        self.observed_host = observed_host
        for name, source in [('exit_code', 'returncode'), ('errno', 'errno'), ('winerror', 'winerror')]:
            value = getattr(cause, source, None)
            if isinstance(value, int):
                setattr(self, name, value)


def digest(file):
    result = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def regular(file, stage):
    if file.is_symlink() or not file.is_file():
        raise RustHostError('not_regular_file', stage, file.name)


def safe_directory(directory, stage, absent=False):
    if directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)():
        raise RustHostError('unsafe_directory', stage)
    if directory.exists() and (not directory.is_dir() or directory.resolve() != directory.absolute()):
        raise RustHostError('unsafe_directory', stage)
    if not absent and not directory.is_dir():
        raise RustHostError('missing_directory', stage)


def header_observation(root):
    observations = {}
    for relative in ['bin/rustc', 'bin/rustc.exe', 'VERSION']:
        file = root / relative
        if file.parent != root and (file.parent.is_symlink() or getattr(file.parent, 'is_junction', lambda: False)()):
            observations[relative] = {'kind': 'unsafe_parent'}
        elif file.is_symlink():
            observations[relative] = {'kind': 'symlink'}
        elif file.is_file():
            with file.open('rb') as stream:
                prefix = stream.read(4)
            observations[relative] = {'kind': 'regular', 'size': file.stat().st_size,
                                      'prefix_hex': prefix.hex()}
        elif file.exists():
            observations[relative] = {'kind': 'other'}
        else:
            observations[relative] = {'kind': 'absent'}
    return observations


def pe_check(file, stage):
    regular(file, stage)
    with file.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise RustHostError('invalid_pe', stage, 'bin/rustc.exe')
        offset = struct.unpack_from('<I', header, 60)[0]
        if not 64 <= offset <= 1048576:
            raise RustHostError('invalid_pe', stage, 'bin/rustc.exe')
        stream.seek(offset)
        pe = stream.read(26)
    if len(pe) != 26 or pe[:4] != b'PE\0\0' or struct.unpack_from('<H', pe, 4)[0] != 0x8664 or struct.unpack_from('<H', pe, 24)[0] != 0x20b:
        raise RustHostError('wrong_pe_architecture', stage, 'bin/rustc.exe')


def run(command, **kwargs):
    return subprocess.run([str(item) for item in command], check=True, **kwargs)


def validate(root, src, runner, stage):
    safe_directory(root, stage)
    safe_directory(root / 'bin', stage)
    # find_std_rlibs.py invokes the extensionless path through this interpreter.
    # A Unix file at that exact path must never survive Windows hydration.
    if (root / 'bin/rustc').exists() or (root / 'bin/rustc').is_symlink():
        raise RustHostError('unexpected_extensionless_binary', stage, 'bin/rustc')
    pe_check(root / 'bin/rustc.exe', stage)
    version = root / 'VERSION'
    regular(version, stage)
    if version.stat().st_size > 4096:
        raise RustHostError('invalid_version_stamp', stage, 'VERSION')
    lines = version.read_text(encoding='utf-8').splitlines()
    stamp = lines[0] if lines else ''
    if stamp != f'rustc {RELEASE} {RUST_REVISION} ({PACKAGE_REVISION} chromium)':
        raise RustHostError('wrong_version_stamp', stage, 'VERSION')
    interpreter = src / 'third_party/cpython3/host/bin/python3.exe'
    regular(interpreter, stage)

    def invoke(tool, arguments):
        try:
            response = runner([interpreter, '-c', CHILD_SCRIPT, root / tool, *arguments],
                              cwd=src, capture_output=True, text=True, timeout=20)
            if len(response.stdout) > 16384 or len(response.stderr) > 4096:
                raise RustHostError('tool_output_limit', stage, tool)
            value = json.loads(response.stdout)
            if set(value) == {'error'} and isinstance(value['error'], dict):
                failure = RustHostError('tool_launch_failed', stage, tool)
                for name, source in [('exit_code', 'returncode'), ('errno', 'errno'), ('winerror', 'winerror')]:
                    if isinstance(value['error'].get(source), int):
                        setattr(failure, name, value['error'][source])
                raise failure
            if set(value) != {'output'} or not isinstance(value['output'], str):
                raise ValueError('Unexpected child receipt')
            return value['output'].strip()
        except RustHostError:
            raise
        except Exception as error:
            raise RustHostError('tool_launch_failed', stage, tool, cause=error) from error

    verbose = invoke('bin/rustc.exe', ['-vV'])
    fields = {}
    for line in verbose.splitlines()[1:]:
        key, separator, value = line.partition(': ')
        if separator:
            fields[key] = value
    if fields.get('host') != HOST:
        host = fields.get('host', '')
        observed = host if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', host) else None
        raise RustHostError('wrong_host', stage, 'bin/rustc.exe', observed_host=observed)
    if fields.get('release', '').split('-')[0] != RELEASE or fields.get('commit-hash') != RUST_REVISION:
        raise RustHostError('wrong_compiler_version', stage, 'bin/rustc.exe')
    # Use exactly the path shape and subprocess entry point from upstream .80.
    library = Path(invoke('bin/rustc', ['--print', 'target-libdir', '--target', HOST]))
    for directory in [root / 'lib', root / 'lib/rustlib', root / 'lib/rustlib' / HOST, root / 'lib/rustlib' / HOST / 'lib']:
        safe_directory(directory, stage)
    if not library.is_absolute() or library.resolve() != (root / 'lib/rustlib' / HOST / 'lib').resolve() or not library.resolve().is_relative_to(root.resolve()) or not library.is_dir():
        raise RustHostError('invalid_target_libdir', stage, 'bin/rustc')
    for crate in ['std', 'core', 'alloc']:
        matches = list(library.glob(f'lib{crate}-*.rlib'))
        if len(matches) != 1 or matches[0].is_symlink() or not matches[0].is_file() or matches[0].stat().st_size == 0:
            raise RustHostError('missing_or_ambiguous_stdlib', stage, 'bin/rustc')
    return {'host': HOST, 'release': fields['release'], 'commit': fields['commit-hash'],
            'rustc_sha256': digest(root / 'bin/rustc.exe'), 'stamp_sha256': digest(version),
            'extensionless_target_libdir_verified': True}


def extract(archive, payload):
    with tarfile.open(archive, 'r:xz') as source:
        members = source.getmembers()
        if len(members) > 50000 or sum(max(0, member.size) for member in members) > 4 * (1 << 30):
            raise RustHostError('archive_limit', 'extract')
        for member in members:
            name = member.name.rstrip('/')
            if not name or '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise RustHostError('unsafe_archive_member', 'extract')
            if member.islnk() or member.issym():
                link = member.linkname
                if '\\' in link or ':' in link:
                    raise RustHostError('unsafe_archive_link', 'extract')
        source.extractall(payload, members=members, filter='data')


def ensure_windows_rust(src, dependency, downloader, runner=None):
    """Return one provenance record. Existing validated clean installs are read-only.

    `downloader(url, path, expected_sha=..., expected_size=...)` is the CI
    owner's verified fetch callback. No full payload is fetched in local tests.
    """
    if not WINDOWS_HOST:
        raise RustHostError('wrong_execution_platform', 'pin')
    if (dependency.get('dep_type') != 'gcs' or dependency.get('bucket') != 'chromium-browser-clang' or
            dependency.get('condition') != 'not rust_force_head_revision' or
            [item for item in dependency.get('objects', []) if item.get('condition') == 'host_os == "win"'] != [WIN_OBJECT]):
        raise RustHostError('dependency_pin_mismatch', 'pin')
    src = Path(src).absolute()
    safe_directory(src, 'root')
    safe_directory(src / 'third_party', 'root')
    target = src / 'third_party/rust-toolchain'
    safe_directory(target, 'root', absent=True)
    runner = runner or run
    url = ('https://storage.googleapis.com/chromium-browser-clang/' + WIN_OBJECT['object_name'] +
           f'?generation={WIN_OBJECT["generation"]}')
    provenance = {'url': url, 'sha256': WIN_OBJECT['sha256sum'], 'size': WIN_OBJECT['size_bytes'],
                  'host': HOST, 'clean_host_schema': SCHEMA}
    marker = target / MARKER
    if marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= 16384:
        try:
            previous = json.loads(marker.read_text(encoding='utf-8'))
            if previous.get('schema') == SCHEMA and previous.get('package_sha256') == WIN_OBJECT['sha256sum']:
                safe_directory(target / 'bin', 'reuse')
                regular(target / 'bin/rustc.exe', 'reuse')
                regular(target / 'VERSION', 'reuse')
                if digest(target / 'bin/rustc.exe') != previous['validation']['rustc_sha256'] or digest(target / 'VERSION') != previous['validation']['stamp_sha256']:
                    raise RustHostError('installed_tool_changed', 'reuse')
                validation = validate(target, src, runner, 'reuse')
                if validation != previous['validation']:
                    raise RustHostError('installed_validation_changed', 'reuse')
                return [{**provenance, 'validation': validation, 'replaced_headers': previous.get('replaced_headers', {})}]
        except (OSError, ValueError, KeyError, RustHostError):
            pass  # Heal by staging the same immutable package, never by overlay.
    work = Path(tempfile.mkdtemp(prefix='.aacc-rust-', dir=src.parent))
    archive, payload, backup = work / 'package.tar.xz', work / 'payload', work / 'previous'
    payload.mkdir()
    before = {}
    moved_old = moved_new = False
    try:
        before = header_observation(target)
        print('Windows Rust prior headers: ' + json.dumps(before, sort_keys=True), flush=True)
        downloader(url, archive, expected_sha=WIN_OBJECT['sha256sum'], expected_size=WIN_OBJECT['size_bytes'])
        regular(archive, 'download')
        if archive.stat().st_size != WIN_OBJECT['size_bytes'] or digest(archive) != WIN_OBJECT['sha256sum']:
            raise RustHostError('archive_pin_mismatch', 'download')
        extract(archive, payload)
        validate(payload, src, runner, 'validate-stage')
        safe_directory(src / 'third_party', 'replace')
        safe_directory(target, 'replace', absent=True)
        if target.exists():
            target.rename(backup)
            moved_old = True
        payload.rename(target)
        moved_new = True
        validation = validate(target, src, runner, 'validate-final')
        (target / MARKER).write_text(json.dumps({'schema': SCHEMA, 'package_sha256': WIN_OBJECT['sha256sum'],
                                               'validation': validation, 'replaced_headers': before}, sort_keys=True) + '\n', encoding='utf-8')
    except Exception as error:
        rollback = 'original_untouched'
        rollback_error = None
        try:
            if moved_new:
                target.rename(work / 'failed-installation')
            if moved_old:
                backup.rename(target)
                rollback = 'previous_restored'
            elif moved_new:
                rollback = 'original_absence_restored'
        except OSError as restore_error:
            rollback = 'failed_preserved_in_stage'
            rollback_error = restore_error
        controlled = error if isinstance(error, RustHostError) else RustHostError('staging_failed', 'stage', cause=error)
        initial_code = controlled.code
        if rollback_error:
            controlled = RustHostError('rollback_failed', 'rollback', cause=rollback_error)
        evidence = {'schema': 1, 'code': controlled.code, 'stage': controlled.stage, 'tool': controlled.tool,
                    'expected_host': HOST, 'observed_host': controlled.observed_host, 'rollback': rollback,
                    'original_headers': before, 'initial_code': initial_code}
        for name in ['exit_code', 'errno', 'winerror']:
            if hasattr(controlled, name):
                evidence[name] = getattr(controlled, name)
        try:
            (work / 'failure.json').write_text(json.dumps(evidence, sort_keys=True) + '\n', encoding='utf-8')
            print(f'Windows Rust failure evidence retained: {work / "failure.json"}', flush=True)
        except OSError:
            print(f'Windows Rust failure stage retained; evidence write failed: {work}', flush=True)
        if controlled is error:
            raise
        raise controlled from error
    try:
        shutil.rmtree(work)
    except OSError as error:
        # The installed validated package remains intact. Never roll it back
        # merely because removal of its old, private staging backup failed.
        failure = RustHostError('stage_cleanup_failed', 'cleanup', cause=error)
        try:
            (work / 'failure.json').write_text(json.dumps({'schema': 1, 'code': failure.code,
                'stage': failure.stage, 'installed_validated': True, 'original_headers': before}) + '\n', encoding='utf-8')
        except OSError:
            pass
        raise failure from error
    return [{**provenance, 'validation': validation, 'replaced_headers': before}]
