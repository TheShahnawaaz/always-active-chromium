#!/usr/bin/env python3
"""Archive-based, resumable Chromium build. Full source is hosted-runner only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from urllib.parse import quote
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
PINS = json.loads((PROJECT / 'ci/pins.json').read_text())


def run(command, **kwargs):
    print('+', subprocess.list2cmdline([str(x) for x in command]), flush=True)
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def write_if_changed(path, text):
    if not path.is_file() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8')


def source_commit():
    return subprocess.check_output(['git', '-C', str(PROJECT), 'rev-parse', 'HEAD'], text=True).strip()


def require_tag(tag, commit):
    repo = os.environ['GITHUB_REPOSITORY']
    try:
        ref = json.loads(subprocess.check_output(
            ['gh', 'api', f'repos/{repo}/git/ref/tags/{tag}'], text=True, timeout=120))
    except subprocess.CalledProcessError as problem:
        raise RuntimeError(f'Create immutable Git tag {tag} at {commit} before dispatch.') from problem
    target = ref['object']
    while target['type'] == 'tag':
        target = json.loads(subprocess.check_output(['gh', 'api', target['url']],
                           text=True, timeout=120))['object']
    if target['type'] != 'commit' or target['sha'] != commit:
        raise RuntimeError(f'Immutable Git tag {tag} does not point to the checked-out commit')


def final_release_tag(platform, commit=None):
    commit = commit or source_commit()
    return f'build-{PINS["version"]}-{platform}-{fingerprint(platform)[:12]}-{commit[:12]}'


def check_source_ref(platform, require_final=False):
    commit = source_commit()
    tag = f'ci-source-{commit[:12]}'
    require_tag(tag, commit)
    final_tag = final_release_tag(platform, commit)
    if require_final:
        require_tag(final_tag, commit)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
            stream.write(f'AA_SOURCE_TAG={tag}\nAA_SOURCE_COMMIT={commit}\n')
    output('source_tag', tag)
    output('repository_commit', commit)
    output('final_release_tag', final_tag)


def fingerprint(platform):
    digest = hashlib.sha256((PROJECT / 'ci/pins.json').read_bytes())
    digest.update(platform.encode())
    provenance = PROJECT / 'native/provenance.json'
    native = json.loads(provenance.read_text())
    for relative in ('native/provenance.json', 'native/apply_patches.py', native['patch']):
        digest.update(relative.encode())
        digest.update((PROJECT / relative).read_bytes())
    return digest.hexdigest()


def output(name, value):
    print(f'{name}={value}', flush=True)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write(f'{name}={value}\n')


def root_path():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Full source/build actions require an ephemeral GitHub-hosted runner.')
    root = Path(os.environ['AA_BUILD_ROOT'])
    expected = Path('D:/aacc') if os.name == 'nt' else Path('/Users/runner/aacc')
    if root != expected:
        raise RuntimeError(f'Unexpected fixed build path: {root}')
    if os.name != 'nt':
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        desired = 10240 if hard == resource.RLIM_INFINITY else min(10240, hard)
        if soft < desired:
            resource.setrlimit(resource.RLIMIT_NOFILE, (desired, hard))
        print(f'Open-file limit: {resource.getrlimit(resource.RLIMIT_NOFILE)}', flush=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def fetch(url, destination, expected_sha=None, expected_size=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '5',
         '--retry-delay', '5', '--connect-timeout', '30', '--max-time', '3600',
         '--output', destination, url])
    actual = sha256(destination)
    if expected_sha and actual != expected_sha:
        raise RuntimeError(f'SHA-256 mismatch for {url}: {actual}')
    if expected_size and destination.stat().st_size != expected_size:
        raise RuntimeError(f'Wrong download size for {url}')
    print(f'Download verified: {destination.name}, {destination.stat().st_size} bytes, sha256={actual}', flush=True)
    return actual


def unpack_windows_source(archive, destination, strip):
    git = shutil.which('git')
    if not git:
        raise RuntimeError('Git for Windows is required for its tested GNU tar extractor')
    gitbin = Path(git).resolve().parent.parent / 'usr/bin'
    executable = gitbin / 'tar.exe'
    if not executable.is_file():
        raise RuntimeError(f'The tested Git GNU tar is unavailable at {executable} (git={git}); no silent extractor fallback')
    env = dict(os.environ, LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8',
               MSYS='winsymlinks:nativestrict', PATH=str(gitbin) + os.pathsep + os.environ['PATH'])
    version = run([executable, '--version'], env=env, capture_output=True, text=True).stdout.splitlines()[0]
    if 'GNU tar' not in version:
        raise RuntimeError(f'Unexpected source extractor: {version}')
    print(f'Source extractor: {executable}; {version}; UTF-8 locale; strict native symlinks; '
          f'xz on process PATH={shutil.which("xz", path=env["PATH"])}', flush=True)
    run([executable, '--force-local', '-xf', archive.as_posix(), '-C', destination.as_posix(),
         f'--strip-components={strip}'], env=env)
    return {'tool': str(executable), 'version': version, 'locale': 'en_US.UTF-8',
            'symlink_policy': 'winsymlinks:nativestrict'}


def unpack(archive, destination, strip=0, source_archive=False):
    destination.mkdir(parents=True, exist_ok=True)
    if source_archive and os.name == 'nt':
        return unpack_windows_source(archive, destination, strip)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                relative = Path(info.filename)
                if relative.is_absolute() or '..' in relative.parts:
                    raise RuntimeError('Unsafe package member')
                mode = info.external_attr >> 16
                path = destination / relative
                if path.is_symlink():
                    path.unlink()
                if stat.S_ISLNK(mode):
                    link = source.read(info).decode('utf-8')
                    resolved = (path.parent / link).resolve()
                    if Path(link).is_absolute() or not resolved.is_relative_to(destination.resolve()):
                        raise RuntimeError('Unsafe package symlink')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        path.unlink()
                    path.symlink_to(link)
                    continue
                # CIPD executable entries can be mode 0500. Unlink an existing
                # file first so replacing a different host's archive payload
                # does not depend on that file having a write bit.
                if path.exists() and not path.is_dir():
                    path.chmod(path.stat().st_mode | stat.S_IWUSR)
                    path.unlink()
                path = Path(source.extract(info, destination))
                if mode and os.name != 'nt':
                    path.chmod(mode & 0o777)
    else:
        run(['tar', '-xf', archive, '-C', destination, f'--strip-components={strip}'])
    return {'tool': 'system tar' if not zipfile.is_zipfile(archive) else 'Python zipfile',
            'strip_components': strip}


def load_deps(path, platform):
    """Read the DEPS from the hash-verified source archive, never moving main."""
    overrides = {'host_os': 'win' if platform == 'win-x64' else 'mac',
                 'host_cpu': 'x64' if platform == 'win-x64' else 'arm64',
                 'checkout_win': platform == 'win-x64', 'checkout_mac': platform == 'mac-arm64',
                 'checkout_linux': False, 'checkout_android': False, 'checkout_ios': False,
                 'checkout_chromeos': False, 'checkout_fuchsia': False,
                 'checkout_x64': platform == 'win-x64', 'checkout_arm64': platform == 'mac-arm64',
                 'build_with_chromium': True, 'non_git_source': True}
    scope = {'__builtins__': {}, 'Str': str}
    scope['Var'] = lambda key: overrides[key] if key in overrides else scope['vars'][key]
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), scope)
    variables = dict(scope.get('vars', {}))
    variables.update(overrides)

    def enabled(condition):
        if not isinstance(condition, str):
            return bool(condition)
        # The DEPS is executable build metadata from the verified upstream archive.
        # Only its ordinary boolean conditions are evaluated here.
        return bool(eval(condition, {'__builtins__': {}}, variables))

    return scope, variables, enabled


def hydrate(src, platform):
    scope, variables, enabled = load_deps(src / 'DEPS', platform)
    host = 'windows-amd64' if platform == 'win-x64' else 'mac-arm64'
    selected = {'src/third_party/llvm-build/Release+Asserts', 'src/third_party/rust-toolchain',
                'src/third_party/llvm-libclang', 'src/third_party/ninja',
                'src/third_party/cpython3/host',
                'src/third_party/node/node_modules',
                'src/third_party/node/win' if platform == 'win-x64' else 'src/third_party/node/mac_arm64',
                'src/buildtools/win' if platform == 'win-x64' else 'src/buildtools/mac',
                f'src/third_party/typescript/{host}/src',
                'src/third_party/subresource-filter-ruleset/data'}
    if platform == 'win-x64':
        selected.update({'src/third_party/lzma_sdk/bin/host_platform',
                         'src/third_party/lzma_sdk/bin/win64',
                         'src/third_party/wtl', 'src/third_party/webview2'})
    else:
        selected.add('src/ui/gl/resources/angle-metal')
    records = []

    def hydrate_entries(entries, base, accept, check):
        for relative, dep in entries.items():
            if relative not in accept or not isinstance(dep, dict) or not check(dep.get('condition', True)):
                continue
            target = base / relative
            target.mkdir(parents=True, exist_ok=True)
            plan = hashlib.sha256(json.dumps([relative, dep, platform, PINS['hydration_revision']], sort_keys=True).encode()).hexdigest()
            marker = target / '.aacc-dependency.json'
            if marker.is_file():
                previous = json.loads(marker.read_text())
                if previous['plan_sha256'] == plan:
                    records.extend(previous['records'])
                    print(f'Pinned dependency already hydrated: {relative}', flush=True)
                    continue
            start = len(records)
            if dep.get('dep_type') == 'gcs':
                for item in dep['objects']:
                    if not check(item.get('condition', True)):
                        continue
                    url = (f'https://storage.googleapis.com/{dep["bucket"]}/'
                           f'{quote(item["object_name"], safe="/")}?generation={item["generation"]}')
                    name = item.get('output_file', Path(item['object_name']).name)
                    archive = target / name
                    actual = fetch(url, archive, item['sha256sum'], item['size_bytes'])
                    records.append({'url': url, 'sha256': actual})
                    if name.endswith(('.tar.xz', '.tar.gz', '.tgz')):
                        unpack(archive, target)
                        archive.unlink()
            elif dep.get('dep_type') == 'cipd':
                for package in dep['packages']:
                    name = package['package'].replace('${{platform}}', host).replace('${{arch}}', 'arm64' if platform == 'mac-arm64' else 'amd64')
                    version = package['version']
                    if name.startswith('gn/gn/') and version != PINS['gn_version']:
                        raise RuntimeError('GN version differs from the source pin')
                    if '/tools/ninja/' in name and version != PINS['ninja_version']:
                        raise RuntimeError('Ninja version differs from the source pin')
                    url = f'https://chrome-infra-packages.appspot.com/dl/{name}/+/{quote(version, safe=":@")}'
                    archive = target / '.aacc-package.zip'
                    actual = fetch(url, archive, PINS['cipd_sha256'].get(name))
                    records.append({'url': url, 'sha256': actual})
                    unpack(archive, target)
                    archive.unlink()
            else:
                raise RuntimeError(f'Unexpected binary dependency: {relative}')
            marker.write_text(json.dumps({'plan_sha256': plan, 'records': records[start:]}, indent=2) + '\n')

    hydrate_entries(scope['deps'], src.parent, selected, enabled)
    devtools = src / 'third_party/devtools-frontend/src'
    nested, _, nested_enabled = load_deps(devtools / 'DEPS', platform)
    hydrate_entries(nested['deps'], devtools, {'third_party/esbuild', 'node_modules'}, nested_enabled)
    # This file is normally emitted by gclient, which archive builds do not run.
    values = {}
    for key in scope['gclient_gn_args']:
        value = variables[key]
        if isinstance(value, str) and any(token in value for token in ('checkout_', 'host_os', ' and ', ' or ')):
            value = enabled(value)
        values[key] = value
    write_if_changed(src / 'build/config/gclient_args.gni',
        '# Generated from the pinned source DEPS by ci/build.py\n' +
        ''.join(f'{key} = {json.dumps(value)}\n' for key, value in values.items()))
    write_if_changed(src.parent / 'dependencies.json', json.dumps(records, indent=2) + '\n')
    # The regular updater can delete this directory when its stamp is missing,
    # including the separately verified llvmobjdump payload. All host packages
    # above came from SHA-checked DEPS objects: validate that their primary
    # package agrees with update.py, then emit its expected stamp directly.
    clang_revision = runpy.run_path(str(src / 'tools/clang/scripts/update.py'))['PACKAGE_VERSION']
    clang_objects = scope['deps']['src/third_party/llvm-build/Release+Asserts']['objects']
    if not any(Path(item['object_name']).name == f'clang-{clang_revision}.tar.xz' and
               enabled(item.get('condition', True)) for item in clang_objects):
        raise RuntimeError('Clang package revision differs from update.py')
    write_if_changed(src / 'third_party/llvm-build/Release+Asserts/cr_build_revision', clang_revision + '\n')
    run([sys.executable, src / 'tools/clang/scripts/update.py', '--print-revision'], cwd=src)
    compiler = src / ('third_party/llvm-build/Release+Asserts/bin/clang-cl.exe' if platform == 'win-x64' else
                      'third_party/llvm-build/Release+Asserts/bin/clang')
    run([compiler, '--version'], cwd=src)
    interpreter = src / ('third_party/cpython3/host/bin/python3.exe' if platform == 'win-x64' else
                         'third_party/cpython3/host/bin/python3')
    run([interpreter, '--version'], cwd=src)
    run([sys.executable, src / 'tools/rust/update_rust.py', '--print-revision=validate'], cwd=src)


def gn_path(src, platform):
    return src / ('buildtools/win/gn.exe' if platform == 'win-x64' else 'buildtools/mac/gn')


def set_build_env(src):
    os.environ['DEPOT_TOOLS_UPDATE'] = '0'
    os.environ['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'
    os.environ['PATH'] = str(src / 'third_party/depot_tools') + os.pathsep + os.environ['PATH']


def prepare(platform):
    root = root_path()
    src = root / 'src'
    state_file = root / 'state.json'
    expected = fingerprint(platform)
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state['fingerprint'] != expected or state['root'] != str(root):
            raise RuntimeError('Checkpoint source/patch/configuration/path mismatch')
    else:
        free = shutil.disk_usage(root).free
        print(f'Build volume free before source: {free / (1 << 30):.1f} GiB', flush=True)
        if free < 75 * (1 << 30):
            raise RuntimeError('Less than 75 GiB free before source; insufficient build reserve')
        archive = root / 'source.tar.xz'
        fetch(PINS['source_url'], archive, PINS['source_sha256'], PINS['source_size'])
        extraction = unpack(archive, src, strip=1, source_archive=True)
        archive.unlink()
        state = {'schema': 1, 'fingerprint': expected, 'root': str(root), 'platform': platform,
                 'version': PINS['version'], 'revision': PINS['revision'], 'status': 'prepared',
                 'hydration_revision': PINS['hydration_revision'], 'source_extraction': extraction}
    set_build_env(src)
    # A failed tool download or GN generation must not discard the validated
    # multi-gigabyte source. Publish checkpointability only after complete source
    # extraction and the exact native source/version checks have succeeded.
    run([sys.executable, PROJECT / 'native/apply_patches.py', '--source', src, '--check'])
    state['phase'] = 'source-ready'
    state['status'] = 'bootstrap-incomplete'
    state['last_prepare_run'] = os.environ.get('GITHUB_RUN_ID', '')
    state['repository_commit'] = source_commit()
    state_file.write_text(json.dumps(state, indent=2) + '\n')
    output('source_checkpointable', 'true')
    # Every resume checks the selected dependency plan. Per-dependency markers
    # avoid touching unchanged tool binaries/mtimes, while newly required tools
    # can be hydrated without silently skipping the bootstrap phase.
    hydrate(src, platform)
    run([sys.executable, PROJECT / 'native/apply_patches.py', '--source', src])
    run([sys.executable, PROJECT / 'native/apply_patches.py', '--source', src, '--verify-applied'])
    args = dict(PINS['common_gn_args'])
    args.update(PINS['platform_gn_args'][platform])
    out = src / 'out/AlwaysActive'
    out.mkdir(parents=True, exist_ok=True)
    write_if_changed(out / 'args.gn', ''.join(f'{key} = {json.dumps(value)}\n' for key, value in args.items()))
    run([gn_path(src, platform), 'gen', 'out/AlwaysActive', '--fail-on-unused-args'], cwd=src)
    state['phase'] = 'build-ready'
    state['status'] = 'prepared'
    state_file.write_text(json.dumps(state, indent=2) + '\n')
    output('fingerprint', expected)
    output('browser', src / ('out/AlwaysActive/chrome.exe' if platform == 'win-x64' else 'out/AlwaysActive/Chromium.app/Contents/MacOS/Chromium'))
    print(f'Build volume free after prepare: {shutil.disk_usage(root).free / (1 << 30):.1f} GiB', flush=True)


def stop(process):
    if os.name == 'nt':
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            pass
    else:
        os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=120)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def compile_browser(platform, bootstrap_only):
    root = root_path()
    src = root / 'src'
    set_build_env(src)
    state_file = root / 'state.json'
    state = json.loads(state_file.read_text())
    status = 'pending'
    if not bootstrap_only:
        # Leaves more than two hours for checkpoint compression/upload before 6h.
        deadline = float(os.environ['AA_JOB_STARTED']) + 220 * 60
        executable = src / ('third_party/ninja/ninja.exe' if platform == 'win-x64' else 'third_party/ninja/ninja')
        command = [str(executable), '-C', 'out/AlwaysActive', '-j', '3' if platform == 'win-x64' else '2', 'chrome']
        if platform == 'win-x64':
            command.append('mini_installer')
        print('+', subprocess.list2cmdline(command), flush=True)
        process = subprocess.Popen(command, cwd=src,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        while process.poll() is None:
            free = shutil.disk_usage(root).free
            print(f'Build running; {max(0, deadline-time.time())/60:.0f} min to checkpoint; {free/(1<<30):.1f} GiB free', flush=True)
            if free < 8 * (1 << 30):
                status = 'disk-blocked'
                stop(process)
                break
            if time.time() >= deadline:
                stop(process)
                break
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
        else:
            status = 'complete' if process.returncode == 0 else 'failed'
    state['status'] = status
    state['last_run'] = os.environ.get('GITHUB_RUN_ID', '')
    state_file.write_text(json.dumps(state, indent=2) + '\n')
    output('status', status)
    if status in ('failed', 'disk-blocked'):
        return 1
    return 0


def package(platform):
    root = root_path()
    out = root / 'src/out/AlwaysActive'
    packages = PROJECT / 'packages'
    packages.mkdir(exist_ok=True)
    stem = f'always-active-chromium-{PINS["version"]}-{platform}'
    if platform == 'mac-arm64':
        app = out / 'Chromium.app'
        run(['codesign', '--verify', '--deep', '--strict', app])
        run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, packages / f'{stem}.zip'])
    else:
        installer = out / 'mini_installer.exe'
        if not installer.is_file():
            raise RuntimeError('The real Chromium mini_installer.exe was not built')
        shutil.copy2(installer, packages / f'{stem}-installer.exe')
    manifest = {'source': PINS, 'build': json.loads((root / 'state.json').read_text()),
                'repository_commit': source_commit(),
                'source_tag': os.environ.get('AA_SOURCE_TAG'),
                'workflow_run': os.environ.get('GITHUB_RUN_ID'),
                'runner_image': os.environ.get('ImageVersion'),
                'signing': 'No Developer ID/notarization or Windows Authenticode certificate configured.'}
    (packages / f'{stem}-build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (packages / f'{stem}-SHA256SUMS.txt').write_text(''.join(
        f'{sha256(path)}  {path.name}\n' for path in sorted(packages.glob(stem + '*')) if not path.name.endswith('SHA256SUMS.txt')))
    output('package_stem', stem)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['source-ref', 'fingerprint', 'prepare', 'compile', 'package'])
    parser.add_argument('--platform', required=True, choices=['mac-arm64', 'win-x64'])
    parser.add_argument('--bootstrap-only', action='store_true')
    parser.add_argument('--require-final-ref', action='store_true')
    args = parser.parse_args()
    if args.command == 'source-ref':
        check_source_ref(args.platform, args.require_final_ref)
    elif args.command == 'fingerprint':
        output('fingerprint', fingerprint(args.platform))
    elif args.command == 'prepare':
        prepare(args.platform)
    elif args.command == 'compile':
        return compile_browser(args.platform, args.bootstrap_only)
    else:
        package(args.platform)
    return 0


if __name__ == '__main__':
    sys.exit(main())
