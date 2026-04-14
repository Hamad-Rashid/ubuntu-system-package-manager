from __future__ import annotations

from dataclasses import dataclass

from .command_runner import run_privileged_command


@dataclass(slots=True)
class PackageActionResult:
    ok: bool
    code: int
    message: str
    stdout: str
    stderr: str
    command: list[str]
    queue_wait_seconds: float
    execution_seconds: float


class PackageActionService:
    def update_package(self, *, name: str, source: str) -> PackageActionResult:
        if source == "apt":
            cmd = ["apt-get", "install", "--only-upgrade", "-y", name]
            result = run_privileged_command(cmd, timeout=2400)
            message = f"Update {name} (apt)"
            return PackageActionResult(
                result.ok,
                result.code,
                message,
                result.stdout,
                result.stderr,
                result.command,
                result.queue_wait_seconds,
                result.execution_seconds,
            )
        if source == "snap":
            cmd = ["snap", "refresh", name]
            result = run_privileged_command(cmd, timeout=2400)
            message = f"Update {name} (snap)"
            return PackageActionResult(
                result.ok,
                result.code,
                message,
                result.stdout,
                result.stderr,
                result.command,
                result.queue_wait_seconds,
                result.execution_seconds,
            )
        return PackageActionResult(
            False, 1, f"Unsupported source for update: {source}", "", "", [], 0.0, 0.0
        )

    def remove_package(self, *, name: str, source: str) -> PackageActionResult:
        if source == "apt":
            cmd = ["apt-get", "remove", "-y", name]
            result = run_privileged_command(cmd, timeout=2400)
            message = f"Remove {name} (apt)"
            return PackageActionResult(
                result.ok,
                result.code,
                message,
                result.stdout,
                result.stderr,
                result.command,
                result.queue_wait_seconds,
                result.execution_seconds,
            )
        if source == "snap":
            cmd = ["snap", "remove", name]
            result = run_privileged_command(cmd, timeout=2400)
            message = f"Remove {name} (snap)"
            return PackageActionResult(
                result.ok,
                result.code,
                message,
                result.stdout,
                result.stderr,
                result.command,
                result.queue_wait_seconds,
                result.execution_seconds,
            )
        return PackageActionResult(
            False, 1, f"Unsupported source for remove: {source}", "", "", [], 0.0, 0.0
        )

    def toggle_package(self, *, name: str, source: str, enabled: bool) -> PackageActionResult:
        if source != "snap":
            return PackageActionResult(
                False,
                1,
                f"Enable/Disable unsupported for source: {source}",
                "",
                "",
                [],
                0.0,
                0.0,
            )

        action = "disable" if enabled else "enable"
        cmd = ["snap", action, name]
        result = run_privileged_command(cmd, timeout=1200)
        message = f"{action.capitalize()} {name} (snap)"
        return PackageActionResult(
            result.ok,
            result.code,
            message,
            result.stdout,
            result.stderr,
            result.command,
            result.queue_wait_seconds,
            result.execution_seconds,
        )
