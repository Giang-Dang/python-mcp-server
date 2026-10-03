"""Register only the three reviewed documentation resources."""

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from mcp_server.core.errors import GuardError
from mcp_server.core.guidance.resources import (
    render_relationships_guide,
    render_schema_guide,
    render_sql_policy,
)
from mcp_server.core.sql_access.domain import Limits


def register_resources(mcp: FastMCP, limits: Limits) -> None:
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
