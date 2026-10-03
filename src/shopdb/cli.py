"""Command line entry point: `poetry run shopdb ...`."""

from __future__ import annotations

import os

import typer

from .config import get_scale, get_settings

app = typer.Typer(help="Tools for the 'shop' test database.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Tools for the 'shop' test database."""


@app.command()
def version() -> None:
    """Print the package version (proves the environment works)."""
    from importlib.metadata import version as pkg_version

    typer.echo(pkg_version("python-mcp-server"))


@app.command("seed")
def seed_command(
    scale: str = typer.Option(
        None, "--scale", "-s", help="Size profile: S (default from .env) or M."
    ),
    seed: int = typer.Option(None, "--seed", help="Random seed. Same seed gives identical data."),
    workers: int = typer.Option(8, "--workers", "-w", help="Parallel loader processes."),
    force: bool = typer.Option(False, "--force", help="Truncate existing data first."),
    confirm_large: bool = typer.Option(
        False, "--confirm-large", help="Required for scale M (hours, 10-15 GB)."
    ),
) -> None:
    """Fill the database with generated data."""
    from .bootstrap import run_seed

    settings = get_settings()
    chosen = get_scale(scale or settings.shop_scale)
    if chosen.name == "M" and not confirm_large:
        typer.echo(
            "Scale M loads about 105 million rows (a 19 GB database) and took about 5 minutes with 12 workers on a 28-CPU machine. Re-run with --confirm-large if you mean it."
        )
        raise typer.Exit(2)
    try:
        run_seed(
            chosen,
            seed if seed is not None else settings.shop_seed,
            workers,
            force=force,
            settings=settings,
            log=typer.echo,
        )
    except RuntimeError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc


@app.command()
def verify(
    scale: str = typer.Option(None, "--scale", "-s", help="Profile the database was seeded with."),
    seed: int = typer.Option(None, "--seed", help="Seed the database was seeded with."),
) -> None:
    """Check row counts and data consistency against the model."""
    from .bootstrap import run_verify

    settings = get_settings()
    results = run_verify(
        get_scale(scale or settings.shop_scale), seed if seed is not None else settings.shop_seed
    )
    failed = 0
    for check in results:
        mark = "PASS" if check.ok else "FAIL"
        failed += not check.ok
        typer.echo(f"{mark}  {check.name}: {check.detail}")
    typer.echo(f"\n{len(results) - failed} passed, {failed} failed")
    if failed:
        raise typer.Exit(1)


@app.command("post-load")
def post_load_command(
    only: str = typer.Option(
        None, "--only", help="Apply only files whose name starts with this prefix, e.g. 100."
    ),
) -> None:
    """Apply db/post_load/*.sql (indexes, functions, triggers, procedures, statistics, grants) as shop_owner."""
    from .bootstrap import apply_post_load

    try:
        count = apply_post_load(only=only, log=typer.echo)
    except RuntimeError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"{count} file(s) applied")


@app.command()
def reset(yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation.")) -> None:
    """Delete ALL data (tables stay) and restart identity sequences."""
    from .db import connect
    from .loader import truncate_all

    if not yes and not typer.confirm("This deletes every row in the shop database. Continue?"):
        raise typer.Abort()
    with connect("loader") as conn:
        truncate_all(conn)
    typer.echo("All tables truncated.")


@app.command("docs")
def docs_command(
    out: str = typer.Option("docs", "--out", help="Folder for data-dictionary.md and erd.md."),
) -> None:
    """Regenerate docs/data-dictionary.md and docs/erd.md from the live database catalog."""
    from pathlib import Path

    from .bootstrap import generate

    for path in generate(Path(out)):
        typer.echo(f"wrote {path}")


if __name__ == "__main__":
    # Needed on Windows: worker processes re-import this module.
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    app()
