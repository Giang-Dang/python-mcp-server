"""Composition and lifecycle. Importing does not read secrets or open connections."""

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import FastMCP
from mcp.server.request_state import RequestStateSecurity

from mcp_server.adapters.identity.auth0 import current_principal, make_auth
from mcp_server.adapters.mcp.approval import ApprovalRounds
from mcp_server.adapters.mcp.completion import register_completion
from mcp_server.adapters.mcp.middleware import IdentityMiddleware
from mcp_server.adapters.mcp.prompts import register_prompts
from mcp_server.adapters.mcp.resources import register_resources
from mcp_server.adapters.mcp.skills import SkillsExtension
from mcp_server.adapters.mcp.tools import register_tools
from mcp_server.adapters.mcp.viewer import register_viewer
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
    rounds = ApprovalRounds()

    @asynccontextmanager
    async def lifespan(_):
        try:
            async with rounds.lifespan():
                yield {}
        finally:
            await services.close()

    mcp = FastMCP(
        "shop-db",
        auth=auth,
        lifespan=lifespan,
        tasks=False,
        list_page_size=settings.list_page_size,
        request_state_security=RequestStateSecurity.ephemeral(
            ttl=settings.approval_seconds, audience="shop-db"
        ),
        # No cache hints: SDK rejects TTL=0, and a scope without a positive TTL.
        instructions=(
            "Authenticated guarded SQL. Mutations require human approval. Never retry uncertain "
            "outcomes. Discover shop:// guidance resources and the explore_schema and "
            "investigate_slow_query prompts for schema and read-plan workflows."
        ),
        mask_error_details=True,
    )
    identity = identity or current_principal
    mcp.add_middleware(IdentityMiddleware(identity))
    register_tools(mcp, services, identity, rounds)
    register_resources(mcp, settings.limits, services, identity)
    register_prompts(mcp, settings.limits)
    register_viewer(mcp)
    register_completion(mcp, services, identity)
    skills = SkillsExtension(identity, settings.list_page_size)
    mcp.add_extension(skills)
    skills.register_files(mcp)
    return mcp
