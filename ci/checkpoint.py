#!/usr/bin/env python3
"""Stream compiler state through bounded draft Release assets, without Actions storage.

Only this project's checkpoint drafts are touched. A new generation becomes
usable when ready.json is uploaded last; until then the preceding one survives.
"""
import argparse
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import threading
import time

import zstandard

from build import fingerprint, output, root_path

PART_BYTES = 1_800_000_000  # Less than GitHub's 2 GiB per-release-asset limit.


def gh(*arguments, binary=False):
    return subprocess.run(['gh', *map(str, arguments)], check=True,
                          stdout=subprocess.PIPE, timeout=120).stdout if binary else json.loads(
        subprocess.run(['gh', *map(str, arguments)], check=True,
                       stdout=subprocess.PIPE, text=True, timeout=120).stdout)


def repository():
    value = os.environ['GITHUB_REPOSITORY']
    if value.count('/') != 1:
        raise RuntimeError('Unexpected repository name')
    return value


def releases():
    pages = gh('api', '--paginate', '--slurp', f'repos/{repository()}/releases?per_page=100')
    return sorted((item for page in pages for item in page),
                  key=lambda item: item['created_at'], reverse=True)


def assets(release):
    pages = gh('api', '--paginate', '--slurp',
               f'repos/{repository()}/releases/{release["id"]}/assets?per_page=100')
    return {item['name']: item for page in pages for item in page}


def prefix(platform):
    return f'checkpoint-{platform}-{fingerprint(platform)[:20]}-'


def upload(tag, path):
    for attempt in range(4):
        try:
            result = subprocess.run(['gh', 'release', 'upload', tag, str(path),
                                     '--repo', repository(), '--clobber'], check=False, timeout=1800)
            if result.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            print(f'Checkpoint upload timed out: {path.name}', flush=True)
        if attempt != 3:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f'Checkpoint asset upload failed after four attempts: {path.name}')


class ChunkWriter:
    def __init__(self, directory, on_part, limit=PART_BYTES):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.on_part = on_part
        self.limit = limit
        self.parts = []
        self.stream = None
        self.digest = None
        self.size = 0

    def writable(self):
        return True

    def write(self, data):
        total = len(data)
        data = memoryview(data)
        while data:
            if self.stream is None:
                self.path = self.directory / f'state.tar.zst.{len(self.parts):05d}'
                self.stream = self.path.open('wb')
                self.digest = hashlib.sha256()
                self.size = 0
            count = min(len(data), self.limit - self.size)
            self.stream.write(data[:count])
            self.digest.update(data[:count])
            self.size += count
            data = data[count:]
            if self.size == self.limit:
                self.finish_part()
        return total

    def flush(self):
        if self.stream:
            self.stream.flush()

    def finish_part(self):
        if self.stream is None:
            return
        self.stream.close()
        record = {'name': self.path.name, 'size': self.size, 'sha256': self.digest.hexdigest()}
        self.on_part(self.path)
        self.parts.append(record)
        self.path.unlink()
        self.stream = None
        print(f'Checkpoint part committed: {record}', flush=True)

    def close(self):
        self.finish_part()


def exact_mtime_filter(root):
    def apply(member):
        # GN's sdk_info.py creates absolute links to the selected runner Xcode.
        # They are generated metadata, not build products. GN recreates them
        # during prepare; retaining them would defeat safe restore filtering.
        excluded = 'src/out/AlwaysActive/sdk/xcode_links'
        if member.name == excluded or member.name.startswith(excluded + '/'):
            return None
        # Fail while saving, rather than producing a checkpoint that a future
        # safe extraction cannot restore.
        tarfile.data_filter(member, str(root))
        if member.isfile() or member.isdir():
            timestamp = (root / member.name).stat().st_mtime_ns
            member.pax_headers['mtime'] = f'{timestamp // 1_000_000_000}.{timestamp % 1_000_000_000:09d}'
        return member
    return apply


def pack(root, writer):
    # Exact nanoseconds matter: Ninja's dependency database stores object mtimes.
    # Rounding through a float would silently discard much incremental progress.
    with zstandard.ZstdCompressor(level=1, threads=2).stream_writer(writer, closefd=False) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for name in ('src', 'dependencies.json', 'state.json'):
                if (root / name).exists():
                    archive.add(root / name, arcname=name, filter=exact_mtime_filter(root))
    writer.close()


