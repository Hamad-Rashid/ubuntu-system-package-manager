from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ubuntu_system_manager.models import PartitionEntry  # noqa: E402
from ubuntu_system_manager.services.command_runner import CommandResult, PrivilegedCommandResult  # noqa: E402
from ubuntu_system_manager.services.partition_action_service import PartitionActionService  # noqa: E402


class PartitionActionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PartitionActionService()

    @staticmethod
    def _priv_result(command: list[str], ok: bool = True, code: int = 0) -> tuple[PrivilegedCommandResult, int]:
        return (
            PrivilegedCommandResult(
                ok=ok,
                stdout="ok" if ok else "",
                stderr="" if ok else "failed",
                code=code,
                command=command,
                queue_wait_seconds=0.01,
                execution_seconds=0.11,
            ),
            1,
        )

    @staticmethod
    def _partition(**overrides: object) -> PartitionEntry:
        data = {
            "device": "/dev/sda1",
            "filesystem": "ntfs",
            "mountpoint": "-",
            "expected_mountpoint": "/media/hamad/Other",
            "size": "100G",
            "status": "Mount error",
            "status_detail": "Expected mountpoint missing",
            "can_mount": False,
            "can_fix": True,
        }
        data.update(overrides)
        return PartitionEntry(**data)

    def test_special_mount_fix_uses_embedded_ntfs3g_flow(self) -> None:
        mkdir_cmd = ["pkexec", "mkdir", "-p", "/media/hamad/Other"]
        mount_cmd = ["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[self._priv_result(mkdir_cmd), self._priv_result(mount_cmd)],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(
                    ok=True,
                    stdout="/media/hamad/Other",
                    stderr="",
                    code=0,
                ),
            ) as mock_cmd,
        ):
            result = self.service.fix_partition(self._partition())

        self.assertTrue(result.ok)
        self.assertEqual(mock_priv.call_count, 2)
        self.assertEqual(
            mock_priv.call_args_list[1].args[0],
            ["mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"],
        )
        expected_calls = [mock.call(["findmnt", "-rn", "-T", "/media/hamad/Other", "-o", "SOURCE,TARGET"], timeout=15)]
        self.assertEqual(mock_cmd.call_args_list, expected_calls)

    def test_special_mount_fix_reports_failure_if_mount_not_restored(self) -> None:
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[
                    self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                    self._priv_result(["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]),
                ],
            ),
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=False, stdout="", stderr="not mounted", code=1),
            ),
        ):
            result = self.service.fix_partition(self._partition())

        self.assertFalse(result.ok)
        self.assertIn("target is still not mounted", result.message)

    def test_root_partition_fix_is_blocked(self) -> None:
        result = self.service.fix_partition(self._partition(expected_mountpoint="/"))
        self.assertFalse(result.ok)
        self.assertIn("Refusing", result.message)

    def test_mount_partition_uses_ntfs3g_and_verifies_mount(self) -> None:
        mkdir_cmd = ["pkexec", "mkdir", "-p", "/media/hamad/Other"]
        mount_cmd = ["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[self._priv_result(mkdir_cmd), self._priv_result(mount_cmd)],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=True, stdout="/media/hamad/Other", stderr="", code=0),
            ),
        ):
            result = self.service.mount_partition(
                self._partition(status="Not mounted", status_detail="No active mountpoint.", can_mount=True, can_fix=False)
            )

        self.assertTrue(result.ok)
        self.assertEqual(mock_priv.call_count, 2)
        self.assertEqual(
            mock_priv.call_args_list[1].args[0],
            ["mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"],
        )

    def test_mount_partition_failure_suggests_fix(self) -> None:
        with mock.patch(
            "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
            side_effect=[
                self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                self._priv_result(
                    ["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"],
                    ok=False,
                    code=32,
                ),
            ],
        ):
            result = self.service.mount_partition(
                self._partition(status="Not mounted", status_detail="No active mountpoint.", can_mount=True, can_fix=False)
            )

        self.assertFalse(result.ok)
        self.assertIn("Use Fix", result.message)

    def test_mount_partition_uses_sda1_fallback_for_special_target(self) -> None:
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[
                    self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                    self._priv_result(
                        ["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda2", "/media/hamad/Other"],
                        ok=False,
                        code=32,
                    ),
                    self._priv_result(["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]),
                ],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=True, stdout="/dev/sda1 /media/hamad/Other", stderr="", code=0),
            ),
        ):
            result = self.service.mount_partition(
                self._partition(
                    device="/dev/sda2",
                    status="Not mounted",
                    status_detail="No active mountpoint.",
                    can_mount=True,
                    can_fix=False,
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(mock_priv.call_count, 3)
        self.assertEqual(
            mock_priv.call_args_list[1].args[0],
            ["mount", "-t", "ntfs-3g", "/dev/sda2", "/media/hamad/Other"],
        )
        self.assertEqual(
            mock_priv.call_args_list[2].args[0],
            ["mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"],
        )

    def test_mount_partition_unknown_filesystem_can_use_ntfs_fallback(self) -> None:
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[
                    self._priv_result(["pkexec", "mount", "/dev/sda2"], ok=False, code=32),
                    self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                    self._priv_result(
                        ["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda2", "/media/hamad/Other"],
                        ok=False,
                        code=32,
                    ),
                    self._priv_result(["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]),
                ],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=True, stdout="/dev/sda1 /media/hamad/Other", stderr="", code=0),
            ),
        ):
            result = self.service.mount_partition(
                self._partition(
                    device="/dev/sda2",
                    filesystem="-",
                    expected_mountpoint="-",
                    status="Not mounted",
                    status_detail="No active mountpoint.",
                    can_mount=True,
                    can_fix=False,
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(mock_priv.call_count, 4)

    def test_mount_partition_normalizes_special_target_case(self) -> None:
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[
                    self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                    self._priv_result(["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]),
                ],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=True, stdout="/dev/sda1 /media/hamad/Other", stderr="", code=0),
            ),
        ):
            result = self.service.mount_partition(
                self._partition(
                    expected_mountpoint="/media/hamad/other",
                    status="Not mounted",
                    status_detail="No active mountpoint.",
                    can_mount=True,
                    can_fix=False,
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(
            mock_priv.call_args_list[0].args[0],
            ["mkdir", "-p", "/media/hamad/Other"],
        )

    def test_mount_partition_normalizes_special_target_variant_other1(self) -> None:
        with (
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_privileged_command_with_retry",
                side_effect=[
                    self._priv_result(["pkexec", "mkdir", "-p", "/media/hamad/Other"]),
                    self._priv_result(["pkexec", "mount", "-t", "ntfs-3g", "/dev/sda1", "/media/hamad/Other"]),
                ],
            ) as mock_priv,
            mock.patch(
                "ubuntu_system_manager.services.partition_action_service.run_command",
                return_value=CommandResult(ok=True, stdout="/dev/sda1 /media/hamad/Other", stderr="", code=0),
            ),
        ):
            result = self.service.mount_partition(
                self._partition(
                    expected_mountpoint="/media/hamad/Other1",
                    status="Not mounted",
                    status_detail="No active mountpoint.",
                    can_mount=True,
                    can_fix=False,
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(
            mock_priv.call_args_list[0].args[0],
            ["mkdir", "-p", "/media/hamad/Other"],
        )


if __name__ == "__main__":
    unittest.main()
