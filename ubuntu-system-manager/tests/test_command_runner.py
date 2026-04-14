from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ubuntu_system_manager.services.command_runner import (  # noqa: E402
    CommandResult,
    PrivilegedCommandResult,
    run_privileged_command_with_retry,
    run_privileged_command,
)


class CommandRunnerTests(unittest.TestCase):
    @staticmethod
    def _priv_result(*, ok: bool, stderr: str = "", stdout: str = "", code: int = 0) -> PrivilegedCommandResult:
        return PrivilegedCommandResult(
            ok=ok,
            stdout=stdout,
            stderr=stderr,
            code=code,
            command=["pkexec", "echo", "x"],
            queue_wait_seconds=0.0,
            execution_seconds=0.0,
        )

    def test_run_privileged_command_adds_pkexec_prefix(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.command_runner.run_command",
            return_value=CommandResult(ok=True, stdout="ok", stderr="", code=0),
        ) as mock_run:
            result = run_privileged_command(["apt-get", "install", "-y", "vim"], timeout=33)

        self.assertTrue(result.ok)
        self.assertEqual(result.command, ["pkexec", "apt-get", "install", "-y", "vim"])
        mock_run.assert_called_once_with(["pkexec", "apt-get", "install", "-y", "vim"], timeout=33)

    def test_run_privileged_command_handles_empty_command(self) -> None:
        result = run_privileged_command([], timeout=10)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.command, [])
        self.assertIn("No command provided", result.stderr)

    def test_run_privileged_command_serializes_operations(self) -> None:
        def slow_run(_args: list[str], timeout: int = 20) -> CommandResult:
            time.sleep(0.2)
            return CommandResult(ok=True, stdout="done", stderr="", code=0)

        results: list = []

        with mock.patch(
            "ubuntu_system_manager.services.command_runner.run_command",
            side_effect=slow_run,
        ):
            t1 = threading.Thread(
                target=lambda: results.append(run_privileged_command(["pkexec", "true"], timeout=5))
            )
            t2 = threading.Thread(
                target=lambda: results.append(run_privileged_command(["pkexec", "true"], timeout=5))
            )
            t1.start()
            time.sleep(0.02)
            t2.start()
            t1.join()
            t2.join()

        self.assertEqual(len(results), 2)
        queue_waits = sorted(item.queue_wait_seconds for item in results)
        self.assertGreater(queue_waits[1], 0.05)
        self.assertGreater(results[0].execution_seconds, 0.0)
        self.assertGreater(results[1].execution_seconds, 0.0)

    def test_run_privileged_command_with_retry_retries_retryable_failure(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.command_runner.run_privileged_command",
            side_effect=[
                self._priv_result(ok=False, stderr="Could not get lock /var/lib/dpkg/lock-frontend", code=100),
                self._priv_result(ok=True, stdout="ok", code=0),
            ],
        ) as mock_run, mock.patch("ubuntu_system_manager.services.command_runner.time.sleep") as mock_sleep:
            result, attempts = run_privileged_command_with_retry(
                ["apt-get", "install", "-y", "vim"],
                timeout=60,
                retry_attempts=1,
            )

        self.assertTrue(result.ok)
        self.assertEqual(attempts, 2)
        self.assertEqual(mock_run.call_count, 2)
        mock_sleep.assert_called_once()

    def test_run_privileged_command_with_retry_does_not_retry_non_retryable_failure(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.command_runner.run_privileged_command",
            return_value=self._priv_result(ok=False, stderr="package not found", code=100),
        ) as mock_run:
            result, attempts = run_privileged_command_with_retry(
                ["apt-get", "install", "-y", "missing-package"],
                timeout=60,
                retry_attempts=2,
            )

        self.assertFalse(result.ok)
        self.assertEqual(attempts, 1)
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
