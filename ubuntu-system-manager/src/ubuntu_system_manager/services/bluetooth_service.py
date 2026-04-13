from __future__ import annotations

import re

from ubuntu_system_manager.models import BluetoothDeviceEntry

from .command_runner import run_command

BATTERY_RE = re.compile(r"Battery Percentage:\s*(?:0x[0-9a-fA-F]+\s*)?\(?(\d+)\)?")
POWERED_RE = re.compile(r"^\s*Powered:\s*(yes|no)\s*$", re.IGNORECASE)


class BluetoothService:
    def adapter_status(self) -> str:
        list_result = run_command(["bluetoothctl", "list"], timeout=10)
        if not list_result.ok:
            return "Bluetooth adapter status unavailable."

        controllers = [line for line in list_result.stdout.splitlines() if line.strip().startswith("Controller ")]
        if not controllers:
            return "No Bluetooth adapter detected."

        show_result = run_command(["bluetoothctl", "show"], timeout=10)
        if not show_result.ok:
            return f"Bluetooth adapter detected ({len(controllers)}), state unknown."

        if "No default controller available" in show_result.stdout:
            return "Bluetooth adapter detected, but no default controller is active."

        for line in show_result.stdout.splitlines():
            match = POWERED_RE.match(line)
            if not match:
                continue
            if match.group(1).lower() == "yes":
                return f"Bluetooth adapter powered on ({len(controllers)} adapter(s))."
            return f"Bluetooth adapter detected but powered off ({len(controllers)} adapter(s))."

        return f"Bluetooth adapter detected ({len(controllers)} adapter(s))."

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
