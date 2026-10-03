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

from shopdb.db import connect

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

# Regular tables and partitioned parents of the shop schema. Partitions (audit_log_2024_01, ...) are
# hidden: they are an implementation detail of their parent.
LIST_TABLES_SQL = """
SELECT c.relname                              AS table_name,
       c.relkind = 'p'                        AS is_partitioned,
       greatest(c.reltuples, 0)::bigint       AS approx_rows,
       obj_description(c.oid, 'pg_class')     AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shop' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
ORDER BY c.relname
"""


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
    # One short connection per call keeps the stub simple; a pool comes with the real server.
    with connect("mcp_reader", autocommit=True) as conn:
        rows = conn.execute(LIST_TABLES_SQL).fetchall()
    return [
        {"table": name, "partitioned": part, "approx_rows": rows_, "comment": comment}
        for name, part, rows_, comment in rows
    ]


if __name__ == "__main__":
    mcp.run()
