from fastmcp import Context
from mcp_types import ToolAnnotations

from mcp_server.adapters.identity.auth0 import current_principal

READ = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)


class ElicitationApprover:
    def __init__(self, context: Context):
        self.context = context

    async def request(self, message: str) -> str:
        try:
            result = await self.context.elicit(message, response_type=bool)
        except Exception:  # noqa: BLE001 - any unavailable or malformed elicitation fails closed
            return "unavailable"
        if result.action == "accept":
            return "approved" if result.data is True else "declined"
        return "declined" if result.action == "decline" else "cancelled"


def register_tools(mcp, services, identity=current_principal):
    @mcp.tool(annotations=READ)
    async def ping() -> str:
        """Authenticated liveness; independent of shop and audit availability."""
        identity()
        return "pong"

    @mcp.tool(annotations=READ)
    async def list_tables() -> dict:
        """List shop tables with planner estimates and comments; data preserves table-list fields."""
        return await services.catalog.list_tables(identity())

    @mcp.tool(annotations=READ)
    async def describe_table(table: str) -> dict:
        """Describe columns of one unqualified table name in the configured shop schema."""
        return await services.catalog.describe_table(identity(), table)

    @mcp.tool(annotations=READ)
    async def query(sql: str) -> dict:
        """Run one permitted read statement with row, byte, timeout, and estimated-cost limits."""
        return await services.sql.run(identity(), "query", sql)

    @mcp.tool(annotations=WRITE)
    async def execute(sql: str, ctx: Context) -> dict:
        """Preview one targeted INSERT, UPDATE, or DELETE and ask the human before execution."""
        return await services.sql.run(identity(), "execute", sql, ElicitationApprover(ctx))

    @mcp.tool(annotations=READ)
    async def explain(sql: str) -> dict:
        """Return a non-ANALYZE plan for permitted read SQL. Costs and rows are estimates."""
        return await services.sql.run(identity(), "explain", sql)

    @mcp.tool(annotations=READ)
    async def list_procedures() -> dict:
        """List reviewed signatures, arguments, declared effects, and limits."""
        return await services.procedures.list(identity())

    @mcp.tool(annotations=WRITE)
    async def call_procedure(name: str, args: dict, ctx: Context) -> dict:
        """Validate a registered procedure, verify its definition, and request human approval."""
        return await services.procedures.call(identity(), name, args, ElicitationApprover(ctx))

    @mcp.tool(annotations=READ)
    async def diagnostics(kind: str) -> dict:
        """Fixed report: query_statistics, locks, table_sizes, or table_health."""
        return await services.diagnostics.run(identity(), kind)
