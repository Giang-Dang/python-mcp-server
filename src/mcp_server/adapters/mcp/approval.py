"""Bounded process-local MRTR handles. SDK seals handles on the wire."""

import asyncio
import json
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from uuid import uuid4

from fastmcp.exceptions import ToolError
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
)

from mcp_server.core.access_control.application import canonical, fingerprint
from mcp_server.core.access_control.domain import Approval
from mcp_server.core.errors import GuardError


@dataclass
class Pending:
    identity: tuple[str, str]
    tool: str
    inputs: dict
    expires_at: float
    size: int
    operation_id: str = ""
    preview: dict | None = None
    state: str = "preparing"
    result: dict | None = None
    audit: object = None
    discard_on_finish: bool = False


class ApprovalRounds:
    def __init__(self, *, max_operations=128, max_bytes=16 * 1024 * 1024):
        self.entries: dict[str, Pending] = {}
        self.lock = asyncio.Lock()
        self.max_operations, self.max_bytes = max_operations, max_bytes

    async def cleanup(self):
        # Caller holds lock. Audit expiration before discarding a waiting operation.
        for handle, entry in list(self.entries.items()):
            if entry.expires_at <= time.time() and entry.state in (
                "waiting",
                "completed",
                "uncertain",
            ):
                if entry.state == "waiting":
                    try:
                        await entry.audit.event(
                            entry.operation_id,
                            "outcome",
                            {"outcome": "cancelled", "reason": "approval_expired"},
                        )
                    except GuardError:
                        # Preserve a fail-closed tombstone until an audit retry succeeds.
                        continue
                del self.entries[handle]

    @asynccontextmanager
    async def lifespan(self):
        async def sweep():
            while True:
                await asyncio.sleep(5)
                async with self.lock:
                    await self.cleanup()

        worker = asyncio.create_task(sweep())
        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            async with self.lock:
                for entry in self.entries.values():
                    if entry.state == "waiting":
                        entry.expires_at = min(entry.expires_at, time.time())
                await self.cleanup()

    async def run(self, ctx, principal, tool, inputs, service):
        principal.require_valid(time.time())
        state = ctx.request_state
        if state is None:
            if ctx.input_responses is not None:
                raise ToolError("policy_rejection: approval requires its original requestState")
            try:
                size = len(canonical(inputs).encode())
            except (TypeError, ValueError, RecursionError):
                raise ToolError("invalid_arguments: finite JSON inputs are required") from None
            if size > service.limits.request_bytes:
                raise ToolError("limits: request exceeds configured bytes")
            # Reserve the worst bounded preview while DB preparation is in flight.
            reservation = 2 * size + service.limits.result_bytes + 4096
            async with self.lock:
                await self.cleanup()
                if (
                    len(self.entries) >= self.max_operations
                    or sum(e.size for e in self.entries.values()) + reservation > self.max_bytes
                ):
                    raise ToolError("limits: approval capacity is full")
                handle = str(uuid4())
                entry = Pending(
                    principal.identity,
                    tool,
                    json.loads(canonical(inputs)),
                    min(time.time() + service.limits.approval_seconds, principal.expires_at),
                    reservation,
                    audit=service.audit,
                )
                self.entries[handle] = entry
            try:
                prepared = await service.prepare(principal, **inputs)
                if "error" in prepared:
                    async with self.lock:
                        self.entries.pop(handle, None)
                    return prepared
                entry.operation_id = prepared["operation_id"]
                entry.preview = json.loads(canonical(prepared["data"]["preview"]))
                extra = len(canonical(entry.preview).encode())
                async with self.lock:
                    if (
                        sum(e.size for e in self.entries.values()) - entry.size + size + extra
                        > self.max_bytes
                    ):
                        # Finalize this audited attempt through the same rejection path.
                        decision = "unavailable"
                        entry.discard_on_finish = True
                    else:
                        entry.size = size + extra
                        decision = None
                    entry.state = "waiting"
                caps = (ctx.request_context.meta or {}).get(CLIENT_CAPABILITIES_META_KEY, {})
                elicitation = caps.get("elicitation") if isinstance(caps, dict) else None
                if not isinstance(elicitation, dict) or "form" not in elicitation:
                    decision = "unavailable"
                if entry.expires_at <= time.time():
                    decision = "expired"
                if decision:
                    return await self.finish(handle, entry, principal, service, decision)
                message = canonical(
                    {
                        "operation_id": entry.operation_id,
                        "preview": entry.preview,
                        "expires_at": entry.expires_at,
                    }
                )
                return InputRequiredResult(
                    input_requests={
                        "approval": ElicitRequest(
                            params=ElicitRequestFormParams(
                                message=message,
                                requested_schema={
                                    "type": "object",
                                    "properties": {
                                        "approve": {
                                            "type": "boolean",
                                            "title": "Approve this exact mutation",
                                            "default": False,
                                        }
                                    },
                                    "required": ["approve"],
                                },
                            )
                        )
                    },
                    request_state=handle,
                )
            except BaseException:
                async with self.lock:
                    # Never turn a possibly consumed operation back into a waiting one.
                    if entry.state == "preparing":
                        self.entries.pop(handle, None)
                raise

        async with self.lock:
            entry = self.entries.get(state)
            if (
                entry is None
                or entry.identity != principal.identity
                or entry.tool != tool
                or fingerprint(entry.inputs) != fingerprint(inputs)
            ):
                raise ToolError(
                    "policy_rejection: approval handle does not match caller or request"
                )
            if entry.state == "completed":
                if entry.expires_at <= time.time() or entry.result is None:
                    raise ToolError(
                        "policy_rejection: approval result expired; inspect audit before retry"
                    )
                return json.loads(canonical(entry.result))
            if entry.state != "waiting":
                raise ToolError(
                    "uncertain_completion: operation already claimed; inspect audit, do not retry"
                )
            entry.state = "executing"
        answer = (ctx.input_responses or {}).get("approval")
        if isinstance(answer, ElicitResult):
            decision = (
                "approved"
                if answer.action == "accept" and (answer.content or {}).get("approve") is True
                else ("declined" if answer.action in ("accept", "decline") else "cancelled")
            )
        else:
            decision = "unavailable"
        if entry.expires_at <= time.time():
            decision = "expired"
        return await self.finish(state, entry, principal, service, decision)

    async def finish(self, handle, entry, principal, service, decision):
        try:
            # Claim before execution; cancellation anywhere leaves a non-retryable tombstone.
            async with self.lock:
                entry.state = "executing"
            approval = Approval(
                entry.operation_id,
                entry.identity,
                fingerprint(entry.preview),
                entry.expires_at,
                decision,
            )
            result = await service.resume(
                principal, **entry.inputs, preview=entry.preview, approval=approval
            )
            result_size = len(canonical(result).encode())
            async with self.lock:
                if entry.discard_on_finish:
                    self.entries.pop(handle, None)
                    return result
                if sum(e.size for e in self.entries.values()) + result_size <= self.max_bytes:
                    entry.result = json.loads(canonical(result))
                    entry.size += result_size
                entry.state = "completed"
            return result
        except BaseException:
            # No await: a second cancellation must not strand an executing entry forever.
            entry.state = "uncertain"
            raise
