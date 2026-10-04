"""HTTP serving, read-only registry inspection, and separately credentialed migrations."""

import json
import os

import typer

from mcp_server.runtime import run_async
from mcp_server.settings import ROOT, Settings

app = typer.Typer(no_args_is_help=True)
audit_app = typer.Typer(no_args_is_help=True)
app.add_typer(audit_app, name="audit")


@app.command()
def serve():
    """Serve authenticated HTTP on loopback. Requires .env.mcp Auth0 and runtime configuration."""
    from mcp_server.bootstrap import create_server

    if os.environ.get("SHOPMCP_MIGRATION_URL"):
        raise typer.BadParameter("Remove SHOPMCP_MIGRATION_URL before starting the runtime server.")
    settings = Settings()
    server = create_server(settings)
    run_async(
        server.run_http_async(
            transport="http",
            host=settings.host,
            port=settings.port,
            path="/mcp",
            stateless_http=True,
            host_origin_protection=True,
            allowed_hosts=[f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"],
            allowed_origins=["http://localhost:6274", "http://127.0.0.1:6274"],
        )
    )


@app.command("inspect-registry")
def inspect_registry():
    """Read live definitions and hashes. Never updates the reviewed YAML."""
    from mcp_server.adapters.postgres.database import Database
    from mcp_server.adapters.postgres.engines import make_engine
    from mcp_server.adapters.registry.yaml_registry import NAMES

    settings = Settings()

    async def run():
        engine = make_engine(settings, "mcp_reader")
        db = Database({"mcp_reader": engine}, engine, settings)
        try:
            return [r for r in await db.definitions() if r["name"] in NAMES]
        finally:
            await engine.dispose()

    typer.echo(json.dumps(run_async(run()), indent=2))


def audit_command(apply):
    from mcp_server.adapters.postgres.migrations import migrate

    url = os.environ.get("SHOPMCP_MIGRATION_URL")
    if not url:
        raise typer.BadParameter("Set SHOPMCP_MIGRATION_URL for the separate migration owner.")
    try:
        result = migrate(url, ROOT / "db/audit/migrations", apply)
    except Exception:  # noqa: BLE001 - never print migration credentials in a driver exception
        typer.echo(
            "Audit migration failed. Check owner credentials, database, and migration checksums.",
            err=True,
        )
        raise typer.Exit(1) from None
    typer.echo(json.dumps(result))


@audit_app.command("migrate")
def audit_migrate():
    """Apply pending audit migrations with the separate owner credential."""
    audit_command(True)


@audit_app.command("status")
def audit_status():
    """Read applied versions and pending files."""
    audit_command(False)


if __name__ == "__main__":
    app()
