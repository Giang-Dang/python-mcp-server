"""Real loopback Streamable HTTP, controlled JWTs, and the isolated shop/audit databases."""

import asyncio
import socket

import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from support import server_settings
from test_mcp_http import controlled_auth

from mcp_server.bootstrap import build_services, create_server
from mcp_server.runtime import run_async

pytestmark = pytest.mark.integration


def test_authenticated_http_sql_approval_batch_and_audit(monkeypatch):
    async def run():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        settings = server_settings(port=sock.getsockname()[1])
        auth, keys = controlled_auth(monkeypatch, settings)
        services = build_services(settings)
        mcp = create_server(settings, auth=auth, services=services)
        app = mcp.http_app(path="/mcp", host_origin_protection=True, stateless_http=True)
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(300):
                if server.started:
                    break
                if task.done():
                    await task
                await asyncio.sleep(0.01)
            assert server.started
            token = keys.create_token(
                issuer=settings.issuer, audience=settings.resource_url, kid="test"
            )
            decisions = iter(("decline", "accept", "accept"))
            previews = []

            async def elicit(message, response_type, params, context):
                previews.append(message)
                decision = next(decisions)
                return ElicitResult(
                    action=decision, content={"approve": True} if decision == "accept" else None
                )

            async with Client(
                settings.resource_url, auth=token, mode="2026-07-28", elicitation_handler=elicit
            ) as client:
                assert len(await client.list_tools()) == 9
                assert (await client.call_tool("ping", {})).data == "pong"
                read = (
                    await client.call_tool(
                        "query", {"sql": "SELECT product_id FROM shop.products LIMIT 2"}
                    )
                ).data
                assert read["data"]["returned_rows"] == 2
                rejected = (await client.call_tool("query", {"sql": "SELECT pg_sleep(10)"})).data
                assert rejected["error"]["category"] == "policy_rejection"
                sql = "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1"
                declined = (await client.call_tool("execute", {"sql": sql})).data
                assert declined["outcome"] == "declined"
                committed = (await client.call_tool("execute", {"sql": sql})).data
                assert committed["outcome"] == "committed", committed
                batch = (
                    await client.call_tool(
                        "call_procedure",
                        {
                            "name": "archive_old_orders",
                            "args": {
                                "p_before": "1900-01-01",
                                "p_batch_size": 1,
                                "p_max_batches": 1,
                            },
                        },
                    )
                ).data
                assert batch["outcome"] == "committed", batch
            assert len(previews) == 3
            import psycopg

            with psycopg.connect(
                host="127.0.0.1",
                port=55439,
                dbname="mcp_audit",
                user="mcp_audit_owner",
                password="test_audit_owner",
            ) as conn:
                kinds = [
                    r[0]
                    for r in conn.execute(
                        "SELECT kind FROM audit.events WHERE operation_id=%s ORDER BY event_id",
                        (committed["operation_id"],),
                    )
                ]
                assert kinds == [
                    "awaiting_approval",
                    "approval",
                    "execution_intent",
                    "commit_intent",
                    "outcome",
                ]
                caller = conn.execute(
                    "SELECT issuer, subject, inputs FROM audit.operations WHERE operation_id=%s",
                    (committed["operation_id"],),
                ).fetchone()
                assert caller[0] == settings.issuer and caller[2] == {"sql": sql}
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
            sock.close()

    run_async(run())
