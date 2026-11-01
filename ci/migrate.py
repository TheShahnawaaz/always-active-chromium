#!/usr/bin/env python3
"""Explicit, hash-verified migration of two approved native compiler-cache seeds.

Old Python is hashed for provenance and NEVER executed. Only the current trusted
patch parser transforms existing C++/header/IDL source; compilation is mandatory.
"""
import base64
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

from build import (PROJECT, PINS, fingerprint, rendered_gn_args, require_tag,
                   source_commit)

APPROVED_SEEDS = {
    'mac-arm64': ('ci-source-67dea4dbe7e2', '67dea4dbe7e2df2f21394efbe8f0346fee3af2f4'),
    'win-x64': ('ci-source-f2f4e1335f61', 'f2f4e1335f61d63f7b9abc4d44dbcfa5e0a9034d'),
}
MAX_FILES = 64
MAX_FILE_BYTES = 16 << 20
MAX_TOTAL_BYTES = 64 << 20
HASH = re.compile(r'^[0-9a-f]{64}$')
MTIME_MARGIN_NS = 100_000_000

spec = importlib.util.spec_from_file_location('current_native_applicator', PROJECT / 'native/apply_patches.py')
CURRENT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CURRENT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native_path(relative):
    path = PurePosixPath(relative)
    if (path.is_absolute() or not path.parts or '..' in path.parts or '\\' in relative or
        path.suffix not in ('.cc', '.h', '.idl') or path.parts[0] in ('build', 'buildtools', 'tools') or
        any(relative.startswith(prefix) for prefix in ('third_party/depot_tools/', 'third_party/llvm-build/',
            'third_party/llvm-libclang/', 'third_party/rust-toolchain/', 'third_party/cpython3/',
            'third_party/node/', 'third_party/ninja/'))):
        raise RuntimeError(f'Migration forbids nonnative/configuration path: {relative}')
    return path


def patch_path(relative):
    path = PurePosixPath(relative)
    if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in relative or path.parts[0] != 'patches' or path.suffix != '.patch':
        raise RuntimeError('Unrecognized native patch path')
    return path


def bundle(provenance, patch, label):
    manifest = json.loads(provenance)
    if manifest.get('schema_version') != 1 or manifest.get('upstream_tag') != PINS['version'] or manifest.get('upstream_revision') != PINS['revision']:
        raise RuntimeError(f'{label} native manifest schema/upstream mismatch')
    patch_path(manifest['patch'])
    if digest(patch) != manifest['patch_sha256']:
        raise RuntimeError(f'{label} native patch SHA-256 mismatch')
    hunks = CURRENT.parse_patch(patch.decode('utf-8'))
    records = {}
    for record in manifest['files']:
        native_path(record['path'])
        if record['path'] in records or not all(HASH.fullmatch(record[key]) for key in ('upstream_sha256', 'patched_sha256')):
            raise RuntimeError(f'{label} duplicate path or invalid source digest')
        records[record['path']] = record
    if not 1 <= len(records) <= MAX_FILES or records.keys() != hunks.keys():
        raise RuntimeError(f'{label} native patch/manifest file set mismatch')
    return {'manifest': manifest, 'records': records, 'hunks': hunks}


def github_blob(commit, relative, limit):
    # Endpoints are always this repository; metadata cannot supply another URL.
    endpoint = f'repos/{os.environ["GITHUB_REPOSITORY"]}/contents/{quote(relative, safe="/")}?ref={commit}'
    response = subprocess.check_output(['gh', 'api', endpoint], text=True, timeout=120)
    if len(response) > limit * 2 + 16384:
        raise RuntimeError('Oversized seed metadata response')
    record = json.loads(response)
    if record.get('type') != 'file' or record.get('encoding') != 'base64' or record['size'] > limit:
        raise RuntimeError(f'Oversized or nonfile seed metadata: {relative}')
    data = base64.b64decode(''.join(record['content'].split()), validate=True)
    blob_hash = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if len(data) != record['size'] or blob_hash != record['sha']:
        raise RuntimeError('Git blob response failed its size/hash check')
    return data


