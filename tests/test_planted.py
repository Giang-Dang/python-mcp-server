"""Guards for the planted problems (docs/planted-problems.md).

Each test proves that a deliberate weakness still exists. If one fails, somebody "fixed" a problem (added an index, ran
ANALYZE, re-enabled autovacuum, ...). That is a decision to make on purpose, not by accident.

The tests work at both profiles (S and M) and never change real data: reads, rolled-back transactions, and one scratch
table that is dropped afterwards. Skipped when the database is down or empty.
"""

import re
import threading

import psycopg
import pytest

from shopdb.db import connect


@pytest.fixture(scope="module")
def conn():
    try:
        c = connect("loader", autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("database is not running (docker compose up -d --wait)")
    if c.execute("SELECT count(*) FROM shop.orders").fetchone()[0] == 0:
        pytest.skip("database is empty (poetry run shopdb seed)")
    yield c
    c.close()


def plan(conn, sql: str, analyze: bool = False) -> dict:
    """Root node of the JSON query plan. EXPLAIN ANALYZE really runs the query (use it on SELECTs only)."""
    options = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
    row = conn.execute(f"EXPLAIN ({options}) {sql}").fetchone()[0]
    return row[0]["Plan"]


def nodes(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from nodes(child)


def scans_of(root: dict, relation: str) -> list[str]:
    """Node types that read the given relation, e.g. ['Seq Scan'] or ['Bitmap Heap Scan', 'Index Scan']."""
    return [n["Node Type"] for n in nodes(root) if n.get("Relation Name") == relation]


# --------------------------------------------------------------------------------------------
# P01 skew
# --------------------------------------------------------------------------------------------
def test_p01_skew_top_one_percent_of_customers_place_about_30_percent_of_orders(conn):
    share = conn.execute(
        """
        SELECT 100.0 * count(*) FILTER (WHERE customer_id <= (SELECT count(*) / 100 FROM shop.customers)) / count(*)
        FROM shop.orders
        """
    ).fetchone()[0]
    assert 25 <= share <= 40


def test_p01_planner_underestimates_a_hot_customer(conn):
    root = plan(conn, "SELECT * FROM shop.orders WHERE customer_id = 1", analyze=True)
    orders = next(n for n in nodes(root) if n.get("Relation Name") == "orders")
    assert orders["Actual Rows"] >= 2 * orders["Plan Rows"], (
        "the planner assumes every customer is average"
    )


# --------------------------------------------------------------------------------------------
# P02 foreign key without an index
# --------------------------------------------------------------------------------------------
def test_p02_order_items_product_id_has_no_index(conn):
    indexes = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'shop' AND tablename = 'order_items'"
    ).fetchall()
    assert not [d for (d,) in indexes if "(product_id" in d]


def test_p02_lookup_by_product_scans_the_whole_table(conn):
    root = plan(conn, "SELECT count(*) FROM shop.order_items WHERE product_id = 42")
    assert "Seq Scan" in scans_of(root, "order_items")


# --------------------------------------------------------------------------------------------
# P03 partitioned table queried without the partition key
# --------------------------------------------------------------------------------------------
def test_p03_without_a_date_filter_every_partition_is_probed(conn):
    root = plan(
        conn,
        "SELECT count(*) FROM shop.audit_log WHERE table_name = 'orders' AND record_id = 123456",
    )
    partitions = {
        n["Relation Name"]
        for n in nodes(root)
        if str(n.get("Relation Name", "")).startswith("audit_log_")
    }
    assert len(partitions) >= 37, f"only {len(partitions)} partitions probed"


def test_p03_with_a_one_month_filter_a_single_partition_is_used(conn):
    root = plan(
        conn,
        "SELECT count(*) FROM shop.audit_log WHERE table_name = 'orders' AND record_id = 123456 "
        "AND created_at >= '2026-09-01' AND created_at < '2026-10-01'",
    )
    partitions = {
        n["Relation Name"]
        for n in nodes(root)
        if str(n.get("Relation Name", "")).startswith("audit_log_")
    }
    assert partitions == {"audit_log_2026_09"}


# --------------------------------------------------------------------------------------------
# P04 LIKE '%x%' without a trigram index
# --------------------------------------------------------------------------------------------
def test_p04_pg_trgm_is_installed_but_no_trigram_index_exists(conn):
    assert (
        conn.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'").fetchone()[0]
        == 1
    )
    assert (
        conn.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%gin_trgm_ops%'"
        ).fetchone()[0]
        == 0
    )


