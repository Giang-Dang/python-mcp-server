"""Modern-only requests and verified identity on every MCP surface."""

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from mcp_server.core.errors import GuardError


class IdentityMiddleware(Middleware):
    def __init__(self, identity):
        self.identity = identity

    async def on_request(self, context, call_next):
        if context.method == "initialize":
            raise ToolError("invalid_arguments: use MCP 2026-07-28 without initialize")
        try:
            self.identity()
            ctx = context.fastmcp_context
            if ctx is not None and ctx.request_context.protocol_version != "2026-07-28":
                raise ToolError("invalid_arguments: only MCP 2026-07-28 is supported")
        except GuardError as exc:
            raise ToolError(f"{exc.category}: {exc}") from None
        result = await call_next(context)
        if context.method == "server/discover":
            return result.model_copy(update={"supported_versions": ["2026-07-28"]})
        return result
