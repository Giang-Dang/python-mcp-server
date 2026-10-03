"""Database access for the MCP server, through SQLAlchemy Core (not the ORM).

Why Core and not the ORM: the server has no domain objects. Its data is "whatever the SQL returns", so
there is nothing to map to classes. What it needs from SQLAlchemy is the engine (a connection pool per
role) and a typed way to build its own fixed queries, so they are never assembled from strings.

One engine per database role. Each role has different privileges (mcp_reader SELECT only, mcp_writer DML,
mcp_proc_exec EXECUTE), and the role is chosen by the server, never by the model.

Pass-through SQL (text the model or the user wrote) is the one thing SQLAlchemy cannot build: it has to be
executed as text. That path will use Connection.exec_driver_sql so SQLAlchemy does not try to read ":name"
inside the text as a bind parameter.
"""

from __future__ import annotations

from functools import cache

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import URL
from sqlalchemy.sql import Select

from shopdb.config import get_settings

SCHEMA = "shop"


@cache
def engine_for(role: str) -> Engine:
    """The pooled engine that connects as `role` (cached: one pool per role per process)."""
    s = get_settings()
    url = URL.create(
        "postgresql+psycopg",
        username=role,
        password=s.password_for(role),
        host=s.postgres_host,
        port=s.postgres_port,
        database=s.postgres_db,
    )
    return create_engine(
        url,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,  # drop connections the server closed (idle timeouts, restarts)
        pool_reset_on_return="rollback",  # never hand back a connection with an open transaction
    )


# The two system catalog tables the server queries, described once. Describing them as Table objects makes
# the queries below ordinary Core expressions (type checked, parameterized) instead of SQL strings.
_catalog = MetaData(schema="pg_catalog")
pg_namespace = Table(
    "pg_namespace", _catalog, Column("oid", Integer, primary_key=True), Column("nspname", String)
)
pg_class = Table(
    "pg_class",
    _catalog,
    Column("oid", Integer, primary_key=True),
    Column("relname", String),
    Column("relnamespace", Integer),
    Column("relkind", String),
    Column("relispartition", Boolean),
    Column("reltuples", Float),
)


def tables_query(schema: str = SCHEMA) -> Select:
    """Ordinary and partitioned tables of `schema`, hiding partitions (they are details of their parent)."""
    return (
        select(
            pg_class.c.relname.label("table_name"),
            (pg_class.c.relkind == "p").label("is_partitioned"),
            # reltuples is -1 for a table that was never analyzed; report 0 rather than a negative count
            func.greatest(pg_class.c.reltuples, 0).cast(BigInteger).label("approx_rows"),
            func.obj_description(pg_class.c.oid, "pg_class").label("comment"),
        )
        .join(pg_namespace, pg_namespace.c.oid == pg_class.c.relnamespace)
        .where(
            pg_namespace.c.nspname == schema,
            pg_class.c.relkind.in_(("r", "p")),
            pg_class.c.relispartition.is_(False),
        )
        .order_by(pg_class.c.relname)
    )
