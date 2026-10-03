from collections.abc import Iterable
from contextlib import contextmanager

import psycopg
from psycopg import sql

from shopdb.adapters.generation.static import static_tables

from .connection import connect


def copy_rows(
    cur: psycopg.Cursor, table: str, columns: Iterable[str], rows: Iterable[tuple]
) -> int:
    """Stream rows into a table with COPY ... FROM STDIN and return how many were sent."""
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            n += 1
    return n


def data_tables(conn: psycopg.Connection) -> list[str]:
    """Every regular or partitioned-parent table in schema shop (partitions are covered by their parent)."""
    rows = conn.execute(
        """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'shop' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
        ORDER BY c.relname
        """
    ).fetchall()
    return [r[0] for r in rows]


def truncate_all(conn: psycopg.Connection) -> None:
    tables = [sql.Identifier("shop", t) for t in data_tables(conn)]
    conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(sql.SQL(", ").join(tables)))
    conn.commit()


def reset_sequences(conn: psycopg.Connection) -> int:
    """Move every identity sequence past the largest loaded id, so the next INSERT gets a fresh value."""
    cols = conn.execute(
        """
        SELECT c.relname, a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'shop' AND a.attidentity <> '' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
        ORDER BY 1
        """
    ).fetchall()
    for table, column in cols:
        query = sql.SQL(
            "SELECT setval(pg_get_serial_sequence(%s, %s), GREATEST(coalesce(max({col}), 0), 1), "
            "coalesce(max({col}), 0) > 0) FROM {tbl}"
        ).format(col=sql.Identifier(column), tbl=sql.Identifier("shop", table))
        conn.execute(query, (f"shop.{table}", column))
    conn.commit()
    return len(cols)


def has_post_load_triggers(conn) -> bool:
    """True when user triggers exist in schema shop (foreign-key triggers are internal and ignored)."""
    row = conn.execute(
        """
        SELECT count(*) FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'shop' AND NOT t.tgisinternal
        """
    ).fetchone()
    return row[0] > 0


class SeedStore:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def session(self):
        with connect("loader", self.settings) as conn:
            yield SeedSession(conn)


class SeedSession:
    def __init__(self, conn):
        self.conn = conn

    def has_triggers(self):
        return has_post_load_triggers(self.conn)

    def has_data(self):
        return bool(
            self.conn.execute(
                "SELECT (SELECT count(*) FROM shop.tenants) + (SELECT count(*) FROM shop.orders)"
            ).fetchone()[0]
        )

    def truncate(self):
        truncate_all(self.conn)

    def load_static(self, ctx):
        counts = {}
        with self.conn.cursor() as cur:
            for table, columns, rows in static_tables(ctx):
                counts[table] = copy_rows(cur, table, columns, rows)
        self.conn.commit()
        return counts

    def reset_sequences(self):
        return reset_sequences(self.conn)
