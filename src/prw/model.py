"""Typed representation of a PR snapshot, parsed from the GraphQL response."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Bots and automation whose reviews/comments are noise for our purposes.
BOT_LOGINS = {"amazon-q-developer", "github-actions", "github-advanced-security", "coderabbitai"}


@dataclass
class PrSnapshot:
    key: str                       # "owner/repo#number" — stable identity
    number: int
    title: str
    url: str
    repo: str
    author: str
    is_draft: bool
    state: str                     # OPEN | MERGED | CLOSED
    merged: bool
    updated_at: str
    review_decision: str | None    # APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | None
    mergeable: str                 # MERGEABLE | CONFLICTING | UNKNOWN
    approvals: list[str] = field(default_factory=list)
    changes_requested: list[str] = field(default_factory=list)
    unresolved_threads: int = 0
    resolved_threads: int = 0
    my_threads_total: int = 0          # review threads I started
    my_threads_unresolved: int = 0     # ...that are still unresolved
    my_threads_waiting_on_me: int = 0  # ...unresolved where someone replied after me
    threads_by_others: int = 0     # review threads started by someone other than me
    comment_count: int = 0         # total top-level (issue) comments on the PR
    last_commenter: str | None = None  # author of the most recent top-level comment
    ci: str | None = None          # SUCCESS | FAILURE | PENDING | ERROR | EXPECTED | None
    my_review: str | None = None   # my latest review state on this PR, if any
    review_requested: bool = False  # I'm still on the requested-reviewers list
    requested_for: str | None = None  # "user" (me directly) | "team" | None
    bucket: str = "mine"           # mine | review | team

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "PrSnapshot":
        return cls(**row)


def _latest_reviews_by_author(review_nodes: list[dict]) -> dict[str, str]:
    """Map each non-bot reviewer to their most recent review state (nodes are chronological)."""
    latest: dict[str, str] = {}
    for node in review_nodes:
        author = (node.get("author") or {}).get("login")
        if not author or author in BOT_LOGINS:
            continue
        latest[author] = node["state"]
    return latest


def _comment_author(thread: dict, alias: str) -> str | None:
    nodes = (thread.get(alias) or {}).get("nodes") or []
    if not nodes:
        return None
    return (nodes[0].get("author") or {}).get("login")


def _first_author(thread: dict) -> str | None:
    return _comment_author(thread, "firstComment")


def _last_author(thread: dict) -> str | None:
    return _comment_author(thread, "lastComment")


def _requested_for(node: dict, me: str) -> str | None:
    """Whether my pending review request is direct ('user') or via a team ('team').

    If I'm listed individually it's direct; otherwise, since the PR matched
    review-requested:@me, the request reached me through a team I'm on.
    """
    has_team = False
    for req in node.get("reviewRequests", {}).get("nodes", []):
        reviewer = req.get("requestedReviewer") or {}
        if reviewer.get("__typename") == "User" and reviewer.get("login") == me:
            return "user"
        if reviewer.get("__typename") == "Team":
            has_team = True
    return "team" if has_team else None


def parse_pr(node: dict, bucket: str, me: str) -> PrSnapshot:
    """Build a PrSnapshot from one GraphQL PullRequest node."""
    repo = node["repository"]["nameWithOwner"]
    number = node["number"]
    author = (node.get("author") or {}).get("login") or "?"

    latest = _latest_reviews_by_author(node.get("reviews", {}).get("nodes", []))
    approvals = sorted(login for login, state in latest.items() if state == "APPROVED")
    changes = sorted(login for login, state in latest.items() if state == "CHANGES_REQUESTED")

    threads = node.get("reviewThreads", {}).get("nodes", [])
    unresolved = sum(1 for t in threads if not t.get("isResolved"))
    resolved = sum(1 for t in threads if t.get("isResolved"))
    my_total = my_unresolved = my_waiting = 0
    threads_by_others = 0
    for t in threads:
        first_author = _first_author(t)
        if first_author != me and first_author not in BOT_LOGINS:
            threads_by_others += 1
        if first_author != me:
            continue
        my_total += 1
        if not t.get("isResolved"):
            my_unresolved += 1
            last_author = _last_author(t)
            if last_author and last_author != me:
                my_waiting += 1

    comments = node.get("comments", {})
    comment_count = comments.get("totalCount", 0)
    comment_nodes = comments.get("nodes", [])
    last_commenter = None
    for c in reversed(comment_nodes):
        login = (c.get("author") or {}).get("login")
        if login and login not in BOT_LOGINS:
            last_commenter = login
            break

    ci = None
    commit_nodes = node.get("commits", {}).get("nodes", [])
    if commit_nodes:
        rollup = commit_nodes[0]["commit"].get("statusCheckRollup")
        if rollup:
            ci = rollup.get("state")

    return PrSnapshot(
        key=f"{repo}#{number}",
        number=number,
        title=node["title"],
        url=node["url"],
        repo=repo,
        author=author,
        is_draft=node.get("isDraft", False),
        state=node.get("state", "OPEN"),
        merged=node.get("merged", False),
        updated_at=node.get("updatedAt", ""),
        review_decision=node.get("reviewDecision"),
        mergeable=node.get("mergeable", "UNKNOWN"),
        approvals=approvals,
        changes_requested=changes,
        unresolved_threads=unresolved,
        resolved_threads=resolved,
        my_threads_total=my_total,
        my_threads_unresolved=my_unresolved,
        my_threads_waiting_on_me=my_waiting,
        threads_by_others=threads_by_others,
        comment_count=comment_count,
        last_commenter=last_commenter,
        ci=ci,
        my_review=latest.get(me),
        requested_for=_requested_for(node, me),
        bucket=bucket,
    )
