"""Authenticate archive provenance and emit only standard LASTCHANGE metadata."""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

DATA = Path(__file__).parent / 'data/chromium-156.0.8078.80.commit.json'
SOURCE_PATHS = {
    'chrome/VERSION', 'chrome/app/theme/chromium/BRANDING',
    'build/util/lastchange.py', 'build/util/version.py',
    'build/util/android_chrome_version.py', 'build/util/lastchange.gni',
    'build/util/BUILD.gn', 'build/util/LASTCHANGE.dummy',
    'build/util/chromium_git_revision.h.in',
    'base/version_info/version_info_values.h.version',
}


class SourceRevisionError(RuntimeError):
    def __init__(self, code, stage):
        super().__init__(f'Source revision {code} at {stage}')
        self.code, self.stage, self.tool = code, stage, 'source_revision'


def _reject(code, stage='validate'):
    raise SourceRevisionError(code, stage)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        _reject('unsafe_source_path')
    result = root.joinpath(*path.parts)
    for parent in [root, *[root / item for item in path.parents]]:
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)() or not parent.is_dir():
            _reject('unsafe_source_directory')
    if result.is_symlink() or result.exists() and not result.is_file():
        _reject('unsafe_source_file')
    return result


def _load(metadata_path, pins):
    metadata_path = Path(metadata_path)
    if metadata_path.is_symlink() or not metadata_path.is_file() or metadata_path.stat().st_size > 65536:
        _reject('invalid_metadata_file', 'metadata')
    try:
        data = json.loads(metadata_path.read_text(encoding='utf-8'))
        raw = base64.b64decode(data['raw_commit_base64'], validate=True)
    except (ValueError, KeyError, TypeError):
        _reject('invalid_metadata_encoding', 'metadata')
    if (not isinstance(data, dict) or data.get('schema') != 1 or len(raw) > 16384 or
            data.get('version') != pins.get('version') or data.get('upstream_revision') != pins.get('revision') or
            data.get('source_archive_sha256') != pins.get('source_sha256')):
        _reject('metadata_pin_mismatch', 'metadata')
    revision = hashlib.sha1(b'commit ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if not re.fullmatch(r'[0-9a-f]{40}', pins['revision']) or revision != pins['revision']:
        _reject('commit_object_hash_mismatch', 'metadata')
    try:
        headers, message = raw.decode('utf-8').split('\n\n', 1)
        committers = [line for line in headers.splitlines() if line.startswith('committer ')]
        match = re.fullmatch(r'committer .+ <[^<>\n]+> ([0-9]{10,12}) ([+-][0-9]{4})', committers[0])
        if len(committers) != 1 or match is None:
            raise ValueError('committer')
        epoch = int(match[1])
        year = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).year
        positions = [line[len('Cr-Commit-Position: '):] for line in message.splitlines() if line.startswith('Cr-Commit-Position: ')]
        position = positions[0]
        build = pins['version'].split('.')[2]
        if (len(positions) != 1 or not re.fullmatch(r'refs/branch-heads/' + re.escape(build) + r'@\{#[1-9][0-9]*\}', position) or
                message.splitlines()[0] != 'Incrementing VERSION to ' + pins['version']):
            raise ValueError('position or version')
    except (ValueError, IndexError, UnicodeDecodeError, OverflowError, OSError):
        _reject('invalid_commit_metadata', 'metadata')
    return data, {'revision': revision, 'commit_position': position, 'committer_epoch': epoch,
                  'year': year, 'raw_commit_sha256': _sha(raw)}


def ensure_source_revision(source_root, pins, metadata_path=DATA):
    """Emit the normal upstream-generated files; never alter dummy or C++ headers.

    Each changed output is atomically replaced; an interrupted two-file update
    is safely resumed. A matching output is never rewritten or retimestamped.
    The returned GN override is metadata-only and must be applied explicitly by
    the caller while retaining the actual nonofficial build configuration.
    """
    data, commit = _load(metadata_path, pins)
    if (pins.get('common_gn_args', {}).get('is_official_build') is not False or
            pins.get('common_gn_args', {}).get('is_chrome_branded') is not False):
        _reject('nonofficial_unbranded_configuration_required')
    root = Path(source_root).absolute()
    if root.resolve() != root:
        _reject('canonical_source_root_required')
    records = data.get('sources')
    if (not isinstance(records, list) or len(records) != len(SOURCE_PATHS) or
            any(not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in records) or
            {item.get('path') for item in records} != SOURCE_PATHS):
        _reject('invalid_source_manifest')
    inputs = []
    for item in records:
        file = _path(root, item['path'])
        if not file.is_file() or file.stat().st_size > 1048576:
            _reject('missing_or_oversized_source')
        payload = file.read_bytes()
        if _sha(payload) != item.get('sha256'):
            _reject('pinned_source_digest_mismatch')
        inputs.append({'path': item['path'], 'sha256': item['sha256']})
    fields = dict(line.split('=', 1) for line in (root / 'chrome/VERSION').read_text().splitlines())
    actual = '.'.join(fields.get(key, '') for key in ['MAJOR', 'MINOR', 'BUILD', 'PATCH'])
    if actual != pins['version']:
        _reject('source_version_mismatch')
    values = {
        'build/util/LASTCHANGE': (f'LASTCHANGE={commit["revision"]}-{commit["commit_position"]}\n'
                                 f'LASTCHANGE_YEAR={commit["year"]}\n').encode(),
        'build/util/LASTCHANGE.committime': str(commit['committer_epoch']).encode(),
    }
    targets = {relative: _path(root, relative) for relative in values}
    for file in targets.values():
        if file.exists() and file.stat().st_size > 4096:
            _reject('oversized_existing_metadata')
    pending = []
    try:
        for relative, payload in values.items():
            target = targets[relative]
            if target.is_file() and target.read_bytes() == payload:
                continue
            descriptor, name = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.tmp', dir=target.parent)
            temporary = Path(name)
            pending.append((temporary, target))
            with os.fdopen(descriptor, 'wb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(stat.S_IMODE(target.stat().st_mode) if target.is_file() else 0o644)
        for temporary, target in pending:
            os.replace(temporary, target)
    except OSError as error:
        raise SourceRevisionError('atomic_metadata_write_failed', 'write') from error
    finally:
        for temporary, _target in pending:
            temporary.unlink(missing_ok=True)
    return {'schema': 1, 'status': 'complete', 'mechanism': 'authenticated-upstream-archive-LASTCHANGE',
            **commit, 'source_archive_sha256': data['source_archive_sha256'],
            'metadata_gn_args': {'use_dummy_lastchange': False},
            'is_official_build': False, 'is_chrome_branded': False,
            'inputs': inputs,
            'outputs': [{'path': relative, 'sha256': _sha(payload), 'size': len(payload)}
                        for relative, payload in values.items()]}
