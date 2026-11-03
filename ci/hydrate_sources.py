"""Hydrate audited Windows git DEPS, including headers and licenses."""
import hashlib
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile


MAX_FILES = 4096
MAX_BYTES = 32 << 20
MAX_FILE_BYTES = 16 << 20
MARKER = '.aacc-git-source.json'
MANIFEST = Path(__file__).with_name('windows-source-deps.json')
ALLOWED = {
    'src/third_party/microsoft_dxheaders/src': (
        'https://chromium.googlesource.com/external/github.com/microsoft/DirectX-Headers.git',
        '07b94cba474be6cdfd934febdbd0b21ca0524187', 'e0d4be126d9eba9eefec6ac2016aeb2407126232'),
    'src/third_party/microsoft_multimedia_redirection/src': (
        'https://chromium.googlesource.com/external/github.com/microsoft/multimedia-redirection.git',
        '8b1d8893d126547309f1bab8d8232418aa7c7109', 'b5f607aef6da553c78d68dbc4aa50657e4d6608d'),
    'src/third_party/microsoft_webauthn/src': (
        'https://chromium.googlesource.com/external/github.com/microsoft/webauthn.git',
        'ef82c157125a0490e05f6ea82a7adb1b8e1bad08', '5d68c9cc6c711940710d72462ced8817fcc56334'),
}


def git_digest(kind, content):
    return hashlib.sha1(kind.encode() + b' ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def safe_relative(value):
    if (not isinstance(value, str) or len(value.encode('utf-8')) > 1024 or
            not value or '\\' in value or ':' in value or '\0' in value):
        raise RuntimeError('Invalid pinned source path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('.', '..', '.git', MARKER) for part in value.split('/')):
        raise RuntimeError('Unsafe pinned source path')
    return path


def tree_digest(files):
    root = {}
    total = 0
    if not 0 < len(files) <= MAX_FILES:
        raise RuntimeError('Pinned source file count exceeds bounds')
    for item in files:
        path = safe_relative(item['path'])
        size = item['size']
        if (item['mode'] not in ('100644', '100755') or
                not re.fullmatch('[0-9a-f]{40}', item['blob']) or
                type(size) is not int or not 0 <= size <= MAX_FILE_BYTES):
            raise RuntimeError('Invalid pinned source object')
        total += size
        if total > MAX_BYTES:
            raise RuntimeError('Pinned source tree exceeds byte bounds')
        parent = root
        for part in path.parts[:-1]:
            parent = parent.setdefault(part, {})
            if not isinstance(parent, dict):
                raise RuntimeError('Pinned source path collision')
        if path.name in parent:
            raise RuntimeError('Duplicate pinned source path')
        parent[path.name] = (item['mode'], item['blob'])

    def digest(tree):
        content = bytearray()
        # Git sorts a subtree as though its name has a trailing slash.
        for name, value in sorted(tree.items(), key=lambda pair:
                pair[0].encode() + (b'/' if isinstance(pair[1], dict) else b'')):
            mode, sha = ('40000', digest(value)) if isinstance(value, dict) else value
            content.extend(mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(sha))
        return git_digest('tree', content)

    return digest(root)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path, item):
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or not path.is_file():
        raise RuntimeError('Pinned source is not a regular file')
    if path.stat().st_size != item['size']:
        raise RuntimeError('Pinned source size mismatch')
    if git_digest('blob', path.read_bytes()) != item['blob']:
        raise RuntimeError('Pinned source Git blob mismatch')


def download(url, output):
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '2', '--connect-timeout', '20', '--max-time', '120',
                    '--max-filesize', str(MAX_BYTES), '--output', str(output), url],
                   check=True, timeout=130)
    if output.stat().st_size > MAX_BYTES:
        raise RuntimeError('Pinned source archive exceeds byte bounds')


class BoundedTarReader:
    def __init__(self, stream, limit):
        self.stream = stream
        self.remaining = limit

    def read(self, size=-1):
        size = self.remaining + 1 if size < 0 else min(size, self.remaining + 1)
        block = self.stream.read(size)
        self.remaining -= len(block)
        if self.remaining < 0:
            raise RuntimeError('Pinned source archive exceeds decompressed byte bounds')
        return block


def extract_verified(archive, destination, pin):
    expected = {item['path']: item for item in pin['files']}
    seen = set()
    members = 0
    # Limit even tar/PAX metadata before parsing; a gzip bomb cannot expand
    # beyond the known file closure plus bounded tar-header/padding overhead.
    tar_limit = sum(item['size'] for item in pin['files']) + max(32768, (len(expected) + 1) * 4096)
    with gzip.open(archive, 'rb') as decompressed, tarfile.open(
            fileobj=BoundedTarReader(decompressed, tar_limit), mode='r|') as source:
        for member in source:
            members += 1
            if members > MAX_FILES * 4:
                raise RuntimeError('Pinned source archive member bound exceeded')
            path = PurePosixPath(member.name)
            if not path.parts or path.parts[0] != pin['archive_prefix']:
                raise RuntimeError('Unexpected pinned source archive prefix')
            relative = '/'.join(path.parts[1:])
            if relative:
                safe_relative(relative)
            if member.isdir():
                continue
            if not member.isreg() or relative not in expected or relative in seen:
                raise RuntimeError('Unknown, duplicate or nonregular pinned source archive member')
            item = expected[relative]
            if member.size != item['size']:
                raise RuntimeError('Pinned source archive member size mismatch')
            stream = source.extractfile(member)
            content = stream.read(MAX_FILE_BYTES + 1)
            if len(content) != item['size'] or git_digest('blob', content) != item['blob']:
                raise RuntimeError('Pinned source archive Git blob mismatch')
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            output.chmod(int(item['mode'], 8) & 0o777)
            seen.add(relative)
    if seen != expected.keys():
        raise RuntimeError('Pinned source archive is missing tracked files')


