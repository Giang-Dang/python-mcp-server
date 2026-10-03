import re

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
            if not isinstance(table, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
                raise GuardError(
                    Category.ARGUMENTS, "Supply an unqualified table name in the configured schema."
                )
            return await self.database.describe_table(table)

        return await self.audit.run(principal, "describe_table", {"table": table}, action)
