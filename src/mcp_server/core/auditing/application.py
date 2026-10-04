import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Protocol
from uuid import uuid4

from mcp_server.core.access_control.application import canonical
from mcp_server.core.access_control.domain import Principal
from mcp_server.core.errors import Category, GuardError
from mcp_server.core.sql_access.domain import Limits

from .domain import Operation


class AuditStore(Protocol):
    async def start(self, operation: Operation) -> None: ...
    async def event(self, operation_id: str, kind: str, detail: dict) -> None: ...


class Audit:
    def __init__(self, store: AuditStore, limits: Limits):
        self.store, self.limits = store, limits

    async def event(self, operation_id: str, kind: str, detail: dict | None = None) -> None:
        try:
            await self.store.event(operation_id, kind, detail or {})
        except Exception:  # noqa: BLE001 - convert adapter failures without importing driver types
            raise GuardError(Category.AUDIT, "Audit event could not be persisted.") from None

    async def run(
        self,
        principal: Principal,
        tool: str,
        inputs: dict,
        action: Callable[[str], Awaitable[dict | list]],
        *,
        operation_id: str | None = None,
    ) -> dict:
        resuming = operation_id is not None
        operation_id = operation_id or str(uuid4())
        started = resuming
        result = None
        try:
            principal.require_valid(time.time())
            try:
                size = len(canonical(inputs).encode("utf-8"))
            except (TypeError, ValueError, RecursionError):
                raise GuardError(
                    Category.ARGUMENTS, "Request must contain finite JSON values."
                ) from None
            if size > self.limits.request_bytes:
                raise GuardError(Category.LIMIT, "Request exceeds the configured byte limit.")
            operation = Operation(operation_id, principal, tool, inputs, asdict(self.limits))
            if not resuming:
                try:
                    await self.store.start(operation)
                    started = True
                except Exception:  # noqa: BLE001 - fail closed for any audit adapter failure
                    raise GuardError(
                        Category.AUDIT, "Audit intent could not be persisted."
                    ) from None
            result = await action(operation_id)
            outcome = (
                result.get("outcome", "completed") if isinstance(result, dict) else "completed"
            )
            detail = {"outcome": outcome}
            if isinstance(result, dict):
                for key in (
                    "affected_rows",
                    "returned_rows",
                    "truncated",
                    "batch_count",
                    "max_batches",
                    "batch_size",
                ):
                    if key in result:
                        detail[key] = result[key]
            if outcome == "awaiting_approval":
                await self.event(operation_id, "awaiting_approval")
            else:
                await self.event(operation_id, "outcome", detail)
            return {
                "operation_id": operation_id,
                "outcome": outcome,
                "data": result,
                "audit_status": "recorded",
            }
        except asyncio.CancelledError:
            confirmed = isinstance(result, dict) and result.get("outcome") == "committed"
            if started:
                try:
                    await asyncio.shield(
                        self.event(
                            operation_id,
                            "cancelled",
                            {
                                "outcome": "committed" if confirmed else "cancelled",
                                "inspect_execution_events": True,
                            },
                        )
                    )
                except GuardError:
                    pass
            raise
        except Exception as exc:  # noqa: BLE001 - public error boundary must not expose driver secrets
            error = (
                exc
                if isinstance(exc, GuardError)
                else GuardError(Category.DATABASE, "Database operation failed.")
            )
            committed = isinstance(result, dict) and result.get("outcome") == "committed"
            outcome = "committed" if committed else error.outcome
            audit_status = (
                "unavailable"
                if error.category == Category.AUDIT
                else ("recorded" if started else "not_recorded")
            )
            if started:
                try:
                    await self.event(
                        operation_id, "error", {"category": error.category, "outcome": outcome}
                    )
                except GuardError:
                    audit_status = "unavailable"
            return {
                "operation_id": operation_id,
                "outcome": outcome,
                "audit_status": audit_status,
                "data": result if committed else None,
                "error": {"category": error.category, "message": str(error)},
                "retry_safe": outcome not in ("committed", "uncertain", "partially_completed"),
            }
