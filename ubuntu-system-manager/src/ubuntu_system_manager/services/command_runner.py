from __future__ import annotations

import subprocess
import threading
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
