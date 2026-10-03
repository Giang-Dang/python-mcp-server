"""Verified identity and session ownership shared by every MCP surface."""

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from mcp_server.core.errors import GuardError


class IdentityMiddleware(Middleware):
    def __init__(self, identity):
        self.identity = identity

    async def on_request(self, context, call_next):
        try:
            principal = self.identity()
            if context.fastmcp_context is not None:
                ctx = context.fastmcp_context
                prior = await ctx.get_state("shopmcp_identity")
                identity = list(principal.identity)
                if prior is not None and prior != identity:
                    raise ToolError("authentication: session belongs to a different caller")
                await ctx.set_state("shopmcp_identity", identity)
        except GuardError as exc:
            raise ToolError(f"{exc.category}: {exc}") from None
        return await call_next(context)
