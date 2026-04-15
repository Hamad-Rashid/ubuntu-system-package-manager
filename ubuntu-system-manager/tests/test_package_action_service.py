from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ubuntu_system_manager.services.command_runner import PrivilegedCommandResult  # noqa: E402
from ubuntu_system_manager.services.package_action_service import PackageActionService  # noqa: E402


class PackageActionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PackageActionService()

    @staticmethod
    def _result(command: list[str], *, ok: bool = True, code: int = 0) -> tuple[PrivilegedCommandResult, int]:
        return (
            PrivilegedCommandResult(
                ok=ok,
                stdout="ok" if ok else "",
                stderr="" if ok else "failed",
                code=code,
                command=command,
                queue_wait_seconds=0.12,
                execution_seconds=0.85,
            ),
            1,
        )

    @staticmethod
    def _ok_result(command: list[str]) -> tuple[PrivilegedCommandResult, int]:
        return PackageActionServiceTests._result(command, ok=True, code=0)

    def test_update_package_apt_uses_expected_command(self) -> None:
        expected_cmd = ["pkexec", "apt-get", "install", "--only-upgrade", "-y", "curl"]
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            return_value=self._ok_result(expected_cmd),
        ) as mock_run:
            result = self.service.update_package(name="curl", source="apt")

        mock_run.assert_called_once_with(
            ["apt-get", "install", "--only-upgrade", "-y", "curl"],
            timeout=2400,
            retry_attempts=1,
            retry_delay_seconds=1.0,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.command, expected_cmd)
        self.assertAlmostEqual(result.queue_wait_seconds, 0.12)
        self.assertAlmostEqual(result.execution_seconds, 0.85)

    def test_update_package_unknown_source_is_rejected(self) -> None:
        result = self.service.update_package(name="curl", source="unknown")
        self.assertFalse(result.ok)
        self.assertIn("Unsupported source for update", result.message)
        self.assertEqual(result.command, [])

    def test_update_package_invalid_name_is_rejected(self) -> None:
        result = self.service.update_package(name="bad package", source="apt")
        self.assertFalse(result.ok)
        self.assertIn("Invalid package name", result.message)
        self.assertEqual(result.command, [])

    def test_update_all_packages_runs_grouped_apt_and_snap_commands(self) -> None:
        apt_cmd = ["pkexec", "apt-get", "install", "--only-upgrade", "-y", "curl", "vim"]
        snap_cmd = ["pkexec", "snap", "refresh", "firefox", "snapd"]
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            side_effect=[self._ok_result(apt_cmd), self._ok_result(snap_cmd)],
        ) as mock_run:
            results = self.service.update_all_packages(
                apt_names=["vim", "curl", "vim"],
                snap_names=["snapd", "firefox", "snapd"],
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].command, apt_cmd)
        self.assertEqual(results[1].command, snap_cmd)
        self.assertEqual(mock_run.call_count, 2)
        first_call = mock_run.call_args_list[0]
        second_call = mock_run.call_args_list[1]
        self.assertEqual(
            first_call.args[0],
            ["apt-get", "install", "--only-upgrade", "-y", "curl", "vim"],
        )
        self.assertEqual(
            second_call.args[0],
            ["snap", "refresh", "firefox", "snapd"],
        )

    def test_update_all_packages_with_empty_lists_returns_no_results(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry"
        ) as mock_run:
            results = self.service.update_all_packages(apt_names=[], snap_names=[])
        self.assertEqual(results, [])
        mock_run.assert_not_called()

    def test_remove_package_snap_uses_expected_command(self) -> None:
        expected_cmd = ["pkexec", "snap", "remove", "firefox"]
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            return_value=self._ok_result(expected_cmd),
        ) as mock_run:
            result = self.service.remove_package(name="firefox", source="snap")

        mock_run.assert_called_once_with(
            ["snap", "remove", "firefox"],
            timeout=2400,
            retry_attempts=1,
            retry_delay_seconds=1.0,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.command, expected_cmd)

    def test_toggle_package_snap_disable_uses_expected_command(self) -> None:
        expected_cmd = ["pkexec", "snap", "disable", "lxd"]
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            return_value=self._ok_result(expected_cmd),
        ) as mock_run:
            result = self.service.toggle_package(name="lxd", source="snap", enabled=True)

        mock_run.assert_called_once_with(
            ["snap", "disable", "lxd"],
            timeout=1200,
            retry_attempts=1,
            retry_delay_seconds=1.0,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.command, expected_cmd)

    def test_toggle_package_apt_is_rejected(self) -> None:
        result = self.service.toggle_package(name="bash", source="apt", enabled=True)
        self.assertFalse(result.ok)
        self.assertIn("unsupported", result.message.lower())
        self.assertEqual(result.command, [])

    def test_clear_all_cache_runs_all_expected_steps(self) -> None:
        expected_calls = [
            ["apt-get", "clean"],
            ["apt-get", "autoclean"],
            ["rm", "-rf", "/var/lib/apt/lists"],
            ["mkdir", "-p", "/var/lib/apt/lists/partial"],
            ["rm", "-rf", "/var/lib/snapd/cache"],
            ["mkdir", "-p", "/var/lib/snapd/cache"],
            ["rm", "-rf", "/var/cache/snapd"],
            ["mkdir", "-p", "/var/cache/snapd"],
        ]
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            side_effect=[self._ok_result(["pkexec", *cmd]) for cmd in expected_calls],
        ) as mock_run:
            results = self.service.clear_all_cache()

        self.assertEqual(len(results), len(expected_calls))
        self.assertTrue(all(item.ok for item in results))
        self.assertEqual(mock_run.call_count, len(expected_calls))
        for index, call in enumerate(mock_run.call_args_list):
            self.assertEqual(call.args[0], expected_calls[index])

    def test_clear_all_cache_stops_after_first_failed_step(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.package_action_service.run_privileged_command_with_retry",
            side_effect=[
                self._ok_result(["pkexec", "apt-get", "clean"]),
                self._result(["pkexec", "apt-get", "autoclean"], ok=False, code=100),
            ],
        ) as mock_run:
            results = self.service.clear_all_cache()

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].ok)
        self.assertFalse(results[1].ok)
        self.assertEqual(mock_run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
