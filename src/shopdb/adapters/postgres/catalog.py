import psycopg
from psycopg.rows import dict_row

from shopdb.core.documentation.domain import Catalog

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
