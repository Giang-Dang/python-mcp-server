import time
from dataclasses import asdict

from mcp_server.core.access_control.application import Approver, obtain_approval, verify_approval
from mcp_server.core.access_control.domain import Principal
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError
from mcp_server.core.sql_access.domain import Limits

from .domain import Procedure
from .ports import ProcedureDatabase


class Procedures:
    def __init__(
        self,
        registry: dict[str, Procedure],
        database: ProcedureDatabase,
        audit: Audit,
        limits: Limits,
    ):
        self.registry, self.database, self.audit, self.limits = registry, database, audit, limits

    async def list(self, principal: Principal) -> dict:
        async def action(_):
            return [entry.public() for entry in self.registry.values()]

        return await self.audit.run(principal, "list_procedures", {}, action)

    async def call(
        self, principal: Principal, name: str, arguments: dict, approver: Approver
    ) -> dict:
        async def action(operation_id):
            entry = self.registry.get(name)
            if entry is None:
                raise GuardError(Category.ARGUMENTS, "Unknown registered procedure.")
            bound = entry.bind(arguments)
            entry.check_definition(await self.database.definition_hash(entry))
            preview = {
                "name": name,
                "arguments": bound,
                "definition_hash": entry.definition_hash,
                "registry_fingerprint": entry.fingerprint,
                "effects": entry.effects,
                "timeout_seconds": min(entry.timeout_seconds, self.limits.procedure_seconds),
                "transaction_mode": entry.transaction_mode,
                "partial_commits": entry.transaction_mode == "autocommit_batches",
                "estimate": "No non-executing procedure row estimate is available.",
                "limits": asdict(self.limits),
                "row_cap": "Ordinary DML cap does not apply to reviewed procedures.",
            }
            approval = await obtain_approval(
                principal, operation_id, preview, approver, self.limits.approval_seconds
            )
            await self.audit.event(operation_id, "approval", asdict(approval))
            verify_approval(approval, principal, operation_id, preview)
            if entry.fingerprint != self.registry[name].fingerprint:
                raise GuardError(Category.REGISTRY, "Registry changed during approval.")
            entry.check_definition(await self.database.definition_hash(entry))
            await self.audit.event(
                operation_id,
                "execution_intent",
                {
                    "definition_hash": entry.definition_hash,
                    "transaction_mode": entry.transaction_mode,
                },
            )

            async def before_commit():
                principal.require_valid(time.time())
                await self.audit.event(
                    operation_id,
                    "commit_intent",
                    {"internal_commits": entry.transaction_mode == "autocommit_batches"},
                )

            return await self.database.call(entry, bound, before_commit)

        return await self.audit.run(
            principal, "call_procedure", {"name": name, "args": arguments}, action
        )
