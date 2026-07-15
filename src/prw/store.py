"""SQLite persistence: latest snapshot per PR, plus an event log with a notified flag."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .model import PrSnapshot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    key        TEXT PRIMARY KEY,
    bucket     TEXT NOT NULL,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_key     TEXT NOT NULL,
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    url        TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notified   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- meta ---
    def is_seeded(self) -> bool:
        row = self.conn.execute("SELECT value FROM meta WHERE key='seeded'").fetchone()
        return row is not None and row["value"] == "1"

    def mark_seeded(self) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('seeded', '1')"
        )
        self.conn.commit()

    # --- snapshots ---
    def load_snapshots(self) -> dict[str, PrSnapshot]:
        rows = self.conn.execute("SELECT key, data FROM snapshots").fetchall()
        return {r["key"]: PrSnapshot.from_row(json.loads(r["data"])) for r in rows}

    def save_snapshots(self, snapshots: list[PrSnapshot]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM snapshots")
            self.conn.executemany(
                "INSERT INTO snapshots(key, bucket, data, updated_at) VALUES(?,?,?,?)",
                [(s.key, s.bucket, json.dumps(s.to_row()), s.updated_at) for s in snapshots],
            )

    # --- events ---
    def add_events(self, events: list["Event"]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO events(pr_key, type, title, body, url, created_at, notified)"
                " VALUES(?,?,?,?,?,?,0)",
                [(e.pr_key, e.type, e.title, e.body, e.url, e.created_at) for e in events],
            )

    def unnotified_events(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM events WHERE notified=0 ORDER BY id"
        ).fetchall()

    def mark_notified(self, event_ids: list[int]) -> None:
        with self.conn:
            self.conn.executemany(
                "UPDATE events SET notified=1 WHERE id=?", [(i,) for i in event_ids]
            )


# Placed here to avoid a circular import between store and diff at module load.
from .diff import Event  # noqa: E402
