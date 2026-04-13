from __future__ import annotations

from dataclasses import dataclass

from .command_runner import run_command


@dataclass(slots=True)
class PackageActionResult:
    ok: bool
    code: int
    message: str
    stdout: str
    stderr: str


class PackageActionService:
    def update_package(self, *, name: str, source: str) -> PackageActionResult:
        if source == "apt":
            cmd = ["pkexec", "apt-get", "install", "--only-upgrade", "-y", name]
            result = run_command(cmd, timeout=2400)
            message = f"Update {name} (apt)"
            return PackageActionResult(result.ok, result.code, message, result.stdout, result.stderr)
        if source == "snap":
            cmd = ["pkexec", "snap", "refresh", name]
            result = run_command(cmd, timeout=2400)
            message = f"Update {name} (snap)"
            return PackageActionResult(result.ok, result.code, message, result.stdout, result.stderr)
        return PackageActionResult(False, 1, f"Unsupported source for update: {source}", "", "")

    def remove_package(self, *, name: str, source: str) -> PackageActionResult:
        if source == "apt":
            cmd = ["pkexec", "apt-get", "remove", "-y", name]
            result = run_command(cmd, timeout=2400)
            message = f"Remove {name} (apt)"
            return PackageActionResult(result.ok, result.code, message, result.stdout, result.stderr)
        if source == "snap":
            cmd = ["pkexec", "snap", "remove", name]
            result = run_command(cmd, timeout=2400)
            message = f"Remove {name} (snap)"
            return PackageActionResult(result.ok, result.code, message, result.stdout, result.stderr)
        return PackageActionResult(False, 1, f"Unsupported source for remove: {source}", "", "")

    def toggle_package(self, *, name: str, source: str, enabled: bool) -> PackageActionResult:
        if source != "snap":
            return PackageActionResult(False, 1, f"Enable/Disable unsupported for source: {source}", "", "")

        action = "disable" if enabled else "enable"
        cmd = ["pkexec", "snap", action, name]
        result = run_command(cmd, timeout=1200)
        message = f"{action.capitalize()} {name} (snap)"
        return PackageActionResult(result.ok, result.code, message, result.stdout, result.stderr)
