#!/usr/bin/env python3
"""Verify a real draft package, then extract/install it on a fresh hosted runner."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform as host_platform
import plistlib
import posixpath
import re
import struct
import subprocess
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
TAG = re.compile(r'ci-source-([0-9a-f]{12})\Z')
REPOSITORY = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')


class DeliveryError(RuntimeError):
    def __init__(self, code, stage, exit_code=None):
        super().__init__(f'Delivery {code} at {stage}')
        self.code, self.stage, self.exit_code = code, stage, exit_code


def run(command, **kwargs):
    kwargs.setdefault('check', True)
    return subprocess.run([str(item) for item in command], **kwargs)


def sha256(file):
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def bounded_json(file, limit=1048576):
    if file.is_symlink() or not file.is_file() or file.stat().st_size > limit:
        raise DeliveryError('invalid_json_file', 'provenance')
    value = json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise DeliveryError('json_object_required', 'provenance')
    return value


def native_fingerprint(project, target):
    pins = (project / 'ci/pins.json').read_bytes()
    provenance = bounded_json(project / 'native/provenance.json')
    patch = provenance['patch']
    if not isinstance(patch, str) or not patch.startswith('patches/') or '\\' in patch or '..' in PurePosixPath(patch).parts:
        raise DeliveryError('invalid_native_patch_path', 'provenance')
    result = hashlib.sha256(pins)
    result.update(target.encode())
    for name in ['native/provenance.json', 'native/apply_patches.py', patch]:
        file = project / name
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(project.resolve()):
            raise DeliveryError('invalid_native_source_file', 'provenance')
        result.update(name.encode())
        result.update(file.read_bytes())
    return result.hexdigest()


def expected_package(source, source_tag, target, trusted=PROJECT, runner=run):
    match = TAG.fullmatch(source_tag)
    if not match or target not in ('mac-arm64', 'win-x64'):
        raise DeliveryError('invalid_source_or_platform', 'provenance')
    commit = runner(['git', '-C', source, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=30).stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not commit.startswith(match[1]):
        raise DeliveryError('source_tag_commit_mismatch', 'provenance')
    pins = bounded_json(source / 'ci/pins.json')
    if pins != bounded_json(trusted / 'ci/pins.json'):
        raise DeliveryError('unexpected_source_pins', 'provenance')
    fingerprint = native_fingerprint(source, target)
    if fingerprint != native_fingerprint(trusted, target):
        raise DeliveryError('unexpected_native_fingerprint', 'provenance')
    stem = f'always-active-chromium-{pins["version"]}-{target}'
    return {'source_tag': source_tag, 'source_commit': commit, 'platform': target,
            'version': pins['version'], 'revision': pins['revision'], 'pins': pins,
            'fingerprint': fingerprint, 'stem': stem,
            'release_tag': f'build-{pins["version"]}-{target}-{fingerprint[:12]}-{commit[:12]}',
            'package_name': stem + ('.zip' if target == 'mac-arm64' else '-installer.exe'),
            'manifest_name': stem + '-build.json', 'sums_name': stem + '-SHA256SUMS.txt'}


def validate_manifest(manifest, expected):
    build = manifest.get('build', {})
    if (manifest.get('source') != expected['pins'] or manifest.get('repository_commit') != expected['source_commit'] or
            manifest.get('source_tag') != expected['source_tag'] or build.get('fingerprint') != expected['fingerprint'] or
            build.get('platform') != expected['platform'] or build.get('version') != expected['version'] or
            build.get('revision') != expected['revision'] or build.get('status') != 'complete' or
            not str(manifest.get('workflow_run', '')).isdigit()):
        raise DeliveryError('build_provenance_mismatch', 'provenance')


def parse_sums(contents, stem):
    if len(contents) > 65536:
        raise DeliveryError('checksum_limit', 'provenance')
    result = {}
    for line in contents.splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or not match[2].startswith(stem + '-') and match[2] != stem + '.zip' or match[2] in result:
            raise DeliveryError('invalid_checksum_manifest', 'provenance')
        result[match[2]] = match[1]
    return result


def verify_asset(file, metadata, expected_hash=None):
    if (file.is_symlink() or not file.is_file() or file.stat().st_size != metadata.get('size') or
            file.stat().st_size <= 0 or file.stat().st_size > (2 << 30)):
        raise DeliveryError('asset_size_or_type_mismatch', 'download')
    actual = sha256(file)
    if expected_hash is not None and actual != expected_hash:
        raise DeliveryError('asset_checksum_mismatch', 'download')
    remote_digest = metadata.get('digest')
    if remote_digest is not None and remote_digest != 'sha256:' + actual:
        raise DeliveryError('asset_api_digest_mismatch', 'download')
    return {'name': file.name, 'id': metadata['id'], 'size': metadata['size'], 'sha256': actual}


def gh_json(arguments, runner):
    response = runner(['gh', *arguments], capture_output=True, text=True, timeout=120)
    if len(response.stdout) > (2 << 20):
        raise DeliveryError('github_metadata_limit', 'provenance')
    return json.loads(response.stdout)


def verify_ref(repository, tag, commit, runner):
    item = gh_json(['api', f'repos/{repository}/git/ref/tags/{tag}'], runner)['object']
    for _ in range(4):
        if item.get('type') != 'tag':
            break
        if not re.fullmatch(r'[0-9a-f]{40}', item.get('sha', '')):
            raise DeliveryError('invalid_git_tag', 'provenance')
        item = gh_json(['api', f'repos/{repository}/git/tags/{item["sha"]}'], runner)['object']
    if item.get('type') != 'commit' or item.get('sha') != commit:
        raise DeliveryError('remote_tag_mismatch', 'provenance')


def download_package(expected, repository, destination, runner):
    if not REPOSITORY.fullmatch(repository):
        raise DeliveryError('invalid_repository', 'provenance')
    for tag in [expected['source_tag'], expected['release_tag']]:
        verify_ref(repository, tag, expected['source_commit'], runner)
    release = gh_json(['release', 'view', expected['release_tag'], '--repo', repository,
                       '--json', 'tagName,isDraft,assets'], runner)
    if release.get('tagName') != expected['release_tag'] or release.get('isDraft') is not True:
        raise DeliveryError('real_draft_required', 'provenance')
    names = [expected['sums_name'], expected['manifest_name'], expected['package_name']]
    selected = {}
    for name in names:
        matches = [item for item in release.get('assets', []) if item.get('name') == name]
        limit = 65536 if name == expected['sums_name'] else 1048576 if name == expected['manifest_name'] else 2 << 30
        if (len(matches) != 1 or not isinstance(matches[0].get('id'), (str, int)) or
                not isinstance(matches[0].get('size'), int) or not 0 < matches[0]['size'] <= limit):
            raise DeliveryError('required_asset_not_unique', 'provenance')
        selected[name] = matches[0]
    observations = []
    for name in names[:2]:
        runner(['gh', 'release', 'download', expected['release_tag'], '--repo', repository,
                '--pattern', name, '--dir', destination], timeout=180)
        observations.append(verify_asset(destination / name, selected[name]))
    sums = parse_sums((destination / expected['sums_name']).read_text(encoding='utf-8'), expected['stem'])
    if expected['manifest_name'] not in sums or expected['package_name'] not in sums:
        raise DeliveryError('required_checksum_missing', 'provenance')
    verify_asset(destination / expected['manifest_name'], selected[expected['manifest_name']], sums[expected['manifest_name']])
    validate_manifest(bounded_json(destination / expected['manifest_name']), expected)
    name = expected['package_name']
    runner(['gh', 'release', 'download', expected['release_tag'], '--repo', repository,
            '--pattern', name, '--dir', destination], timeout=900)
    observations.append(verify_asset(destination / name, selected[name], sums[name]))
    return destination / name, observations


def validate_zip(archive):
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if len(members) > 100000 or sum(item.file_size for item in members) > (8 << 30):
            raise DeliveryError('zip_size_limit', 'extract')
        seen = set()
        for item in members:
            name = item.filename.rstrip('/')
            parts = PurePosixPath(name).parts
            if not parts or parts[0] not in ('Chromium.app', '__MACOSX') or '\\' in name or ':' in name or '..' in parts or name in seen:
                raise DeliveryError('unsafe_zip_member', 'extract')
            seen.add(name)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                if item.file_size > 4096:
                    raise DeliveryError('unsafe_zip_link', 'extract')
                link = package.read(item).decode('utf-8')
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                if link.startswith('/') or '\\' in link or ':' in link or not resolved.startswith('Chromium.app/'):
                    raise DeliveryError('unsafe_zip_link', 'extract')


def mac_delivery(archive, directory, expected, runner=run):
    validate_zip(archive)
    directory.mkdir()
    runner(['ditto', '-x', '-k', archive, directory], timeout=300)
    app = directory / 'Chromium.app'
    browser = app / 'Contents/MacOS/Chromium'
    if browser.is_symlink() or not browser.is_file() or not browser.resolve().is_relative_to(directory.resolve()):
        raise DeliveryError('extracted_browser_missing', 'extract')
    runner(['codesign', '--verify', '--deep', '--strict', app], timeout=120)
    architectures = runner(['lipo', '-archs', browser], capture_output=True, text=True, timeout=30).stdout.strip().split()
    if architectures != ['arm64']:
        raise DeliveryError('wrong_macos_architecture', 'extract')
    plist = app / 'Contents/Info.plist'
    if plist.is_symlink() or not plist.is_file() or plist.stat().st_size > 1048576:
        raise DeliveryError('invalid_bundle_metadata', 'extract')
    metadata = plistlib.loads(plist.read_bytes())
    if metadata.get('CFBundleIdentifier') != 'org.chromium.Chromium' or metadata.get('CFBundleShortVersionString') != expected['version']:
        raise DeliveryError('wrong_bundle_identity_or_version', 'extract')
    return browser.resolve(), {'method': 'ditto-zip-extraction', 'codesign_structure_verified': True,
        'architectures': architectures, 'bundle_id': metadata['CFBundleIdentifier'],
        'version': metadata['CFBundleShortVersionString'], 'executable_sha256': sha256(browser),
        'executable_size': browser.stat().st_size,
        'developer_id_or_notarization_verified': False}


def pe_machine(file):
    if file.is_symlink() or not file.is_file():
        raise DeliveryError('installed_browser_missing', 'install')
    with file.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise DeliveryError('invalid_installed_pe', 'install')
        offset = struct.unpack_from('<I', header, 60)[0]
        if not 64 <= offset <= 1048576:
            raise DeliveryError('invalid_installed_pe', 'install')
        stream.seek(offset)
        pe = stream.read(6)
    if len(pe) != 6 or pe[:4] != b'PE\0\0':
        raise DeliveryError('invalid_installed_pe', 'install')
    return struct.unpack_from('<H', pe, 4)[0]


def windows_clean_identity(environ, exists=None, key_exists=None):
    exists = exists or (lambda value: value.exists() or value.is_symlink())
    paths = []
    for key in ['LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)']:
        base = Path(environ.get(key, ''))
        if not base.is_absolute():
            raise DeliveryError('unknown_windows_install_root', 'install')
        paths.append(base / 'Chromium')
    if any(exists(item) for item in paths):
        raise DeliveryError('existing_chromium_directory', 'install')
    if key_exists is None:
        import winreg
        def key_exists(hive, view, key):
            try:
                with winreg.OpenKey(getattr(winreg, hive), key, 0, winreg.KEY_READ | getattr(winreg, view)):
                    return True
            except FileNotFoundError:
                return False
    for hive in ['HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE']:
        for view in ['KEY_WOW64_32KEY', 'KEY_WOW64_64KEY']:
            for key in ['Software\\Chromium', 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Chromium']:
                if key_exists(hive, view, key):
                    raise DeliveryError('existing_chromium_registration', 'install')
    return paths[0] / 'Application/chrome.exe'


def windows_delivery(installer, expected, runner=run, environ=None, clean_check=windows_clean_identity):
    environ = os.environ if environ is None else environ
    browser = clean_check(environ)
    try:
        response = runner([installer, '--do-not-launch-chrome'], check=False, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        raise DeliveryError('installer_timed_out', 'install') from error
    except OSError as error:
        raise DeliveryError('installer_launch_failed', 'install') from error
    if response.returncode != 0:
        raise DeliveryError('installer_failed', 'install', response.returncode)
    if pe_machine(browser) != 0x8664 or browser.resolve() != browser.absolute():
        raise DeliveryError('wrong_installed_architecture_or_path', 'install')
    setup = browser.parent / expected['version'] / 'Installer/setup.exe'
    if setup.is_symlink() or not setup.is_file():
        raise DeliveryError('installed_setup_missing', 'install')
    script = '$v=(Get-Item -LiteralPath $env:AA_DELIVERY_BROWSER).VersionInfo;[pscustomobject]@{version=$v.FileVersion;productVersion=$v.ProductVersion}|ConvertTo-Json -Compress'
    raw = runner(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        env={**environ, 'AA_DELIVERY_BROWSER': str(browser)}, capture_output=True, text=True, timeout=30).stdout
    metadata = json.loads(raw.lstrip('\ufeff'))
    if metadata.get('version') != expected['version'] or metadata.get('productVersion') != expected['version']:
        raise DeliveryError('wrong_installed_version', 'install')
    return browser.resolve(), {'method': 'real-mini-installer-default-per-user', 'installer_exit_code': response.returncode,
        'architecture': 'x64', 'version': metadata['version'], 'setup_present': True,
        'executable_sha256': sha256(browser), 'executable_size': browser.stat().st_size, 'authenticode_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-tag', required=True)
    parser.add_argument('--platform', choices=['mac-arm64', 'win-x64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'schema': 1, 'stage': 'real-package-delivery', 'status': 'failed', 'platform': args.platform,
        'source_tag': args.source_tag, 'custom_native_browser_verified': False,
        'scope': 'Artifact provenance and real extraction/installation only; native/Store behavior is verified separately.'}
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
            raise DeliveryError('hosted_runner_required', 'environment')
        if (args.platform == 'mac-arm64' and (sys.platform != 'darwin' or host_platform.machine() != 'arm64') or
                args.platform == 'win-x64' and (sys.platform != 'win32' or host_platform.machine().lower() not in ('amd64', 'x86_64'))):
            raise DeliveryError('wrong_host_platform', 'environment')
        expected = expected_package(args.source_root.resolve(), args.source_tag, args.platform)
        archive, assets = download_package(expected, os.environ['GITHUB_REPOSITORY'], args.output, run)
        report.update({key: expected[key] for key in ['source_commit', 'release_tag', 'fingerprint', 'version', 'revision']})
        report['assets'] = assets
        browser, delivery = (mac_delivery(archive, args.output / 'extracted', expected) if args.platform == 'mac-arm64'
                             else windows_delivery(archive, expected))
        report.update(status='delivered', browser=str(browser), delivery=delivery)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
                stream.write(f'browser={browser}\n')
    except Exception as error:
        report['error'] = {'code': getattr(error, 'code', 'acquisition_failed'), 'stage': getattr(error, 'stage', 'acquire'),
                           'exception': type(error).__name__, 'exit_code': getattr(error, 'exit_code', None)}
    (args.output / 'delivery-provenance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'delivered' else 1


if __name__ == '__main__':
    sys.exit(main())
