"""Desktop notifications via notify-send, with a soft accompanying sound."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_CRITICAL = {"PR_MERGED", "CI_FAILED", "CHANGES_REQUESTED"}
_APP_NAME = "prw"

# A gentle freedesktop sound-theme cue, played quietly — not the sharper "bell"/"dialog-*" ones.
_SOUND_FILE = Path("/usr/share/sounds/freedesktop/stereo/message-new-instant.oga")
_SOUND_VOLUME = "24000"  # paplay's linear scale tops out at 65536; ~37% keeps it soft


def available() -> bool:
    return shutil.which("notify-send") is not None


def _play_sound() -> None:
    if not shutil.which("paplay") or not _SOUND_FILE.exists():
        return
    try:
        subprocess.run(
            ["paplay", f"--volume={_SOUND_VOLUME}", str(_SOUND_FILE)],
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def send(event_type: str, title: str, body: str) -> None:
    """Fire a single desktop notification with a soft sound. Silently no-op if notify-send is missing."""
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
    _play_sound()
