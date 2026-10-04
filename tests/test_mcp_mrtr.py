"""Modern wire guard, replay protection and failure outcomes using controlled services."""

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fakes import MemoryAudit, principal
from fastmcp import Client
from fastmcp.exceptions import McpError, ToolError
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp_types import CLIENT_CAPABILITIES_META_KEY, ElicitResult, InputRequiredResult
from support import server_settings
from test_guarded_core import FakeDatabase

from mcp_server.adapters.mcp.approval import ApprovalRounds
from mcp_server.adapters.sql_parser.sqlglot import Parser
from mcp_server.bootstrap import create_server
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError
from mcp_server.core.sql_access.application import SQLAccess
from mcp_server.core.sql_access.domain import Limits

SQL = "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1"


def context(state=None, answer=None, form=True):
    return SimpleNamespace(
        request_state=state,
        input_responses=None if answer is None else {"approval": answer},
        request_context=SimpleNamespace(
            meta={CLIENT_CAPABILITIES_META_KEY: {"elicitation": {"form": {}}} if form else {}}
        ),
    )


def fixture(fail=None, database=None):
    db = database or FakeDatabase()
    store = MemoryAudit(fail)
    service = SQLAccess(Parser(), db, Audit(store, Limits()), Limits())
    return db, store, service, ApprovalRounds()


def test_wire_input_required_then_exact_resume_and_replay():
    async def run():
        db, store, service, _ = fixture()

        async def close():
            pass

        server = create_server(
            server_settings(),
            auth=StaticTokenVerifier(tokens={}),
            services=SimpleNamespace(sql=service, close=close),
            identity=principal,
        )
        # A handler advertises form support. Raw session calls leave MRTR visible.
        async with Client(
            server, mode="2026-07-28", elicitation_handler=lambda *a: {"approve": True}
        ) as client:
            first = await client.session.call_tool(
                "execute", {"sql": SQL}, allow_input_required=True
            )
            assert isinstance(first, InputRequiredResult)
            assert first.request_state.startswith("v1.")
            assert not db.calls
            assert [e[1] for e in store.events] == ["awaiting_approval"]
            for state, sql in (
                (first.request_state[:-2] + "xx", SQL),
                (first.request_state, SQL + " "),
            ):
                with pytest.raises(McpError):
                    await client.session.call_tool(
                        "execute",
                        {"sql": sql},
                        request_state=state,
                        input_responses={
                            "approval": ElicitResult(action="accept", content={"approve": True})
                        },
                        allow_input_required=True,
                    )
                assert not db.calls
            kwargs = {
                "request_state": first.request_state,
                "input_responses": {
                    "approval": ElicitResult(action="accept", content={"approve": True})
                },
                "allow_input_required": True,
            }
            final = await client.session.call_tool("execute", {"sql": SQL}, **kwargs)
            assert final.structured_content["outcome"] == "committed"
            replay = await client.session.call_tool("execute", {"sql": SQL}, **kwargs)
            assert final.structured_content == replay.structured_content
            assert db.calls == len(store.operations) == 1
            assert [e[1] for e in store.events] == [
                "awaiting_approval",
                "approval",
                "execution_intent",
                "commit_intent",
                "outcome",
            ]

    asyncio.run(run())


@pytest.mark.parametrize(
    "case", ["caller", "inputs", "expiry", "missing", "false", "cancel", "restart"]
)
def test_resume_fails_closed(case):
    async def run():
        db, _, service, rounds = fixture()
        user = principal()
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        handle = first.request_state
        answer = ElicitResult(
            action="cancel" if case == "cancel" else "accept", content={"approve": case != "false"}
        )
        current = principal("other") if case == "caller" else user
        inputs = {"sql": SQL + " "} if case == "inputs" else {"sql": SQL}
        if case == "expiry":
            rounds.entries[handle].expires_at = time.time() - 1
        if case == "restart":
            rounds = ApprovalRounds()
        if case in ("caller", "inputs", "restart"):
            with pytest.raises(ToolError):
                await rounds.run(context(handle, answer), current, "execute", inputs, service)
        else:
            result = await rounds.run(
                context(handle, None if case == "missing" else answer),
                current,
                "execute",
                inputs,
                service,
            )
            assert result["outcome"] in ("cancelled", "declined")
        assert not db.calls

    asyncio.run(run())


def test_concurrent_resume_claims_once():
    async def run():
        class SlowDB(FakeDatabase):
            async def mutate(self, sql, before_commit):
                await asyncio.sleep(0.02)
                return await super().mutate(sql, before_commit)

        db, _, service, rounds = fixture(database=SlowDB())
        user = principal()
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        ctx = context(first.request_state, ElicitResult(action="accept", content={"approve": True}))
        results = await asyncio.gather(
            *(rounds.run(ctx, user, "execute", {"sql": SQL}, service) for _ in range(2)),
            return_exceptions=True,
        )
        assert db.calls == 1
        assert sum(isinstance(r, ToolError) for r in results) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "fail",
    ["start", "awaiting_approval", "approval", "execution_intent", "commit_intent", "outcome"],
)
def test_mrtr_audit_failure(fail):
    async def run():
        db, _, service, rounds = fixture(fail)
        user = principal()
        result = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        if isinstance(result, InputRequiredResult):
            result = await rounds.run(
                context(
                    result.request_state, ElicitResult(action="accept", content={"approve": True})
                ),
                user,
                "execute",
                {"sql": SQL},
                service,
            )
        assert result["error"]["category"] == "audit_unavailability"
        assert db.calls == (1 if fail == "outcome" else 0)
        if fail == "outcome":
            assert result["outcome"] == "committed" and result["retry_safe"] is False

    asyncio.run(run())


