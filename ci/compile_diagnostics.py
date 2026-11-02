"""Finite structured compiler diagnostics and conservative Ninja progress proof."""
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import subprocess
import sys
import threading

MAX_REPORT = 65536
MAX_LOG = 64 << 20
MAX_MANIFEST = 32 << 20


def safe_path(value, source):
    value = value.replace('\\', '/')
    if (not value or len(value.encode('utf-8')) > 512 or
            any(ord(char) < 32 for char in value) or any(char in value for char in '?=$@#') or '://' in value):
        return None
    base = str(source).replace('\\', '/').rstrip('/')
    absolute = value.startswith('/') or bool(re.match(r'^[A-Za-z]:/', value))
    full = posixpath.normpath(value if absolute else base + '/out/AlwaysActive/' + value)
    if full.casefold().startswith(base.casefold() + '/'):
        return full[len(base) + 1:]
    # A missing SDK executable remains useful without exposing an external path.
    name = posixpath.basename(value)
    if absolute and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}\.(?:exe|dll|py|h|lib)', name):
        return 'external-basename/' + name
    return None


class Collector:
    def __init__(self, source):
        self.source = source
        self.events = []
        self.pending = bytearray()
        self.dropping = False
        self.oversized_lines = 0
        self.bytes_seen = 0
        self.complete = False
        self.normal_failure = False
        self.log_error = False
        self.last_action = None

    def event(self, kind, **fields):
        item = {'kind': kind, **{key: value for key, value in fields.items() if value is not None}}
        if len(self.events) < 24 and item not in self.events:
            self.events.append(item)

    def line(self, raw):
        line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', raw.decode('utf-8', errors='replace')).strip()
        lowered = line.lower()
        if re.match(r'^\[\d+/\d+\] ', line):
            self.last_action = None
            action = re.fullmatch(r'\[\d+/\d+\] ACTION (//[A-Za-z0-9_/.:()+-]{1,240})', line)
            if action:
                self.last_action = action[1]
        if any(text in lowered for text in ('error writing to build log', 'error writing to deps log',
                                             'failed to open build log', 'could not open build log')):
            self.log_error = True
            self.event('ninja_log_error')
        if line == 'ninja: build stopped: subcommand failed.':
            self.normal_failure = True
            self.event('subcommand_failed')
        missing = re.fullmatch(r"ninja: error: '([^']+)', needed by '([^']+)', missing and no known rule to make it", line)
        if missing:
            self.normal_failure = True
            self.event('missing_declared_input', path=safe_path(missing[1], self.source),
                       needed_by=safe_path(missing[2], self.source))
        if line.startswith('FAILED: '):
            output = line[8:].strip()
            self.event('failed_target', path=safe_path(output.split()[0], self.source) if output else None,
                       action=self.last_action)
        module = re.fullmatch(r"ModuleNotFoundError: No module named '([A-Za-z_][A-Za-z0-9_.]{0,150})'", line)
        if module:
            self.event('python_exception', exception='ModuleNotFoundError', module=module[1])
        exception = re.match(r'^(FileNotFoundError|PermissionError|OSError|ImportError|RuntimeError|ValueError|TypeError|AssertionError):', line)
        if exception:
            paths = re.findall(r"'([^']+)'", line)
            self.event('python_exception', exception=exception[1],
                       path=safe_path(paths[-1], self.source) if paths else None)
            os_code = re.search(r'\[(WinError|Errno) (\d{1,8})\]', line)
            if os_code:
                self.event('os_error_code', family=os_code[1], code=int(os_code[2]))
        frame = re.fullmatch(r'File "([^"]+)", line (\d{1,8}), in .*', line)
        if frame:
            path = safe_path(frame[1], self.source)
            if path and not path.startswith('external-basename/'):
                self.event('python_source_location', path=path, line=int(frame[2]))
        location = re.match(r'^(.*?):(\d{1,8}):(\d{1,8}): (?:fatal )?error:', line)
        if location:
            self.event('compiler_error', path=safe_path(location[1], self.source),
                       line=int(location[2]), column=int(location[3]))
        code = re.search(r'\b(?:fatal error|error) (C\d{4}|LNK\d{4}|MIDL\d{4})\b', line)
        if code:
            self.event('compiler_error_code', code=code[1])
        for pattern, kind in ((r"fatal error: ['<]([^'<>]+)[>'] file not found", 'missing_header'),
                              (r"no member named '([A-Za-z_][A-Za-z0-9_]{0,100})'", 'missing_member'),
                              (r"use of undeclared identifier '([A-Za-z_][A-Za-z0-9_]{0,100})'", 'undeclared_identifier')):
            found = re.search(pattern, line)
            if found:
                if kind == 'missing_header':
                    header = found[1] if re.fullmatch(r'[A-Za-z0-9_./-]{1,240}', found[1]) else None
                    self.event(kind, header=header)
                else:
                    self.event(kind, symbol=found[1])

    def feed(self, block):
        self.bytes_seen += len(block)
        for piece in block.splitlines(keepends=True):
            if not self.dropping:
                if len(self.pending) + len(piece) <= 4096:
                    self.pending.extend(piece)
                else:
                    self.pending.clear()
                    self.dropping = True
                    self.oversized_lines += 1
            if piece.endswith((b'\n', b'\r')):
                if not self.dropping:
                    self.line(bytes(self.pending))
                self.pending.clear()
                self.dropping = False

    def finish(self):
        if self.pending and not self.dropping:
            self.line(bytes(self.pending))
        self.pending.clear()
        self.complete = True


