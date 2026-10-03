"""Command line entry point: `poetry run shopdb ...`.

Only a version command exists for now; seed/verify/reset/docs arrive in later steps.
"""

import typer

app = typer.Typer(help="Tools for the 'shop' test database.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Tools for the 'shop' test database.

    This callback makes Typer treat the app as a group of subcommands even while only
    one command exists. Without it, `shopdb version` would be rejected.
    """


@app.command()
def version() -> None:
    """Print the package version (proves the environment works)."""
    from importlib.metadata import version as pkg_version

    typer.echo(pkg_version("python-mcp-server"))


if __name__ == "__main__":
    app()
