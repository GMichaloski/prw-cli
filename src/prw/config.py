"""Configuration loading. Config lives at ~/.config/prw/config.json (all keys optional)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "prw"
CONFIG_PATH = CONFIG_DIR / "config.json"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "prw"
DB_PATH = DATA_DIR / "state.db"

DEFAULT_EVENTS = [
    "PR_MERGED",
    "PR_CLOSED",
    "REVIEW_REQUESTED",
    "APPROVED",
    "CHANGES_REQUESTED",
    "CI_FAILED",
    "THREAD_RESOLVED",
    "THREAD_REPLIED",
    "READY_FOR_REVIEW",
]


@dataclass
class Config:
    poll_interval_seconds: int = 120
    me: str | None = None
    team_members: list[str] = field(default_factory=list)
    enabled_events: list[str] = field(default_factory=lambda: list(DEFAULT_EVENTS))
    include_team: bool = False

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            return cls()
        raw = json.loads(CONFIG_PATH.read_text())
        team = raw.get("team", {})
        notif = raw.get("notifications", {})
        members = team.get("members", [])
        return cls(
            poll_interval_seconds=int(raw.get("poll_interval_seconds", 120)),
            me=raw.get("me"),
            team_members=members,
            enabled_events=notif.get("enabled_events", list(DEFAULT_EVENTS)),
            include_team=bool(members),
        )


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