def start_capture(process, collector):
    def read():
        try:
            while True:
                block = process.stdout.read1(65536)
                if not block:
                    break
                if hasattr(sys.stdout, 'buffer'):
                    sys.stdout.buffer.write(block)
                    sys.stdout.buffer.flush()
                else:
                    sys.stdout.write(block.decode('utf-8', errors='replace'))
                    sys.stdout.flush()
                collector.feed(block)
            collector.finish()
        except (OSError, ValueError):
            collector.complete = False
        finally:
            process.stdout.close()
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    return thread


def snapshot_log(path):
    try:
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            return {'state': 'uncertain', 'reason': 'linked_log'}
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_LOG:
            return {'state': 'uncertain', 'reason': 'log_type_or_size'}
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            header = stream.readline(128)
            if header != b'# ninja log v6\n':
                return {'state': 'uncertain', 'reason': 'unknown_log_format'}
            digest.update(header)
            for count, line in enumerate(stream):
                if count > 1000000 or len(line) > 8192 or not line.endswith(b'\n'):
                    return {'state': 'uncertain', 'reason': 'invalid_log_row'}
                fields = line.rstrip(b'\n').split(b'\t')
                if (len(fields) != 5 or not all(re.fullmatch(rb'-?\d+', value) for value in fields[:3]) or
                        not fields[3] or not re.fullmatch(rb'[0-9a-fA-F]{1,16}', fields[4])):
                    return {'state': 'uncertain', 'reason': 'invalid_log_row'}
                digest.update(line)
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            return {'state': 'uncertain', 'reason': 'changing_log'}
        return {'state': 'valid', 'size': after.st_size, 'sha256': digest.hexdigest()}
    except FileNotFoundError:
        return {'state': 'absent'}
    except OSError:
        return {'state': 'uncertain', 'reason': 'unreadable_log'}


def manifest_policy(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST:
            return {'valid': False}
        content = path.read_bytes()
        for line in content.splitlines():
            if re.match(rb'^include\s', line):
                return {'valid': False}
            if re.match(rb'^builddir\s*=', line) and line.strip() != b'builddir = .':
                return {'valid': False}
        return {'valid': True, 'sha256': hashlib.sha256(content).hexdigest()}
    except OSError:
        return {'valid': False}


def verify_version(ninja):
    try:
        result = subprocess.run([str(ninja), '--version'], capture_output=True, timeout=5, check=True)
        return result.stdout.strip() == b'1.12.1' and not result.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def no_completed_actions(before, after, manifest_before, manifest_after, collector, status, exit_code, version):
    same_log = (before.get('state') == after.get('state') == 'valid' and
                (before.get('size'), before.get('sha256')) == (after.get('size'), after.get('sha256')))
    both_absent = before.get('state') == after.get('state') == 'absent'
    return bool(status == 'failed' and exit_code == 1 and version and collector.complete and
                collector.normal_failure and not collector.log_error and
                manifest_before.get('valid') and manifest_before == manifest_after and
                (same_log or both_absent))


def write_report(path, report):
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if len(payload) > MAX_REPORT:
        raise RuntimeError('Structured compile report exceeds byte bound')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(payload)
    os.replace(temporary, path)
