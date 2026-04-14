from __future__ import annotations

from dataclasses import dataclass
import re

from .command_runner import run_privileged_command_with_retry

VALID_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.:-]*$")
SUPPORTED_SOURCES = {"apt", "snap"}


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
    def _normalize_source(self, source: str) -> str:
        return (source or "").strip().lower()

    def _is_valid_package_name(self, name: str) -> bool:
        return bool(name and VALID_PACKAGE_NAME_RE.match(name.strip()))

    def _format_failure_message(self, base: str, stderr: str, stdout: str) -> str:
        text = f"{stderr}\n{stdout}".lower()
        if "not authorized" in text or "authentication" in text:
            return f"{base} failed: authentication denied or canceled."
        if "unable to locate package" in text:
            return f"{base} failed: package not found."
        if "could not get lock" in text or "another process is using it" in text:
            return f"{base} failed: package manager is busy. Retry in a few moments."
        if "another change is in progress" in text:
            return f"{base} failed: snapd already has another change running."
        return f"{base} failed."

    def _execute_action(
        self,
        *,
        cmd: list[str],
        timeout: int,
        message: str,
        retry_attempts: int = 1,
    ) -> PackageActionResult:
        result, attempts = run_privileged_command_with_retry(
            cmd,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_delay_seconds=1.0,
        )
        action_message = message
        if not result.ok:
            action_message = self._format_failure_message(message, result.stderr, result.stdout)
        if attempts > 1:
            action_message = f"{action_message} (attempts: {attempts})"
        return PackageActionResult(
            result.ok,
            result.code,
            action_message,
            result.stdout,
            result.stderr,
            result.command,
            result.queue_wait_seconds,
            result.execution_seconds,
        )

    def update_all_packages(self, *, apt_names: list[str], snap_names: list[str]) -> list[PackageActionResult]:
        results: list[PackageActionResult] = []

        normalized_apt = sorted({name.strip() for name in apt_names if self._is_valid_package_name(name)})
        if normalized_apt:
            cmd = ["apt-get", "install", "--only-upgrade", "-y", *normalized_apt]
            results.append(
                self._execute_action(
                    cmd=cmd,
                    timeout=3600,
                    message=f"Update all apt packages ({len(normalized_apt)})",
                    retry_attempts=1,
                )
            )

        normalized_snap = sorted({name.strip() for name in snap_names if self._is_valid_package_name(name)})
        if normalized_snap:
            cmd = ["snap", "refresh", *normalized_snap]
            results.append(
                self._execute_action(
                    cmd=cmd,
                    timeout=3600,
                    message=f"Update all snap packages ({len(normalized_snap)})",
                    retry_attempts=1,
                )
            )

        return results

    def update_package(self, *, name: str, source: str) -> PackageActionResult:
        normalized_source = self._normalize_source(source)
        package_name = (name or "").strip()
        if normalized_source not in SUPPORTED_SOURCES:
            return PackageActionResult(
                False, 1, f"Unsupported source for update: {source}", "", "", [], 0.0, 0.0
            )
        if not self._is_valid_package_name(package_name):
            return PackageActionResult(False, 1, f"Invalid package name: {name}", "", "", [], 0.0, 0.0)
        if normalized_source == "apt":
            return self._execute_action(
                cmd=["apt-get", "install", "--only-upgrade", "-y", package_name],
                timeout=2400,
                message=f"Update {package_name} (apt)",
                retry_attempts=1,
            )
        if normalized_source == "snap":
            return self._execute_action(
                cmd=["snap", "refresh", package_name],
                timeout=2400,
                message=f"Update {package_name} (snap)",
                retry_attempts=1,
            )
        return PackageActionResult(
            False, 1, f"Unsupported source for update: {source}", "", "", [], 0.0, 0.0
        )

    def remove_package(self, *, name: str, source: str) -> PackageActionResult:
        normalized_source = self._normalize_source(source)
        package_name = (name or "").strip()
        if normalized_source not in SUPPORTED_SOURCES:
            return PackageActionResult(
                False, 1, f"Unsupported source for remove: {source}", "", "", [], 0.0, 0.0
            )
        if not self._is_valid_package_name(package_name):
            return PackageActionResult(False, 1, f"Invalid package name: {name}", "", "", [], 0.0, 0.0)
        if normalized_source == "apt":
            return self._execute_action(
                cmd=["apt-get", "remove", "-y", package_name],
                timeout=2400,
                message=f"Remove {package_name} (apt)",
                retry_attempts=1,
            )
        if normalized_source == "snap":
            return self._execute_action(
                cmd=["snap", "remove", package_name],
                timeout=2400,
                message=f"Remove {package_name} (snap)",
                retry_attempts=1,
            )
        return PackageActionResult(
            False, 1, f"Unsupported source for remove: {source}", "", "", [], 0.0, 0.0
        )

    def toggle_package(self, *, name: str, source: str, enabled: bool) -> PackageActionResult:
        normalized_source = self._normalize_source(source)
        package_name = (name or "").strip()
        if normalized_source != "snap":
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
        if not self._is_valid_package_name(package_name):
            return PackageActionResult(False, 1, f"Invalid package name: {name}", "", "", [], 0.0, 0.0)

        action = "disable" if enabled else "enable"
        return self._execute_action(
            cmd=["snap", action, package_name],
            timeout=1200,
            message=f"{action.capitalize()} {package_name} (snap)",
            retry_attempts=1,
        )
