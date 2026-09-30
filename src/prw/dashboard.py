"""Render the PR buckets as rich tables."""

from __future__ import annotations

from rich.console import Console, Group, RenderableType
from rich.table import Table
from rich.text import Text

from .model import PrSnapshot

_DECISION_STYLE = {
    "APPROVED": "[green]approved[/green]",
    "CHANGES_REQUESTED": "[red]changes req[/red]",
    "REVIEW_REQUIRED": "[yellow]needs review[/yellow]",
    None: "[dim]—[/dim]",
}

_CI_STYLE = {
    "SUCCESS": "[green]✓[/green]",
    "FAILURE": "[red]✗[/red]",
    "ERROR": "[red]✗[/red]",
    "PENDING": "[yellow]•[/yellow]",
    "EXPECTED": "[yellow]•[/yellow]",
    None: "[dim]—[/dim]",
}


def _decision(pr: PrSnapshot) -> str:
    return _DECISION_STYLE.get(pr.review_decision, str(pr.review_decision))


def _ci(pr: PrSnapshot) -> str:
    return _CI_STYLE.get(pr.ci, str(pr.ci))


def _threads(pr: PrSnapshot) -> str:
    if pr.unresolved_threads:
        return f"[red]{pr.unresolved_threads} open[/red]"
    return "[dim]0[/dim]"


def _my_comments(pr: PrSnapshot) -> str:
    """Status of the threads I started on a PR I'm reviewing — do I need to come back?"""
    if pr.my_threads_total == 0:
        return "[dim]—[/dim]"
    if pr.my_threads_unresolved == 0:
        return "[green]all resolved[/green]"
    if pr.my_threads_waiting_on_me:
        return f"[bold red]{pr.my_threads_unresolved} open · reply ↩[/bold red]"
    return f"[yellow]{pr.my_threads_unresolved} open[/yellow]"


def _pr_link(pr: PrSnapshot) -> Text:
    """The PR id, rendered as a terminal hyperlink so it opens the PR when clicked."""
    label = f"{pr.repo.split('/')[-1]}#{pr.number}"
    return Text(label, style=f"link {pr.url}")


def _title_cell(pr: PrSnapshot) -> str:
    prefix = "[dim](draft)[/dim] " if pr.is_draft else ""
    return f"{prefix}{pr.title}"


def _mine_table(prs: list[PrSnapshot]) -> Table:
    table = Table(title="My PRs", title_style="bold cyan", expand=True)
    table.add_column("PR", style="cyan", no_wrap=True)
    table.add_column("Title", no_wrap=True, overflow="ellipsis", ratio=1)
    table.add_column("Decision")
    table.add_column("Approvals")
    table.add_column("CI", justify="center")
    table.add_column("Threads")
    for pr in prs:
        approvals = ", ".join(f"@{a}" for a in pr.approvals) or "[dim]—[/dim]"
        table.add_row(_pr_link(pr), _title_cell(pr),
                      _decision(pr), approvals, _ci(pr), _threads(pr))
    return table


def _review_table(prs: list[PrSnapshot], title: str) -> Table:
    table = Table(title=title, title_style="bold magenta", expand=True)
    table.add_column("PR", style="magenta", no_wrap=True)
    table.add_column("Author", no_wrap=True)
    table.add_column("Title", no_wrap=True, overflow="ellipsis", ratio=1)
    table.add_column("My review")
    table.add_column("My comments")
    table.add_column("Threads")
    table.add_column("CI", justify="center")
    for pr in prs:
        table.add_row(_pr_link(pr), f"@{pr.author}", _title_cell(pr), _my_review(pr),
                      _my_comments(pr), _threads(pr), _ci(pr))
    return table


def _my_review(pr: PrSnapshot) -> str:
    """My standing on a PR I'm reviewing: pending, my submitted state, or re-review asked.

    Pending/re-review requests are tagged (you) for a direct request or (team) when the
    request reached me via a team — team requests are shown in a calmer color.
    """
    state_label = {
        "APPROVED": "[green]approved[/green]",
        "CHANGES_REQUESTED": "[red]changes req[/red]",
        "COMMENTED": "[yellow]commented[/yellow]",
    }.get(pr.my_review)

    if pr.review_requested:
        who = "team" if pr.requested_for == "team" else "you"
        color = "yellow" if who == "team" else "bold red"
        if state_label is None:
            return f"[{color}]pending ({who})[/{color}]"
        # Reviewed before, but a new review was requested.
        return f"[{color}]re-review ({who})[/{color}] [dim](was {pr.my_review.lower()})[/dim]"
    return state_label or "[dim]—[/dim]"


def build(snapshots: list[PrSnapshot], footer: str | None = None) -> RenderableType:
    """Compose the buckets into a single renderable (for one-shot or live rendering)."""
    parts: list[RenderableType] = []
    mine = [s for s in snapshots if s.bucket == "mine"]
    review = [s for s in snapshots if s.bucket == "review"]
    team = [s for s in snapshots if s.bucket == "team"]

    if mine:
        parts.append(_mine_table(sorted(mine, key=lambda p: p.updated_at, reverse=True)))
    if review:
        parts.append(_review_table(sorted(review, key=lambda p: p.updated_at, reverse=True),
                                    "To review"))
    if team:
        parts.append(_review_table(sorted(team, key=lambda p: p.updated_at, reverse=True), "Team"))
    if not snapshots:
        parts.append(Text("No open PRs found.", style="dim"))
    if footer:
        parts.append(Text(footer, style="dim"))
    return Group(*parts)


def render(console: Console, snapshots: list[PrSnapshot], footer: str | None = None) -> None:
    console.print(build(snapshots, footer))