def test_p04_infix_search_scans_every_product(conn):
    root = plan(conn, "SELECT count(*) FROM shop.products WHERE description ILIKE '%wool%'")
    assert "Seq Scan" in scans_of(root, "products")


# --------------------------------------------------------------------------------------------
# P05 JSONB bloat
# --------------------------------------------------------------------------------------------
def test_p05_products_table_is_bloated_by_rewritten_documents(conn):
    options = (
        conn.execute(
            "SELECT reloptions FROM pg_class WHERE oid = 'shop.products'::regclass"
        ).fetchone()[0]
        or []
    )
    assert "autovacuum_enabled=false" in options
    table_bytes, rows, row_width = conn.execute(
        "SELECT pg_table_size('shop.products'), count(*), avg(pg_column_size(p.*)) FROM shop.products p"
    ).fetchone()
    assert table_bytes / rows >= 2 * float(row_width), (
        "dead row versions should at least double the size per row"
    )


def test_p05_attributes_documents_are_large_and_unindexed(conn):
    avg_bytes = conn.execute(
        "SELECT avg(pg_column_size(attributes)) FROM shop.products"
    ).fetchone()[0]
    assert avg_bytes > 700
    assert not conn.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = 'shop' AND tablename = 'products' AND indexdef ILIKE '%attributes%'"
    ).fetchall()


# --------------------------------------------------------------------------------------------
# P06 soft-deleted rows
# --------------------------------------------------------------------------------------------
def test_p06_soft_deleted_rows_stay_in_the_tables(conn):
    customers = conn.execute(
        "SELECT 100.0 * count(deleted_at) / count(*) FROM shop.customers"
    ).fetchone()[0]
    orders = conn.execute(
        "SELECT 100.0 * count(deleted_at) / count(*) FROM shop.orders"
    ).fetchone()[0]
    assert 4 <= customers <= 8
    assert 2.5 <= orders <= 6


def test_p06_no_partial_indexes_exclude_deleted_rows(conn):
    partial = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'shop' AND indexdef ILIKE '%deleted_at IS NULL%'"
    ).fetchall()
    assert partial == []


# --------------------------------------------------------------------------------------------
# P07 stale statistics
# --------------------------------------------------------------------------------------------
def test_p07_carts_statistics_are_stale_and_autovacuum_is_off(conn):
    options = (
        conn.execute(
            "SELECT reloptions FROM pg_class WHERE oid = 'shop.carts'::regclass"
        ).fetchone()[0]
        or []
    )
    assert "autovacuum_enabled=false" in options
    root = plan(conn, "SELECT * FROM shop.carts WHERE status = 'open'", analyze=True)
    carts = next(n for n in nodes(root) if n.get("Relation Name") == "carts")
    assert carts["Actual Rows"] >= 2 * carts["Plan Rows"], (
        "the planner should underestimate open carts by at least 2x"
    )


