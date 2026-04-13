from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    code: int


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
