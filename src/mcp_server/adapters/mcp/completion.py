"""Audited completion for the table template and schema prompt."""

from fastmcp.exceptions import FastMCPError
from mcp_types import Completion, PromptReference, ResourceTemplateReference


def register_completion(mcp, services, identity):
    @mcp.completion
    async def complete(ref, argument, context):
        supported = (isinstance(ref, PromptReference) and ref.name == "explore_schema") or (
            isinstance(ref, ResourceTemplateReference) and ref.uri == "shop://tables/{table}"
        )
        if not supported or argument.name != "table":
            return Completion(values=[], has_more=False)
        result = await services.catalog.complete_tables(identity(), argument.value)
        if "error" in result:
            error = result["error"]
            raise FastMCPError(f"{error['category']}: {error['message']}")
        return Completion(**result["data"])
