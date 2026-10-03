"""Bulk loader: plans the data, then streams it into Postgres with COPY using a pool of worker processes.

Stages (a stage starts only when the previous one is fully committed, because of foreign keys):
  main process : lookups, tenants, categories, suppliers, warehouses
  stage B      : customers, products, employees
  stage C      : addresses, product variants
  stage D      : orders (+ lines, payments, shipments, invoices, refunds), carts, inventory,
                 inventory movements, audit log, price history
Afterwards the identity sequences are moved past the largest loaded id.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed

import psycopg
from psycopg import sql

from .config import Scale, Settings, get_settings
from .context import SeedContext
from .db import connect
from .generators import CHUNK_SIZES, REGISTRY
from .generators.static import static_tables
from .model import ORDER_CHUNK, compute_order_layout, ranges
from .postload import has_post_load_triggers

Log = Callable[[str], None]

# --- worker process state ---------------------------------------------------------------------
_CTX: SeedContext | None = None


def _init_worker(ctx: SeedContext) -> None:
    global _CTX
    _CTX = ctx


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


def _run_task(task: tuple[str, int, int, int]) -> tuple[str, int, dict[str, int], float]:
    """Runs inside a worker process: generate one chunk and load it in a single transaction."""
    kind, idx, lo, hi = task
    started = time.perf_counter()
    assert _CTX is not None
    batches = REGISTRY[kind](_CTX, idx, lo, hi)
    counts: dict[str, int] = {}
    with connect("loader") as conn:
        # Do not wait for the WAL flush at commit: a crash during a seed just means we seed again.
        conn.execute("SET synchronous_commit = off")
        with conn.cursor() as cur:
            for table, columns, rows in batches:
                counts[table] = copy_rows(cur, table, columns, rows)
        conn.commit()
    return kind, idx, counts, time.perf_counter() - started


# --- planning and stages ----------------------------------------------------------------------
def build_context(scale: Scale, seed: int) -> SeedContext:
    offsets, totals, order_counts = compute_order_layout(scale, seed)
    return SeedContext(
        scale=scale, seed=seed, order_offsets=offsets, totals=totals, order_counts=order_counts
    )


def _tasks(ctx: SeedContext, kind: str) -> list[tuple[str, int, int, int]]:
    s = ctx.scale
    if kind == "orders":
        chunks = ranges(s.orders, ORDER_CHUNK)
    else:
        n = {
            "customers": s.customers,
            "addresses": s.customers,  # chunked by customer id
            "products": s.products,
            "product_variants": s.variants,
            "employees": s.employees,
            "carts": s.carts,
            "inventory": s.variants,  # chunked by variant id
            "inventory_movements": s.inventory_movements,
            "audit_log": s.audit_log,
            "price_history": s.price_history,
        }[kind]
        chunks = ranges(n, CHUNK_SIZES[kind])
    return [(kind, idx, lo, hi) for idx, lo, hi in chunks]


STAGES: list[tuple[str, list[str]]] = [
    ("B: customers, products, employees", ["customers", "products", "employees"]),
    ("C: addresses, product variants", ["addresses", "product_variants"]),
    (
        "D: orders and children, carts, inventory, movements, audit log, price history",
        ["orders", "audit_log", "inventory_movements", "carts", "inventory", "price_history"],
    ),
]


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


def run_seed(
    scale: Scale,
    seed: int,
    workers: int,
    force: bool = False,
    settings: Settings | None = None,
    log: Log = print,
) -> dict[str, int]:
    """Load a complete dataset. Returns rows loaded per table."""
    settings = settings or get_settings()
    started = time.perf_counter()
    loaded: Counter[str] = Counter()

    with connect("loader", settings) as conn:
        if has_post_load_triggers(conn):
            raise RuntimeError(
                "Triggers exist in schema shop (db/post_load was applied). Loading would fire them for every row and "
                "corrupt the data. To re-seed, recreate the database volume (docker compose down -v; docker compose "
                "up -d --wait), then seed, then run `shopdb post-load`."
            )
        existing = conn.execute(
            "SELECT (SELECT count(*) FROM shop.tenants) + (SELECT count(*) FROM shop.orders)"
        ).fetchone()[0]
        if existing and not force:
            raise RuntimeError(
                "The database already has data. Use --force to truncate it first, or run `shopdb reset`."
            )
        if existing:
            log("Truncating existing data ...")
            truncate_all(conn)

        t = time.perf_counter()
        log(f"Planning orders for scale {scale.name} (seed {seed}) ...")
        ctx = build_context(scale, seed)
        log(
            f"  planned {scale.orders:,} orders -> {ctx.totals['items']:,} lines, {ctx.totals['payments']:,} payments "
            f"({time.perf_counter() - t:.1f}s)"
        )

        t = time.perf_counter()
        with conn.cursor() as cur:
            for table, columns, rows in static_tables(ctx):
                loaded[table] += copy_rows(cur, table, columns, rows)
        conn.commit()
        log(
            f"Loaded lookups, tenants, categories, suppliers, warehouses ({time.perf_counter() - t:.1f}s)"
        )

    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(ctx,)
    ) as pool:
        for stage_name, kinds in STAGES:
            tasks = [task for kind in kinds for task in _tasks(ctx, kind)]
            log(f"Stage {stage_name}: {len(tasks)} chunks on {workers} workers")
            stage_started = time.perf_counter()
            futures = [pool.submit(_run_task, task) for task in tasks]
            for done, fut in enumerate(as_completed(futures), start=1):
                kind, idx, counts, secs = fut.result()  # re-raises any worker error
                loaded.update(counts)
                log(
                    f"  [{done}/{len(tasks)}] {kind} chunk {idx}: {sum(counts.values()):,} rows in {secs:.1f}s"
                )
            log(f"  stage finished in {time.perf_counter() - stage_started:.1f}s")

    with connect("loader", settings) as conn:
        n = reset_sequences(conn)
        log(f"Reset {n} identity sequences")

    log(f"Done: {sum(loaded.values()):,} rows in {time.perf_counter() - started:.1f}s")
    return dict(loaded)
