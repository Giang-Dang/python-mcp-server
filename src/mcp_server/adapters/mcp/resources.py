"""Reviewed documentation and bounded live table metadata."""

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources.base import ResourceContent, ResourceResult

from mcp_server.core.access_control.application import canonical
from mcp_server.core.errors import GuardError
from mcp_server.core.guidance.resources import (
    render_relationships_guide,
    render_schema_guide,
    render_sql_policy,
)
from mcp_server.core.sql_access.domain import Limits


def register_resources(mcp: FastMCP, limits: Limits, services, identity) -> None:
    @mcp.resource(
        "shop://tables/{table}",
        name="table_metadata",
        description="Live column metadata for one unqualified shop table; no table rows.",
        mime_type="application/json",
    )
    async def table_metadata(table: str) -> ResourceResult:
        result = await services.catalog.read_table(identity(), table)
        if "error" in result:
            error = result["error"]
            raise ResourceError(f"{error['category']}: {error['message']}")
        return ResourceResult(
            contents=[ResourceContent(canonical(result["data"]), mime_type="application/json")],
            meta={"operation_id": result["operation_id"]},
        )

    @mcp.resource(
        "shop://guide/schema",
        name="schema_guide",
        description="Shipped shop domain overview and live catalog inspection instructions.",
        mime_type="text/markdown",
    )
    def schema_guide() -> str:
        try:
            return render_schema_guide()
        except GuardError as exc:
            raise ResourceError(f"{exc.category}: {exc}") from None

    @mcp.resource(
        "shop://guide/relationships",
        name="relationships_guide",
        description="Selected curated join keys, cardinality cautions and fixture limitations.",
        mime_type="text/markdown",
    )
    def relationships_guide() -> str:
        try:
            return render_relationships_guide()
        except GuardError as exc:
            raise ResourceError(f"{exc.category}: {exc}") from None

    @mcp.resource(
        "shop://policy/sql",
        name="sql_policy",
        description="Guarded SQL workflows, human approval rules and this instance's SQL limits.",
        mime_type="text/markdown",
    )
    def sql_policy() -> str:
        try:
            return render_sql_policy(limits)
        except GuardError as exc:
            raise ResourceError(f"{exc.category}: {exc}") from None
