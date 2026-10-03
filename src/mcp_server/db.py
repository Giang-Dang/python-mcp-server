"""Compatibility entry point for pure Core query construction."""

from mcp_server.adapters.postgres.queries import tables_query

__all__ = ["tables_query"]
