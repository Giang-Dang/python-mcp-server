"""Translate PostgreSQL syntax into policy facts. Never execute parser output blindly."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from mcp_server.core.errors import Category, GuardError
from mcp_server.core.sql_access.domain import Analysis

SAFE_TYPES = {
    "BIGINT",
    "INT",
    "SMALLINT",
    "DECIMAL",
    "DOUBLE",
    "FLOAT",
    "TEXT",
    "VARCHAR",
    "BOOLEAN",
    "DATE",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "UUID",
}


class Parser:
    def analyze(self, sql: str) -> Analysis:
        if not isinstance(sql, str) or not sql.strip() or "\x00" in sql:
            raise GuardError(Category.ARGUMENTS, "SQL must be nonempty text without NUL.")
        try:
            statements = sqlglot.parse(sql, read="postgres", error_level=ErrorLevel.RAISE)
        except (SqlglotError, ValueError, RecursionError):
            raise GuardError(Category.POLICY, "SQL could not be safely parsed.") from None
        if len(statements) != 1 or statements[0] is None:
            raise GuardError(Category.POLICY, "Exactly one SQL statement is required.")
        tree = statements[0]
        kind = {exp.Insert: "insert", exp.Update: "update", exp.Delete: "delete"}.get(type(tree))
        if isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            kind = "read"
        violations = []
        if kind is None:
            violations.append("Statement form is not permitted.")
        nodes = list(tree.walk())
        if any(
            isinstance(n, (exp.Insert, exp.Update, exp.Delete)) and n is not tree for n in nodes
        ):
            violations.append("Nested modifying statements are forbidden.")
        if tree.find(exp.Returning):
            violations.append("DML RETURNING is not supported.")
        if tree.find(exp.Into) or tree.find(exp.Lock):
            violations.append("SELECT INTO and locking reads are forbidden.")
        if any(isinstance(n, exp.Dot) for n in nodes):
            violations.append("Qualified functions and complex field access are not reviewed.")
        for node in nodes:
            if (
                isinstance(node, exp.DataType)
                and getattr(node.this, "value", None) not in SAFE_TYPES
            ):
                violations.append("Cast type is not reviewed.")
            if isinstance(node, exp.Table) and (
                node.catalog or not isinstance(node.this, exp.Identifier)
            ):
                violations.append("Dynamic or cross-database table references are forbidden.")
        ctes = {n.alias_or_name for n in tree.find_all(exp.CTE)}
        tables = tuple(
            (n.db, n.name) for n in tree.find_all(exp.Table) if n.db or n.name not in ctes
        )
        return Analysis(
            kind or "unknown",
            tree.sql(dialect="postgres"),
            frozenset(type(n).__name__ for n in nodes),
            frozenset(type(n).__name__ for n in nodes if isinstance(n, exp.Func)),
            tables,
            bool(tree.args.get("where")),
            tuple(violations),
        )