# --------------------------------------------------------------------------------------------
# P08 hot-row contention
# --------------------------------------------------------------------------------------------
def test_p08_two_sessions_cannot_update_the_same_inventory_row_at_once(conn):
    row = conn.execute(
        "SELECT warehouse_id, variant_id FROM shop.inventory ORDER BY variant_id LIMIT 1"
    ).fetchone()
    update = "UPDATE shop.inventory SET reorder_point = reorder_point WHERE (warehouse_id, variant_id) = (%s, %s)"
    with connect("loader") as first, connect("loader") as second:
        first.execute(update, row)  # holds the row lock until the transaction ends
        second.execute("SET lock_timeout = '500ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            second.execute(update, row)  # a popular variant makes every order wait here
        second.rollback()
        first.rollback()


# --------------------------------------------------------------------------------------------
# P09 unbounded queries / P10 huge result sets
# --------------------------------------------------------------------------------------------
def test_p09_an_accidental_cross_join_is_stopped_only_by_statement_timeout():
    with connect("mcp_reader") as reader:
        reader.execute("SET statement_timeout = '1500ms'")
        with pytest.raises(psycopg.errors.QueryCanceled):
            reader.execute("SELECT count(*) FROM shop.orders a CROSS JOIN shop.customers b")


def test_p09_the_reader_role_has_a_default_statement_timeout():
    with connect("mcp_reader") as reader:
        assert reader.execute("SHOW statement_timeout").fetchone()[0] == "15s"


def test_p10_select_star_on_a_big_table_returns_a_huge_result_set(conn):
    root = plan(conn, "SELECT * FROM shop.order_items")
    assert root["Plan Rows"] >= 500_000, (
        "without a LIMIT this would stream the whole table to the client"
    )


# --------------------------------------------------------------------------------------------
# P11 deadlock between two transactions that lock rows in opposite order
# --------------------------------------------------------------------------------------------
def test_p11_opposite_lock_order_produces_a_deadlock(conn):
    rows = conn.execute(
        "SELECT warehouse_id, variant_id FROM shop.inventory ORDER BY variant_id LIMIT 2"
    ).fetchall()
    update = "UPDATE shop.inventory SET reorder_point = reorder_point WHERE (warehouse_id, variant_id) = (%s, %s)"
    both_hold_one = threading.Barrier(2, timeout=15)
    outcomes: dict[str, str] = {}

    def worker(name: str, first: tuple, second: tuple) -> None:
        with connect("loader") as c:
            try:
                c.execute(update, first)
                both_hold_one.wait()
                c.execute(update, second)
                outcomes[name] = "finished"
            except psycopg.errors.DeadlockDetected:
                outcomes[name] = "deadlock"
            finally:
                c.rollback()

    a = threading.Thread(target=worker, args=("a", rows[0], rows[1]))
    b = threading.Thread(target=worker, args=("b", rows[1], rows[0]))
    a.start()
    b.start()
    a.join(30)
    b.join(30)
    assert sorted(outcomes.values()) == ["deadlock", "finished"], outcomes


# --------------------------------------------------------------------------------------------
# P12 a long transaction stops VACUUM from removing dead rows
# --------------------------------------------------------------------------------------------
def test_p12_an_open_transaction_keeps_vacuum_from_reclaiming_dead_rows():
    with connect("shop_owner", autocommit=True) as owner:
        owner.execute("DROP TABLE IF EXISTS shop._p12_scratch")
        owner.execute(
            "CREATE TABLE shop._p12_scratch (id int PRIMARY KEY, v int) WITH (autovacuum_enabled = false)"
        )
        try:
            owner.execute(
                "INSERT INTO shop._p12_scratch SELECT g, 0 FROM generate_series(1, 5000) g"
            )

            def dead_rows() -> int:
                owner.execute("VACUUM shop._p12_scratch")
                return owner.execute(
                    "SELECT n_dead_tup FROM pg_stat_user_tables WHERE relname = '_p12_scratch'"
                ).fetchone()[0]

            long_txn = connect("shop_owner")
            long_txn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            long_txn.execute(
                "SELECT count(*) FROM shop._p12_scratch"
            )  # takes a snapshot and keeps it
            owner.execute("UPDATE shop._p12_scratch SET v = v + 1")  # leaves 5000 old versions

            while_open = dead_rows()
            long_txn.rollback()
            long_txn.close()
            after_close = dead_rows()
        finally:
            owner.execute("DROP TABLE IF EXISTS shop._p12_scratch")

    assert while_open >= 4000, (
        f"vacuum should not be able to remove rows that the open snapshot can still see ({while_open})"
    )
    assert after_close <= 100, f"once the transaction ends vacuum can clean up ({after_close})"


# --------------------------------------------------------------------------------------------
# P13 slow trigger
# --------------------------------------------------------------------------------------------
def test_p13_shipment_status_trigger_scans_the_whole_table(conn):
    assert (
        conn.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_carrier_sla' AND NOT tgisinternal"
        ).fetchone()[0]
        == 1
    )
    body = conn.execute(
        "SELECT prosrc FROM pg_proc WHERE proname = 'carrier_sla_check'"
    ).fetchone()[0]
    # Take the SELECT out of the PL/pgSQL body. "INTO a, b" only exists in PL/pgSQL, so remove it to get plain SQL.
    select = re.search(r"SELECT .*?;", body, re.DOTALL).group(0).rstrip(";")
    query = re.sub(r"\bINTO\s+[\w\s,]+?(?=\s+FROM\b)", "", select).replace("NEW.carrier", "'UPS'")
    root = plan(conn, query)
    assert "Seq Scan" in scans_of(root, "shipments"), (
        "no index on shipments(carrier), so every updated row scans the table"
    )
