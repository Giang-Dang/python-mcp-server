"""Generate docs/data-dictionary.md and docs/erd.md from the live database catalog.

Everything comes from Postgres itself (pg_class, pg_attribute, pg_constraint, pg_description, ...), so the
documents cannot describe something that does not exist. The text comes from COMMENT ON statements
(db/schema/*.sql and db/post_load/160_comments.sql).

The output has no timestamps, so regenerating on an unchanged database produces an identical file
(clean git diffs).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .db import connect

# Columns of ordinary tables and partitioned parents (partitions are an implementation detail of the parent).
TABLES_SQL = """
SELECT c.oid, c.relname AS name, c.relkind AS kind,
       obj_description(c.oid, 'pg_class') AS comment,
       c.relrowsecurity AS rls,
       greatest(c.reltuples, 0)::bigint AS approx_rows,
       (SELECT count(*) FROM pg_inherits i WHERE i.inhparent = c.oid) AS partitions
FROM pg_class c
WHERE c.relnamespace = 'shop'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'm') AND NOT c.relispartition
ORDER BY c.relname
"""

COLUMNS_SQL = """
SELECT c.relname AS tbl, a.attnum AS pos, a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS type,
       a.attnotnull AS not_null,
       pg_get_expr(d.adbin, d.adrelid) AS default_expr,
       a.attidentity AS identity,
       col_description(c.oid, a.attnum) AS comment
