import asyncio
import hashlib
import json
import time
from typing import Protocol

from mcp_server.core.errors import Category, GuardError

from .domain import Approval, Principal


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    )


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Approver(Protocol):
    async def request(self, message: str) -> str: ...


async def obtain_approval(
    principal: Principal,
    operation_id: str,
    preview: dict,
    approver: Approver,
    seconds: float,
    clock=time.time,
) -> Approval:
    principal.require_valid(clock())
    expiry = min(clock() + seconds, principal.expires_at)
    digest = fingerprint(preview)
    message = canonical({"operation_id": operation_id, "preview": preview, "expires_at": expiry})
    try:
        async with asyncio.timeout(max(0, expiry - clock())):
            decision = await approver.request(message)
    except TimeoutError:
        decision = "expired"
    approval = Approval(operation_id, principal.identity, digest, expiry, decision)
    return approval


def verify_approval(
    approval: Approval, principal: Principal, operation_id: str, preview: dict, clock=time.time
) -> None:
    principal.require_valid(clock())
    if approval.decision != "approved":
        outcome = {"declined": "declined", "cancelled": "cancelled", "expired": "cancelled"}.get(
            approval.decision, "cancelled"
        )
        raise GuardError(Category.POLICY, f"Mutation approval {approval.decision}.", outcome)
    if (
        approval.expires_at <= clock()
        or approval.operation_id != operation_id
        or approval.identity != principal.identity
        or approval.fingerprint != fingerprint(preview)
    ):
        raise GuardError(
            Category.POLICY, "Approval expired or no longer matches the request.", "cancelled"
        )
