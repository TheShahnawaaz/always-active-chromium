"""Read-only Ninja input audit; fixtures never execute their build commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import audit_inputs as audit


class NinjaAuditTests(unittest.TestCase):
    def fixture(self, directory):
        def escape(path):
            return path.replace('$', '$$').replace(' ', '$ ').replace(':', '$:')
        missing = ['missing.hpp', 'name with space.hpp', '日本語.hpp',
                   "single'quote.hpp", 'implicit.hpp', 'order.hpp', 'phony-only-missing.hpp']
        if os.name != 'nt':
            missing.append('double"quote.hpp')
        inputs = ' '.join(escape(path) for path in missing[:4] + missing[7:])
        (directory / 'build.ninja').write_text(
            'rule generate\n'
            '  command = MUST_NOT_EXECUTE_THIS_COMMAND\n'
            'build generated.hpp: generate existing.schema\n'
            f'build obj.o: generate source.cpp generated.hpp {inputs} '
            '| implicit.hpp || order.hpp |@ validation-only-missing.hpp\n'
            'build empty: phony\n'
            'build chrome: phony obj.o empty phony-only-missing.hpp\n'
            'build mini_installer: phony chrome\n'
            'build unrelated: phony disconnected-missing.hpp\n', encoding='utf-8')
        (directory / 'existing.schema').write_text('fixture')
        (directory / 'source.cpp').write_text('fixture')
        return sorted(missing)

    @unittest.skipUnless(shutil.which('ninja'), 'Ninja required for the real read-only fixture')
    def test_real_pinned_ninja_scoped_missing_leaves_and_then_pass_without_building(self):
        ninja = Path(shutil.which('ninja')).resolve()
        version = subprocess.check_output([ninja, '--version'], text=True, timeout=5).strip()
        if version != '1.12.1':
            self.skipTest('Exact pinned Ninja 1.12.1 fixture required')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = self.fixture(directory)
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}
            report = audit.audit(ninja, directory, ['chrome', 'mini_installer'])
            self.assertEqual(report['status'], 'missing', report)
            self.assertEqual(report['missing'], expected)
            self.assertTrue(report['missing_complete'])
            self.assertEqual(report['counts']['missing'], len(expected))
            self.assertEqual({path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                              for path in directory.iterdir()}, before)
            for path in expected:
                (directory / path).write_text('now present')
            report = audit.audit(ninja, directory, ['chrome', 'mini_installer'])
            self.assertEqual(report['status'], 'pass', report)
            self.assertEqual(report['missing'], [])
            self.assertFalse((directory / 'generated.hpp').exists())
            self.assertFalse((directory / 'obj.o').exists())
            self.assertFalse((directory / 'empty').exists())
            self.assertFalse((directory / 'disconnected-missing.hpp').exists())
            self.assertFalse((directory / 'validation-only-missing.hpp').exists())

    def test_graph_preserves_raw_backslash_path_and_quoted_labels(self):
        graph = '\n'.join(['digraph ninja {', 'rankdir="LR"',
            'node [fontsize=10, shape=box, height=0.25]', 'edge [fontsize=10]',
            '"00000001" [label="folder/leaf.hpp"]',
            '"00000002" [label="double"quote.hpp"]', '}'])
        selected, _ = audit.scoped_leaves(graph, {'folder\\leaf.hpp', 'double"quote.hpp'}, audit.LIMITS)
        self.assertEqual(selected, ['double"quote.hpp', 'folder\\leaf.hpp'])
        with self.assertRaisesRegex(audit.Incomplete, 'unambiguously'):
            audit.scoped_leaves(graph, {'folder\\leaf.hpp', 'folder/leaf.hpp', 'double"quote.hpp'}, audit.LIMITS)

    def test_unknown_graph_line_and_rule_file_collision_are_rejected(self):
        for graph in ['digraph ninja {\nunknown syntax\n}',
                      'digraph ninja {\n"0x1" [label="file"]\n"0x1" [label="phony", shape=ellipse]\n}']:
            with self.subTest(graph=graph), self.assertRaises(audit.Incomplete):
                audit.scoped_leaves(graph, {'file'}, audit.LIMITS)

    def test_tool_output_and_time_are_bounded_without_publishing_raw_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            limits = dict(audit.LIMITS, stdout_bytes=1024, tool_seconds=1)
            with self.assertRaisesRegex(audit.Incomplete, 'byte limit'):
                audit.run_tool([sys.executable, '-c', 'print("x"*2048)'], temporary,
                               time.monotonic() + 2, limits)
            limits['tool_seconds'] = 0.05
            began = time.monotonic()
            with self.assertRaisesRegex(audit.Incomplete, 'time limit'):
                audit.run_tool([sys.executable, '-c', 'import time; time.sleep(30)'], temporary,
                               time.monotonic() + 1, limits)
            self.assertLess(time.monotonic() - began, 2)

    def test_nonzero_tool_or_stderr_cannot_leak_raw_values_into_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for failure in (audit.AuditError('Ninja tool exited status 1; raw output withheld'),
                            OSError(13, 'PRIVATE_RAW_VALUE')):
                with self.subTest(failure=type(failure).__name__), \
                        mock.patch.object(audit, 'run_tool', side_effect=failure):
                    report = audit.audit(Path('ninja'), root, ['chrome'])
                    self.assertEqual(report['status'], 'error')
                    self.assertFalse(report['missing_complete'])
                    self.assertNotIn('PRIVATE_RAW_VALUE', json.dumps(report))
            for code in ['import sys;sys.stderr.write("PRIVATE_RAW_VALUE");sys.exit(1)',
                         'import sys;sys.stderr.write("PRIVATE_RAW_VALUE")']:
                with self.subTest(code=code), self.assertRaises((audit.AuditError, audit.Incomplete)) as caught:
                    audit.run_tool([sys.executable, '-c', code], root,
                                   time.monotonic() + 2, audit.LIMITS)
                self.assertNotIn('PRIVATE_RAW_VALUE', str(caught.exception))

    def test_caps_and_serialized_report_limit_remain_explicit(self):
        with self.assertRaisesRegex(audit.Incomplete, 'Leaf count'):
            audit.raw_leaves('one\ntwo\n', dict(audit.LIMITS, leaf_count=1))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(audit, 'run_tool', side_effect=audit.Incomplete('bounded fixture')):
                report = audit.audit(Path('ninja'), root, ['chrome'])
            self.assertEqual(report['status'], 'incomplete')
            self.assertFalse(report['missing_complete'])
            report['bounds']['report_bytes'] = 2048
            report['missing'] = ['x' * 4096]
            output = root / 'input-audit.json'
            audit.write_report(output, report)
            self.assertLessEqual(output.stat().st_size, 2048)
            saved = json.loads(output.read_text())
            self.assertEqual(saved['status'], 'incomplete')
            self.assertFalse(saved['missing_complete'])
            self.assertEqual(list(root.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
