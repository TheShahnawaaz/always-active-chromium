"""Bounded controller cleanup must precede force for detached no-debug browsers."""
import signal
import subprocess
import unittest
from unittest import mock

import verify


class VerificationCleanupTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
