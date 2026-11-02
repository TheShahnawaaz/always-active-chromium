"""Restore the exact .80 rc_win hook and exercise its real Windows toolchain."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

WINDOWS_HOST = os.name == 'nt'
REVISION = 'fb096c0011f9d50f0a264a9376420cdea9c421e3'
RC_RELATIVE = 'build/toolchain/win/rc/win/rc.exe'
PIN = {
    'sha1': 'dea7da0d9bfcb8dad6cf53ca608dddac3459faaa',
    'sha256': '903769d98df8a005c79d52d7089fe34f23c0b7ada4cd0c42b6063526a5593e6a',
    'size': 603648,
    'generation': 1729017425353926,
}
SOURCES = {
    'build/toolchain/win/rc/rc.py': '92a77c734dee1864ffa635309e6e70d356f05906c42a7152d026d89508c62727',
    'build/toolchain/win/tool_wrapper.py': 'e907e6970b5f1d2a6115372a7bf81508e06fe40e14156b81c010127eae300a67',
    RC_RELATIVE + '.sha1': 'ad6cd3835f44229227d120a4d13d070a1af4c3cd2461105d63951e179364100c',
}
HOOK = {
    'name': 'rc_win', 'pattern': '.', 'condition': 'checkout_win and host_os == "win"',
    'action': ['python3', 'src/third_party/depot_tools/download_from_google_storage.py',
               '--no_resume', '--bucket', 'chromium-browser-clang/rc',
               '-s', 'src/' + RC_RELATIVE + '.sha1'],
}


class WindowsRcError(RuntimeError):
    """Controlled fields only; source logs/commands/environment stay private."""
    def __init__(self, code, stage, cause=None):
        super().__init__(f'Windows RC {code} at {stage}')
        self.code, self.stage, self.tool = code, stage, 'windows_rc'
        for name, source in [('exit_code', 'returncode'), ('errno', 'errno'), ('winerror', 'winerror')]:
            value = getattr(cause, source, None)
            if isinstance(value, int):
                setattr(self, name, value)


def regular(file, stage):
    if file.is_symlink() or not file.is_file():
        raise WindowsRcError('not_regular_file', stage)


def safe_path(src, relative):
    file = src / relative
    for directory in [src, *file.relative_to(src).parents]:
        directory = directory if directory == src else src / directory
        if (directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)() or
                not directory.is_dir()):
            raise WindowsRcError('unsafe_directory', 'source_validation')
    return file


def source_validation(src, scope=None, enabled=None):
    if not WINDOWS_HOST:
        raise WindowsRcError('windows_host_required', 'source_validation')
    if scope is not None:
        hooks = [hook for hook in scope.get('hooks', []) if hook.get('name') == 'rc_win']
        if hooks != [HOOK] or enabled is None or not enabled(HOOK['condition']):
            raise WindowsRcError('unexpected_deps_hook', 'source_validation')
    for relative, expected in SOURCES.items():
        file = safe_path(src, relative)
        regular(file, 'source_validation')
        if file.stat().st_size > 65536 or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise WindowsRcError('unexpected_pinned_source', 'source_validation')
    if (src / (RC_RELATIVE + '.sha1')).read_text().strip() != PIN['sha1']:
        raise WindowsRcError('unexpected_sha1_pin', 'source_validation')


def validate_binary(file):
    regular(file, 'binary_validation')
    if file.stat().st_size != PIN['size']:
        raise WindowsRcError('wrong_binary_size', 'binary_validation')
    data = file.read_bytes()
    if (hashlib.sha256(data).hexdigest() != PIN['sha256'] or
            hashlib.sha1(data).hexdigest() != PIN['sha1']):
        raise WindowsRcError('wrong_binary_digest', 'binary_validation')
    if len(data) < 64 or data[:2] != b'MZ':
        raise WindowsRcError('invalid_pe', 'binary_validation')
    offset = struct.unpack_from('<I', data, 60)[0]
    if (not 64 <= offset <= len(data) - 26 or data[offset:offset + 4] != b'PE\0\0' or
            struct.unpack_from('<H', data, offset + 4)[0] != 0x8664 or
            struct.unpack_from('<H', data, offset + 24)[0] != 0x20b):
        raise WindowsRcError('wrong_pe_architecture', 'binary_validation')


def ensure_windows_rc(src, scope, enabled, fetch):
    """Hash-check before install; correct existing bytes retain their mtimes."""
    src = Path(src)
    source_validation(src, scope, enabled)
    target = safe_path(src, RC_RELATIVE)
    url = (f'https://storage.googleapis.com/chromium-browser-clang/rc/{PIN["sha1"]}'
           f'?generation={PIN["generation"]}')
    if target.exists() or target.is_symlink():
        validate_binary(target)
    else:
        handle, temporary = tempfile.mkstemp(prefix='.aacc-rc-', suffix='.tmp', dir=target.parent)
        os.close(handle)
        pending = Path(temporary)
        try:
            fetch(url, pending, expected_sha=PIN['sha256'], expected_size=PIN['size'])
            validate_binary(pending)
            # Never replace an unexpected existing executable or reparse point.
            if target.exists() or target.is_symlink():
                raise WindowsRcError('target_appeared_during_download', 'binary_install')
            pending.replace(target)
        except WindowsRcError:
            raise
        except Exception as error:
            raise WindowsRcError('download_or_install_failed', 'binary_install', error) from error
        finally:
            pending.unlink(missing_ok=True)
    return [{'url': url, 'sha256': PIN['sha256'], 'sha1': PIN['sha1'], 'size': PIN['size'],
             'source_revision': REVISION, 'tool': RC_RELATIVE,
             'pe_machine': 'amd64', 'required_system_dlls': ['KERNEL32.dll', 'SHLWAPI.dll']}]


def preflight_windows_rc(src, runner=None):
    """Use generated x64 environment and unchanged wrapper, including SDK RC."""
    src = Path(src)
    source_validation(src)
    validate_binary(safe_path(src, RC_RELATIVE))
    interpreter = safe_path(src, 'third_party/cpython3/host/bin/python3.exe')
    regular(interpreter, 'preflight')
    out = safe_path(src, 'out/AlwaysActive/environment.x64').parent
    environment = out / 'environment.x64'
    regular(environment, 'preflight')
    if environment.stat().st_size < 2 or environment.stat().st_size > 1048576:
        raise WindowsRcError('invalid_generated_environment', 'preflight')
    receipt_path = src.parent / 'windows-rc-preflight.json'
    if receipt_path.exists() or receipt_path.is_symlink():
        regular(receipt_path, 'preflight')
        receipt_path.unlink()
    invoke = runner or subprocess.run
    try:
        with tempfile.TemporaryDirectory(prefix='.aacc-rc-preflight-', dir=src.parent) as temporary:
            root = Path(temporary)
            fixture, resource = root / 'probe.rc', root / 'probe.res'
            fixture.write_text('#define AACC_RC_WORD 0x1234\n1 10 { AACC_RC_WORD, 0xabcd }\n', encoding='ascii')
            command = [interpreter, src / 'build/toolchain/win/tool_wrapper.py',
                       'rc-wrapper', 'environment.x64', 'rc.exe', '/nologo',
                       '/fo' + str(resource), fixture]
            result = invoke([str(part) for part in command], cwd=out, check=True,
                            capture_output=True, text=True, timeout=30)
            if (not isinstance(result.stdout, str) or not isinstance(result.stderr, str) or
                    len(result.stdout) > 16384 or len(result.stderr) > 8192):
                raise WindowsRcError('preflight_output_limit', 'preflight')
            ms_resource = Path(str(resource) + '_ms_rc')
            for file in [resource, ms_resource]:
                regular(file, 'preflight')
                if not 32 <= file.stat().st_size <= 4096:
                    raise WindowsRcError('invalid_resource_output', 'preflight')
            binary = resource.read_bytes()
            if (binary != ms_resource.read_bytes() or struct.unpack_from('<II', binary) != (0, 32) or
                    b'\x34\x12\xcd\xab' not in binary):
                raise WindowsRcError('resource_comparison_failed', 'preflight')
            receipt = {'schema': 1, 'status': 'passed', 'tool': RC_RELATIVE,
                       'sha256': PIN['sha256'], 'pe_machine': 'amd64',
                       'generated_environment': 'environment.x64',
                       'mechanism': 'pinned-tool-wrapper-clang-rc-and-microsoft-sdk-comparison',
                       'resource_sha256': hashlib.sha256(binary).hexdigest(),
                       'resource_size': len(binary)}
    except WindowsRcError:
        raise
    except Exception as error:
        raise WindowsRcError('real_resource_preflight_failed', 'preflight', error) from error
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
