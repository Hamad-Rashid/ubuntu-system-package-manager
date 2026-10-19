from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import count


@dataclass(slots=True)
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    code: int


@dataclass(slots=True)
class PrivilegedCommandResult:
    ok: bool
    stdout: str
    stderr: str
    code: int
    command: list[str]
    queue_wait_seconds: float
    execution_seconds: float


_privileged_lock = threading.Lock()
_queue_state_lock = threading.Lock()
_queue_order = count(1)
_queued_ticket_ids: list[int] = []
_privileged_session: "PrivilegedSession | None" = None
RETRYABLE_ERROR_TOKENS = (
    "could not get lock",
    "unable to acquire the dpkg frontend lock",
    "is another process using it",
    "resource temporarily unavailable",
    "temporary failure",
    "another change is in progress",
    "snapd is not ready yet",
)


def run_command(args: list[str], timeout: int = 20) -> CommandResult:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return CommandResult(
            ok=proc.returncode == 0,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
            code=proc.returncode,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return CommandResult(ok=False, stdout="", stderr=str(exc), code=1)


def is_retryable_failure(stderr: str, stdout: str = "") -> bool:
    text = f"{stderr}\n{stdout}".strip().lower()
    if not text:
        return False
    return any(token in text for token in RETRYABLE_ERROR_TOKENS)


class PrivilegedSession:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self._process = process

    @classmethod
    def start(cls, timeout: int = 30) -> tuple["PrivilegedSession | None", CommandResult]:
        helper_path = os.path.join(os.path.dirname(__file__), "privileged_helper.py")
        try:
            process = subprocess.Popen(
                ["pkexec", helper_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return None, CommandResult(False, "", str(exc), 1)

        session = cls(process)
        result = session.execute(["true"], timeout=timeout)
        if result.ok:
            return session, result
        session.close()
        return None, result

    def execute(self, args: list[str], timeout: int) -> CommandResult:
        if self._process.poll() is not None:
            return CommandResult(
                False,
                "",
                "Privileged session is no longer running.",
                self._process.poll() or 1,
            )
        if self._process.stdin is None or self._process.stdout is None:
            return CommandResult(False, "", "Privileged session pipes are unavailable.", 1)

        try:
            self._process.stdin.write(json.dumps({"args": args, "timeout": timeout}) + "\n")
            self._process.stdin.flush()
            response_line = self._readline_with_timeout(timeout)
            if response_line is None:
                return CommandResult(False, "", "Privileged command timed out.", 1)
            if not response_line:
                stderr = "Privileged session exited before returning a result."
                if self._process.stderr is not None:
                    stderr_text = self._process.stderr.read().strip()
                    if stderr_text:
                        stderr = stderr_text
                return CommandResult(False, "", stderr, self._process.poll() or 1)
            payload = json.loads(response_line)
            return CommandResult(
                bool(payload.get("ok", False)),
                str(payload.get("stdout", "")).strip(),
                str(payload.get("stderr", "")).strip(),
                int(payload.get("code", 1)),
            )
        except (BrokenPipeError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return CommandResult(False, "", str(exc), 1)

    def _readline_with_timeout(self, timeout: int) -> str | None:
        if self._process.stdout is None:
            return ""
        ready, _, _ = select.select([self._process.stdout], [], [], max(timeout, 1))
        if not ready:
            return None
        return self._process.stdout.readline()

    def close(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                self._process.kill()
            except OSError:
                pass


def initialize_privileged_session(timeout: int = 30) -> CommandResult:
    global _privileged_session
    with _privileged_lock:
        if _privileged_session is not None:
            return CommandResult(True, "", "", 0)
        session, result = PrivilegedSession.start(timeout=timeout)
        if session is not None:
            _privileged_session = session
        return result


def shutdown_privileged_session() -> None:
    global _privileged_session
    with _privileged_lock:
        if _privileged_session is not None:
            _privileged_session.close()
            _privileged_session = None


def run_privileged_command(args: list[str], timeout: int = 20) -> PrivilegedCommandResult:
    if not args:
        return PrivilegedCommandResult(
            ok=False,
            stdout="",
            stderr="No command provided.",
            code=1,
            command=[],
            queue_wait_seconds=0.0,
            execution_seconds=0.0,
        )

    command = args if args[0] == "pkexec" else ["pkexec", *args]
    ticket_id = next(_queue_order)
    queued_at = datetime.now()

    with _queue_state_lock:
        _queued_ticket_ids.append(ticket_id)

    with _privileged_lock:
        started_at = datetime.now()
        with _queue_state_lock:
            if ticket_id in _queued_ticket_ids:
                _queued_ticket_ids.remove(ticket_id)

        if _privileged_session is not None:
            result = _privileged_session.execute(args if args[0] != "pkexec" else args[1:], timeout=timeout)
        else:
            result = run_command(command, timeout=timeout)
        finished_at = datetime.now()

    queue_wait_seconds = max((started_at - queued_at).total_seconds(), 0.0)
    execution_seconds = max((finished_at - started_at).total_seconds(), 0.0)
    return PrivilegedCommandResult(
        ok=result.ok,
        stdout=result.stdout,
        stderr=result.stderr,
        code=result.code,
        command=command,
        queue_wait_seconds=queue_wait_seconds,
        execution_seconds=execution_seconds,
    )


def run_privileged_command_with_retry(
    args: list[str],
    *,
    timeout: int = 20,
    retry_attempts: int = 1,
    retry_delay_seconds: float = 1.0,
) -> tuple[PrivilegedCommandResult, int]:
    attempts = 0
    while True:
        attempts += 1
        result = run_privileged_command(args, timeout=timeout)
        if result.ok:
            return result, attempts
        if attempts > retry_attempts:
            return result, attempts
        if not is_retryable_failure(result.stderr, result.stdout):
            return result, attempts
        time.sleep(max(retry_delay_seconds, 0.0))
