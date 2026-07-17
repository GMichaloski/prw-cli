"""GraphQL query strings and per-bucket search filters."""

from __future__ import annotations

# Single query used for every bucket. Returns everything needed to compute both
# the dashboard status and the diff-based events.
#
# `first`/`last` values are kept low on purpose: GitHub's GraphQL rate limit is
# point-based and charges for the *requested* node count (first × first along the
# path), not the results — so oversized limits burn the hourly budget fast.
# `reviews(last: N)` (not first) keeps the most-recent review state per author.
SEARCH_QUERY = """
query($q: String!, $first: Int!) {
  rateLimit { cost remaining resetAt }
  search(query: $q, type: ISSUE, first: $first) {
    issueCount
    nodes {
      ... on PullRequest {
        number
        title
        url
        isDraft
        state
        merged
        updatedAt
        repository { nameWithOwner }
        author { login }
        reviewDecision
        mergeable
        reviews(last: 20) {
          nodes { author { login } state submittedAt }
        }
        reviewRequests(first: 20) {
          nodes {
            requestedReviewer {
              __typename
              ... on User { login }
              ... on Team { slug }
            }
          }
        }
        reviewThreads(first: 20) {
          totalCount
          nodes {
            isResolved
            isOutdated
            firstComment: comments(first: 1) { nodes { author { login } } }
            lastComment: comments(last: 1) { nodes { author { login } } }
          }
        }
        comments(last: 5) {
          totalCount
          nodes { author { login } }
        }
        commits(last: 1) {
          nodes { commit { statusCheckRollup { state } } }
        }
      }
    }
  }
}
"""


def mine_filter() -> str:
    return "is:open is:pr author:@me archived:false"


def review_requested_filter() -> str:
    return "is:open is:pr review-requested:@me archived:false"


def reviewed_by_filter() -> str:
    """PRs I already reviewed that are still open (so they don't vanish after review)."""
    return "is:open is:pr reviewed-by:@me archived:false"


def team_filter(members: list[str]) -> str:
    """PRs authored by teammates (excluding self is handled by the caller if needed)."""
    authors = " ".join(f"author:{login}" for login in members)
    return f"is:open is:pr archived:false {authors}".strip()
