#!/usr/bin/env python3
"""Bounded, read-only existence audit of Ninja's scoped declared leaf inputs.

This cannot establish compilation success, header/runtime dependency completeness,
or correctness. In particular, validation-only and undeclared inputs are outside
the graph tools' scope. No build commands or dependency downloads are executed.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time


LIMITS = {'tool_seconds': 60, 'overall_seconds': 120,
          'stdout_bytes': 128 << 20, 'stderr_bytes': 1 << 20,
          'graph_stdout_bytes': 512 << 20,
          'node_count': 1000000, 'leaf_count': 500000,
          'path_bytes': 32768, 'report_bytes': 2 << 20}
SCOPE = ('Existence of declared leaf inputs in the requested Ninja target graph; '
         'generated outputs and phony nodes are excluded. This is not build success '
         'or proof of complete compile/runtime dependencies.')
EXCLUSIONS = ['validation-only inputs', 'undeclared inputs',
              'headers discovered only through compiler depfiles/deps logs',
              'runtime dependencies not declared in this graph']


class Incomplete(RuntimeError):
    pass


class AuditError(RuntimeError):
    pass


def run_tool(command, cwd, deadline, limits, output_path=None, output_stats=None):
    if output_path is None:
        return collect_tool(command, cwd, deadline, limits, None, output_stats)
    with output_path.open('wb') as sink:
        return collect_tool(command, cwd, deadline, limits, sink, output_stats)


def collect_tool(command, cwd, deadline, limits, sink, output_stats):
    """Read bounded pipes; tool modes never execute a build or helper process."""
    buffers = [bytearray(), bytearray()]
    counts = [0, 0]
    retained = [0, 0]
    problems = []
    stop = threading.Event()
    process = subprocess.Popen([str(value) for value in command], cwd=cwd,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)

    def read(stream, index, cap):
        try:
            while True:
                block = stream.read(65536)
                if not block:
                    break
                room = max(0, cap - retained[index])
                kept = block[:room]
                counts[index] += len(block)
                retained[index] += len(kept)
                if index == 0 and sink is not None:
                    sink.write(kept)
                else:
                    buffers[index].extend(kept)
                if len(block) > room:
                    problems.append(f'{"stdout" if index == 0 else "stderr"} byte limit exceeded')
                    stop.set()
                    break
        except OSError as problem:
            problems.append(f'Pipe read failed ({type(problem).__name__}, errno={problem.errno})')
            stop.set()
        finally:
            stream.close()

    stdout_cap = limits['graph_stdout_bytes'] if sink is not None else limits['stdout_bytes']
    readers = [threading.Thread(target=read, args=(process.stdout, 0, stdout_cap), daemon=True),
               threading.Thread(target=read, args=(process.stderr, 1, limits['stderr_bytes']), daemon=True)]
    for reader in readers:
        reader.start()
    expires = min(deadline, time.monotonic() + limits['tool_seconds'])
    while process.poll() is None:
        if stop.is_set() or time.monotonic() >= expires:
            if not stop.is_set():
                problems.append('Tool/overall time limit exceeded')
            process.kill()
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as problem:
        raise Incomplete('Read-only Ninja process did not exit after termination') from problem
    for reader in readers:
        reader.join(timeout=5)
    if output_stats is not None:
        output_stats.update(stdout_bytes_read=counts[0], stderr_bytes_read=counts[1],
                            stdout_bytes_retained=retained[0], stderr_bytes_retained=retained[1])
    if any(reader.is_alive() for reader in readers):
        raise Incomplete('Tool output readers did not finish')
    if problems:
        raise Incomplete('; '.join(problems))
    if process.returncode != 0:
        raise AuditError(f'Ninja tool exited status {process.returncode}; raw output withheld')
    if bytes(buffers[1]).strip():
        # A missing dyndep, for example, must not silently yield a complete audit.
        raise Incomplete('Ninja tool emitted a diagnostic; raw output withheld')
    return None if sink is not None else bytes(buffers[0]).decode('utf-8', errors='strict')


def raw_leaves(text, limits):
    paths = set()
    for line in io.StringIO(text):
        path = line.rstrip('\r\n')
        if not path or len(path.encode('utf-8')) > limits['path_bytes']:
            raise Incomplete('Invalid or over-limit leaf path')
        paths.add(path)
        if len(paths) > limits['leaf_count']:
            raise Incomplete('Leaf count limit exceeded')
    return paths


def graph_lines(stream, limits):
    """Never materialize the complete DOT output or an unbounded single line."""
    cap = limits['path_bytes'] + 512
    while True:
        line = stream.readline(cap + 1)
        if not line:
            break
        if len(line) > cap:
            raise Incomplete('Graph line byte limit exceeded')
        yield line.decode('utf-8', errors='strict')


def scoped_leaves(graph, leaves, limits, deadline=None):
    """Parse the pinned tool's fixed lines, not general or shell-escaped DOT."""
    pointer = r'(?:0x)?[0-9a-fA-F]+'
    file_line = re.compile(r'^"(' + pointer + r')" \[label="(.*)"\]$')
    rule_line = re.compile(r'^"(' + pointer + r')" \[label="[^"\r\n]+", shape=ellipse\]$')
    edge_line = re.compile(r'^"(' + pointer + r')" -> "(' + pointer +
                           r')"(?: \[(?:label="[^"\r\n]*"|arrowhead=none(?: style=dotted)?)\])?$')
    headers = {'rankdir="LR"', 'node [fontsize=10, shape=box, height=0.25]', 'edge [fontsize=10]'}
    files, rules, incoming, sources = {}, set(), set(), set()
    lines = io.StringIO(graph) if isinstance(graph, str) else graph
    started, finished = False, False
    for raw in lines:
        if deadline is not None and time.monotonic() >= deadline:
            raise Incomplete('Overall time limit exceeded during graph parsing')
        line = raw.rstrip('\r\n')
        if not started:
            if line != 'digraph ninja {':
                raise Incomplete('Incomplete or unknown Ninja graph format')
            started = True
            continue
        if finished:
            raise Incomplete('Unexpected data after Ninja graph end')
        if line == '}':
            finished = True
            continue
        if line in headers:
            continue
        match = file_line.fullmatch(line)
        if match:
            node, label = match.groups()
            if node in files or node in rules or len(label.encode('utf-8')) > limits['path_bytes']:
                raise Incomplete('Duplicate, ambiguous or over-limit graph file node')
            files[node] = label
        elif (match := rule_line.fullmatch(line)):
            node = match.group(1)
            if node in rules or node in files:
                raise Incomplete('Graph rule/file node collision')
            rules.add(node)
        elif (match := edge_line.fullmatch(line)):
            sources.add(match.group(1))
            incoming.add(match.group(2))
        else:
            raise Incomplete('Unknown Ninja graph line format')
        if len(files) + len(rules) > limits['node_count']:
            raise Incomplete('Graph node count limit exceeded')
    if not started or not finished:
        raise Incomplete('Incomplete or unknown Ninja graph format')
    if not sources.issubset(files.keys() | rules):
        raise Incomplete('Graph contains undefined edge sources')
    # Ninja graph replaces backslashes with '/'; raw targets preserves the
    # exact OS path. Reject collisions rather than checking the wrong file.
    normalized = {}
    for path in leaves:
        normalized.setdefault(path.replace('\\', '/'), set()).add(path)
    selected = set()
    for node, label in files.items():
        if node in incoming:
            continue
        matches = normalized.get(label, set())
        if len(matches) != 1:
            raise Incomplete('Scoped leaf cannot be mapped unambiguously to a raw Ninja leaf')
        selected.update(matches)
    if len(selected) > limits['leaf_count']:
        raise Incomplete('Scoped leaf count limit exceeded')
    return sorted(selected), {'graph_file_nodes': len(files), 'graph_rule_nodes': len(rules),
                              'scoped_declared_leaf_inputs': len(selected),
                              'all_manifest_leaf_inputs': len(leaves)}


