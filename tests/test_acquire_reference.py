"""Finite archive-boundary checks; no browser launch or network required."""
import importlib.util
import io
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("acquire_reference", Path(__file__).with_name("acquire-reference.py"))
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def packed(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, value, mode in entries:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, value)
    out.seek(0)
    return zipfile.ZipFile(out)


class ArchiveBoundaryTests(unittest.TestCase):
    def extract(self, entries, budget=1000):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "extracted"
        with packed(entries) as archive:
            reference.safe_extract(archive, root, budget)
        return root

    def test_regular_file(self):
        root = self.extract([("app/run", b"binary", stat.S_IFREG | 0o755)])
        self.assertEqual((root / "app/run").read_bytes(), b"binary")
        if os.name != "nt":
            self.assertTrue((root / "app/run").stat().st_mode & stat.S_IXUSR)

    def test_path_traversal_rejected(self):
        for name in ("../escape", "/absolute", "C:/absolute", "a\\..\\escape"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.extract([(name, b"bad", stat.S_IFREG | 0o644)])

    def test_symlink_escape_rejected(self):
        for target in ("../escape", "/absolute"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.extract([("link", target, stat.S_IFLNK | 0o777)])

    def test_file_below_symlink_rejected(self):
        with self.assertRaises(ValueError):
            self.extract([("link", "real", stat.S_IFLNK | 0o777), ("link/file", b"bad", stat.S_IFREG | 0o644)])

    @unittest.skipIf(os.name == "nt", "Windows reference archives have no symlinks; creation needs extra OS privilege")
    def test_framework_symlink_preserved(self):
        root = self.extract([("Versions/156/file", b"binary", stat.S_IFREG | 0o755), ("Versions/Current", "156", stat.S_IFLNK | 0o777), ("binary", "Versions/Current/file", stat.S_IFLNK | 0o777)])
        self.assertTrue((root / "Versions/Current").is_symlink())
        self.assertEqual((root / "binary").read_bytes(), b"binary")

    def test_extraction_budget(self):
        with self.assertRaises(ValueError):
            self.extract([("large", b"12345", stat.S_IFREG | 0o644)], budget=4)

    def test_invalid_crx_header(self):
        for package in (b"", b"not-a-crx-package", b"Cr24" + struct.pack("<II", 2, 0), b"Cr24" + struct.pack("<II", 3, 1000)):
            with self.subTest(package=package), self.assertRaises(ValueError):
                reference.crx3_zip(package)


if __name__ == "__main__":
    unittest.main()
