"""Composition and lifecycle. Importing does not read secrets or open connections."""

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import FastMCP

from mcp_server.adapters.identity.auth0 import current_principal, make_auth
from mcp_server.adapters.mcp.tools import register_tools
from mcp_server.adapters.postgres.audit import PostgresAudit
from mcp_server.adapters.postgres.database import Database
from mcp_server.adapters.postgres.engines import make_engine
from mcp_server.adapters.registry.yaml_registry import load_registry
from mcp_server.adapters.sql_parser.sqlglot import Parser
from mcp_server.core.auditing.application import Audit
from mcp_server.core.catalog.application import Catalog
from mcp_server.core.diagnostics.application import Diagnostics
from mcp_server.core.procedures.application import Procedures
from mcp_server.core.sql_access.application import SQLAccess
from mcp_server.settings import Settings


@dataclass
class Services:
    catalog: Catalog
    sql: SQLAccess
    procedures: Procedures
    diagnostics: Diagnostics
    database: Database
    audit_engine: object

    async def close(self):
        await self.database.close()
        await self.audit_engine.dispose()


def build_services(settings: Settings) -> Services:
    registry = load_registry(settings.registry_path)
    engines = {
        role: make_engine(settings, role)
        for role in ("mcp_reader", "mcp_writer", "mcp_proc_exec", "mcp_monitor")
    }
    database = Database(engines, make_engine(settings, "mcp_writer", dedicated=True), settings)
    audit_engine = make_engine(settings, "mcp_audit_runtime")
    audit = Audit(PostgresAudit(audit_engine), settings.limits)
    return Services(
        Catalog(database, audit),
        SQLAccess(Parser(), database, audit, settings.limits, settings.schema_name),
        Procedures(registry, database, audit, settings.limits),
        Diagnostics(database, audit),
        database,
        audit_engine,
    )


def create_server(settings: Settings | None = None, *, auth=None, services=None, identity=None):
    settings = settings or Settings()
    auth = auth if auth is not None else make_auth(settings)
    services = services if services is not None else build_services(settings)

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield {}
        finally:
            await services.close()

    mcp = FastMCP(
        "shop-db",
        auth=auth,
        lifespan=lifespan,
        tasks=False,
        instructions="Authenticated guarded SQL. Mutations require human approval. Never retry uncertain outcomes.",
        mask_error_details=True,
    )
    register_tools(mcp, services, identity or current_principal)
    return mcp
