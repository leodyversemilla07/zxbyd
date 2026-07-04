"""Rich terminal display utilities."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# Windows terminal cp1252 doesn't have the Peso sign (U+20B1), so use PHP suffix.
_PESO_SIGN = "PHP"


def _fmt_php(amount: float | int | None) -> str:
    """Format an amount with PHP currency label, safe for Windows terminal."""
    if amount is None:
        return "—"
    return f"{_PESO_SIGN} {amount:,.0f}"


def info(msg: str) -> None:
    """Print an info message."""
    console.print(f"[dim]info[/dim] {msg}")


def error(msg: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]error[/bold red] {msg}")


def warn(msg: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]warn[/bold yellow] {msg}")


def success(msg: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]ok[/bold green] {msg}")


def show_notices(notices: list[dict[str, Any]], query: str = "") -> None:
    """Display search results as a table."""
    if not notices:
        info("No results found.")
        return

    table = Table(
        title=f'Procurement Notices — "{query}"' if query else "Procurement Notices",
        show_lines=True,
    )
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Title", max_width=50)
    table.add_column("Agency", max_width=30)
    table.add_column("ABC", justify="right", style="green")
    table.add_column("Mode", max_width=15)
    table.add_column("Closing", no_wrap=True)

    for n in notices:
        abc = n.get("abc")
        abc_str = _fmt_php(abc)
        table.add_row(
            n.get("ref_no", "—"),
            n.get("title", "—"),
            n.get("agency", "—"),
            abc_str,
            n.get("mode", "—"),
            n.get("closing_date", "—"),
        )

    console.print(table)
    info(f"{len(notices)} result(s)")


def show_notice_detail(notice: dict[str, Any]) -> None:
    """Display full notice details."""
    title = notice.get("title", "Untitled")
    ref = notice.get("ref_no", "—")

    content = Text()
    for key in [
        "agency", "category", "abc", "mode",
        "area_of_delivery", "published_date", "closing_date",
        "description",
    ]:
        val = notice.get(key, "—")
        if key == "abc" and val and val != "—":
            val = _fmt_php(val)
        content.append(f"{key}: ", style="bold")
        content.append(f"{val}\n")

    console.print(Panel(content, title=f"[cyan]{ref}[/cyan] — {title}"))


def show_awards(
    awards: list[dict[str, Any]],
    agency: str | None = None,
    supplier: str | None = None,
) -> None:
    """Display awards as a table."""
    if not awards:
        info("No awards found.")
        return

    title_parts = ["Contract Awards"]
    if agency:
        title_parts.append(f"Agency={agency}")
    if supplier:
        title_parts.append(f"Supplier={supplier}")

    table = Table(title=" — ".join(title_parts), show_lines=True)
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Title", max_width=40)
    table.add_column("Agency", max_width=25)
    table.add_column("Supplier", max_width=25)
    table.add_column("Amount", justify="right", style="green")
    table.add_column("Date", no_wrap=True)

    for a in awards:
        amount = a.get("amount")
        amt_str = _fmt_php(amount)
        table.add_row(
            a.get("ref_no", "—"),
            a.get("title", "—"),
            a.get("agency", "—"),
            a.get("supplier", "—"),
            amt_str,
            a.get("award_date", "—"),
        )

    console.print(table)
    info(f"{len(awards)} award(s)")


def show_supplier_stats(stats: dict[str, Any], name: str) -> None:
    """Display supplier profile."""
    if not stats:
        info(f"No data for supplier: {name}")
        return

    content = Text()
    for key, label in [
        ("total_awards", "Total Awards"),
        ("total_amount", "Total Amount"),
        ("avg_amount", "Avg Award"),
        ("agency_count", "Agencies Served"),
    ]:
        val = stats.get(key, "—")
        if "amount" in key and val and val != "—":
            val = _fmt_php(val)
        content.append(f"{label}: ", style="bold")
        content.append(f"{val}\n")

    console.print(Panel(content, title=f"[cyan]Supplier[/cyan] — {name}"))


def show_agency_stats(stats: dict[str, Any], name: str) -> None:
    """Display agency profile."""
    if not stats:
        info(f"No data for agency: {name}")
        return

    content = Text()
    for key, label in [
        ("total_awards", "Total Awards"),
        ("total_amount", "Total Amount"),
        ("avg_amount", "Avg Award"),
        ("supplier_count", "Unique Suppliers"),
    ]:
        val = stats.get(key, "—")
        if "amount" in key and val and val != "—":
            val = _fmt_php(val)
        content.append(f"{label}: ", style="bold")
        content.append(f"{val}\n")

    console.print(Panel(content, title=f"[cyan]Agency[/cyan] — {name}"))


# ── OCDS-aware display ────────────────────────────────────────────

def show_releases(releases: list, query: str = "") -> None:
    """Display OCDS Release search results as a table.

    Accepts either Release model instances or their dump dicts.
    """
    if not releases:
        info("No releases found.")
        return

    # Normalize to dicts
    rows = []
    for r in releases:
        if hasattr(r, "model_dump_simple"):
            rows.append(r.model_dump_simple())
        elif hasattr(r, "get"):
            rows.append(r)
        else:
            rows.append(r)

    table = Table(
        title=f'OCDS Releases — "{query}"' if query else "OCDS Releases",
        show_lines=True,
    )
    table.add_column("OCID", style="cyan", no_wrap=True)
    table.add_column("Ref #", style="dim", no_wrap=True)
    table.add_column("Title", max_width=45)
    table.add_column("Agency", max_width=25)
    table.add_column("ABC", justify="right", style="green")
    table.add_column("Status", max_width=12)

    for r in rows:
        abc = r.get("abc")
        abc_str = _fmt_php(abc)
        ocid = r.get("ocid", "")
        ref = ocid.split("-")[-1] if "-" in ocid else r.get("ref_no", "—")
        if not ocid:
            ref = r.get("ref_no", "—")
        table.add_row(
            ocid or "—",
            ref,
            (r.get("title", "") or "—")[:45],
            (r.get("agency", "") or "—")[:25],
            abc_str,
            r.get("status", "") or "—",
        )

    console.print(table)
    info(f"{len(rows)} release(s)")


def show_release_detail(release) -> None:
    """Display full OCDS Release details."""
    if hasattr(release, "model_dump_simple"):
        data = release.model_dump_simple()
    elif hasattr(release, "get"):
        data = release
    else:
        data = {}

    title = data.get("title", "Untitled")
    ref = data.get("ref_no", data.get("ocid", "—"))

    content = Text()
    for key in [
        "ocid", "agency", "category", "abc", "mode",
        "area_of_delivery", "published_date", "closing_date",
        "description", "status", "solicitation_number",
    ]:
        val = data.get(key, "—")
        if key == "abc" and val and val != "—":
            val = _fmt_php(val)
        content.append(f"{key}: ", style="bold")
        content.append(f"{val}\n")

    console.print(Panel(content, title=f"[cyan]{ref}[/cyan] — {title}"))
