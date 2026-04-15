"""zxbyd CLI entrypoint."""

from __future__ import annotations

import typer

from zxbyd import __version__

app = typer.Typer(
    name="zxbyd",
    help="Probe Philippine government procurement.",
    no_args_is_help=False,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        is_eager=True,
    ),
) -> None:
    """zxbyd — Probe Philippine government procurement.

    Search procurement notices, track contract awards, and detect suspicious
    patterns. Data sourced from PhilGEPS (Philippine Government Electronic
    Procurement System).
    """
    if version:
        typer.echo(f"zxbyd {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        typer.echo("zxbyd — Probe Philippine government procurement.")
        typer.echo(f"Version {__version__}")
        typer.echo()
        typer.echo("Run 'zxbyd --help' for available commands.")


# ── Register command groups ──────────────────────────────────────────

from zxbyd.commands.search import search_app
from zxbyd.commands.detail import detail_app
from zxbyd.commands.awards import awards_app
from zxbyd.commands.profiles import profiles_app
from zxbyd.commands.analysis import analysis_app

app.add_typer(search_app, name="search", help="Search procurement notices.")
app.add_typer(detail_app, name="detail", help="Fetch notice details.")
app.add_typer(awards_app, name="awards", help="List contract awards.")
app.add_typer(profiles_app, name="profile", help="Agency and supplier profiles.")
app.add_typer(analysis_app, name="analysis", help="Anomaly detection and probing.")
