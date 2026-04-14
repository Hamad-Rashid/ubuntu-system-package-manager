from __future__ import annotations

import json
from pathlib import Path

from ubuntu_system_manager.models import PartitionEntry

from .command_runner import run_command

EXT_FILESYSTEMS = {"ext2", "ext3", "ext4"}
NTFS_FILESYSTEMS = {"ntfs", "ntfs3", "fuseblk"}
FS_CHECK_TIMEOUT_SECONDS = 12
MAX_FS_CHECKS_PER_REFRESH = 2


def _read_fstab_expected_mounts() -> dict[str, str]:
    expected: dict[str, str] = {}
    fstab = Path("/etc/fstab")
    if not fstab.exists():
        return expected

    for raw_line in fstab.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        spec, mountpoint = parts[0], parts[1]
        expected[spec] = mountpoint
    return expected


def _read_active_mount_targets() -> set[str]:
    result = run_command(["findmnt", "-rn", "-o", "TARGET"], timeout=10)
    if not result.ok:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _node_aliases(path: str, uuid: str, label: str) -> list[str]:
    aliases: list[str] = []
    if path:
        aliases.append(path)
    if uuid:
        aliases.append(f"UUID={uuid}")
    if label:
        aliases.append(f"LABEL={label}")
    return aliases


def _first_nonempty_line(content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _detect_filesystem_error(device: str, filesystem: str, mounted: bool) -> tuple[bool, str]:
    if mounted or not device or device == "-" or not filesystem or filesystem == "-":
        return False, ""

    fstype = filesystem.lower()
    if fstype in EXT_FILESYSTEMS:
        result = run_command(["fsck", "-n", device], timeout=FS_CHECK_TIMEOUT_SECONDS)
        combined = f"{result.stdout}\n{result.stderr}".lower()
        if any(token in combined for token in ("permission denied", "must be superuser", "operation not permitted")):
            return False, ""
        if any(token in combined for token in ("unexpected inconsistency", "error", "corrupt", "bad superblock")):
            return True, _first_nonempty_line(result.stderr or result.stdout) or "ext filesystem check reported errors."
        if result.code not in (0, 1):
            return True, _first_nonempty_line(result.stderr or result.stdout) or "ext filesystem check failed."
        return False, ""

    if fstype in NTFS_FILESYSTEMS:
        result = run_command(["ntfsfix", "-n", device], timeout=FS_CHECK_TIMEOUT_SECONDS)
        combined = f"{result.stdout}\n{result.stderr}".lower()
        if "no such file or directory" in combined and "ntfsfix" in combined:
            return False, ""
        if any(token in combined for token in ("permission denied", "operation not permitted")):
            return False, ""
        if any(token in combined for token in ("corrupt", "inconsisten", "error")) or result.code != 0:
            return True, _first_nonempty_line(result.stderr or result.stdout) or "ntfs filesystem check reported errors."
        return False, ""

    return False, ""


class PartitionService:
    def collect(self) -> list[PartitionEntry]:
        result = run_command(
            ["lsblk", "-J", "-o", "PATH,TYPE,FSTYPE,SIZE,UUID,LABEL,MOUNTPOINT"],
            timeout=20,
        )
        if not result.ok:
            return []

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        expected_mounts = _read_fstab_expected_mounts()
        mounted_targets = _read_active_mount_targets()
        entries: list[PartitionEntry] = []
        fs_check_budget = {"remaining": MAX_FS_CHECKS_PER_REFRESH}
        self._collect_nodes(
            payload.get("blockdevices", []),
            entries,
            expected_mounts=expected_mounts,
            mounted_targets=mounted_targets,
            fs_check_budget=fs_check_budget,
        )
        return sorted(entries, key=lambda item: item.device)

    def _collect_nodes(
        self,
        nodes: list[dict],
        entries: list[PartitionEntry],
        *,
        expected_mounts: dict[str, str],
        mounted_targets: set[str],
        fs_check_budget: dict[str, int],
    ) -> None:
        for node in nodes:
            node_type = (node.get("type") or "").strip()
            if node_type == "part":
                path = (node.get("path") or "").strip()
                fstype = (node.get("fstype") or "").strip() or "-"
                size = (node.get("size") or "").strip() or "-"
                mountpoint = (node.get("mountpoint") or "").strip()
                uuid = (node.get("uuid") or "").strip()
                label = (node.get("label") or "").strip()

                expected_target = ""
                for alias in _node_aliases(path, uuid, label):
                    if alias in expected_mounts:
                        expected_target = expected_mounts[alias]
                        break

                if mountpoint:
                    status = "Mounted"
                    status_detail = f"Mounted at {mountpoint}."
                    can_mount = False
                    can_fix = False
                else:
                    should_probe_fs = (
                        bool(expected_target)
                        and fs_check_budget["remaining"] > 0
                        and fstype.lower() in EXT_FILESYSTEMS.union(NTFS_FILESYSTEMS)
                    )
                    fs_error = False
                    fs_error_detail = ""
                    if should_probe_fs:
                        fs_check_budget["remaining"] -= 1
                        fs_error, fs_error_detail = _detect_filesystem_error(path, fstype, mounted=False)
                    if fs_error:
                        status = "Filesystem error"
                        status_detail = fs_error_detail or "Filesystem check reported issues."
                        can_mount = False
                        can_fix = True
                    elif expected_target and expected_target not in mounted_targets:
                        status = "Mount error"
                        status_detail = f"Expected mountpoint: {expected_target}"
                        can_mount = True
                        can_fix = False
                    else:
                        status = "Not mounted"
                        status_detail = "No active mountpoint."
                        can_mount = True
                        can_fix = False

                if can_fix and (mountpoint == "/" or expected_target == "/"):
                    can_fix = False
                    status_detail = "Root partition fix is blocked from this panel."
                if can_mount and (mountpoint == "/" or expected_target == "/"):
                    can_mount = False

                entries.append(
                    PartitionEntry(
                        device=path or "-",
                        filesystem=fstype,
                        mountpoint=mountpoint or "-",
                        expected_mountpoint=expected_target or "-",
                        size=size,
                        status=status,
                        status_detail=status_detail,
                        can_mount=can_mount,
                        can_fix=can_fix,
                    )
                )
            children = node.get("children") or []
            if children:
                self._collect_nodes(
                    children,
                    entries,
                    expected_mounts=expected_mounts,
                    mounted_targets=mounted_targets,
                    fs_check_budget=fs_check_budget,
                )
