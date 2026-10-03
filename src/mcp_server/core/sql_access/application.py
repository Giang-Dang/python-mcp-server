import time
from dataclasses import asdict

from mcp_server.core.access_control.application import Approver, obtain_approval, verify_approval
from mcp_server.core.access_control.domain import Principal
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError

from .domain import Limits
from .policy import authorize
from .ports import SQLDatabase, SQLParser


class SQLAccess:
    def __init__(
        self,
        parser: SQLParser,
        database: SQLDatabase,
        audit: Audit,
        limits: Limits,
        schema: str = "shop",
    ):
        self.parser, self.database, self.audit = parser, database, audit
        self.limits, self.schema = limits, schema

    async def run(
        self, principal: Principal, tool: str, sql: str, approver: Approver | None = None
    ) -> dict:
        async def action(operation_id: str) -> dict:
            analysis = authorize(self.parser.analyze(sql), tool, self.schema)
            # Execute exact approved input; normalization is for analysis only.
            role = "mcp_reader" if tool in ("query", "explain") else "mcp_writer"
            plan = await self.database.preview(sql, role)
            if plan["total_cost_estimate"] > self.limits.plan_cost:
                raise GuardError(
                    Category.LIMIT, "Planner cost estimate exceeds the configured ceiling."
                )
            if tool == "explain":
                return plan
            if tool == "query":
                principal.require_valid(time.time())
                return await self.database.query(sql)
            preview = {
                "sql": sql,
                "effects": f"Direct {analysis.kind}; triggers may cause additional changes.",
                "plan": plan,
                "limits": asdict(self.limits),
                "rollback_note": "The row cap counts direct rows only. Rollback does not restore sequence values.",
                "transaction_mode": "atomic",
            }
            approval = await obtain_approval(
                principal, operation_id, preview, approver, self.limits.approval_seconds
            )
            await self.audit.event(operation_id, "approval", asdict(approval))
            verify_approval(approval, principal, operation_id, preview)
            await self.audit.event(operation_id, "execution_intent")

            async def before_commit():
                principal.require_valid(time.time())
                await self.audit.event(operation_id, "commit_intent")

            return await self.database.mutate(sql, before_commit)

        return await self.audit.run(principal, tool, {"sql": sql}, action)
