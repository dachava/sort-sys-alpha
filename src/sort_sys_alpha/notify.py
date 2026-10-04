"""Best-effort toast notifications for the scheduled `run` command.

Windows has no toast API in the standard library, and PLAN.md section 3
deliberately keeps that kind of Windows-only plumbing out of the Python
dependency list: it's handled by the "thin PowerShell layer" from ADR 0001
instead (`scripts/windows/notify.ps1`). On any other OS this is a no-op, the
same Linux-fake-adapter convention CLAUDE.md asks for.

A missed notification must never fail a run, so every failure mode here
(PowerShell missing, the call erroring, it timing out) is swallowed after a
warning to stderr.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

NOTIFY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "notify.ps1"


def notify(title: str, message: str) -> None:
    if platform.system() != "Windows":
        return
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(NOTIFY_SCRIPT),
                "-Title",
                title,
                "-Message",
                message,
            ],
            timeout=10,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"# notification failed: {e}", file=sys.stderr)
