"""Tests for the stub MCP server, through a real MCP client connected in memory (no subprocess)."""

from __future__ import annotations

import asyncio

import psycopg
import pytest
from fastmcp import Client
from sqlalchemy import func, select

from mcp_server.db import engine_for
from mcp_server.server import mcp
from shopdb.db import connect


def call(tool: str) -> object:
    async def run() -> object:
        async with Client(mcp) as client:
            result = await client.call_tool(tool, {})
            return result.data

    return asyncio.run(run())


def test_the_server_lists_exactly_the_two_stub_tools_marked_read_only():
    async def run():
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(run())}
    assert set(tools) == {"ping", "list_tables"}
    assert all(t.annotations.read_only_hint for t in tools.values())


def test_ping_answers_pong():
    assert call("ping") == "pong"


def test_list_tables_returns_the_25_tables_without_partitions():
    tables = call("list_tables")
    names = {t["table"] for t in tables}
    assert len(names) == 25
    assert {"orders", "customers", "audit_log"} <= names
    assert not any(n.startswith("audit_log_") for n in names)
    audit = next(t for t in tables if t["table"] == "audit_log")
    assert audit["partitioned"] is True
    assert all(t["comment"] for t in tables), (
        "every table has a COMMENT ON (the data dictionary needs it)"
    )


def test_the_role_behind_the_server_cannot_write():
    # The tool annotation is only a hint; this is the actual guarantee.
    # default_transaction_read_only is advisory (any session may switch it off), so switch it off to
    # prove that the missing UPDATE privilege is what stops the write.
    with connect("mcp_reader", autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE shop.products SET name = name WHERE product_id = 1")


def test_the_server_engine_connects_as_the_role_it_was_asked_for():
    for role in ("mcp_reader", "mcp_writer"):
        with engine_for(role).connect() as conn:
            assert conn.execute(select(func.current_user())).scalar_one() == role
    assert engine_for("mcp_reader") is engine_for("mcp_reader"), "one pool per role"