def fingerprint_blobs(platform, pins, provenance, applicator, patch, relative):
    result = hashlib.sha256(pins)
    result.update(platform.encode())
    for name, data in (('native/provenance.json', provenance), ('native/apply_patches.py', applicator), (relative, patch)):
        result.update(name.encode())
        result.update(data)
    return result.hexdigest()


@dataclass(frozen=True)
class Proof:
    old: dict
    new: dict
    old_fingerprint: str
    new_fingerprint: str
    old_commit: str
    old_ref: str
    seed_tag: str
    platform: str
    new_commit: str


def prove_seed(state, platform, root, seed_tag, fetch_blob=github_blob, verify_ref=require_tag):
    old_ref, old_commit = APPROVED_SEEDS[platform]
    if state.get('repository_commit') != old_commit:
        raise RuntimeError('Checkpoint is outside the explicit seed-ref allowlist')
    if (state.get('schema') != 1 or state.get('platform') != platform or Path(state['root']) != root or
        state.get('version') != PINS['version'] or state.get('revision') != PINS['revision'] or
        state.get('phase') not in ('source-ready', 'build-ready') or
        state.get('status') not in ('bootstrap-incomplete', 'prepared', 'pending', 'failed', 'disk-blocked', 'complete')):
        raise RuntimeError('Seed platform/root/schema/upstream/phase mismatch')
    verify_ref(old_ref, old_commit)
    old_pins = fetch_blob(old_commit, 'ci/pins.json', 64 << 10)
    if old_pins != (PROJECT / 'ci/pins.json').read_bytes():
        raise RuntimeError('Seed PINS/configuration differ from current build')
    provenance = fetch_blob(old_commit, 'native/provenance.json', 128 << 10)
    applicator = fetch_blob(old_commit, 'native/apply_patches.py', 128 << 10)
    relative = json.loads(provenance)['patch']
    patch_path(relative)
    patch = fetch_blob(old_commit, relative, 2 << 20)
    old = bundle(provenance, patch, 'Old')
    old_fingerprint = fingerprint_blobs(platform, old_pins, provenance, applicator, patch, relative)
    if old_fingerprint != state['fingerprint'] or not seed_tag.startswith(f'checkpoint-{platform}-{old_fingerprint[:20]}-'):
        raise RuntimeError('Seed fingerprint/tag failed independent Git-blob proof')
    current_provenance = (PROJECT / 'native/provenance.json').read_bytes()
    current_relative = json.loads(current_provenance)['patch']
    patch_path(current_relative)
    new = bundle(current_provenance, (PROJECT / current_relative).read_bytes(), 'Current')
    return Proof(old, new, old_fingerprint, fingerprint(platform), old_commit, old_ref,
                 seed_tag, platform, source_commit())


def plan_source(root, proof, state, max_output_mtime_ns):
    source = root / 'src'
    out = source / 'out/AlwaysActive'
    args = out / 'args.gn'
    if not out.exists() and not out.is_symlink():
        if (state.get('phase') != 'source-ready' or state.get('status') != 'bootstrap-incomplete' or
            max_output_mtime_ns != 0):
            raise RuntimeError('Absent output tree is allowed only for a strict source-only seed')
    elif not args.is_file() or args.read_text(encoding='utf-8') != rendered_gn_args(proof.platform):
        raise RuntimeError('Restored GN arguments differ or are unavailable')
    old, new = proof.old, proof.new
    paths = sorted(old['records'].keys() | new['records'].keys())
    if len(paths) > MAX_FILES:
        raise RuntimeError('Native migration file-count bound exceeded')
    total = 0
    identities = set()
    plan = []
    for relative in paths:
        native_path(relative)
        path = CURRENT.safe_path(source.resolve(), relative)
        info = path.lstat()
        identity = os.path.normcase(str(path.resolve()))
        if not stat.S_ISREG(info.st_mode) or identity in identities or info.st_size > MAX_FILE_BYTES:
            raise RuntimeError(f'Nonregular, aliased, or oversized native source: {relative}')
        identities.add(identity)
        data = path.read_bytes()
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError('Native migration byte bound exceeded')
        before, after = old['records'].get(relative), new['records'].get(relative)
        if before and after and before['upstream_sha256'] != after['upstream_sha256']:
            raise RuntimeError(f'Native upstream source differs: {relative}')
        original_hash = (after or before)['upstream_sha256']
        current_hash = digest(data)
        allowed = {original_hash}
        if before:
            allowed.add(before['patched_sha256'])
        if current_hash not in allowed:
            raise RuntimeError(f'Unknown native source edit: {relative}')
        target_hash = after['patched_sha256'] if after else original_hash
        # Byte-identical targets remain untouched, including their exact mtimes.
        if current_hash == target_hash:
            continue
        original = data
        if before and current_hash == before['patched_sha256']:
            original = CURRENT.transform(data, old['hunks'][relative], reverse=True)
        if digest(original) != original_hash:
            raise RuntimeError(f'Old native reverse transformation failed: {relative}')
        updated = CURRENT.transform(original, new['hunks'][relative]) if after else original
        if digest(updated) != target_hash:
            raise RuntimeError(f'New native transformation failed: {relative}')
        plan.append({'relative': relative, 'path': path, 'before': data, 'after': updated,
                     'mode': info.st_mode, 'atime_ns': info.st_atime_ns, 'mtime_ns': info.st_mtime_ns,
                     'before_sha256': current_hash, 'after_sha256': target_hash})
    return plan


