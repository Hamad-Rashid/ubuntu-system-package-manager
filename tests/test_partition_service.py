from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ubuntu_system_manager.services.command_runner import CommandResult  # noqa: E402
from ubuntu_system_manager.services.partition_service import PartitionService  # noqa: E402


class PartitionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PartitionService()

    @staticmethod
    def _cmd_result(*, ok: bool = True, stdout: str = "", stderr: str = "", code: int = 0) -> CommandResult:
        return CommandResult(ok=ok, stdout=stdout, stderr=stderr, code=code)

    def test_collect_skips_filesystem_probe_for_partitions_without_expected_mount(self) -> None:
        lsblk_payload = {
            "blockdevices": [
                {
                    "path": "/dev/sda",
                    "type": "disk",
                    "children": [
                        {
                            "path": "/dev/sda1",
                            "type": "part",
                            "fstype": "ntfs",
                            "size": "100G",
                            "uuid": "",
                            "label": "",
                            "mountpoint": None,
                        }
                    ],
                }
            ]
        }

        calls: list[list[str]] = []

        def side_effect(args: list[str], timeout: int = 20) -> CommandResult:
            calls.append(args)
            if args[:3] == ["lsblk", "-J", "-o"]:
                return self._cmd_result(stdout=json.dumps(lsblk_payload))
            if args[:3] == ["findmnt", "-rn", "-o"]:
                return self._cmd_result(stdout="")
            return self._cmd_result(ok=False, stderr="unexpected command", code=1)

        with (
            mock.patch("ubuntu_system_manager.services.partition_service.run_command", side_effect=side_effect),
            mock.patch("ubuntu_system_manager.services.partition_service.Path.exists", return_value=False),
        ):
            entries = self.service.collect()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, "Not mounted")
        self.assertEqual(entries[0].status_detail, "No active mountpoint.")
        self.assertFalse(any(cmd and cmd[0] in {"fsck", "ntfsfix"} for cmd in calls))

    def test_collect_limits_filesystem_checks_with_budget(self) -> None:
        lsblk_payload = {
            "blockdevices": [
                {
                    "path": "/dev/sda",
                    "type": "disk",
                    "children": [
                        {
                            "path": "/dev/sda1",
                            "type": "part",
                            "fstype": "ext4",
                            "size": "10G",
                            "uuid": "",
                            "label": "",
                            "mountpoint": None,
                        },
                        {
                            "path": "/dev/sda2",
                            "type": "part",
                            "fstype": "ext4",
                            "size": "10G",
                            "uuid": "",
                            "label": "",
                            "mountpoint": None,
                        },
                        {
                            "path": "/dev/sda3",
                            "type": "part",
                            "fstype": "ext4",
                            "size": "10G",
                            "uuid": "",
                            "label": "",
                            "mountpoint": None,
                        },
                    ],
                }
            ]
        }
        fstab = "/dev/sda1 /mnt/a ext4 defaults 0 0\n/dev/sda2 /mnt/b ext4 defaults 0 0\n/dev/sda3 /mnt/c ext4 defaults 0 0\n"
        fsck_calls = 0

        def side_effect(args: list[str], timeout: int = 20) -> CommandResult:
            nonlocal fsck_calls
            if args[:3] == ["lsblk", "-J", "-o"]:
                return self._cmd_result(stdout=json.dumps(lsblk_payload))
            if args[:3] == ["findmnt", "-rn", "-o"]:
                return self._cmd_result(stdout="")
            if args and args[0] == "fsck":
                fsck_calls += 1
                return self._cmd_result(stdout="clean", code=0)
            return self._cmd_result(ok=False, stderr="unexpected command", code=1)

        with (
            mock.patch("ubuntu_system_manager.services.partition_service.run_command", side_effect=side_effect),
            mock.patch("ubuntu_system_manager.services.partition_service.Path.exists", return_value=True),
            mock.patch("ubuntu_system_manager.services.partition_service.Path.read_text", return_value=fstab),
        ):
            entries = self.service.collect()

        self.assertEqual(len(entries), 3)
        self.assertEqual(fsck_calls, 2)


if __name__ == "__main__":
    unittest.main()
