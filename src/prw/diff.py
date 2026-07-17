"""Compare a previous snapshot map against the freshly fetched one to derive events."""

from __future__ import annotations

from dataclasses import dataclass

from .model import PrSnapshot

_FAIL_STATES = {"FAILURE", "ERROR"}


@dataclass
class Event:
    pr_key: str
    type: str
    title: str
    body: str
    url: str
    created_at: str


def _body(pr: PrSnapshot) -> str:
    return f"{pr.repo}#{pr.number} · {pr.title}"


def diff_snapshots(
    previous: dict[str, PrSnapshot],
    current: list[PrSnapshot],
    now: str,
) -> list[Event]:
    """Emit events for meaningful transitions between previous and current state."""
    events: list[Event] = []

    for pr in current:
        old = previous.get(pr.key)
        body = _body(pr)

        # Brand-new PR in a bucket.
        if old is None:
            if pr.bucket == "review" and pr.review_requested and not pr.is_draft:
                who = "team" if pr.requested_for == "team" else "you"
                events.append(Event(pr.key, "REVIEW_REQUESTED",
                                     f"👀 Review requested ({who}) — @{pr.author}", body, pr.url, now))
            continue

        is_mine = pr.bucket == "mine"
        is_reviewer = pr.bucket == "review"

        # State transitions — only matter for my own PRs.
        if is_mine:
            if old.state == "OPEN" and pr.state == "MERGED":
                events.append(Event(pr.key, "PR_MERGED", "🚀 PR merged", body, pr.url, now))
            elif old.state == "OPEN" and pr.state == "CLOSED" and not pr.merged:
                events.append(Event(pr.key, "PR_CLOSED", "🔒 PR closed", body, pr.url, now))

        # Re-review requested after I already reviewed.
        if is_reviewer and pr.review_requested and not old.review_requested and not pr.is_draft:
            who = "team" if pr.requested_for == "team" else "you"
            events.append(Event(pr.key, "REVIEW_REQUESTED",
                                f"🔄 Re-review requested ({who}) — @{pr.author}", body, pr.url, now))

        # Draft -> ready, only if I'm a requested reviewer.
        if is_reviewer and old.is_draft and not pr.is_draft:
            events.append(Event(pr.key, "READY_FOR_REVIEW", "📢 Marked ready for review", body, pr.url, now))

        # New approvals/change-requests — only meaningful on my own PR.
        if is_mine:
            for login in pr.approvals:
                if login not in old.approvals:
                    events.append(Event(pr.key, "APPROVED", f"✅ Approved by @{login}", body, pr.url, now))

            for login in pr.changes_requested:
                if login not in old.changes_requested:
                    events.append(Event(pr.key, "CHANGES_REQUESTED",
                                        f"✋ Changes requested by @{login}", body, pr.url, now))

            # CI transitions.
            if pr.ci in _FAIL_STATES and old.ci not in _FAIL_STATES:
                events.append(Event(pr.key, "CI_FAILED", "❌ CI failed", body, pr.url, now))
            elif pr.ci == "SUCCESS" and old.ci is not None and old.ci != "SUCCESS":
                events.append(Event(pr.key, "CI_PASSED", "🟢 CI passed", body, pr.url, now))

        # Someone commented on my PR — either a top-level comment or a new review thread.
        if is_mine:
            if pr.comment_count > old.comment_count:
                who = f"@{pr.last_commenter}" if pr.last_commenter else "someone"
                events.append(Event(pr.key, "PR_COMMENTED",
                                    f"💬 New comment by {who}", body, pr.url, now))
            if pr.threads_by_others > old.threads_by_others:
                events.append(Event(pr.key, "PR_COMMENTED",
                                    "💬 New review comment on your PR", body, pr.url, now))

        # A thread I started got resolved (my comment, answered/resolved) — regardless of bucket.
        my_resolved = pr.my_threads_total - pr.my_threads_unresolved
        old_my_resolved = old.my_threads_total - old.my_threads_unresolved
        if my_resolved > old_my_resolved:
            delta = my_resolved - old_my_resolved
            events.append(Event(pr.key, "THREAD_RESOLVED",
                                f"💬 {delta} of your comment thread(s) resolved", body, pr.url, now))

        # Someone replied to a thread I started — I need to come back.
        if pr.my_threads_waiting_on_me > old.my_threads_waiting_on_me:
            events.append(Event(pr.key, "THREAD_REPLIED",
                                "↩️ Reply on your review comment", body, pr.url, now))

    return events
