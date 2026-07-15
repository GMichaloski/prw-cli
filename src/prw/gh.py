"""Thin wrapper around the `gh` CLI. All GitHub access goes through here."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

RATE_LIMIT_FALLBACK_SECONDS = 900  # used if GitHub didn't give us a reset time


class GhError(RuntimeError):
    """Raised when a gh invocation fails."""


class RateLimitError(GhError):
    """Raised when GitHub reports the API rate limit was exceeded."""

    def __init__(self, message: str, reset_at: str | None = None):
        super().__init__(message)
        self.reset_at = reset_at


# Rate-limit info from the most recent successful GraphQL call: {remaining, resetAt}.
last_rate_limit: dict | None = None


def seconds_until_reset(reset_at: str | None) -> int:
    """Seconds from now until an ISO-8601 reset timestamp (0 if past; fallback if unknown)."""
    if not reset_at:
        return RATE_LIMIT_FALLBACK_SECONDS
    try:
        reset = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    except ValueError:
        return RATE_LIMIT_FALLBACK_SECONDS
    return max(0, int((reset - datetime.now(timezone.utc)).total_seconds()))


def _label(args: list[str]) -> str:
    """A concise command label for error messages (never dumps a GraphQL query body)."""
    if args[:2] == ["api", "graphql"]:
        return "gh api graphql"
    return "gh " + " ".join(args)


def _run(args: list[str], timeout: int = 30) -> str:
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GhError("gh CLI not found on PATH. Install GitHub CLI and run `gh auth login`.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"{_label(args)} timed out after {timeout}s") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if "rate limit" in stderr.lower():
            reset_at = last_rate_limit.get("resetAt") if last_rate_limit else None
            raise RateLimitError("GitHub API rate limit exceeded", reset_at)
        raise GhError(f"{_label(args)} failed ({proc.returncode}): {stderr}")
    return proc.stdout


def current_login() -> str:
    """Return the login of the authenticated gh user."""
    return _run(["api", "user", "--jq", ".login"]).strip()


def graphql(query: str, variables: dict[str, object]) -> dict:
    """Run a GraphQL query via `gh api graphql` and return the parsed `data` object.

    String variables are passed with -f; ints/bools with -F so gh sends them typed.
    """
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, bool):
            args += ["-F", f"{key}={str(value).lower()}"]
        elif isinstance(value, int):
            args += ["-F", f"{key}={value}"]
        else:
            args += ["-f", f"{key}={value}"]
    raw = _run(args)
    payload = json.loads(raw)
    if "errors" in payload:
        raise GhError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def search_prs(search_query: str, limit: int = 30) -> list[dict]:
    """Search PRs and return the raw node dicts for the given search filter."""
    global last_rate_limit
    data = graphql(SEARCH_QUERY, {"q": search_query, "first": limit})
    if "rateLimit" in data:
        last_rate_limit = data["rateLimit"]
    return data["search"]["nodes"]


# Imported lazily to avoid a cycle; queries module holds only strings.
from .queries import SEARCH_QUERY  # noqa: E402
