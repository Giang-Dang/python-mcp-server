from collections.abc import Iterable

from psycopg import sql

from shopdb.core.verification.domain import Measurements

from .connection import connect

SQL_CHECKS = {
    "order total = subtotal + tax + shipping - discount": "SELECT count(*) FROM shop.orders WHERE total_amount <> subtotal + tax_amount + shipping_amount - discount_amount",
    "order subtotal = sum of its lines": "SELECT count(*) FROM shop.orders o JOIN (SELECT order_id, sum(line_total) AS s FROM shop.order_items GROUP BY order_id) i ON i.order_id = o.order_id WHERE o.subtotal <> i.s",
    "every order has at least one line": "SELECT count(*) FROM shop.orders o WHERE NOT EXISTS (SELECT 1 FROM shop.order_items i WHERE i.order_id = o.order_id)",
    "order tenant = customer tenant": "SELECT count(*) FROM shop.orders o JOIN shop.customers c ON c.customer_id = o.customer_id WHERE o.tenant_id <> c.tenant_id",
    "payment tenant = order tenant": "SELECT count(*) FROM shop.payments p JOIN shop.orders o ON o.order_id = p.order_id WHERE p.tenant_id <> o.tenant_id",
    "customers.order_count = real number of orders": "SELECT count(*) FROM shop.customers c LEFT JOIN (SELECT customer_id, count(*) AS n FROM shop.orders GROUP BY customer_id) o ON o.customer_id = c.customer_id WHERE c.order_count <> coalesce(o.n, 0)",
    "refund payment belongs to the refunded order": "SELECT count(*) FROM shop.refunds r JOIN shop.payments p ON p.payment_id = r.payment_id WHERE p.order_id <> r.order_id",
    "invoice total = order total": "SELECT count(*) FROM shop.invoices i JOIN shop.orders o ON o.order_id = i.order_id WHERE i.total_amount <> o.total_amount",
    "P01 skew: share of orders placed by the top 1% of customers (%)": "SELECT round(100.0 * count(*) FILTER (WHERE customer_id <= (SELECT count(*) / 100 FROM shop.customers)) / count(*), 1) FROM shop.orders",
    "orders placed inside 2024-01-01 .. 2026-09-30": "SELECT count(*) FROM shop.orders WHERE placed_at < '2024-01-01 00:00:00+00' OR placed_at >= '2026-10-01 00:00:00+00'",
    "no order or shipment timestamp after 'now' (2026-10-02)": "SELECT (SELECT count(*) FROM shop.orders WHERE updated_at > '2026-10-02 00:00:00+00') + (SELECT count(*) FROM shop.shipments WHERE delivered_at > '2026-10-02 00:00:00+00')",
    "audit_log default partition is empty (every row fits a monthly partition)": "SELECT count(*) FROM shop.audit_log_default",
    "P06 soft-deleted customers (%)": "SELECT round(100.0 * count(*) FILTER (WHERE deleted_at IS NOT NULL) / count(*), 1) FROM shop.customers",
}


class Verifier:
    def __init__(self, settings):
        self.settings = settings

    def measure(self, tables: Iterable[str]) -> Measurements:
        counts = {}
        with connect("loader", self.settings) as conn:
            for table in tables:
                counts[table] = conn.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("shop", table))
                ).fetchone()[0]
            values = {
                name: float(conn.execute(query).fetchone()[0]) for name, query in SQL_CHECKS.items()
            }
            identity = conn.execute(
                """
                SELECT c.relname, a.attname FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'shop' AND a.attidentity <> '' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
                ORDER BY 1
                """
            ).fetchall()
            sequences = []
            for table, column in identity:
                row = conn.execute(
                    sql.SQL(
                        "SELECT pg_sequence_last_value(pg_get_serial_sequence(%s, %s)::regclass), max({col}) FROM {tbl}"
                    ).format(col=sql.Identifier(column), tbl=sql.Identifier("shop", table)),
                    (f"shop.{table}", column),
                ).fetchone()
                last_value, max_id = row
                sequences.append((table, last_value, max_id))
        return Measurements(counts, values, sequences)
