"""Bounded controller cleanup must precede force for detached no-debug browsers."""
import signal
import os
import subprocess
import unittest
from unittest import mock

import verify


class VerificationCleanupTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX signals/process groups are not Windows APIs')
    def test_no_debug_sigterm_allows_owned_cleanup_before_any_group_kill(self):
        process = mock.Mock(pid=123)
        process.wait.return_value = 0
        with mock.patch.object(verify.os, 'killpg') as kill:
            report = verify.cleanup_timeout(process, 'no-debug', windows=False)
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=30)
        kill.assert_not_called()
        self.assertEqual(report['method'], 'controller-sigterm')
        self.assertTrue(report['controller_exited'])
        self.assertTrue(report['detached_browser_cleanup_uncertain'])

    @unittest.skipIf(os.name == 'nt', 'POSIX signals/process groups are not Windows APIs')
    def test_no_debug_force_is_bounded_and_explicitly_uncertain(self):
        process = mock.Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired('node', 30), 0]
        with mock.patch.object(verify.os, 'killpg') as kill:
            report = verify.cleanup_timeout(process, 'no-debug', windows=False)
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        kill.assert_called_once_with(123, signal.SIGKILL)
        self.assertEqual(process.wait.call_args_list, [mock.call(timeout=30), mock.call(timeout=30)])
        self.assertTrue(report['detached_browser_cleanup_uncertain'])
        self.assertIn('uncertain', report['note'])

    def test_windows_timeout_uses_bounded_owned_process_tree(self):
        process = mock.Mock(pid=123)
        process.wait.return_value = 0
        with mock.patch.object(verify.subprocess, 'run', return_value=mock.Mock(returncode=0)) as taskkill:
            report = verify.cleanup_timeout(process, 'no-debug', windows=True)
        taskkill.assert_called_once_with(['taskkill', '/PID', '123', '/T', '/F'], check=False, timeout=30)
        process.send_signal.assert_not_called()
        process.wait.assert_called_once_with(timeout=30)
        self.assertEqual(report['method'], 'windows-process-tree')
        self.assertTrue(report['controller_exited'])
        self.assertTrue(report['detached_browser_cleanup_uncertain'])

    def test_windows_cleanup_failure_is_reported(self):
        process = mock.Mock(pid=123)
        process.wait.side_effect = subprocess.TimeoutExpired('node', 30)
        with mock.patch.object(verify.subprocess, 'run', return_value=mock.Mock(returncode=5)):
            report = verify.cleanup_timeout(process, 'no-debug', windows=True)
        self.assertFalse(report['controller_exited'])
        self.assertTrue(report['detached_browser_cleanup_uncertain'])
        self.assertIn('cleanup_error', report)


if __name__ == '__main__':
    unittest.main()
