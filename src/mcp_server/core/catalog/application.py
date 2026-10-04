import re

from mcp_server.core.access_control.application import canonical
from mcp_server.core.access_control.domain import Principal
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError

from .ports import CatalogDatabase


class Catalog:
    def __init__(self, database: CatalogDatabase, audit: Audit):
        self.database, self.audit = database, audit

    async def list_tables(self, principal: Principal) -> dict:
        return await self.audit.run(
            principal, "list_tables", {}, lambda _: self.database.list_tables()
        )

    async def describe_table(self, principal: Principal, table: str) -> dict:
        async def action(_):
            if not isinstance(table, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", table):
                raise GuardError(
                    Category.ARGUMENTS, "Supply an unqualified table name in the configured schema."
                )
            return await self.database.describe_table(table)

        return await self.audit.run(principal, "describe_table", {"table": table}, action)

    async def read_table(self, principal: Principal, table: str) -> dict:
        async def action(_):
            if not isinstance(table, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", table):
                raise GuardError(Category.ARGUMENTS, "Supply an unqualified shop table name.")
            result = await self.database.describe_table(table)
            if result["truncated"]:
                raise GuardError(Category.LIMIT, "Table metadata exceeds the result limit.")
            payload = {
                "schema": "shop",
                "table": table,
                "columns": [dict(zip(result["columns"], row)) for row in result["rows"]],
            }
            if len(canonical(payload).encode()) > self.audit.limits.result_bytes:
                raise GuardError(Category.LIMIT, "Table metadata exceeds the byte limit.")
            return payload

        return await self.audit.run(
            principal,
            "read_table_resource",
            {"uri": f"shop://tables/{table}", "table": table},
            action,
        )

    async def complete_tables(self, principal: Principal, prefix: str) -> dict:
        async def action(_):
            if not isinstance(prefix, str) or (
                prefix and not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", prefix)
            ):
                raise GuardError(Category.ARGUMENTS, "Supply a shop table-name prefix.")
            result = await self.database.complete_tables(prefix)
            values = [row[0] for row in result["rows"]]
            return {"values": values[:100], "has_more": result["truncated"] or len(values) > 100}

        return await self.audit.run(principal, "complete_tables", {"prefix": prefix}, action)
