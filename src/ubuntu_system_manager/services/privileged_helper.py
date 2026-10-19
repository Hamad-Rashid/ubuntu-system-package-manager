#!/usr/bin/env python3
"""Private command helper launched once through PolicyKit."""

from __future__ import annotations

import json
import subprocess
import sys


def _send(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
            args = request["args"]
            timeout = request.get("timeout", 20)
            if not isinstance(args, list) or not args or not all(isinstance(item, str) for item in args):
                raise ValueError("Invalid command arguments.")
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                raise ValueError("Invalid command timeout.")

            process = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            _send(
                {
                    "ok": process.returncode == 0,
                    "stdout": process.stdout or "",
                    "stderr": process.stderr or "",
                    "code": process.returncode,
                }
            )
        except subprocess.TimeoutExpired as exc:
            _send({"ok": False, "stdout": "", "stderr": str(exc), "code": 1})
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            _send({"ok": False, "stdout": "", "stderr": str(exc), "code": 1})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
