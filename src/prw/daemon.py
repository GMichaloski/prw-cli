"""Poll loop: fetch -> diff -> persist -> notify. Used by `prw daemon`."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import gh, notify
from .config import Config, DB_PATH
from .diff import diff_snapshots
from .fetch import fetch_snapshots
from .model import PrSnapshot
from .store import Store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PollResult:
    snapshots: list[PrSnapshot] = field(default_factory=list)
    fired: int = 0            # notifications fired this cycle
    seeded_baseline: bool = False


def poll_once(config: Config, me: str, store: Store) -> PollResult:
    """Run one poll cycle: fetch, diff, persist, notify. Returns the fetched snapshots."""
    snapshots = fetch_snapshots(config, me)
    previous = store.load_snapshots()
    seeded = store.is_seeded()

    events = diff_snapshots(previous, snapshots, _now())
    events = [e for e in events if e.type in config.enabled_events]

    store.save_snapshots(snapshots)

    if not seeded:
        # First run: establish a baseline silently so we don't alert on everything.
        store.mark_seeded()
        return PollResult(snapshots, 0, True)

    if events:
        store.add_events(events)

    fired = 0
    for row in store.unnotified_events():
        notify.send(row["type"], row["title"], row["body"])
        store.mark_notified([row["id"]])
        fired += 1
    return PollResult(snapshots, fired, False)


def run(config: Config, me: str, once: bool = False) -> None:
    store = Store(DB_PATH)

    def log(msg: str) -> None:
        print(f"[{_now()}] {msg}", flush=True)

    try:
        while True:
            wait_for = config.poll_interval_seconds
            try:
                result = poll_once(config, me, store)
                if result.seeded_baseline:
                    log(f"seeded baseline with {len(result.snapshots)} PR(s); "
                        "notifications start next poll")
                elif result.fired:
                    log(f"fired {result.fired} notification(s)")
            except gh.RateLimitError as exc:
                wait_for = min(max(gh.seconds_until_reset(exc.reset_at) + 5, 60), 3600)
                log(f"rate limit reached; backing off {wait_for}s until reset")
            except gh.GhError as exc:
                log(f"gh error (will retry): {exc}")
            except Exception as exc:  # never let the loop die
                log(f"unexpected error (will retry): {exc!r}")
            if once:
                return
            time.sleep(wait_for)
    finally:
        store.close()
