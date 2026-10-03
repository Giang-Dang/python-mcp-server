"""FastMCP prompt definitions, with framework-free rendering in Core."""

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import PromptError
from fastmcp.prompts import PromptResult
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp_types import GetPromptRequestParams
from pydantic import Field

from mcp_server.core.errors import GuardError
from mcp_server.core.guidance.prompts import render_explore_schema, render_investigate_slow_query
from mcp_server.core.sql_access.domain import Limits


class PromptArgumentsMiddleware(Middleware):
    """Keep expected input errors useful before FastMCP's masked validation."""

    async def on_get_prompt(
        self,
        context: MiddlewareContext[GetPromptRequestParams],
        call_next: CallNext[GetPromptRequestParams, PromptResult],
    ) -> PromptResult:
        request = context.message
        arguments = request.arguments or {}
        expected = {"explore_schema": "table", "investigate_slow_query": "sql"}.get(request.name)
        if expected is not None:
            if set(arguments) - {expected}:
                raise PromptError("invalid_arguments: unsupported prompt arguments.")
            if request.name == "investigate_slow_query" and "sql" not in arguments:
                raise PromptError("invalid_arguments: sql is required.")
            if expected in arguments and not isinstance(arguments[expected], str):
                raise PromptError(f"invalid_arguments: {expected} must be text.")
        return await call_next(context)


def register_prompts(mcp: FastMCP, limits: Limits) -> None:
    mcp.add_middleware(PromptArgumentsMiddleware())

    @mcp.prompt(name="explore_schema")
    def explore_schema(
        table: Annotated[
            str,
            Field(description="Optional unqualified ASCII table name; empty explores the schema."),
        ] = "",
    ) -> str:
        """Explore shop domains and joins through curated guides and live catalog tools."""
        try:
            return render_explore_schema(table, limits)
        except GuardError as exc:
            raise PromptError(f"{exc.category}: {exc}") from None

    @mcp.prompt(name="investigate_slow_query")
    def investigate_slow_query(
        sql: Annotated[
            str, Field(description="Original nonempty SQL text to analyze as untrusted data.")
        ],
    ) -> str:
        """Investigate read SQL with a non-ANALYZE plan; suggest improvements for review."""
        try:
            return render_investigate_slow_query(sql, limits)
        except GuardError as exc:
            raise PromptError(f"{exc.category}: {exc}") from None
