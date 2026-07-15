"""Command-line entrypoint for prw."""

from __future__ import annotations

import argparse
import select
import subprocess
import sys
import termios
import time
import tty

from rich.console import Console
from rich.live import Live
from rich.text import Text

from . import daemon, gh
from .config import CONFIG_PATH, Config, DB_PATH, ensure_dirs
from . import dashboard
from .daemon import PollResult
from .fetch import fetch_snapshots
from .store import Store


def _resolve_me(config: Config) -> str:
    if config.me:
        return config.me
    return gh.current_login()


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit}" + ("s" if n != 1 else "")


def _relative(elapsed: int) -> str:
    """'Updated 5 seconds ago' / 'Updated 1 minute and 20 seconds ago'."""
    if elapsed < 60:
        return f"Updated {_plural(elapsed, 'second')} ago"
    minutes, seconds = divmod(elapsed, 60)
    return f"Updated {_plural(minutes, 'minute')} and {_plural(seconds, 'second')} ago"


def _footer(elapsed: int, result: PollResult | None) -> str:
    extra = ""
    if result and result.seeded_baseline:
        extra = " · baseline seeded (notifications start next refresh)"
    elif result and result.fired:
        extra = f" · 🔔 {result.fired} new notification(s)"
    return (f"{_relative(elapsed)} · "
            f"[R] reload · click a PR id to open · [Ctrl+C] quit{extra}")


def _fmt_wait(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs:02d}s"


def _wait(seconds: float, interactive: bool) -> bool:
    """Wait up to `seconds`. Return True if reload ('r') was requested; False on timeout.
    'q' raises KeyboardInterrupt. Reads stdin without echo (terminal is in cbreak mode)."""
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if not interactive:
            time.sleep(min(1.0, remaining))
            continue
        ready, _, _ = select.select([sys.stdin], [], [], min(1.0, remaining))
        if ready:
            ch = sys.stdin.read(1)
            if ch and ch.lower() == "r":
                return True
            if ch and ch.lower() == "q":
                raise KeyboardInterrupt


def cmd_status(config: Config, console: Console, once: bool) -> int:
    me = _resolve_me(config)
    store = Store(DB_PATH)
    interval = config.poll_interval_seconds
    try:
        if once:
            result = daemon.poll_once(config, me, store)
            dashboard.render(console, result.snapshots,
                             "Updated just now · click a PR id to open")
            return 0

        interactive = sys.stdin.isatty()
        old_termios = None
        if interactive:
            old_termios = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        try:
            last_snapshots = []
            last_result: PollResult | None = None
            err: gh.GhError | None = None
            with Live(Text("Loading PRs…", style="dim"), console=console,
                      auto_refresh=False, screen=False) as live:
                while True:
                    try:
                        last_result = daemon.poll_once(config, me, store)
                        last_snapshots = last_result.snapshots
                        err = None
                    except gh.GhError as exc:
                        err = exc

                    # When rate-limited, wait until the limit resets instead of hammering.
                    if isinstance(err, gh.RateLimitError):
                        wait_for = min(max(gh.seconds_until_reset(err.reset_at) + 5, 60), 3600)
                    else:
                        wait_for = interval

                    polled_at = time.monotonic()
                    # Tick the footer every second so "Updated N seconds ago" counts up,
                    # re-polling once the wait elapses or when 'R' is pressed.
                    while True:
                        elapsed = int(time.monotonic() - polled_at)
                        if isinstance(err, gh.RateLimitError):
                            left = max(0, wait_for - elapsed)
                            footer = (f"[yellow]⏳ GitHub API rate limit reached[/yellow] · "
                                      f"resuming in {_fmt_wait(left)} · [R] retry now · [Ctrl+C] quit")
                        elif err is not None:
                            footer = (f"[red]gh error (will retry):[/red] {err} · "
                                      f"[R] retry now · [Ctrl+C] quit")
                        else:
                            footer = _footer(elapsed, last_result)
                        live.update(dashboard.build(last_snapshots, footer), refresh=True)
                        if elapsed >= wait_for:
                            break
                        if _wait(1, interactive):  # 'R' pressed -> re-poll now
                            break
        finally:
            if old_termios is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_termios)
    except KeyboardInterrupt:
        console.print("\n[dim]bye[/dim]")
    finally:
        store.close()
    return 0


def cmd_daemon(config: Config, once: bool) -> int:
    me = _resolve_me(config)
    daemon.run(config, me, once=once)
    return 0


def cmd_open(config: Config, pr_ref: str, console: Console) -> int:
    me = _resolve_me(config)
    snapshots = fetch_snapshots(config, me)
    match = [s for s in snapshots if str(s.number) == pr_ref or s.key.endswith(f"#{pr_ref}")]
    if not match:
        console.print(f"[red]No open PR matching '{pr_ref}'.[/red]")
        return 1
    subprocess.run(["gh", "browse", "--repo", match[0].repo, str(match[0].number)], check=False)
    return 0


def cmd_config(console: Console) -> int:
    if CONFIG_PATH.exists():
        console.print(CONFIG_PATH.read_text())
    else:
        console.print(f"[dim]No config at {CONFIG_PATH}. Using defaults.[/dim]")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_dirs()
    parser = argparse.ArgumentParser(prog="prw", description="Track and get notified about GitHub PRs.")
    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="Live PR dashboard (auto-refreshing). Default command.")
    p_status.add_argument("--once", action="store_true", help="Render once and exit.")

    p_daemon = sub.add_parser("daemon", help="Run the background poller (no dashboard).")
    p_daemon.add_argument("--once", action="store_true", help="Poll a single time and exit.")

    p_open = sub.add_parser("open", help="Open a PR in the browser by number.")
    p_open.add_argument("pr", help="PR number.")

    sub.add_parser("config", help="Print the active config file path/contents.")

    args = parser.parse_args(argv)
    config = Config.load()
    console = Console()

    try:
        if args.command in (None, "status"):
            return cmd_status(config, console, once=getattr(args, "once", False))
        if args.command == "daemon":
            return cmd_daemon(config, args.once)
        if args.command == "open":
            return cmd_open(config, args.pr, console)
        if args.command == "config":
            return cmd_config(console)
    except gh.GhError as exc:
        console.print(f"[red]gh error:[/red] {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
