"""Fetch and parse PR snapshots for each configured bucket via gh."""

from __future__ import annotations

from . import gh, queries
from .config import Config
from .model import PrSnapshot, parse_pr


def fetch_snapshots(config: Config, me: str) -> list[PrSnapshot]:
    """Return parsed snapshots across all enabled buckets, de-duplicated by key.

    A PR can appear in more than one search (e.g. authored by me and I'm also a
    reviewer); the first occurrence wins, with priority mine > review > team.

    The review bucket unions two searches so PRs stay visible after I review them:
      - review-requested:@me  -> still awaiting my review (review_requested=True)
      - reviewed-by:@me       -> I already reviewed, still open (review_requested=False)
    A PR in both is treated as requested (a re-review was asked for).
    """
    by_key: dict[str, PrSnapshot] = {}

    def add(node: dict, bucket: str, requested: bool = False) -> None:
        snap = parse_pr(node, bucket, me)
        snap.review_requested = requested
        by_key.setdefault(snap.key, snap)

    for node in gh.search_prs(queries.mine_filter()):
        add(node, "mine")

    for node in gh.search_prs(queries.review_requested_filter()):
        add(node, "review", requested=True)
    for node in gh.search_prs(queries.reviewed_by_filter()):
        add(node, "review", requested=False)

    if config.include_team and config.team_members:
        for node in gh.search_prs(queries.team_filter(config.team_members)):
            add(node, "team")

    return list(by_key.values())
