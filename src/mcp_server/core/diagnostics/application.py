from mcp_server.core.access_control.domain import Principal
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError

from .domain import KINDS
from .ports import DiagnosticsDatabase


class Diagnostics:
    def __init__(self, database: DiagnosticsDatabase, audit: Audit):
        self.database, self.audit = database, audit

    async def run(self, principal: Principal, kind: str) -> dict:
        async def action(_):
            if kind not in KINDS:
                raise GuardError(Category.ARGUMENTS, "Unknown diagnostic report.")
            return {**await self.database.diagnostics(kind), "kind": kind}

        return await self.audit.run(principal, "diagnostics", {"kind": kind}, action)
