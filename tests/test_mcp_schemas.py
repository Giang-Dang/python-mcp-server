"""Output contracts describe positional report rows and preserve raw plans."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fakes import MemoryAudit, principal
from fastmcp import Client
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from support import server_settings

from mcp_server.adapters.mcp.schemas import DiagnosticsResponse, ExplainResponse
from mcp_server.adapters.sql_parser.sqlglot import Parser
from mcp_server.bootstrap import create_server
from mcp_server.core.auditing.application import Audit
from mcp_server.core.diagnostics.application import Diagnostics
from mcp_server.core.sql_access.application import SQLAccess
from mcp_server.core.sql_access.domain import Limits

ROWS = {
    "query_statistics": [1, 2, 3.5, 1.75, 4, "SELECT 1", 123],
    "locks": [None, "transactionid", None, "ExclusiveLock", False],
    "table_sizes": ["orders", 4096, 2048],
    "table_health": ["shop", "orders", 10, 1, None, "2026-10-04T00:00:00+00:00", 2, None],
}


class DB:
    async def preview(self, sql, role):
        return {
            "plan": {
                "Node Type": "Result",
                "Total Cost": 1.0,
                "Plan Rows": 1,
                "Future Property": {"key": True},
                "Plans": [{"Node Type": "Custom"}],
            },
            "total_cost_estimate": 1.0,
            "rows_estimate": 1,
            "estimates_only": True,
        }

    async def diagnostics(self, kind):
        return {
            "columns": [str(i) for i in range(len(ROWS[kind]))],
            "rows": [ROWS[kind]],
            "returned_rows": 1,
            "truncated": False,
            "truncation_reason": None,
            "result_bytes": 100,
            "byte_scope": "JSON columns and rows",
        }


@pytest.mark.parametrize("kind", list(ROWS))
def test_diagnostics_contract_full_empty_and_truncated(kind):
    async def run():
        service = Diagnostics(DB(), Audit(MemoryAudit(), Limits()))
        result = await service.run(principal(), kind)
        assert DiagnosticsResponse.model_validate(result).data.kind == kind
        result["data"].update(rows=[], returned_rows=0, truncated=True, truncation_reason="bytes")
        DiagnosticsResponse.model_validate(result)

    asyncio.run(run())


def test_wire_schemas_and_text_match_structured_content():
    async def run():
        db = DB()
        audit = Audit(MemoryAudit(), Limits())

        async def close():
            pass

        server = create_server(
            server_settings(),
            auth=StaticTokenVerifier(tokens={}),
            services=SimpleNamespace(
                sql=SQLAccess(Parser(), db, audit, Limits()),
                diagnostics=Diagnostics(db, audit),
                close=close,
            ),
            identity=principal,
        )
        async with Client(server, mode="2026-07-28") as client:
            tools = {t.name: t for t in await client.list_tools()}
            assert tools["explain"].output_schema["$defs"]["ExplainData"]
            branches = tools["diagnostics"].output_schema["properties"]["data"]["anyOf"][0]["oneOf"]
            assert {b["properties"]["kind"]["const"] for b in branches} == set(ROWS)
            for name, args in (
                ("explain", {"sql": "SELECT 1"}),
                ("diagnostics", {"kind": "locks"}),
                ("explain", {"sql": "SELECT pg_sleep(10)"}),
                ("diagnostics", {"kind": "bad"}),
            ):
                result = await client.call_tool_mcp(name, args)
                assert json.loads(result.content[0].text) == result.structured_content
            explained = (
                await client.call_tool_mcp("explain", {"sql": "SELECT 1"})
            ).structured_content
            parsed = ExplainResponse.model_validate(explained)
            assert parsed.data.plan.model_extra["Future Property"] == {"key": True}

    asyncio.run(run())