def replace_file(path, data, mode, atime_ns, mtime_ns):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.native-migration-', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.utime(temporary, ns=(atime_ns, mtime_ns))
        # Windows cannot replace a readonly destination even when its parent is writable.
        path.chmod(mode | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def migrate_source(root, proof, max_output_mtime_ns, replacer=replace_file, verifier=None):
    state_file = root / 'state.json'
    state = json.loads(state_file.read_text())
    if state['fingerprint'] != proof.old_fingerprint:
        raise RuntimeError('Restored state differs from verified seed')
    plan = plan_source(root, proof, state, max_output_mtime_ns)  # Complete validation precedes every write.
    now = time.time_ns()
    if max_output_mtime_ns > now + 300_000_000_000:
        raise RuntimeError('Unreasonable future compiler-output timestamp in seed')
    desired = max(now, max_output_mtime_ns + MTIME_MARGIN_NS + 1_000_000)
    history = state.get('native_migrations', [])
    if not isinstance(history, list) or len(history) >= 8:
        raise RuntimeError('Native migration audit bound exceeded')
    attempted = []
    try:
        for change in plan:
            if digest(change['path'].read_bytes()) != change['before_sha256']:
                raise RuntimeError('Native source changed after migration validation')
            attempted.append(change)
            replacer(change['path'], change['after'], change['mode'], change['atime_ns'], desired)
            actual = change['path'].stat().st_mtime_ns
            if actual <= max_output_mtime_ns or actual - max_output_mtime_ns < MTIME_MARGIN_NS:
                raise RuntimeError('Filesystem rounded the changed source mtime below the required output margin')
            if digest(change['path'].read_bytes()) != change['after_sha256']:
                raise RuntimeError('Written native source failed its target digest')
        if verifier:
            verifier()
        else:
            subprocess.run([sys.executable, str(PROJECT / 'native/apply_patches.py'),
                            '--source', str(root / 'src'), '--verify-applied'], check=True)
        state['fingerprint'] = proof.new_fingerprint
        state['repository_commit'] = proof.new_commit
        state['phase'] = 'source-ready'
        state['status'] = 'bootstrap-incomplete'
        state['native_migrations'] = history + [{
            'from_ref': proof.old_ref, 'from_commit': proof.old_commit,
            'from_fingerprint': proof.old_fingerprint, 'seed_checkpoint': proof.seed_tag,
            'to_commit': proof.new_commit, 'to_fingerprint': proof.new_fingerprint,
            'changed_paths': [item['relative'] for item in plan],
            'changed_source_mtime_ns': desired, 'max_restored_output_mtime_ns': max_output_mtime_ns,
        }]
        # Commit the new state only after every source write and native verification.
        info = state_file.stat()
        replace_file(state_file, (json.dumps(state, indent=2) + '\n').encode(),
                     info.st_mode, info.st_atime_ns, time.time_ns())
    except BaseException:
        for change in reversed(attempted):
            replace_file(change['path'], change['before'], change['mode'], change['atime_ns'], change['mtime_ns'])
        raise
    return state
