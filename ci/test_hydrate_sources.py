"""Tiny closed Git-tree archive fixtures; no Chromium/network download."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock

import hydrate_sources as hydration


class SourceHydrationTests(unittest.TestCase):
    def fixture(self, root):
        contents = {'src/implementation.cpp': b'#include "../include/header.h"\n',
                    'include/header.h': b'// pinned header\n', 'LICENSE': b'pinned license\n'}
        files = [{'path': path, 'mode': '100644', 'blob': hydration.git_digest('blob', content),
                  'size': len(content)} for path, content in contents.items()]
        pin = {'relative': 'src/third_party/fixture/src', 'repository': 'https://example.invalid/fixture.git',
               'revision': '1' * 40, 'tree': hydration.tree_digest(files), 'archive_prefix': 'fixture-' + '1' * 40,
               'archive_url': 'https://example.invalid/fixture.tar.gz', 'files': files}
        scope = {'deps': {pin['relative']: {'url': pin['repository'] + '@' + pin['revision'], 'condition': True}}}
        archive = root / 'fixture.tar.gz'
        self.archive(archive, pin, contents)
        downloader = mock.Mock(side_effect=lambda _url, output: shutil.copyfile(archive, output))
        return contents, pin, scope, downloader

    def archive(self, path, pin, contents, extra=None):
        with tarfile.open(path, 'w:gz', format=tarfile.PAX_FORMAT) as archive:
            for relative, content in contents.items():
                member = tarfile.TarInfo(pin['archive_prefix'] + '/' + relative)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            if extra:
                archive.addfile(extra)

    def test_complete_headers_license_tree_and_resume_preserve_matching_mtimes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents, pin, scope, download = self.fixture(root)
            src = root / 'src'
            record = hydration.hydrate_one(src, scope, bool, pin, download)
            target = root / pin['relative']
            self.assertEqual(record['archive_sha256'], hashlib.sha256((root / 'fixture.tar.gz').read_bytes()).hexdigest())
            self.assertEqual(record['git_tree'], pin['tree'])
            stamps = {}
            for path, content in contents.items():
                self.assertEqual((target / path).read_bytes(), content)
                stamps[path] = (target / path).stat().st_mtime_ns
            self.assertEqual(hydration.hydrate_one(src, scope, bool, pin, download), record)
            download.assert_called_once()
            for path, stamp in stamps.items():
                self.assertEqual((target / path).stat().st_mtime_ns, stamp)
            # A known partial tree heals only missing files; retained C++/header
            # mtimes do not trigger needless Ninja work after resume.
            (target / 'LICENSE').unlink()
            hydration.hydrate_one(src, scope, bool, pin, download)
            self.assertEqual(download.call_count, 2)
            for path in ('src/implementation.cpp', 'include/header.h'):
                self.assertEqual((target / path).stat().st_mtime_ns, stamps[path])

    def test_foreign_existing_file_rejects_before_download_or_any_source_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _contents, pin, scope, download = self.fixture(root)
            target = root / pin['relative']
            foreign = target / 'include/header.h'
            foreign.parent.mkdir(parents=True)
            foreign.write_bytes(b'foreign edit')
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                hydration.hydrate_one(root / 'src', scope, bool, pin, download)
            download.assert_not_called()
            self.assertEqual(foreign.read_bytes(), b'foreign edit')
            self.assertFalse((target / 'src/implementation.cpp').exists())

    def test_wrong_tree_or_deps_revision_reject_before_downloading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _contents, pin, scope, download = self.fixture(root)
            wrong = dict(pin, tree='0' * 40)
            with self.assertRaisesRegex(RuntimeError, 'Git tree mismatch'):
                hydration.hydrate_one(root / 'src', scope, bool, wrong, download)
            scope['deps'][pin['relative']]['url'] += 'foreign'
            with self.assertRaisesRegex(RuntimeError, 'archive DEPS'):
                hydration.hydrate_one(root / 'src', scope, bool, pin, download)
            download.assert_not_called()

    def test_corrupt_incomplete_and_link_archives_cannot_write_a_partial_tree(self):
        for variant in ('foreign', 'missing', 'link', 'traversal'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                contents, pin, scope, download = self.fixture(root)
                contents = dict(contents)
                extra = None
                if variant == 'foreign':
                    contents['LICENSE'] = b'foreign license'
                elif variant == 'missing':
                    del contents['LICENSE']
                else:
                    name = 'unexpected' if variant == 'link' else '../outside'
                    extra = tarfile.TarInfo(pin['archive_prefix'] + '/' + name)
                    if variant == 'link':
                        extra.type = tarfile.SYMTYPE
                        extra.linkname = '../../outside'
                self.archive(root / 'fixture.tar.gz', pin, contents, extra)
                with self.assertRaises(RuntimeError):
                    hydration.hydrate_one(root / 'src', scope, bool, pin, download)
                self.assertFalse((root / pin['relative']).exists())
                self.assertFalse((root / 'outside').exists())

    def test_unknown_existing_file_and_tree_bounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _contents, pin, scope, download = self.fixture(root)
            target = root / pin['relative']
            target.mkdir(parents=True)
            (target / 'unknown').write_bytes(b'foreign')
            with self.assertRaisesRegex(RuntimeError, 'Foreign file'):
                hydration.hydrate_one(root / 'src', scope, bool, pin, download)
            download.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'Invalid pinned source object'):
            hydration.tree_digest([{'path': 'large', 'mode': '100644', 'blob': '0' * 40,
                                    'size': hydration.MAX_FILE_BYTES + 1}])
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            hydration.safe_relative('../outside')
        reader = hydration.BoundedTarReader(io.BytesIO(b'x' * 100), 10)
        with self.assertRaisesRegex(RuntimeError, 'decompressed byte bounds'):
            reader.read(100)

    def test_all_real_complete_manifests_reconstruct_exact_pinned_git_trees(self):
        manifest = json.loads(hydration.MANIFEST.read_text())
        expected = {(81, 4265112), (15, 145661), (8, 101632)}
        actual = set()
        for pin in manifest['dependencies']:
            self.assertEqual(hydration.tree_digest(pin['files']), pin['tree'])
            self.assertEqual((pin['repository'], pin['revision'], pin['tree']), hydration.ALLOWED[pin['relative']])
            self.assertIn('LICENSE', {item['path'] for item in pin['files']})
            actual.add((len(pin['files']), sum(item['size'] for item in pin['files'])))
        self.assertEqual(actual, expected)

    def test_webauthn_complete_closure_is_selected_and_foreign_archive_refuses_before_writes(self):
        manifest = json.loads(hydration.MANIFEST.read_text())
        webauthn = next(pin for pin in manifest['dependencies'] if pin['relative'].endswith('microsoft_webauthn/src'))
        self.assertIn('webauthn.h', {item['path'] for item in webauthn['files']})
        with mock.patch.object(hydration, 'hydrate_one', return_value={}) as hydrate:
            hydration.hydrate_windows_sources(Path('/unused/src'), {}, bool)
            self.assertEqual([call.args[3]['relative'] for call in hydrate.call_args_list],
                             [pin['relative'] for pin in manifest['dependencies']])
        # A new allowed root must not create an arbitrary download/write path.
        webauthn['archive_url'] = webauthn['archive_url'].replace('codeload.github.com', 'foreign.invalid')
        with mock.patch.object(Path, 'read_text', return_value=json.dumps(manifest)), \
                mock.patch.object(hydration, 'hydrate_one') as hydrate:
            with self.assertRaisesRegex(RuntimeError, 'archive identity'):
                hydration.hydrate_windows_sources(Path('/unused/src'), {}, bool)
            hydrate.assert_not_called()

    def test_unlisted_windows_source_root_cannot_expand_the_allowlist(self):
        manifest = json.loads(hydration.MANIFEST.read_text())
        manifest['dependencies'].append(dict(manifest['dependencies'][-1], relative='src/third_party/unlisted/src'))
        with mock.patch.object(Path, 'read_text', return_value=json.dumps(manifest)), \
                mock.patch.object(hydration, 'hydrate_one') as hydrate:
            with self.assertRaisesRegex(RuntimeError, 'Unexpected pinned Windows source manifest'):
                hydration.hydrate_windows_sources(Path('/unused/src'), {}, bool)
            hydrate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
