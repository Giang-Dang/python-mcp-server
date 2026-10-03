"""Stub MCP server for the shop database (step 8).

It only proves the chain MCP client -> this server -> the mcp_reader role -> Postgres works. The real
"guarded SQL" logic (classify read or mutate, ask before mutating, allowlisted procedures) comes later.

Run it:
    poetry run fastmcp run src/mcp_server/server.py          # stdio, what an MCP client launches
    poetry run fastmcp dev src/mcp_server/server.py          # with the MCP Inspector in a browser
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from mcp_types import ToolAnnotations

from mcp_server.db import engine_for, tables_query

mcp = FastMCP(
    "shop-db",
    instructions=(
        "Read-only access to the 'shop' e-commerce database (Postgres 17). "
        "Use list_tables to see what exists. Every call runs as the mcp_reader role."
    ),
)

# Hints for the client UI. They are advisory: the real barrier is that mcp_reader has SELECT only.
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def ping() -> str:
    """Check that the server is alive. Does not touch the database."""
    return "pong"


@mcp.tool(annotations=READ_ONLY)
def list_tables() -> list[dict[str, Any]]:
    """List the tables of the shop schema with an approximate row count and their description.

    The row count is the planner's estimate from pg_class.reltuples, not count(*): counting 30 million
    audit rows takes seconds, and the estimate is good enough to decide what to look at.
    """
    # engine_for() returns a pooled engine for the mcp_reader role; the query is a Core expression, not SQL text.
    with engine_for("mcp_reader").connect() as conn:
        rows = conn.execute(tables_query()).all()
    return [
        {
            "table": r.table_name,
            "partitioned": r.is_partitioned,
            "approx_rows": r.approx_rows,
            "comment": r.comment,
        }
        for r in rows
    ]


if __name__ == "__main__":
    mcp.run()