def test_capacity_and_original_token_expiry():
    async def run():
        db, _, service, rounds = fixture()
        rounds.max_operations = 1
        user = replace(principal(), expires_at=time.time() + 30)
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        assert rounds.entries[first.request_state].expires_at == user.expires_at
        with pytest.raises(ToolError, match="capacity"):
            await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        assert not db.calls

    asyncio.run(run())


def test_uncertain_result_is_cached_without_repeat_mutation():
    async def run():
        db = FakeDatabase()
        db.failure = GuardError(Category.UNCERTAIN, "Lost acknowledgement.", "uncertain")
        _, _, service, rounds = fixture(database=db)
        user = principal()
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        ctx = context(first.request_state, ElicitResult(action="accept", content={"approve": True}))
        for _ in range(2):
            result = await rounds.run(ctx, user, "execute", {"sql": SQL}, service)
            assert result["outcome"] == "uncertain" and result["retry_safe"] is False
        assert db.calls == 1

    asyncio.run(run())


@pytest.mark.parametrize("drift", ["registry", "definition", "limits", "none"])
def test_procedure_resume_rechecks_reviewed_definition(drift):
    async def run():
        from mcp_server.adapters.registry.yaml_registry import load_registry
        from mcp_server.core.procedures.application import Procedures

        db = FakeDatabase()
        store = MemoryAudit()
        registry = load_registry(server_settings().registry_path)
        service = Procedures(registry, db, Audit(store, Limits()), Limits())
        rounds = ApprovalRounds()
        user = principal()
        inputs = {"name": "cancel_order", "arguments": {"p_order_id": 1}}
        first = await rounds.run(context(), user, "call_procedure", inputs, service)
        assert isinstance(first, InputRequiredResult), first
        if drift == "registry":
            registry["cancel_order"] = replace(registry["cancel_order"], effects="Changed effects")
        if drift == "definition":
            db.hash = "0" * 64
        if drift == "limits":
            service.limits = replace(service.limits, affected_rows=2)
        result = await rounds.run(
            context(first.request_state, ElicitResult(action="accept", content={"approve": True})),
            user,
            "call_procedure",
            inputs,
            service,
        )
        assert db.calls == (drift == "none")
        assert result["operation_id"] == store.operations[0].id
        assert result["outcome"] == (
            "committed" if drift == "none" else ("cancelled" if drift == "limits" else "rejected")
        )

    asyncio.run(run())


def test_approval_expiry_during_preview_prevents_execution():
    async def run():
        db, _, service, rounds = fixture()
        user = principal()
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        rounds.entries[first.request_state].expires_at = time.time() + 0.01
        original = db.preview

        async def slow_preview(*args):
            await asyncio.sleep(0.02)
            return await original(*args)

        db.preview = slow_preview
        result = await rounds.run(
            context(first.request_state, ElicitResult(action="accept", content={"approve": True})),
            user,
            "execute",
            {"sql": SQL},
            service,
        )
        assert result["outcome"] == "cancelled" and not db.calls

    asyncio.run(run())


def test_expiration_cleanup_records_terminal_outcome():
    async def run():
        _, store, service, rounds = fixture()
        first = await rounds.run(context(), principal(), "execute", {"sql": SQL}, service)
        rounds.entries[first.request_state].expires_at = time.time() - 1
        async with rounds.lock:
            await rounds.cleanup()
        assert not rounds.entries
        assert store.events[-1][1:] == (
            "outcome",
            {"outcome": "cancelled", "reason": "approval_expired"},
        )

    asyncio.run(run())


def test_cancelled_resume_keeps_non_retryable_tombstone_until_expiry():
    async def run():
        class CancelDB(FakeDatabase):
            async def mutate(self, sql, before_commit):
                raise asyncio.CancelledError

        _, store, service, rounds = fixture(database=CancelDB())
        user = principal()
        first = await rounds.run(context(), user, "execute", {"sql": SQL}, service)
        ctx = context(first.request_state, ElicitResult(action="accept", content={"approve": True}))
        with pytest.raises(asyncio.CancelledError):
            await rounds.run(ctx, user, "execute", {"sql": SQL}, service)
        assert rounds.entries[first.request_state].state == "uncertain"
        with pytest.raises(ToolError, match="already claimed"):
            await rounds.run(ctx, user, "execute", {"sql": SQL}, service)
        assert store.events[-1][1] == "cancelled"
        rounds.entries[first.request_state].expires_at = time.time() - 1
        async with rounds.lock:
            await rounds.cleanup()
        assert not rounds.entries

    asyncio.run(run())