def audit(ninja, directory, targets, limits=None):
    limits = dict(LIMITS if limits is None else limits)
    started = time.monotonic()
    deadline = started + limits['overall_seconds']
    report = {'schema': 1, 'status': 'error', 'scope': SCOPE, 'exclusions': EXCLUSIONS,
              'targets': list(targets), 'tool': str(ninja), 'bounds': limits,
              'commands': [['-t', 'graph', *targets], ['-t', 'targets', 'rule']],
              'tool_output_bytes': {'graph': {}, 'leaf_list': {}},
              'counts': {'checked': 0, 'missing': 0}, 'missing': [],
              'missing_complete': False, 'errors': []}
    try:
        with tempfile.TemporaryDirectory(prefix='aacc-input-audit-') as temporary:
            graph = Path(temporary) / 'graph.dot'
            run_tool([ninja, '-t', 'graph', *targets], directory, deadline, limits,
                     output_path=graph, output_stats=report['tool_output_bytes']['graph'])
            leaves = raw_leaves(run_tool([ninja, '-t', 'targets', 'rule'], directory, deadline, limits,
                               output_stats=report['tool_output_bytes']['leaf_list']), limits)
            with graph.open('rb') as stream:
                selected, counts = scoped_leaves(graph_lines(stream, limits), leaves, limits, deadline)
        report['counts'].update(counts)
        missing_bytes = 0
        truncated = False
        for path in selected:
            if time.monotonic() >= deadline:
                raise Incomplete('Overall time limit exceeded during leaf existence checks')
            try:
                (directory / path).stat()
            except (FileNotFoundError, NotADirectoryError):
                report['counts']['missing'] += 1
                size = len(json.dumps(path, ensure_ascii=False).encode('utf-8')) + 8
                if missing_bytes + size < limits['report_bytes'] - 65536:
                    report['missing'].append(path)
                    missing_bytes += size
                else:
                    truncated = True
            except OSError as problem:
                raise Incomplete('Cannot determine declared input existence '
                                 f'({type(problem).__name__}, errno={problem.errno})') from problem
            report['counts']['checked'] += 1
        if truncated:
            raise Incomplete('Missing-path report limit exceeded; missing list is truncated')
        report['missing_complete'] = True
        report['status'] = 'missing' if report['missing'] else 'pass'
    except Incomplete as problem:
        report['status'] = 'incomplete'
        report['errors'].append(str(problem)[:4096])
    except AuditError as problem:
        report['status'] = 'error'
        report['errors'].append(str(problem)[:4096])
    except Exception as problem:
        report['status'] = 'error'
        report['errors'].append(f'Audit operation failed ({type(problem).__name__}, '
                                f'errno={getattr(problem, "errno", None)}); raw output withheld')
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return report


def write_report(path, report):
    content = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if len(content) > report['bounds']['report_bytes']:
        report.update(status='incomplete', missing_complete=False, missing=[],
                      errors=['Final serialized report exceeded its byte limit'])
        content = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if len(content) > report['bounds']['report_bytes']:
        raise Incomplete('Report metadata itself exceeds its byte limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(content)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--platform', required=True, choices=['mac-arm64', 'win-x64'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.source = args.source.resolve()
    ninja = args.source / 'third_party/ninja' / ('ninja.exe' if args.platform == 'win-x64' else 'ninja')
    targets = ['chrome', 'mini_installer'] if args.platform == 'win-x64' else ['chrome']
    report = audit(ninja, args.source / 'out/AlwaysActive', targets)
    report['platform'] = args.platform
    write_report(args.output, report)
    print(json.dumps({'status': report['status'], 'counts': report['counts'],
                      'missing_complete': report['missing_complete'], 'report': str(args.output)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
