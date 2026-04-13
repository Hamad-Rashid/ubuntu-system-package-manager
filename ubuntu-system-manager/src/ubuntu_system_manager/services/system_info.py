from __future__ import annotations

from pathlib import Path

from ubuntu_system_manager.models import SystemMetrics

from .command_runner import run_command

BYTES_IN_GB = 1024**3


def _read_meminfo() -> tuple[int, int]:
    mem_total_kb = 0
    mem_available_kb = 0
    with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("MemTotal:"):
                mem_total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_available_kb = int(line.split()[1])
    if mem_total_kb <= 0:
        raise RuntimeError("Unable to read RAM total from /proc/meminfo")
    used_kb = max(mem_total_kb - mem_available_kb, 0)
    return mem_total_kb * 1024, used_kb * 1024


def _sum_disk_bytes_from_lsblk() -> int:
    result = run_command(["lsblk", "-b", "-dn", "-o", "SIZE,TYPE"], timeout=10)
    if not result.ok:
        return 0

    total = 0
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        size_text, dev_type = parts
        if dev_type != "disk":
            continue
        try:
            total += int(size_text)
        except ValueError:
            continue
    return total


def _sum_used_bytes_from_df() -> int:
    result = run_command(
        [
            "df",
            "-B1",
            "--output=used,target,fstype",
            "-x",
            "tmpfs",
            "-x",
            "devtmpfs",
            "-x",
            "squashfs",
        ],
        timeout=10,
    )
    if not result.ok:
        return 0

    used_sum = 0
    seen_targets: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        used_raw, target, fstype = parts[0], parts[1], parts[2]
        if target in seen_targets:
            continue
        seen_targets.add(target)
        if fstype in {"overlay"}:
            continue
        try:
            used_sum += int(used_raw)
        except ValueError:
            continue
    return used_sum


class SystemInfoService:
    def collect(self) -> SystemMetrics:
        total_ram_bytes, used_ram_bytes = _read_meminfo()
        total_storage_bytes = _sum_disk_bytes_from_lsblk()
        used_storage_bytes = _sum_used_bytes_from_df()

        return SystemMetrics(
            total_ram_gb=total_ram_bytes / BYTES_IN_GB,
            used_ram_gb=used_ram_bytes / BYTES_IN_GB,
            total_storage_gb=total_storage_bytes / BYTES_IN_GB,
            used_storage_gb=used_storage_bytes / BYTES_IN_GB,
        )
