from __future__ import annotations

import re

from ubuntu_system_manager.models import BluetoothDeviceEntry

from .command_runner import run_command

BATTERY_RE = re.compile(r"Battery Percentage:\s*(?:0x[0-9a-fA-F]+\s*)?\(?(\d+)\)?")


class BluetoothService:
    def collect(self) -> list[BluetoothDeviceEntry]:
        devices_result = run_command(["bluetoothctl", "devices", "Connected"], timeout=10)
        if not devices_result.ok:
            return []

        entries: list[BluetoothDeviceEntry] = []
        for line in devices_result.stdout.splitlines():
            parts = line.split(maxsplit=2)
            if len(parts) < 3 or parts[0] != "Device":
                continue

            address = parts[1]
            name = parts[2]
            battery_percent = self._read_device_battery(address)
            entries.append(
                BluetoothDeviceEntry(
                    address=address,
                    name=name,
                    connected=True,
                    battery_percent=battery_percent,
                )
            )
        return entries

    def _read_device_battery(self, address: str) -> str:
        info_result = run_command(["bluetoothctl", "info", address], timeout=10)
        if not info_result.ok:
            return "N/A"
        for line in info_result.stdout.splitlines():
            line = line.strip()
            match = BATTERY_RE.search(line)
            if match:
                return f"{match.group(1)}%"
        return "N/A"
