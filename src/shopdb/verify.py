"""Checks that a seeded database matches what the model says it should contain."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import sql

from .config import Scale, Settings, get_settings
from .context import SeedContext
from .db import connect
from .generators.static import COUNTRIES, CURRENCIES, ORDER_STATUSES, PAYMENT_METHODS
from .loader import build_context
from .model import DATA_NOW_TS, END_TS, START_TS, fmt_ts, inventory_row_count


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def expected_counts(ctx: SeedContext) -> dict[str, int]:
    s, t = ctx.scale, ctx.totals
    return {
        "currencies": len(CURRENCIES),
        "countries": len(COUNTRIES),
        "order_statuses": len(ORDER_STATUSES),
        "payment_methods": len(PAYMENT_METHODS),
        "tenants": s.tenants,
        "categories": s.categories,
        "suppliers": s.suppliers,
        "warehouses": s.warehouses,
        "employees": s.employees,
        "customers": s.customers,
        "addresses": s.addresses,
        "products": s.products,
        "product_variants": s.variants,
        "carts": s.carts,
        "orders": s.orders,
        "order_items": t["items"],
        "payments": t["payments"],
        "shipments": t["shipments"],
        "shipment_items": t["shipment_items"],
        "invoices": t["invoices"],
        "refunds": t["refunds"],
        "inventory": inventory_row_count(s),
        "inventory_movements": s.inventory_movements,
        "audit_log": s.audit_log,
        "price_history": s.price_history,
    }


# Each check is a query that returns one number plus a rule for what that number must be.
SQL_CHECKS: list[tuple[str, str, str, tuple[float, float]]] = [
    (
        "order total = subtotal + tax + shipping - discount",
        "SELECT count(*) FROM shop.orders WHERE total_amount <> subtotal + tax_amount + shipping_amount - discount_amount",
        "mismatching orders",
        (0, 0),
    ),
    (
        "order subtotal = sum of its lines",
        (
            "SELECT count(*) FROM shop.orders o JOIN (SELECT order_id, sum(line_total) AS s FROM shop.order_items GROUP BY order_id) i "
            "ON i.order_id = o.order_id WHERE o.subtotal <> i.s"
        ),
        "mismatching orders",
        (0, 0),
    ),
    (
        "every order has at least one line",
        "SELECT count(*) FROM shop.orders o WHERE NOT EXISTS (SELECT 1 FROM shop.order_items i WHERE i.order_id = o.order_id)",
        "orders without lines",
        (0, 0),
    ),
    (
        "order tenant = customer tenant",
        "SELECT count(*) FROM shop.orders o JOIN shop.customers c ON c.customer_id = o.customer_id WHERE o.tenant_id <> c.tenant_id",
        "mismatching orders",
        (0, 0),
    ),
    (
        "payment tenant = order tenant",
        "SELECT count(*) FROM shop.payments p JOIN shop.orders o ON o.order_id = p.order_id WHERE p.tenant_id <> o.tenant_id",
        "mismatching payments",
        (0, 0),
    ),
    (
        "customers.order_count = real number of orders",
        (
            "SELECT count(*) FROM shop.customers c LEFT JOIN (SELECT customer_id, count(*) AS n FROM shop.orders GROUP BY customer_id) o "
            "ON o.customer_id = c.customer_id WHERE c.order_count <> coalesce(o.n, 0)"
        ),
        "mismatching customers",
        (0, 0),
    ),
    (
        "refund payment belongs to the refunded order",
        "SELECT count(*) FROM shop.refunds r JOIN shop.payments p ON p.payment_id = r.payment_id WHERE p.order_id <> r.order_id",
        "mismatching refunds",
        (0, 0),
    ),
    (
        "invoice total = order total",
        "SELECT count(*) FROM shop.invoices i JOIN shop.orders o ON o.order_id = i.order_id WHERE i.total_amount <> o.total_amount",
        "mismatching invoices",
        (0, 0),
    ),
    (
        "P01 skew: share of orders placed by the top 1% of customers (%)",
        "SELECT round(100.0 * count(*) FILTER (WHERE customer_id <= (SELECT count(*) / 100 FROM shop.customers)) / count(*), 1) FROM shop.orders",
        "percent",
        (25, 40),
    ),
    (
        "orders placed inside 2024-01-01 .. 2026-09-30",
        f"SELECT count(*) FROM shop.orders WHERE placed_at < '{fmt_ts(START_TS)}' OR placed_at >= '{fmt_ts(END_TS)}'",
        "orders outside the window",
        (0, 0),
    ),
    (
        "no order or shipment timestamp after 'now' (2026-10-02)",
        (
            f"SELECT (SELECT count(*) FROM shop.orders WHERE updated_at > '{fmt_ts(DATA_NOW_TS)}') "
            f"+ (SELECT count(*) FROM shop.shipments WHERE delivered_at > '{fmt_ts(DATA_NOW_TS)}')"
        ),
        "rows in the future",
        (0, 0),
    ),
    (
        "audit_log default partition is empty (every row fits a monthly partition)",
        "SELECT count(*) FROM shop.audit_log_default",
        "rows in default partition",
        (0, 0),
    ),
    (
        "P06 soft-deleted customers (%)",
        "SELECT round(100.0 * count(*) FILTER (WHERE deleted_at IS NOT NULL) / count(*), 1) FROM shop.customers",
        "percent",
        (4, 8),
    ),
]


def run_verify(scale: Scale, seed: int, settings: Settings | None = None) -> list[Check]:
    settings = settings or get_settings()
    ctx = build_context(scale, seed)
    results: list[Check] = []

    with connect("loader", settings) as conn:
        for table, want in expected_counts(ctx).items():
            got = conn.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("shop", table))
            ).fetchone()[0]
            results.append(Check(f"rows in {table}", got == want, f"{got:,} (expected {want:,})"))

        for name, query, unit, (low, high) in SQL_CHECKS:
            value = float(conn.execute(query).fetchone()[0])
            results.append(
                Check(name, low <= value <= high, f"{value:g} {unit} (allowed {low:g}..{high:g})")
            )

        identity = conn.execute(
            """
            SELECT c.relname, a.attname FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'shop' AND a.attidentity <> '' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
            ORDER BY 1
            """
        ).fetchall()
        behind = []
        for table, column in identity:
            row = conn.execute(
                sql.SQL(
                    "SELECT pg_sequence_last_value(pg_get_serial_sequence(%s, %s)::regclass), max({col}) FROM {tbl}"
                ).format(col=sql.Identifier(column), tbl=sql.Identifier("shop", table)),
                (f"shop.{table}", column),
            ).fetchone()
            last_value, max_id = row
            if max_id is not None and (last_value is None or last_value < max_id):
                behind.append(table)
        results.append(
            Check(
                f"identity sequences are past max(id) ({len(identity)} tables)",
                not behind,
                ", ".join(behind) or "all ok",
            )
        )

    return results
