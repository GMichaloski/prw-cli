"""Desktop notifications via notify-send."""

from __future__ import annotations

import shutil
import subprocess

_CRITICAL = {"PR_MERGED", "CI_FAILED", "CHANGES_REQUESTED"}
_APP_NAME = "prw"


def available() -> bool:
    return shutil.which("notify-send") is not None


def send(event_type: str, title: str, body: str) -> None:
    """Fire a single desktop notification. Silently no-op if notify-send is missing."""
    if not available():
        return
    urgency = "critical" if event_type in _CRITICAL else "normal"
    try:
        subprocess.run(
            ["notify-send", "--app-name", _APP_NAME, f"--urgency={urgency}", title, body],
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass
