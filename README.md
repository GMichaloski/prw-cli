# prw — GitHub PR companion

A small terminal companion that tracks your GitHub Pull Requests and sends desktop
notifications when something happens (approved, changes requested, merged, CI failed,
review requested, comment threads resolved…).

It uses your existing **`gh` CLI** authentication — no tokens to manage.

## Requirements

- `gh` CLI, authenticated (`gh auth status`)
- Python 3.10+
- `notify-send` (libnotify) for desktop notifications — optional, degrades gracefully

## Install

```bash
cd ~/IdeaProjects/pr-companion
python3 -m venv .venv
.venv/bin/pip install -e .
mkdir -p ~/.local/bin
ln -sf "$PWD/.venv/bin/prw" ~/.local/bin/prw     # make `prw` available on PATH
```

Ensure `~/.local/bin` is on your `PATH`.

## Usage

```bash
prw               # live dashboard: auto-refreshes every 5 min AND fires notifications
prw status --once # render once and exit (no loop)
prw daemon        # headless background poller (notifications only, no dashboard)
prw daemon --once # single poll (first run just seeds the baseline, silently)
prw open 7760     # open a PR in the browser
prw config        # show active config
```

Running `prw` keeps the terminal open with a live view; leave it running and it both
refreshes the tables and sends desktop notifications every 2 minutes. The footer counts
up ("Updated 5 seconds ago", "Updated 1 minute and 20 seconds ago") since the last refresh.

- Press **`R`** to reload immediately (don't wait for the next cycle).
- Press **`Q`** or `Ctrl+C` to quit.

**Click to open:** each PR id in the table is a terminal hyperlink — click it (or Ctrl+click,
depending on your terminal) to open that PR in the browser. Works in GNOME Terminal and most
modern terminals.

The **To review** bucket shows both PRs awaiting your review *and* PRs you already reviewed
(they no longer vanish once you submit). The *My review* column shows where you stand:

- `pending (you)` a review was requested from you directly (red — you must act)
- `pending (team)` the request reached you via a team you're on (yellow — a teammate may take it)
- `approved` / `changes req` / `commented` your submitted review
- `re-review (you|team) (was …)` you reviewed before, but a new review was just requested

The `(you)` / `(team)` tag tells you whether a request is aimed at you specifically or at your
team — team-routed requests are shown in a calmer color. You get the same distinction in the
review-requested desktop notification.

**"To review" — do I need to come back?** The *My comments* column tracks the review threads
*you* started on someone else's PR:

- `—` you haven't commented
- `all resolved` your threads were all resolved — nothing to do
- `N open` your comments are unresolved, waiting on the author
- `N open · reply ↩` the author **replied** to your comment and it's still open — come back and check

You also get a desktop notification (`THREAD_REPLIED`) the moment someone replies to one of your
review comments.

> Run the live view *or* the background daemon — not both at once, since they share the
> same state DB and would each try to notify.

## Run the daemon on login (systemd user service)

```bash
mkdir -p ~/.config/systemd/user
cp systemd/prw.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now prw.service
journalctl --user -u prw.service -f    # follow logs
```

## API rate limits

The tool uses GitHub's GraphQL API, which has a **point-based budget of 5000/hour**. Each
poll runs three lightweight searches (~13 points each, ~39/poll); at the default 2-minute
interval that's ~1200 points/hour, leaving plenty of headroom for your own `gh` usage.

If the limit is ever hit anyway (e.g. very frequent manual `gh` use), `prw` **detects it and
backs off automatically** until the limit resets — the footer shows a countdown
(`⏳ GitHub API rate limit reached · resuming in 4m 30s`). Press `R` to retry sooner.

To be gentler, raise `poll_interval_seconds` in the config. Query cost is kept low by
requesting only small result pages (see `queries.py`), so cost scales with the interval, not
the number of PRs you have.

## Config (optional)

`~/.config/prw/config.json` — all keys optional:

```json
{
  "poll_interval_seconds": 120,
  "me": "GMichaloski",
  "team": { "members": ["login1", "login2"] },
  "notifications": {
    "enabled_events": [
      "PR_MERGED", "PR_CLOSED", "REVIEW_REQUESTED", "APPROVED",
      "CHANGES_REQUESTED", "CI_FAILED", "THREAD_RESOLVED", "THREAD_REPLIED", "READY_FOR_REVIEW"
    ]
  }
}
```

If `team.members` is set, a third "Team" bucket is tracked. `me` defaults to the
authenticated `gh` user.
