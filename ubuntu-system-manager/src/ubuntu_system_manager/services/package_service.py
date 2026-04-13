from __future__ import annotations

import re

from ubuntu_system_manager.models import PackageEntry

from .command_runner import run_command

APT_UPGRADABLE_RE = re.compile(r"^(?P<name>[^/]+)/\S+\s+(?P<latest>\S+)\s+\S+\s+\[upgradable from:\s*(?P<installed>[^\]]+)\]")


class PackageService:
    def collect(self) -> list[PackageEntry]:
        apt_items = self._read_apt_packages()
        snap_items = self._read_snap_packages()
        return sorted(apt_items + snap_items, key=lambda item: (item.source, item.name.lower()))

    def _read_apt_packages(self) -> list[PackageEntry]:
        installed_result = run_command(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
            timeout=60,
        )
        installed: dict[str, str] = {}
        if installed_result.ok:
            for line in installed_result.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                installed[parts[0]] = parts[1]

        upgradable_result = run_command(["apt", "list", "--upgradable"], timeout=60)
        upgradable: dict[str, str] = {}
        if upgradable_result.ok:
            for line in upgradable_result.stdout.splitlines():
                match = APT_UPGRADABLE_RE.match(line.strip())
                if not match:
                    continue
                upgradable[match.group("name")] = match.group("latest")

        entries: list[PackageEntry] = []
        for name, installed_version in installed.items():
            update_available = name in upgradable
            latest_version = upgradable.get(name, installed_version)
            status = "Update available" if update_available else "Up-to-date"
            entries.append(
                PackageEntry(
                    name=name,
                    source="apt",
                    installed_version=installed_version,
                    latest_version=latest_version,
                    status=status,
                    update_available=update_available,
                    can_toggle=False,
                    enabled=True,
                )
            )
        return entries

    def _read_snap_packages(self) -> list[PackageEntry]:
        snap_list_result = run_command(["snap", "list"], timeout=30)
        installed: dict[str, tuple[str, str]] = {}
        if snap_list_result.ok:
            for idx, line in enumerate(snap_list_result.stdout.splitlines()):
                if idx == 0:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[0]
                version = parts[1]
                notes = parts[5] if len(parts) >= 6 else "-"
                installed[name] = (version, notes)

        refresh_result = run_command(["snap", "refresh", "--list"], timeout=30)
        upgradable: dict[str, str] = {}
        if refresh_result.ok:
            for idx, line in enumerate(refresh_result.stdout.splitlines()):
                if idx == 0:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                upgradable[parts[0]] = parts[1]

        entries: list[PackageEntry] = []
        for name, details in installed.items():
            installed_version, notes = details
            enabled = "disabled" not in notes.lower()
            update_available = name in upgradable
            latest_version = upgradable.get(name, installed_version)
            if not enabled:
                status = "Disabled"
            elif update_available:
                status = "Update available"
            else:
                status = "Up-to-date"
            entries.append(
                PackageEntry(
                    name=name,
                    source="snap",
                    installed_version=installed_version,
                    latest_version=latest_version,
                    status=status,
                    update_available=update_available,
                    can_toggle=True,
                    enabled=enabled,
                )
            )
        return entries
