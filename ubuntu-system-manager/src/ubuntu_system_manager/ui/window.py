from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ubuntu_system_manager.models import (
    BluetoothDeviceEntry,
    PackageEntry,
    PartitionEntry,
    SystemMetrics,
)
from ubuntu_system_manager.services.bluetooth_service import BluetoothService
from ubuntu_system_manager.services.package_service import PackageService
from ubuntu_system_manager.services.partition_service import PartitionService
from ubuntu_system_manager.services.system_info import SystemInfoService


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_title("Ubuntu System Manager - Phase 1")
        self.set_default_size(1300, 860)

        self._system_service = SystemInfoService()
        self._package_service = PackageService()
        self._bluetooth_service = BluetoothService()
        self._partition_service = PartitionService()

        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="phase1-refresh")
        self._refresh_inflight = False

        self._build_ui()
        self._start_refresh(reason="startup")
        GLib.timeout_add_seconds(60, self._on_auto_refresh_timer)

    def _build_ui(self) -> None:
        header = Adw.HeaderBar()

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", self._on_manual_refresh_clicked)
        header.pack_end(self.refresh_button)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        self.set_content(toolbar_view)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        toolbar_view.set_content(root)

        self.status_label = Gtk.Label(label="Waiting for first refresh...", xalign=0)
        root.append(self.status_label)

        metrics_frame = Gtk.Frame(label="System Metrics")
        root.append(metrics_frame)

        metrics_grid = Gtk.Grid(column_spacing=30, row_spacing=8)
        metrics_grid.set_margin_top(12)
        metrics_grid.set_margin_bottom(12)
        metrics_grid.set_margin_start(12)
        metrics_grid.set_margin_end(12)
        metrics_frame.set_child(metrics_grid)

        self.total_ram_label = Gtk.Label(label="-", xalign=0)
        self.used_ram_label = Gtk.Label(label="-", xalign=0)
        self.total_storage_label = Gtk.Label(label="-", xalign=0)
        self.used_storage_label = Gtk.Label(label="-", xalign=0)

        metrics_grid.attach(Gtk.Label(label="Total RAM:", xalign=0), 0, 0, 1, 1)
        metrics_grid.attach(self.total_ram_label, 1, 0, 1, 1)
        metrics_grid.attach(Gtk.Label(label="Used RAM:", xalign=0), 2, 0, 1, 1)
        metrics_grid.attach(self.used_ram_label, 3, 0, 1, 1)
        metrics_grid.attach(Gtk.Label(label="Total Storage:", xalign=0), 0, 1, 1, 1)
        metrics_grid.attach(self.total_storage_label, 1, 1, 1, 1)
        metrics_grid.attach(Gtk.Label(label="Used Storage:", xalign=0), 2, 1, 1, 1)
        metrics_grid.attach(self.used_storage_label, 3, 1, 1, 1)

        split_vertical = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        split_vertical.set_vexpand(True)
        root.append(split_vertical)

        pkg_frame, self.package_summary_label, self.package_view = self._build_text_section("Packages")
        split_vertical.set_start_child(pkg_frame)

        lower_split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split_vertical.set_end_child(lower_split)

        bt_frame, self.bluetooth_summary_label, self.bluetooth_view = self._build_text_section(
            "Bluetooth Devices"
        )
        lower_split.set_start_child(bt_frame)

        partition_frame, self.partition_summary_label, self.partition_view = self._build_text_section(
            "Partition Health"
        )
        lower_split.set_end_child(partition_frame)

    def _build_text_section(self, title: str) -> tuple[Gtk.Frame, Gtk.Label, Gtk.TextView]:
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        frame.set_child(box)

        summary = Gtk.Label(label="-", xalign=0)
        box.append(summary)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        box.append(scroller)

        text = Gtk.TextView()
        text.set_editable(False)
        text.set_cursor_visible(False)
        text.set_monospace(True)
        text.set_wrap_mode(Gtk.WrapMode.NONE)
        scroller.set_child(text)
        return frame, summary, text

    def _on_manual_refresh_clicked(self, _button: Gtk.Button) -> None:
        self._start_refresh(reason="manual")

    def _on_auto_refresh_timer(self) -> bool:
        self._start_refresh(reason="auto")
        return True

    def _start_refresh(self, *, reason: str) -> None:
        if self._refresh_inflight:
            return
        self._refresh_inflight = True
        self.refresh_button.set_sensitive(False)
        self.status_label.set_text(f"Refreshing data ({reason})...")

        future = self._executor.submit(self._collect_snapshot)
        future.add_done_callback(lambda fut: GLib.idle_add(self._apply_snapshot, fut))

    def _collect_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "metrics": None,
            "packages": [],
            "bluetooth_devices": [],
            "bluetooth_status": "Bluetooth adapter status unavailable.",
            "partitions": [],
            "errors": [],
            "collected_at": datetime.now(),
        }
        try:
            snapshot["metrics"] = self._system_service.collect()
        except Exception as exc:  # noqa: BLE001
            snapshot["errors"].append(f"system metrics: {exc}")

        try:
            snapshot["packages"] = self._package_service.collect()
        except Exception as exc:  # noqa: BLE001
            snapshot["errors"].append(f"packages: {exc}")

        try:
            snapshot["bluetooth_status"] = self._bluetooth_service.adapter_status()
        except Exception as exc:  # noqa: BLE001
            snapshot["errors"].append(f"bluetooth status: {exc}")

        try:
            snapshot["bluetooth_devices"] = self._bluetooth_service.collect()
        except Exception as exc:  # noqa: BLE001
            snapshot["errors"].append(f"bluetooth: {exc}")

        try:
            snapshot["partitions"] = self._partition_service.collect()
        except Exception as exc:  # noqa: BLE001
            snapshot["errors"].append(f"partitions: {exc}")

        return snapshot

    def _apply_snapshot(self, future: Future[dict[str, Any]]) -> bool:
        try:
            snapshot = future.result()
        except Exception as exc:  # noqa: BLE001
            self.status_label.set_text(f"Refresh failed: {exc}")
            self._refresh_inflight = False
            self.refresh_button.set_sensitive(True)
            return False

        metrics = snapshot.get("metrics")
        packages: list[PackageEntry] = snapshot.get("packages", [])
        bluetooth_devices: list[BluetoothDeviceEntry] = snapshot.get("bluetooth_devices", [])
        bluetooth_status: str = snapshot.get("bluetooth_status", "Bluetooth adapter status unavailable.")
        partitions: list[PartitionEntry] = snapshot.get("partitions", [])
        errors: list[str] = snapshot.get("errors", [])
        collected_at: datetime = snapshot.get("collected_at", datetime.now())

        if isinstance(metrics, SystemMetrics):
            self.total_ram_label.set_text(f"{metrics.total_ram_gb:.2f} GB")
            self.used_ram_label.set_text(f"{metrics.used_ram_gb:.2f} GB")
            self.total_storage_label.set_text(f"{metrics.total_storage_gb:.2f} GB")
            self.used_storage_label.set_text(f"{metrics.used_storage_gb:.2f} GB")
        else:
            self.total_ram_label.set_text("N/A")
            self.used_ram_label.set_text("N/A")
            self.total_storage_label.set_text("N/A")
            self.used_storage_label.set_text("N/A")

        updatable_count = len([item for item in packages if item.status == "Update available"])
        self.package_summary_label.set_text(
            f"Installed packages: {len(packages)} | Updates available: {updatable_count}"
        )
        self._set_textview_content(self.package_view, self._render_package_lines(packages))

        bt_count = len([device for device in bluetooth_devices if device.connected])
        self.bluetooth_summary_label.set_text(f"{bluetooth_status} | Connected devices: {bt_count}")
        self._set_textview_content(
            self.bluetooth_view,
            self._render_bluetooth_lines(bluetooth_devices, bluetooth_status),
        )

        mount_error_count = len([entry for entry in partitions if entry.status.startswith("Mount error")])
        self.partition_summary_label.set_text(
            f"Partitions: {len(partitions)} | Mount errors: {mount_error_count}"
        )
        self._set_textview_content(self.partition_view, self._render_partition_lines(partitions))

        status_text = f"Last refresh: {collected_at.strftime('%Y-%m-%d %H:%M:%S')}"
        if errors:
            status_text += " | Warnings: " + "; ".join(errors)
        self.status_label.set_text(status_text)

        self._refresh_inflight = False
        self.refresh_button.set_sensitive(True)
        return False

    def _set_textview_content(self, text_view: Gtk.TextView, content: str) -> None:
        buffer = text_view.get_buffer()
        buffer.set_text(content)

    def _render_package_lines(self, items: list[PackageEntry]) -> str:
        header = f"{'Name':<42} {'Src':<6} {'Installed':<20} {'Latest':<20} Status"
        lines = [header, "-" * len(header)]
        if not items:
            lines.append("No packages found or package tools unavailable.")
            return "\n".join(lines)

        for item in items:
            lines.append(
                f"{item.name[:41]:<42} "
                f"{item.source:<6} "
                f"{item.installed_version[:19]:<20} "
                f"{item.latest_version[:19]:<20} "
                f"{item.status}"
            )
        return "\n".join(lines)

    def _render_bluetooth_lines(self, devices: list[BluetoothDeviceEntry], adapter_status: str) -> str:
        header = f"{'Name':<34} {'Address':<20} {'Connected':<10} Battery"
        lines = [header, "-" * len(header)]
        if not devices:
            lines.append("No connected Bluetooth devices detected.")
            lines.append(f"Adapter status: {adapter_status}")
            lines.append("Tip: USB receiver (2.4GHz dongle) devices are not Bluetooth.")
            lines.append("To connect Bluetooth devices, pair/connect from Ubuntu Settings > Bluetooth.")
            return "\n".join(lines)

        for device in devices:
            lines.append(
                f"{device.name[:33]:<34} "
                f"{device.address:<20} "
                f"{str(device.connected):<10} "
                f"{device.battery_percent}"
            )
        return "\n".join(lines)

    def _render_partition_lines(self, entries: list[PartitionEntry]) -> str:
        header = f"{'Device':<18} {'FS':<10} {'Size':<10} {'Mountpoint':<28} Status"
        lines = [header, "-" * len(header)]
        if not entries:
            lines.append("No partitions found or lsblk unavailable.")
            return "\n".join(lines)

        for entry in entries:
            lines.append(
                f"{entry.device[:17]:<18} "
                f"{entry.filesystem[:9]:<10} "
                f"{entry.size[:9]:<10} "
                f"{entry.mountpoint[:27]:<28} "
                f"{entry.status}"
            )
        return "\n".join(lines)
