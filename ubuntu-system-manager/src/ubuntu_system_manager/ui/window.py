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
from ubuntu_system_manager.services.package_action_service import (
    PackageActionResult,
    PackageActionService,
)
from ubuntu_system_manager.services.package_service import PackageService
from ubuntu_system_manager.services.partition_service import PartitionService
from ubuntu_system_manager.services.system_info import SystemInfoService


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_title("Ubuntu System Manager - Phase 2")
        self.set_default_size(1300, 860)

        self._system_service = SystemInfoService()
        self._package_service = PackageService()
        self._package_action_service = PackageActionService()
        self._bluetooth_service = BluetoothService()
        self._partition_service = PartitionService()

        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="phase2-worker")
        self._refresh_inflight = False
        self._operation_inflight = False
        self._packages: list[PackageEntry] = []
        self._package_log_lines: list[str] = []

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

        (
            pkg_frame,
            self.package_summary_label,
            self.package_notebook,
            self.package_all_listbox,
            self.package_updates_listbox,
            self.package_log_view,
        ) = self._build_package_section()
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

        self._update_controls_state()

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

    def _build_package_section(
        self,
    ) -> tuple[Gtk.Frame, Gtk.Label, Gtk.Notebook, Gtk.ListBox, Gtk.ListBox, Gtk.TextView]:
        frame = Gtk.Frame(label="Packages")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        frame.set_child(box)

        summary_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(summary_row)

        summary = Gtk.Label(label="-", xalign=0)
        summary.set_hexpand(True)
        summary_row.append(summary)

        self.update_all_button = Gtk.Button(label="Update All")
        self.update_all_button.connect("clicked", self._on_update_all_clicked)
        summary_row.append(self.update_all_button)

        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        box.append(notebook)

        all_listbox = Gtk.ListBox()
        all_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        all_scroller = Gtk.ScrolledWindow()
        all_scroller.set_hexpand(True)
        all_scroller.set_vexpand(True)
        all_scroller.set_child(all_listbox)
        notebook.append_page(all_scroller, Gtk.Label(label="All Installed"))

        updates_listbox = Gtk.ListBox()
        updates_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        updates_scroller = Gtk.ScrolledWindow()
        updates_scroller.set_hexpand(True)
        updates_scroller.set_vexpand(True)
        updates_scroller.set_child(updates_listbox)
        notebook.append_page(updates_scroller, Gtk.Label(label="Updates Available"))

        log_title = Gtk.Label(label="Package Action Log", xalign=0)
        box.append(log_title)

        log_scroller = Gtk.ScrolledWindow()
        log_scroller.set_min_content_height(120)
        box.append(log_scroller)

        log_view = Gtk.TextView()
        log_view.set_editable(False)
        log_view.set_cursor_visible(False)
        log_view.set_monospace(True)
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        log_scroller.set_child(log_view)

        return frame, summary, notebook, all_listbox, updates_listbox, log_view

    def _on_manual_refresh_clicked(self, _button: Gtk.Button) -> None:
        self._start_refresh(reason="manual")

    def _on_auto_refresh_timer(self) -> bool:
        self._start_refresh(reason="auto")
        return True

    def _start_refresh(self, *, reason: str) -> None:
        if self._refresh_inflight:
            return
        self._refresh_inflight = True
        self.status_label.set_text(f"Refreshing data ({reason})...")
        self._update_controls_state()

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
            self._update_controls_state()
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

        updatable_packages = [item for item in packages if item.update_available]
        self._packages = packages
        self.package_summary_label.set_text(
            f"Installed packages: {len(packages)} | Updates available: {len(updatable_packages)}"
        )
        self._rebuild_package_list(
            self.package_all_listbox,
            packages,
            empty_message="No packages found or package tools unavailable.",
        )
        self._rebuild_package_list(
            self.package_updates_listbox,
            updatable_packages,
            empty_message="No updates available.",
        )

        bt_count = len([device for device in bluetooth_devices if device.connected])
        self.bluetooth_summary_label.set_text(f"{bluetooth_status} | Connected Bluetooth/USB devices: {bt_count}")
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
        self._update_controls_state()
        return False

    def _rebuild_package_list(self, listbox: Gtk.ListBox, items: list[PackageEntry], *, empty_message: str) -> None:
        self._clear_listbox(listbox)

        if not items:
            empty_row = Gtk.ListBoxRow()
            label = Gtk.Label(label=empty_message, xalign=0)
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            label.set_margin_start(8)
            label.set_margin_end(8)
            empty_row.set_child(label)
            listbox.append(empty_row)
            return

        for package in items:
            listbox.append(self._build_package_row(package))

    def _clear_listbox(self, listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            listbox.remove(child)
            child = next_child

    def _build_package_row(self, package: PackageEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)
        row.set_child(row_box)

        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details_box.set_hexpand(True)
        row_box.append(details_box)

        title = Gtk.Label(
            label=f"{package.name} [{package.source}]",
            xalign=0,
        )
        details_box.append(title)

        meta = Gtk.Label(
            label=(
                f"Installed: {package.installed_version} | "
                f"Latest: {package.latest_version} | "
                f"Status: {package.status}"
            ),
            xalign=0,
        )
        meta.add_css_class("dim-label")
        meta.set_wrap(True)
        details_box.append(meta)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row_box.append(action_box)

        update_btn = Gtk.Button(label="Update")
        update_btn.set_sensitive(package.update_available)
        if not package.update_available:
            update_btn.set_tooltip_text("No update available.")
        update_btn.connect("clicked", self._on_package_update_clicked, package)
        action_box.append(update_btn)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self._on_package_remove_clicked, package)
        action_box.append(remove_btn)

        toggle_label = "Disable" if package.enabled else "Enable"
        toggle_btn = Gtk.Button(label=toggle_label)
        toggle_btn.set_sensitive(package.can_toggle)
        if not package.can_toggle:
            toggle_btn.set_tooltip_text("Enable/Disable is only supported for snap packages.")
        toggle_btn.connect("clicked", self._on_package_toggle_clicked, package)
        action_box.append(toggle_btn)

        return row

    def _on_package_update_clicked(self, _button: Gtk.Button, package: PackageEntry) -> None:
        if not package.update_available:
            return
        heading = f"Update package '{package.name}'?"
        body = (
            f"This will update the {package.source} package '{package.name}' "
            "using administrator privileges."
        )
        self._confirm_package_action(
            heading=heading,
            body=body,
            confirm_label="Update",
            destructive=False,
            action="update",
            package=package,
        )

    def _on_update_all_clicked(self, _button: Gtk.Button) -> None:
        updatable_packages = [item for item in self._packages if item.update_available]
        if not updatable_packages:
            self.status_label.set_text("No updates are currently available.")
            return

        apt_count = len([item for item in updatable_packages if item.source == "apt"])
        snap_count = len([item for item in updatable_packages if item.source == "snap"])
        total_count = len(updatable_packages)

        heading = f"Update all available packages ({total_count})?"
        body = (
            "This will run package updates with administrator privileges.\n"
            f"APT: {apt_count} package(s)\n"
            f"Snap: {snap_count} package(s)"
        )
        dialog = Adw.MessageDialog.new(self, heading, body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", "Update All")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg: Adw.MessageDialog, response: str) -> None:
            if response == "confirm":
                self._run_update_all_action(updatable_packages)
            dialog.close()

        dialog.connect("response", _on_response)
        dialog.present()

    def _on_package_remove_clicked(self, _button: Gtk.Button, package: PackageEntry) -> None:
        heading = f"Remove package '{package.name}'?"
        body = f"This will remove the {package.source} package '{package.name}'."
        self._confirm_package_action(
            heading=heading,
            body=body,
            confirm_label="Remove",
            destructive=True,
            action="remove",
            package=package,
        )

    def _on_package_toggle_clicked(self, _button: Gtk.Button, package: PackageEntry) -> None:
        if not package.can_toggle:
            return

        action_name = "Disable" if package.enabled else "Enable"
        heading = f"{action_name} package '{package.name}'?"
        body = f"This will {action_name.lower()} the snap package '{package.name}'."
        self._confirm_package_action(
            heading=heading,
            body=body,
            confirm_label=action_name,
            destructive=False,
            action="toggle",
            package=package,
        )

    def _confirm_package_action(
        self,
        *,
        heading: str,
        body: str,
        confirm_label: str,
        destructive: bool,
        action: str,
        package: PackageEntry,
    ) -> None:
        dialog = Adw.MessageDialog.new(self, heading, body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", confirm_label)
        if destructive:
            dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        else:
            dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg: Adw.MessageDialog, response: str) -> None:
            if response == "confirm":
                self._run_package_action(action, package)
            dialog.close()

        dialog.connect("response", _on_response)
        dialog.present()

    def _run_package_action(self, action: str, package: PackageEntry) -> None:
        if self._operation_inflight:
            self.status_label.set_text("Another package operation is already running.")
            return

        self._operation_inflight = True
        self._update_controls_state()
        self._append_package_log(f"Running action: {action} {package.name} ({package.source})")
        self.status_label.set_text(f"Running {action} on {package.name}...")

        future = self._executor.submit(self._execute_package_action, action, package)
        future.add_done_callback(
            lambda fut, act=action, pkg_name=package.name: GLib.idle_add(
                self._on_package_action_done, fut, act, pkg_name
            )
        )

    def _run_update_all_action(self, packages: list[PackageEntry]) -> None:
        if self._operation_inflight:
            self.status_label.set_text("Another package operation is already running.")
            return

        self._operation_inflight = True
        self._update_controls_state()
        self._append_package_log(f"Running action: update-all ({len(packages)} package(s))")
        self.status_label.set_text(f"Running update-all for {len(packages)} package(s)...")

        apt_names = [item.name for item in packages if item.source == "apt"]
        snap_names = [item.name for item in packages if item.source == "snap"]

        future = self._executor.submit(self._execute_update_all_action, apt_names, snap_names)
        future.add_done_callback(
            lambda fut, total=len(packages): GLib.idle_add(self._on_update_all_done, fut, total)
        )

    def _execute_package_action(self, action: str, package: PackageEntry) -> PackageActionResult:
        if action == "update":
            return self._package_action_service.update_package(name=package.name, source=package.source)
        if action == "remove":
            return self._package_action_service.remove_package(name=package.name, source=package.source)
        if action == "toggle":
            return self._package_action_service.toggle_package(
                name=package.name,
                source=package.source,
                enabled=package.enabled,
            )
        return PackageActionResult(False, 1, f"Unsupported action: {action}", "", "", [], 0.0, 0.0)

    def _execute_update_all_action(self, apt_names: list[str], snap_names: list[str]) -> list[PackageActionResult]:
        return self._package_action_service.update_all_packages(apt_names=apt_names, snap_names=snap_names)

    def _on_update_all_done(self, future: Future[list[PackageActionResult]], total_count: int) -> bool:
        try:
            results = future.result()
        except Exception as exc:  # noqa: BLE001
            self._append_package_log(f"Action failed unexpectedly: update-all | {exc}")
            self.status_label.set_text(f"Update-all failed: {exc}")
            self._operation_inflight = False
            self._update_controls_state()
            return False

        if not results:
            self._append_package_log("FAILED: Update-all had no runnable package sources.")
            self.status_label.set_text("Update-all failed: no supported package sources were found.")
            self._operation_inflight = False
            self._update_controls_state()
            return False

        success_count = 0
        for result in results:
            if result.ok:
                success_count += 1
                self._append_package_log(f"SUCCESS: {result.message}")
            else:
                self._append_package_log(f"FAILED: {result.message} (exit {result.code})")

            if result.command:
                self._append_package_log("command: " + " ".join(result.command))
            self._append_package_log(
                f"timing: queue={result.queue_wait_seconds:.2f}s exec={result.execution_seconds:.2f}s"
            )
            if result.stdout:
                self._append_package_log(f"stdout: {result.stdout[-1200:]}")
            if result.stderr:
                self._append_package_log(f"stderr: {result.stderr[-1200:]}")

        if success_count == len(results):
            self.status_label.set_text(f"Success: update-all completed for {total_count} package(s).")
        else:
            failed_count = len(results) - success_count
            self.status_label.set_text(
                f"Update-all completed with errors ({failed_count}/{len(results)} command(s) failed)."
            )

        self._operation_inflight = False
        self._update_controls_state()
        self._start_refresh(reason="post-action")
        return False

    def _on_package_action_done(self, future: Future[PackageActionResult], action: str, pkg_name: str) -> bool:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self._append_package_log(f"Action failed unexpectedly: {action} {pkg_name} | {exc}")
            self.status_label.set_text(f"Operation failed: {exc}")
            self._operation_inflight = False
            self._update_controls_state()
            return False

        if result.ok:
            self._append_package_log(f"SUCCESS: {result.message}")
            self.status_label.set_text(f"Success: {result.message}")
        else:
            self._append_package_log(f"FAILED: {result.message} (exit {result.code})")
            self.status_label.set_text(f"Failed: {result.message}")

        if result.command:
            self._append_package_log("command: " + " ".join(result.command))
        self._append_package_log(
            f"timing: queue={result.queue_wait_seconds:.2f}s exec={result.execution_seconds:.2f}s"
        )

        if result.stdout:
            self._append_package_log(f"stdout: {result.stdout[-1200:]}")
        if result.stderr:
            self._append_package_log(f"stderr: {result.stderr[-1200:]}")

        self._operation_inflight = False
        self._update_controls_state()
        self._start_refresh(reason="post-action")
        return False

    def _append_package_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._package_log_lines.append(f"[{timestamp}] {message}")
        if len(self._package_log_lines) > 250:
            self._package_log_lines = self._package_log_lines[-250:]
        self._set_textview_content(self.package_log_view, "\n".join(self._package_log_lines))

    def _update_controls_state(self) -> None:
        refresh_sensitive = not self._refresh_inflight and not self._operation_inflight
        self.refresh_button.set_sensitive(refresh_sensitive)
        package_panel_sensitive = not self._refresh_inflight and not self._operation_inflight
        self.package_notebook.set_sensitive(package_panel_sensitive)
        has_updates = any(item.update_available for item in self._packages)
        self.update_all_button.set_sensitive(package_panel_sensitive and has_updates)
        if has_updates:
            self.update_all_button.set_tooltip_text("Update all currently upgradable packages.")
        else:
            self.update_all_button.set_tooltip_text("No updates available.")

    def _set_textview_content(self, text_view: Gtk.TextView, content: str) -> None:
        buffer = text_view.get_buffer()
        buffer.set_text(content)

    def _render_bluetooth_lines(self, devices: list[BluetoothDeviceEntry], adapter_status: str) -> str:
        header = f"{'Name':<34} {'Address':<20} {'Connected':<10} Battery"
        lines = [header, "-" * len(header)]
        if not devices:
            lines.append("No connected Bluetooth/USB receiver devices detected.")
            lines.append(f"Adapter status: {adapter_status}")
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