FROM pg_class c
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE c.relnamespace = 'shop'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'm') AND NOT c.relispartition
ORDER BY c.relname, a.attnum
"""

# conparentid = 0 skips the copies that Postgres makes on every partition of a partitioned table.
CONSTRAINTS_SQL = """
SELECT t.relname AS tbl, con.conname AS name, con.contype AS kind,
       pg_get_constraintdef(con.oid) AS definition,
       ref.relname AS ref_table,
       (SELECT string_agg(a.attname, ', ' ORDER BY k.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS columns
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
LEFT JOIN pg_class ref ON ref.oid = con.confrelid
WHERE con.connamespace = 'shop'::regnamespace AND con.conparentid = 0 AND NOT t.relispartition
ORDER BY t.relname, con.contype, con.conname
"""

INDEXES_SQL = """
SELECT t.relname AS tbl, i.relname AS name, pg_get_indexdef(x.indexrelid) AS definition
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
WHERE t.relnamespace = 'shop'::regnamespace AND NOT t.relispartition AND NOT i.relispartition
  AND t.relkind IN ('r', 'p', 'm') AND NOT x.indisprimary
ORDER BY t.relname, i.relname
"""

TRIGGERS_SQL = """
SELECT c.relname AS tbl, t.tgname AS name, pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
WHERE c.relnamespace = 'shop'::regnamespace AND NOT t.tgisinternal AND t.tgparentid = 0 AND NOT c.relispartition
ORDER BY c.relname, t.tgname
"""

ROUTINES_SQL = """
SELECT p.proname AS name, p.prokind AS kind,
       pg_get_function_identity_arguments(p.oid) AS args,
       pg_get_function_result(p.oid) AS result,
       p.prosecdef AS definer, p.provolatile AS volatility,
       obj_description(p.oid, 'pg_proc') AS comment
FROM pg_proc p
WHERE p.pronamespace = 'shop'::regnamespace AND p.prokind IN ('f', 'p')
ORDER BY p.prokind DESC, p.proname, p.oid
"""

POLICIES_SQL = """
SELECT tablename AS tbl, policyname AS name, cmd, roles::text AS roles, qual, with_check
FROM pg_policies WHERE schemaname = 'shop' ORDER BY tablename, policyname
"""

KIND_LABEL = {"r": "table", "p": "partitioned table", "v": "view", "m": "materialized view"}
VOLATILITY = {"i": "immutable", "s": "stable", "v": "volatile"}
CONSTRAINT_LABEL = {
    "p": "primary key",
    "f": "foreign key",
    "u": "unique",
    "c": "check",
    "x": "exclusion",
}


@dataclass
class Catalog:
    tables: list[dict]
    columns: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    constraints: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    indexes: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    triggers: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    policies: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    routines: list[dict] = field(default_factory=list)


def read_catalog(conn: psycopg.Connection) -> Catalog:
    cur = conn.cursor(row_factory=dict_row)
    cat = Catalog(tables=cur.execute(TABLES_SQL).fetchall())
    for sql, target in (
        (COLUMNS_SQL, cat.columns),
        (CONSTRAINTS_SQL, cat.constraints),
        (INDEXES_SQL, cat.indexes),
        (TRIGGERS_SQL, cat.triggers),
        (POLICIES_SQL, cat.policies),
    ):
        for row in cur.execute(sql).fetchall():
            target[row["tbl"]].append(row)
    cat.routines = cur.execute(ROUTINES_SQL).fetchall()
    return cat


def _cell(text: str | None) -> str:
    """Make text safe inside a markdown table cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _flags(table: str, column: str, cat: Catalog) -> list[str]:
    flags = []
    for con in cat.constraints.get(table, []):
        cols = (con["columns"] or "").split(", ")
        if column not in cols:
            continue
        if con["kind"] == "p":
            flags.append("PK")
        elif con["kind"] == "f":
            flags.append(f"FK to {con['ref_table']}")
        elif con["kind"] == "u" and len(cols) == 1:
            flags.append("unique")
    return flags


def render_dictionary(cat: Catalog) -> str:
    out = [
        "# Data dictionary",
        "",
        "> Generated by `poetry run shopdb docs` from the live database catalog and its `COMMENT ON` text.",
        "> Do not edit by hand: change the comment (db/schema/*.sql or db/post_load/160_comments.sql) and regenerate.",
        "> Row counts are the planner's estimates (`pg_class.reltuples`) and depend on the size profile that is loaded.",
        "",
        "## Contents",
        "",
    ]
    base = [t for t in cat.tables if t["kind"] in ("r", "p")]
    views = [t for t in cat.tables if t["kind"] in ("v", "m")]
    out += [f"- Tables ({len(base)}): " + ", ".join(f"[{t['name']}](#{t['name']})" for t in base)]
    out += [f"- Views ({len(views)}): " + ", ".join(f"[{t['name']}](#{t['name']})" for t in views)]
    out += [
        f"- [Routines](#routines) ({len(cat.routines)})",
        "- [Row-level security](#row-level-security)",
        "",
    ]

    for t in cat.tables:
        name = t["name"]
        out += [f"## {name}", ""]
        meta = [KIND_LABEL[t["kind"]]]
        if t["kind"] in ("r", "p", "m"):
            meta.append(f"about {t['approx_rows']:,} rows")
        if t["partitions"]:
            meta.append(f"{t['partitions']} partitions")
        if t["rls"]:
            meta.append("row-level security on")
        out += [f"*{', '.join(meta)}*", "", t["comment"] or "(no description)", ""]

        out += [
            "| Column | Type | Null | Default | Notes | Description |",
            "|---|---|---|---|---|---|",
        ]
        for col in cat.columns[name]:
            default = col["default_expr"] or ("identity" if col["identity"] else "")
            if len(default) > 40:
                default = default[:37] + "..."
            notes = ", ".join(_flags(name, col["name"], cat))
            out.append(
                f"| `{col['name']}` | {_cell(col['type'])} | {'' if col['not_null'] else 'yes'} "
                f"| {('`' + _cell(default) + '`') if default else ''} | {_cell(notes)} | {_cell(col['comment'])} |"
            )
        out.append("")

        checks = [
            c
            for c in cat.constraints.get(name, [])
            if c["kind"] in ("u", "c", "x") or (c["kind"] == "f")
        ]
        if checks:
            out += ["Constraints:", ""]
            out += [
                f"- `{c['name']}`: {CONSTRAINT_LABEL[c['kind']]} - `{_cell(c['definition'])}`"
                for c in checks
            ]
            out.append("")
        if cat.indexes.get(name):
            out += ["Indexes (besides the primary key):", ""]
            out += [f"- `{i['name']}`: `{_cell(i['definition'])}`" for i in cat.indexes[name]]
            out.append("")
        if cat.triggers.get(name):
            out += ["Triggers:", ""]
            out += [f"- `{tr['name']}`: `{_cell(tr['definition'])}`" for tr in cat.triggers[name]]
            out.append("")

    out += [
        "## Routines",
        "",
        "Functions and procedures of the `shop` schema. *definer* means SECURITY DEFINER: it runs with its owner's",
        "privileges (and therefore bypasses row-level security); invoker routines run as the caller.",
        "",
        "| Name | Kind | Arguments | Returns | Runs as | Volatility | Description |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in cat.routines:
        out.append(
            f"| `{r['name']}` | {'procedure' if r['kind'] == 'p' else 'function'} | `{_cell(r['args'])}` "
            f"| {('`' + _cell(r['result']) + '`') if r['kind'] == 'f' else ''} "
            f"| {'definer' if r['definer'] else 'invoker'} | {VOLATILITY[r['volatility']]} | {_cell(r['comment'])} |"
        )
    out.append("")

    out += [
        "## Row-level security",
        "",
        "Policies filter rows by `current_setting('app.tenant_id')`. The `mcp_*` roles default to tenant 1.",
        "",
        "| Table | Policy | Command | Roles | USING |",
        "|---|---|---|---|---|",
    ]
    for rows in cat.policies.values():
        for p in rows:
            out.append(
                f"| {p['tbl']} | {p['name']} | {p['cmd']} | {_cell(p['roles'])} | `{_cell(p['qual'])}` |"
            )
    out.append("")
    return "\n".join(out)


def _mermaid_type(sql_type: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]", "_", sql_type)).strip("_")


def render_erd(cat: Catalog) -> str:
    """A Mermaid entity-relationship diagram: every table with its key columns, and every foreign key."""
    tables = {t["name"] for t in cat.tables if t["kind"] in ("r", "p")}
    not_null = {(c["tbl"], c["name"]): c["not_null"] for cols in cat.columns.values() for c in cols}
    types = {(c["tbl"], c["name"]): c["type"] for cols in cat.columns.values() for c in cols}

    fks = [
        c
        for cons in cat.constraints.values()
        for c in cons
        if c["kind"] == "f" and c["tbl"] in tables and c["ref_table"] in tables
    ]
    fk_columns: dict[str, set[str]] = defaultdict(set)
    for c in fks:
        fk_columns[c["tbl"]].update(c["columns"].split(", "))

    lines = ["erDiagram"]
    for fk in sorted(fks, key=lambda c: (c["ref_table"], c["tbl"], c["columns"])):
        optional = not all(not_null[(fk["tbl"], col)] for col in fk["columns"].split(", "))
        parent_side = "|o" if optional else "||"
        lines.append(f'    {fk["ref_table"]} {parent_side}--o{{ {fk["tbl"]} : "{fk["columns"]}"')

    for name in sorted(tables):
        pk_cols: set[str] = set()
        for c in cat.constraints.get(name, []):
            if c["kind"] == "p":
                pk_cols.update(c["columns"].split(", "))
        shown = [
            col["name"] for col in cat.columns[name] if col["name"] in pk_cols | fk_columns[name]
        ]
        lines.append(f"    {name} {{")
        for col in shown:
            tag = "PK" if col in pk_cols else "FK"
            if col in pk_cols and col in fk_columns[name]:
                tag = "PK, FK"
            lines.append(f"        {_mermaid_type(types[(name, col)])} {col} {tag}")
        lines.append("    }")

    standalone = sorted(t for t in tables if not any(t in (c["tbl"], c["ref_table"]) for c in fks))
    body = "\n".join(lines)
    notes = ""
    if standalone:
        names = ", ".join(f"`{t}`" for t in standalone)
        verb = "has" if len(standalone) == 1 else "have"
        notes = f"\nNo foreign keys to or from other tables: {names} {verb} none by design"
        if "audit_log" in standalone:
            notes += " (`audit_log` points at rows by table name and id, so the audit trail survives deletes)"
        notes += ".\n"
    return (
        "# Entity-relationship diagram\n\n"
        "> Generated by `poetry run shopdb docs` from the foreign keys in the live database. Do not edit by hand.\n"
        "> Only key columns are shown; all columns are in [data-dictionary.md](data-dictionary.md).\n"
        "> Reading the lines: `A ||--o{ B` means one A has zero or more B; `|o` on the left means the parent is optional (nullable foreign key).\n\n"
        f"```mermaid\n{body}\n```\n{notes}\n"
    )


def generate(out_dir: Path) -> list[Path]:
    """Write both documents into out_dir and return their paths."""
    with connect("shop_owner", autocommit=True) as conn:
        cat = read_catalog(conn)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, text in (
        ("data-dictionary.md", render_dictionary(cat)),
        ("erd.md", render_erd(cat)),
    ):
        path = out_dir / filename
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