def inspect_existing(target, files):
    expected = {item['path']: item for item in files}
    if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
        raise RuntimeError('Pinned source root must not be a link')
    if target.exists():
        if not target.is_dir():
            raise RuntimeError('Pinned source root must be a directory')
        count = 0
        for directory, directories, names in os.walk(target, followlinks=False):
            count += len(directories) + len(names)
            if count > MAX_FILES * 4:
                raise RuntimeError('Existing pinned source tree exceeds entry bounds')
            for name in directories:
                path = Path(directory) / name
                if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                    raise RuntimeError('Pinned source directory must not be a link')
            for name in names:
                path = Path(directory) / name
                relative = path.relative_to(target).as_posix()
                if relative == MARKER:
                    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
                        raise RuntimeError('Invalid pinned source marker')
                    continue
                if relative not in expected:
                    raise RuntimeError('Foreign file in pinned source tree')
                verify_file(path, expected[relative])
    return [item for item in files if not (target / item['path']).exists()]


def hydrate_one(src, scope, enabled, pin, downloader=download):
    relative = safe_relative(pin['relative'])
    if not str(relative).startswith('src/third_party/') or tree_digest(pin['files']) != pin['tree']:
        raise RuntimeError('Pinned source manifest Git tree mismatch')
    dep = scope['deps'].get(pin['relative'])
    if (not isinstance(dep, dict) or dep.get('url') != pin['repository'] + '@' + pin['revision'] or
            not enabled(dep.get('condition', True))):
        raise RuntimeError('Pinned source dependency differs from the archive DEPS')
    target = src.parent / str(relative)
    if not target.resolve().is_relative_to(src.resolve()):
        raise RuntimeError('Pinned source root escapes source directory')
    missing = inspect_existing(target, pin['files'])
    marker = target / MARKER
    archive_sha256 = None
    if marker.is_file():
        previous = json.loads(marker.read_text(encoding='utf-8'))
        if previous.get('git_tree') == pin['tree'] and previous.get('revision') == pin['revision']:
            archive_sha256 = previous.get('archive_sha256')
            if archive_sha256 is not None and not re.fullmatch('[0-9a-f]{64}', archive_sha256):
                raise RuntimeError('Invalid pinned source archive provenance')
    if missing:
        # Only a tiny, complete pinned dependency is fetched, on the hosted
        # runner; no repository history, checkout hooks or upstream scripts.
        # Stage on the build volume: Windows source is D:, while %TEMP% is C:;
        # os.replace must stay on one volume for atomic installation.
        with tempfile.TemporaryDirectory(prefix='.aacc-pinned-source-', dir=src.parent) as temporary:
            temporary = Path(temporary)
            archive = temporary / 'source.tar.gz'
            downloader(pin['archive_url'], archive)
            if archive.stat().st_size > MAX_BYTES:
                raise RuntimeError('Pinned source archive exceeds byte bounds')
            archive_sha256 = sha256_file(archive)
            stage = temporary / 'verified'
            extract_verified(archive, stage, pin)
            # Complete archive and all existing files were validated before
            # the first source write; matching files retain exact mtimes.
            for item in missing:
                destination = target / item['path']
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / item['path'], destination)
    for item in pin['files']:
        verify_file(target / item['path'], item)
    record = {'repository': pin['repository'], 'revision': pin['revision'],
              'git_tree': pin['tree'], 'file_count': len(pin['files']),
              'source_size_bytes': sum(item['size'] for item in pin['files']),
              'archive_url': pin['archive_url'], 'archive_sha256': archive_sha256}
    text = json.dumps(record, indent=2) + '\n'
    if not marker.is_file() or marker.read_text(encoding='utf-8') != text:
        marker.write_text(text, encoding='utf-8')
    return record


def hydrate_windows_sources(src, scope, enabled):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if (manifest['schema'] != 1 or len(manifest['dependencies']) != len(ALLOWED) or
            {pin['relative'] for pin in manifest['dependencies']} != ALLOWED.keys()):
        raise RuntimeError('Unexpected pinned Windows source manifest')
    for pin in manifest['dependencies']:
        identity = (pin['repository'], pin['revision'], pin['tree'])
        if identity != ALLOWED[pin['relative']]:
            raise RuntimeError('Windows source manifest is outside the exact dependency allowlist')
        repository = pin['repository'].split('/external/github.com/', 1)[1].removesuffix('.git')
        if (pin['archive_url'] != f'https://codeload.github.com/{repository}/tar.gz/{pin["revision"]}' or
                pin['archive_prefix'] != repository.split('/')[1] + '-' + pin['revision']):
            raise RuntimeError('Unexpected pinned Windows source archive identity')
    return [hydrate_one(src, scope, enabled, pin) for pin in manifest['dependencies']]
