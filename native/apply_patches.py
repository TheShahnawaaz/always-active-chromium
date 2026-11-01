#!/usr/bin/env python3
"""Apply the pinned native patch without git, patch, a checkout, or dependencies.

Every source input and output is SHA-256 checked. No fuzzy patching or source
version guessing is permitted. Re-running after success is a no-op. A partial
application can be resumed because each input must match its recorded original
or patched digest. --reverse restores exactly the recorded originals.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_patch(text):
    files = {}
    lines = text.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        if lines[index].startswith("diff --git "):
            index += 1
            continue
        if not lines[index].startswith("--- a/"):
            raise ValueError(f"Unexpected patch line {index + 1}")
        old = lines[index][6:].rstrip("\n")
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ b/"):
            raise ValueError("Missing new-file header")
        new = lines[index][6:].rstrip("\n")
        if old != new or old in files:
            raise ValueError("Renames, deletions, and duplicate files forbidden")
        index += 1
        hunks = []
        while index < len(lines) and lines[index].startswith("@@ "):
            match = HUNK.match(lines[index])
            if not match:
                raise ValueError(f"Malformed hunk at line {index + 1}")
            old_start, old_count, new_start, new_count = match.groups()
            header = (int(old_start), int(old_count or 1),
                      int(new_start), int(new_count or 1))
            index += 1
            body = []
            seen_old = seen_new = 0
            while seen_old < header[1] or seen_new < header[3]:
                if index >= len(lines) or lines[index][0] not in " +-":
                    raise ValueError("Incomplete hunk")
                line = lines[index]
                body.append(line)
                seen_old += line[0] != "+"
                seen_new += line[0] != "-"
                index += 1
            if (seen_old, seen_new) != (header[1], header[3]):
                raise ValueError("Hunk line count mismatch")
            hunks.append((header, body))
        if not hunks:
            raise ValueError(f"No hunks in {old}")
        files[old] = hunks
    return files


def transform(data, hunks, reverse=False):
    original = data.decode("utf-8").splitlines(keepends=True)
    result = []
    cursor = 0
    for header, body in hunks:
        start = header[2 if reverse else 0] - 1
        if start < cursor or start > len(original):
            raise ValueError("Overlapping or out-of-range hunk")
        result.extend(original[cursor:start])
        cursor = start
        for line in body:
            marker, text = line[0], line[1:]
            if reverse:
                marker = {"+": "-", "-": "+", " ": " "}[marker]
            if marker != "+":
                if cursor >= len(original) or original[cursor] != text:
                    raise ValueError(f"Patch context mismatch at line {cursor + 1}")
                cursor += 1
            if marker != "-":
                result.append(text)
    result.extend(original[cursor:])
    return "".join(result).encode("utf-8")


def safe_path(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError(f"Unsafe patch path: {relative}")
    candidate = root.joinpath(*path.parts)
    try:
        candidate.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError(f"Source path escapes root: {relative}") from error
    return candidate


def check_version(source, expected, allow_partial):
    version = source / "chrome" / "VERSION"
    if not version.is_file():
        if allow_partial:
            return
        raise ValueError("Source missing chrome/VERSION; pass a Chromium source root")
    fields = dict(line.split("=", 1) for line in version.read_text().splitlines()
                  if "=" in line)
    actual = ".".join(fields.get(key, "") for key in
                      ("MAJOR", "MINOR", "BUILD", "PATCH"))
    if actual != expected:
        raise ValueError(f"Wrong source version: {actual}; required {expected}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="validate without writing")
    parser.add_argument("--reverse", action="store_true", help="restore pinned originals")
    parser.add_argument("--verify-applied", action="store_true",
                        help="require every input to have its patched digest")
    parser.add_argument("--allow-partial-source", action="store_true",
                        help="allow selected-file authoring snapshot without chrome/VERSION")
    args = parser.parse_args()
    if args.reverse and args.verify_applied:
        parser.error("--reverse and --verify-applied cannot be combined")
    project = Path(__file__).resolve().parent.parent
    manifest = json.loads((project / "native" / "provenance.json").read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported provenance manifest")
    patch_path = safe_path(project, manifest["patch"])
    patch = patch_path.read_bytes()
    if digest(patch) != manifest["patch_sha256"]:
        raise ValueError("Patch SHA-256 differs from provenance manifest")
    files = parse_patch(patch.decode("utf-8"))
    records = {record["path"]: record for record in manifest["files"]}
    if len(records) != len(manifest["files"]) or files.keys() != records.keys():
        raise ValueError("Patch/manifest file set mismatch")
    source = args.source.resolve(strict=True)
    check_version(source, manifest["upstream_tag"], args.allow_partial_source)
    changes = []
    for relative, hunks in files.items():
        path = safe_path(source, relative)
        data = path.read_bytes()
        record = records[relative]
        before = record["patched_sha256" if args.reverse else "upstream_sha256"]
        after = record["upstream_sha256" if args.reverse else "patched_sha256"]
        current = digest(data)
        if args.verify_applied and current != record["patched_sha256"]:
            raise ValueError(f"Native patch not applied: {relative}")
        if current == after:
            continue
        if current != before:
            raise ValueError(f"Unrecognized source SHA-256 (refusing to overwrite): {relative}")
        updated = transform(data, hunks, args.reverse)
        if digest(updated) != after:
            raise ValueError(f"Patched output SHA-256 mismatch: {relative}")
        changes.append((path, updated))
    # Validate the entire input set before making any write.
    if not args.check and not args.verify_applied:
        for path, data in changes:
            temporary = path.with_name(path.name + ".always-active-tmp")
            with temporary.open("xb") as stream:
                stream.write(data)
            temporary.chmod(path.stat().st_mode)
            temporary.replace(path)
    verb = "validated" if args.check or args.verify_applied else "restored" if args.reverse else "applied"
    print(f"Native patch {verb}: {len(files)} verified files, {len(changes)} changes; "
          f"Chromium {manifest['upstream_tag']} ({manifest['upstream_revision']})")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f"Native patch error: {error}", file=sys.stderr)
        sys.exit(1)
