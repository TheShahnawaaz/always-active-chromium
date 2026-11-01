#!/usr/bin/env python3
"""Acquire exact public test references; never uses a user's browser/profile.

Only Python's standard library is required. The CRX must match the audited
package exactly; a store update fails closed instead of silently changing the
oracle. CFT URLs and the measured Mac/Windows ZIP digests are pinned.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import sys
import urllib.request
import zipfile

VERSION = "156.0.8078.80"
REVISION = "fb096c0011f9d50f0a264a9376420cdea9c421e3"
EXTENSION_ID = "ehllkhjndgnlokhomdlhgbineffifcbj"
EXTENSION_SHA256 = "17e792706dcc8d7b1ad236bd090b662ca97786c085594b35da421851a33b655b"
EXTENSION_ZIP_SHA256 = "8eee6ad2b1fbc04726f77eb6eada38c700b91f13132cb64b8012cd9b7e7b038c"
MAC_ZIP_SHA256 = "8bc590d1b1acac042a000234c768f31830f25a3983a83ed5e067114c87c4cad1"
WINDOWS_ZIP_SHA256 = "16edb57d6107bf1c48a7c149b8d78b155fe614410093796dd72441fd6640540f"
EXTENSION_URL = ("https://clients2.google.com/service/update2/crx?response=redirect"
                 f"&prodversion={VERSION}&acceptformat=crx3&x=id%3D{EXTENSION_ID}%26uc")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, destination: Path, maximum: int) -> str:
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "AlwaysActiveChromiumReference/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("xb") as out:
            if not response.url.startswith("https://"):
                raise ValueError("Download redirected away from HTTPS")
            total = 0
            h = hashlib.sha256()
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > maximum:
                    raise ValueError(f"Download exceeds {maximum} bytes")
                h.update(chunk)
                out.write(chunk)
        partial.replace(destination)
        return h.hexdigest()
    finally:
        partial.unlink(missing_ok=True)


def crx3_zip(package: bytes) -> bytes:
    if len(package) < 12 or package[:4] != b"Cr24":
        raise ValueError("Expected a CRX package")
    version, header_size = struct.unpack_from("<II", package, 4)
    if version != 3 or header_size > len(package) - 12:
        raise ValueError("Invalid/unsupported CRX3 header")
    payload = package[12 + header_size:]
    if not payload.startswith(b"PK\x03\x04"):
        raise ValueError("CRX3 payload is not a ZIP")
    if hashlib.sha256(payload).hexdigest() != EXTENSION_ZIP_SHA256:
        raise ValueError("Derived extension ZIP does not match the audited payload")
    return payload


def member_path(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if not name or "\\" in name or "\x00" in name or p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    if any(":" in part for part in p.parts):
        raise ValueError(f"ZIP path contains drive/stream syntax: {name!r}")
    return p


def safe_extract(archive: zipfile.ZipFile, destination: Path, maximum: int) -> None:
    """Validate all names first; preserve only safe Mac framework symlinks.

    Files are extracted before symlinks so no entry can traverse an archive
    symlink. Windows reference/extension archives should not contain symlinks.
    """
    entries = archive.infolist()
    if len(entries) > 100000 or sum(i.file_size for i in entries) > maximum:
        raise ValueError("ZIP exceeds extraction budget")
    paths: dict[PurePosixPath, zipfile.ZipInfo] = {}
    links: dict[PurePosixPath, str] = {}
    for entry in entries:
        relative = member_path(entry.filename)
        if relative in paths:
            raise ValueError(f"Duplicate ZIP path: {entry.filename}")
        paths[relative] = entry
        mode = entry.external_attr >> 16
        if stat.S_ISLNK(mode):
            target = archive.read(entry).decode("utf-8")
            if not target or "\\" in target or "\x00" in target or PurePosixPath(target).is_absolute():
                raise ValueError(f"Unsafe ZIP symlink: {entry.filename}")
            normalized = os.path.normpath(str(relative.parent / target)).replace("\\", "/")
            if normalized == ".." or normalized.startswith("../") or ":" in target:
                raise ValueError(f"ZIP symlink escapes extraction root: {entry.filename}")
            links[relative] = target
        elif stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError(f"Unsupported ZIP entry type: {entry.filename}")
    for relative in paths:
        if any(parent in links for parent in relative.parents):
            raise ValueError(f"ZIP member descends through symlink: {relative}")
    destination.mkdir(parents=True, exist_ok=False)
    for relative, entry in paths.items():
        if relative in links:
            continue
        target = destination.joinpath(*relative.parts)
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry) as source, target.open("xb") as out:
            shutil.copyfileobj(source, out)
        mode = entry.external_attr >> 16
        if os.name != "nt":
            target.chmod((mode & 0o777) or 0o644)
    for relative, target in links.items():
        link = destination.joinpath(*relative.parts)
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        # Validate complete chains too (e.g. framework -> Versions/Current).
        if not link.resolve().is_relative_to(destination.resolve()):
            raise ValueError(f"ZIP symlink chain escapes extraction root: {relative}")


def emit_outputs(values: dict[str, str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("Output path contains a newline")
                stream.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["mac-arm64", "win64", "win-x64"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cft-archive", type=Path, help="Reuse a local CFT ZIP (the pinned digest is still required)")
    args = parser.parse_args()
    selected = args.platform or ("mac-arm64" if sys.platform == "darwin" and platform.machine() == "arm64" else "win64" if sys.platform == "win32" else None)
    if selected == "win-x64":
        selected = "win64"
    if selected is None:
        parser.error("Select --platform mac-arm64 or win64")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    cft_url = f"https://storage.googleapis.com/chrome-for-testing-public/{VERSION}/{selected}/chrome-{selected}.zip"
    if args.cft_archive:
        archive_path = args.cft_archive.resolve()
        cft_sha = digest(archive_path)
    else:
        archive_path = root / f"chrome-{selected}.zip"
        print(f"Downloading pinned CFT {VERSION} {selected}", flush=True)
        cft_sha = download(cft_url, archive_path, 1024 * 1024 * 1024)
    expected_cft_sha = MAC_ZIP_SHA256 if selected == "mac-arm64" else WINDOWS_ZIP_SHA256
    if cft_sha != expected_cft_sha:
        raise ValueError(f"CFT {selected} ZIP SHA mismatch: {cft_sha}")
    extension_crx = root / f"{EXTENSION_ID}.crx"
    print("Downloading current extension and requiring the audited CRX digest", flush=True)
    extension_sha = download(EXTENSION_URL, extension_crx, 20 * 1024 * 1024)
    if extension_sha != EXTENSION_SHA256:
        raise ValueError(f"Extension changed; oracle refused. Expected {EXTENSION_SHA256}, got {extension_sha}")
    extension_zip = crx3_zip(extension_crx.read_bytes())
    extension_root = root / "extension"
    with zipfile.ZipFile(io.BytesIO(extension_zip)) as archive:
        safe_extract(archive, extension_root, 100 * 1024 * 1024)
    manifest = json.loads((extension_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != "0.4.8" or manifest.get("manifest_version") != 3:
        raise ValueError("Unexpected extension manifest identity")
    browser_root = root / "browser"
    with zipfile.ZipFile(archive_path) as archive:
        safe_extract(archive, browser_root, 3 * 1024 * 1024 * 1024)
    browser = browser_root / f"chrome-{selected}"
    if selected == "mac-arm64":
        browser /= "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    else:
        browser /= "chrome.exe"
    if not browser.is_file():
        raise ValueError(f"Expected browser executable missing: {browser}")
    provenance = {
        "schema": 1, "version": VERSION, "expected_revision": REVISION, "platform": selected,
        "cft": {"url": cft_url, "sha256": cft_sha, "acquisition": "provided-local" if args.cft_archive else "official-version-url", "digest_check": "pinned-known-digest"},
        "extension": {"url": EXTENSION_URL, "id": EXTENSION_ID, "version": manifest["version"], "crx_sha256": extension_sha, "zip_sha256": EXTENSION_ZIP_SHA256},
        "note": "Actual running browser revision must be read from tests/results.json Browser.getVersion; this file records the expected pin.",
    }
    provenance_path = root / "reference-provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    values = {"browser": str(browser), "extension": str(extension_root), "provenance": str(provenance_path), "cft_sha256": cft_sha, "extension_sha256": extension_sha, "version": VERSION, "revision": REVISION}
    emit_outputs(values)
    print(json.dumps(values), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Reference acquisition failed: {error}", file=sys.stderr)
        sys.exit(1)
