from __future__ import annotations

import json
from pathlib import Path

from ubuntu_system_manager.models import PartitionEntry

from .command_runner import run_command


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
        self._collect_nodes(
            payload.get("blockdevices", []),
            entries,
            expected_mounts=expected_mounts,
            mounted_targets=mounted_targets,
        )
        return sorted(entries, key=lambda item: item.device)

    def _collect_nodes(
        self,
        nodes: list[dict],
        entries: list[PartitionEntry],
        *,
        expected_mounts: dict[str, str],
        mounted_targets: set[str],
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
                elif expected_target and expected_target not in mounted_targets:
                    status = f"Mount error (expected: {expected_target})"
                else:
                    status = "Not mounted"

                entries.append(
                    PartitionEntry(
                        device=path or "-",
                        filesystem=fstype,
                        mountpoint=mountpoint or "-",
                        size=size,
                        status=status,
                    )
                )

            children = node.get("children") or []
            if children:
                self._collect_nodes(
                    children,
                    entries,
                    expected_mounts=expected_mounts,
                    mounted_targets=mounted_targets,
                )