def save(platform):
    root = root_path()
    state = json.loads((root / 'state.json').read_text())
    if state['fingerprint'] != fingerprint(platform):
        raise RuntimeError('Refusing to checkpoint a different source/patch configuration')
    tag = prefix(platform) + os.environ['GITHUB_RUN_ID'] + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    storage_anchor = gh('api', f'repos/{repository()}')['default_branch']
    # Drafts are intermediate software build checkpoints, never claimed as binaries.
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository(), '--draft',
                    '--target', storage_anchor, '--title', f'Compiler checkpoint: {platform}',
                    '--notes', 'Internal resumable Chromium build state. Not an installable browser. '
                    'The release tag targets the default branch only as a storage anchor; '
                    'ready.json/state.json record the actual source version, native patch and checkout commit. '
                    'Created only on standard GitHub-hosted runners; replaced after the next complete checkpoint.'], check=True)
    writer = ChunkWriter(root / '.checkpoint-upload', lambda path: upload(tag, path))
    pack(root, writer)
    manifest = {'schema': 1, 'format': 'tar+zstd+pax-nanoseconds', 'state': state,
                'parts': writer.parts, 'run_id': os.environ['GITHUB_RUN_ID'],
                'checkpoint_storage_anchor': storage_anchor}
    ready = root / '.checkpoint-upload/ready.json'
    ready.write_text(json.dumps(manifest, indent=2) + '\n')
    upload(tag, ready)
    output('checkpoint_tag', tag)
    # Keep the preceding generation until the new ready.json and every part exist.
    for old in releases():
        if old['draft'] and old['tag_name'].startswith(prefix(platform)) and old['tag_name'] != tag:
            subprocess.run(['gh', 'release', 'delete', old['tag_name'], '--repo', repository(), '--yes'], check=True)
    ready.unlink()


class ChunkReader(io.RawIOBase):
    def __init__(self, parts, release_assets, opener=None):
        self.parts = iter(parts)
        self.release_assets = release_assets
        self.process = None
        self.stream = None
        self.opener = opener
        self.timer = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.stream is None:
                self.record = next(self.parts, None)
                if self.record is None:
                    return 0
                self.digest = hashlib.sha256()
                self.size = 0
                if self.opener:
                    self.stream = self.opener(self.record)
                else:
                    asset = self.release_assets[self.record['name']]
                    if asset['size'] != self.record['size']:
                        raise RuntimeError('Release asset size differs from checkpoint manifest')
                    # gh handles authenticated API redirects without leaking the token.
                    self.process = subprocess.Popen(['gh', 'api', asset['url'],
                        '-H', 'Accept: application/octet-stream'], stdout=subprocess.PIPE)
                    self.timer = threading.Timer(1800, self.process.kill)
                    self.timer.daemon = True
                    self.timer.start()
                    self.stream = self.process.stdout
            data = self.stream.read(len(buffer))
            if data:
                buffer[:len(data)] = data
                self.digest.update(data)
                self.size += len(data)
                return len(data)
            self.stream.close()
            self.stream = None
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if self.process and self.process.wait() != 0:
                raise RuntimeError('Checkpoint asset download failed')
            self.process = None
            if self.size != self.record['size'] or self.digest.hexdigest() != self.record['sha256']:
                raise RuntimeError(f'Checkpoint checksum failed: {self.record["name"]}')


def restore_archive(root, reader):
    directories = []
    with zstandard.ZstdDecompressor().stream_reader(reader, read_across_frames=True, closefd=False) as decompressed:
        with tarfile.open(fileobj=decompressed, mode='r|') as archive:
            for member in archive:
                if Path(member.name).parts[0] not in ('src', 'state.json', 'dependencies.json'):
                    raise RuntimeError(f'Unexpected checkpoint member: {member.name}')
                archive.extract(member, root, filter='data')
                if member.isfile() or member.isdir():
                    ns = int(Decimal(member.pax_headers.get('mtime', str(member.mtime))) * 1_000_000_000)
                    path = root / member.name
                    if member.isdir():
                        directories.append((path, ns))
                    else:
                        os.utime(path, ns=(ns, ns))
        # Consume the framing/footer and finish verification of every chunk.
        while decompressed.read(1 << 20):
            pass
    while reader.read(1 << 20):
        pass
    for path, ns in reversed(directories):
        os.utime(path, ns=(ns, ns))


def restore(platform):
    root = root_path()
    for release in releases():
        if not release['draft'] or not release['tag_name'].startswith(prefix(platform)):
            continue
        files = assets(release)
        if 'ready.json' not in files:
            print(f'Skipping incomplete checkpoint: {release["tag_name"]}', flush=True)
            continue
        manifest = json.loads(gh('api', files['ready.json']['url'], '-H', 'Accept: application/octet-stream', binary=True))
        if manifest['schema'] != 1 or manifest['format'] != 'tar+zstd+pax-nanoseconds':
            raise RuntimeError('Unsupported checkpoint format')
        state = manifest['state']
        if state['fingerprint'] != fingerprint(platform) or Path(state['root']) != root:
            raise RuntimeError('Checkpoint pin/path mismatch')
        reader = ChunkReader(manifest['parts'], files)
        restore_archive(root, reader)
        if json.loads((root / 'state.json').read_text()) != state:
            raise RuntimeError('Restored build-state manifest differs from ready.json')
        output('restored', 'true')
        output('checkpoint_tag', release['tag_name'])
        return
    print('No complete matching checkpoint; starting from the verified source archive.', flush=True)
    output('restored', 'false')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['restore', 'save'])
    parser.add_argument('--platform', required=True, choices=['mac-arm64', 'win-x64'])
    args = parser.parse_args()
    (save if args.command == 'save' else restore)(args.platform)
