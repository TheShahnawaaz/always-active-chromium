#!/usr/bin/env python3
"""Produce the auditable patch/manifest from selected pristine/edited files.

This authoring helper never downloads a Chromium checkout. It operates on the
small locally acquired source snapshots in native/.cache/{upstream,modified}.
The resulting checked-in patch and provenance.json are the build inputs.
"""

import argparse
import difflib
import hashlib
import json
from pathlib import Path


REVISION = "fb096c0011f9d50f0a264a9376420cdea9c421e3"
TAG = "156.0.8078.80"
PATCH_NAME = "0001-native-always-active.patch"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(__file__).parent / ".cache")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    output = project / "patches"
    output.mkdir(exist_ok=True)
    parts = []
    records = []
    for before in sorted((args.cache / "upstream").rglob("*")):
        if not before.is_file():
            continue
        relative = before.relative_to(args.cache / "upstream").as_posix()
        after = args.cache / "modified" / relative
        if not after.is_file():
            raise SystemExit(f"Missing edited snapshot: {relative}")
        original = before.read_bytes()
        edited = after.read_bytes()
        if original == edited:
            continue
        parts.append("diff --git a/{0} b/{0}\n".format(relative))
        parts.extend(difflib.unified_diff(
            original.decode("utf-8").splitlines(keepends=True),
            edited.decode("utf-8").splitlines(keepends=True),
            fromfile=f"a/{relative}", tofile=f"b/{relative}", n=3))
        records.append({
            "path": relative,
            "upstream_sha256": sha256(original),
            "patched_sha256": sha256(edited),
            "source_url": f"https://raw.githubusercontent.com/chromium/chromium/{REVISION}/{relative}",
        })
    if not records:
        raise SystemExit("No changes found")
    patch = "".join(parts).encode("utf-8")
    (output / PATCH_NAME).write_bytes(patch)
    manifest = {
        "schema_version": 1,
        "upstream_tag": TAG,
        "upstream_revision": REVISION,
        "patch": f"patches/{PATCH_NAME}",
        "patch_sha256": sha256(patch),
        "files": records,
    }
    (project / "native" / "provenance.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {PATCH_NAME}: {len(records)} source files, {len(patch)} bytes")


if __name__ == "__main__":
    main()
