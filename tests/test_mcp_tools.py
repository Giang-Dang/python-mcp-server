import asyncio

from fakes import MemoryAudit, principal
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from support import server_settings
from test_guarded_core import FakeDatabase

from mcp_server.adapters.sql_parser.sqlglot import Parser
from mcp_server.bootstrap import create_server
from mcp_server.core.auditing.application import Audit
from mcp_server.core.sql_access.application import SQLAccess
from mcp_server.core.sql_access.domain import Limits


def test_mcp_client_elicitation_approve_decline_and_missing():
    async def run():
        for decision in ("approve", "decline", "cancel", "missing"):
            db = FakeDatabase()
            audit = Audit(MemoryAudit(), Limits())

            class Services:
                sql = SQLAccess(Parser(), db, audit, Limits())

                async def close(self):
                    pass

            server = create_server(
                server_settings(),
                auth=StaticTokenVerifier(tokens={}),
                services=Services(),
                identity=principal,
            )
            seen = []

            async def elicit(message, response_type, params, context, decision=decision, seen=seen):
                seen.append(message)
                if decision == "approve":
                    return {"approve": True}
                return ElicitResult(action="decline" if decision == "decline" else "cancel")

            async with Client(
                server,
                mode="2026-07-28",
                elicitation_handler=None if decision == "missing" else elicit,
            ) as client:
                assert (await client.call_tool("ping", {})).data == "pong"
                result = await client.call_tool(
                    "execute",
                    {"sql": "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1"},
                )
                assert (
                    result.data["outcome"]
                    == {
                        "approve": "committed",
                        "decline": "declined",
                        "cancel": "cancelled",
                        "missing": "cancelled",
                    }[decision]
                ), result.data
                assert db.calls == (decision == "approve")
                if seen:
                    assert "operation_id" in seen[0] and "UPDATE shop.customers" in seen[0]

    asyncio.run(run())
