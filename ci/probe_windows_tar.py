#!/usr/bin/env python3
"""Compare hosted Windows tar implementations on small, explicit fixtures.

No Chromium source download, no blanket ignored errors, no user-machine changes.
The intentionally unsupported-name fixtures are diagnostic, not success criteria.
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


PREFIX = 'chromium-156.0.8078.80'


def fixture(path, kind):
    archive_format = tarfile.GNU_FORMAT if kind == 'raw-byte-name' else tarfile.PAX_FORMAT
    expected = []
    with tarfile.open(path, 'w:xz', format=archive_format, preset=1) as archive:
        root = tarfile.TarInfo(PREFIX + '/')
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        archive.addfile(root)

        def add(name):
            member = tarfile.TarInfo(PREFIX + '/' + name)
            member.size = len(b'fixture data\n')
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(b'fixture data\n'))
            expected.append(name)

        if kind == 'unicode-pax':
            add('third_party/blink/web_tests/resources/ascii.txt')
            add('third_party/blink/web_tests/resources/caf\u00e9-\u65e5\u672c-\U0001f680.txt')
            add('third_party/blink/web_tests/resources/cafe\u0301.txt')
        elif kind == 'long-path-pax':
            add('third_party/blink/web_tests/' + '/'.join('nested-' + 'a' * 35 for _ in range(8)) + '/file.txt')
        elif kind == 'links-pax':
            add('resources/file.txt')
            member = tarfile.TarInfo(PREFIX + '/resources/relative-link.txt')
            member.type = tarfile.SYMTYPE
            member.linkname = 'file.txt'
            archive.addfile(member)
            member = tarfile.TarInfo(PREFIX + '/resources/hard-link.txt')
            member.type = tarfile.LNKTYPE
            member.linkname = PREFIX + '/resources/file.txt'
            archive.addfile(member)
        elif kind == 'raw-byte-name':
            add('third_party/blink/web_tests/resources/non-utf8-\udcff.txt')
        elif kind == 'ntfs-special-name':
            add('third_party/blink/web_tests/resources/colon:name.txt')
            add('third_party/blink/web_tests/resources/trailing-dot.')
        else:
            raise ValueError(kind)
    return expected


def execute(command, env):
    result = subprocess.run(command, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=90)
    return {'return_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


def main():
    if os.name != 'nt' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Run this probe only on the ephemeral hosted Windows runner.')
    native = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/tar.exe'
    git = Path(shutil.which('git')).resolve()
    gitbin = git.parent.parent / 'usr/bin'
    gnu = gitbin / 'tar.exe'
    utf8 = dict(os.environ, LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8')
    gnu_env = dict(utf8, MSYS='winsymlinks:nativestrict', PATH=str(gitbin) + os.pathsep + os.environ['PATH'])
    engines = [('native-default', native, os.environ.copy(), False),
               ('native-utf8', native, utf8, False)]
    if gnu.is_file():
        engines.append(('git-gnu-utf8', gnu, gnu_env, True))
    report = {'git': str(git), 'gnu_tar': str(gnu), 'gnu_present': gnu.is_file(), 'engines': {}}
    with tempfile.TemporaryDirectory(prefix='aacc-tar-probe-', dir=os.environ['RUNNER_TEMP'],
                                     ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        for label, executable, env, is_gnu in engines:
            version = execute([str(executable), '--version'], env)
            cases = {}
            for kind in ('unicode-pax', 'long-path-pax', 'links-pax', 'raw-byte-name', 'ntfs-special-name'):
                archive = directory / (kind + '.tar.xz')
                expected = fixture(archive, kind)
                destination = directory / label / kind
                destination.mkdir(parents=True)
                command = [str(executable)]
                if is_gnu:
                    command.append('--force-local')
                command += ['-xf', archive.as_posix(), '-C', destination.as_posix(), '--strip-components=1']
                record = execute(command, env)
                record['expected_names_present'] = all((destination / name).is_file() for name in expected)
                record['extracted_names'] = sorted(path.relative_to(destination).as_posix()
                                                   for path in destination.rglob('*') if not path.is_dir())
                if kind == 'links-pax':
                    symbolic = destination / 'resources/relative-link.txt'
                    hard = destination / 'resources/hard-link.txt'
                    original = destination / 'resources/file.txt'
                    record['native_symlink'] = symbolic.is_symlink()
                    record['symbolic_contents_match'] = symbolic.is_file() and symbolic.read_bytes() == original.read_bytes()
                    record['native_hardlink'] = hard.exists() and hard.samefile(original)
                cases[kind] = record
            report['engines'][label] = {'version': version, 'cases': cases}
    print(json.dumps(report, indent=2, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
