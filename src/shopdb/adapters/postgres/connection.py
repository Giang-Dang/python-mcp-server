"""Database connections for the host-side tools."""

from __future__ import annotations

import psycopg

from shopdb.settings import Settings, get_settings


def connect(
    role: str, settings: Settings | None = None, autocommit: bool = False
) -> psycopg.Connection:
    """Open a connection as one of the application roles (loader, shop_owner, mcp_reader, ...)."""
    s = settings or get_settings()
    return psycopg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        dbname=s.postgres_db,
        user=role,
        password=s.password_for(role),
        autocommit=autocommit,
    )
