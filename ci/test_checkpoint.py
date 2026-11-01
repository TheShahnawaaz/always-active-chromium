"""Small local tests for checkpoint correctness; never fetch or compile Chromium."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

import zstandard

from checkpoint import ChunkReader, ChunkWriter, pack, restore_archive


class CheckpointTests(unittest.TestCase):
    def capture(self, root):
        blobs = {}
        writer = ChunkWriter(root / 'upload', lambda path: blobs.update({path.name: path.read_bytes()}), limit=1024)
        with contextlib.redirect_stdout(io.StringIO()):
            pack(root, writer)
        return writer.parts, blobs

    def reader(self, records, blobs):
        return ChunkReader(records, {}, lambda record: io.BytesIO(blobs[record['name']]))

    def test_split_restore_preserves_contents_modes_symlinks_and_nanoseconds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'before'
            source = root / 'src/nested'
            source.mkdir(parents=True)
            file = source / 'object.o'
            content = os.urandom(8192)
            file.write_bytes(content)
            file.chmod(0o755)
            timestamp = 1712345678123456700 if os.name == 'nt' else 1712345678123456789
            os.utime(file, ns=(timestamp, timestamp))
            (root / 'state.json').write_text(json.dumps({'status': 'pending'}))
            linked = False
            try:
                (source / 'alias').symlink_to('object.o')
                linked = True
            except OSError:
                pass
            parts, blobs = self.capture(root)
            self.assertGreater(len(parts), 1)
            self.assertTrue(all(item['size'] <= 1024 for item in parts))
            destination = Path(temporary) / 'after'
            destination.mkdir()
            restore_archive(destination, self.reader(parts, blobs))
            restored = destination / 'src/nested/object.o'
            self.assertEqual(restored.read_bytes(), content)
            self.assertEqual(restored.stat().st_mtime_ns, timestamp)
            if os.name != 'nt':
                self.assertEqual(restored.stat().st_mode & 0o777, 0o755)
            if linked:
                self.assertTrue((destination / 'src/nested/alias').is_symlink())
                self.assertEqual((destination / 'src/nested/alias').read_bytes(), content)

    def test_corrupt_chunk_fails_its_checksum(self):
        data = b'correct bytes'
        records = [{'name': 'part', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]
        reader = self.reader(records, {'part': b'corrupt bytes'})
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            while reader.read(4096):
                pass

    def test_archive_cannot_write_outside_restore_root(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as archive:
            member = tarfile.TarInfo('../escape')
            member.size = 1
            archive.addfile(member, io.BytesIO(b'x'))
        compressed = zstandard.ZstdCompressor().compress(raw.getvalue())
        records = [{'name': 'part', 'size': len(compressed), 'sha256': hashlib.sha256(compressed).hexdigest()}]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'restore'
            destination.mkdir()
            with self.assertRaisesRegex(RuntimeError, 'Unexpected checkpoint member'):
                restore_archive(destination, self.reader(records, {'part': compressed}))
            self.assertFalse((Path(temporary) / 'escape').exists())

    def test_generated_absolute_xcode_links_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'before'
            links = root / 'src/out/AlwaysActive/sdk/xcode_links'
            links.mkdir(parents=True)
            try:
                (links / 'Xcode.app').symlink_to('/Applications/Xcode_26.6.app')
            except OSError:
                self.skipTest('Creating a symlink is unavailable')
            (root / 'src/source.cc').write_text('source')
            parts, blobs = self.capture(root)
            destination = Path(temporary) / 'after'
            destination.mkdir()
            restore_archive(destination, self.reader(parts, blobs))
            self.assertEqual((destination / 'src/source.cc').read_text(), 'source')
            self.assertFalse((destination / 'src/out/AlwaysActive/sdk/xcode_links').exists())

    def test_restore_measures_output_time_without_unrelated_future_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'before'
            output = root / 'src/out/AlwaysActive/obj/seed.o'
            output.parent.mkdir(parents=True)
            output.write_bytes(b'compiler output')
            expected = 1712345678123456000
            os.utime(output, ns=(expected, expected))
            future = root / 'src/future-test-data.txt'
            future.write_bytes(b'unrelated test fixture')
            os.utime(future, ns=(expected + 10_000_000_000, expected + 10_000_000_000))
            parts, blobs = self.capture(root)
            destination = Path(temporary) / 'after'
            destination.mkdir()
            maximum = restore_archive(destination, self.reader(parts, blobs))
            self.assertEqual(maximum, expected)

    @unittest.skipUnless(shutil.which('ninja'), 'Ninja not available for the incremental database smoke check')
    def test_restored_ninja_dependency_database_needs_no_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'before'
            build = root / 'src/out/AlwaysActive'
            build.mkdir(parents=True)
            (build / 'input.txt').write_text('unchanged input')
            (build / 'build_one.py').write_text(
                'from pathlib import Path\n'
                'Path("object.o").write_bytes(Path("input.txt").read_bytes())\n'
                'Path("object.o.d").write_text("object.o: input.txt\\n")\n')
            (build / 'build.ninja').write_text(
                f'rule compile\n  command = "{sys.executable}" build_one.py\n'
                '  depfile = object.o.d\n  deps = gcc\n'
                'build object.o: compile input.txt\ndefault object.o\n')
            subprocess.run(['ninja', '-C', str(build)], check=True, capture_output=True)
            parts, blobs = self.capture(root)
            destination = Path(temporary) / 'after'
            destination.mkdir()
            restore_archive(destination, self.reader(parts, blobs))
            result = subprocess.run(['ninja', '-C', str(destination / 'src/out/AlwaysActive')],
                                    check=True, capture_output=True, text=True)
            self.assertIn('no work to do', result.stdout)


if __name__ == '__main__':
    unittest.main()
