"""Generators for the high-volume tables: carts, inventory, stock movements, audit log, price history.

These use Python's random module and small pools instead of calling Faker per row. At the M profile the
audit log alone has 30 million rows, and Faker costs tens of microseconds per call.
"""

from __future__ import annotations

from random import Random

from ..context import SeedContext
from ..model import (
    SALT_AUDIT,
    SALT_CART,
    SALT_INVENTORY,
    SALT_MOVEMENT,
    SALT_PRICE_HISTORY,
    START_TS,
    WINDOW,
    cents,
    clamp_ts,
    fmt_ts,
    hash3,
    inventory_warehouses,
    plan_order,
    tenant_of,
)

CART_COLUMNS = ("cart_id", "customer_id", "status", "created_at", "updated_at", "expires_at")


def carts(ctx: SeedContext, idx: int, lo: int, hi: int):
    s = ctx.scale
    rng = Random(hash3(ctx.seed, SALT_CART, idx))
    rows = []
    for cart_id in range(lo, hi + 1):
        created = START_TS + rng.randrange(WINDOW)
        r = rng.random()
        status = "converted" if r < 0.30 else "abandoned" if r < 0.80 else "open"
        rows.append(
            (
                cart_id,
                1 + rng.randrange(s.customers),
                status,
                fmt_ts(created),
                fmt_ts(clamp_ts(created + rng.randrange(0, 3 * 86400))),
                fmt_ts(created + 7 * 86400),
            )
        )
    return [("shop.carts", CART_COLUMNS, rows)]


INVENTORY_COLUMNS = (
    "warehouse_id",
    "variant_id",
    "quantity_on_hand",
    "quantity_reserved",
    "reorder_point",
    "updated_at",
)


def inventory(ctx: SeedContext, idx: int, lo: int, hi: int):
    """lo..hi are variant ids; each variant is stocked in one or two warehouses."""
    s = ctx.scale
    rng = Random(hash3(ctx.seed, SALT_INVENTORY, idx))
    rows = []
    for variant in range(lo, hi + 1):
        for warehouse in inventory_warehouses(variant, s):
            on_hand = 0 if rng.random() < 0.05 else min(2000, int(rng.expovariate(1 / 120)))
            rows.append(
                (
                    warehouse,
                    variant,
                    on_hand,
                    min(on_hand, rng.randrange(0, 5)),
                    rng.randrange(5, 50),
                    fmt_ts(START_TS + rng.randrange(WINDOW)),
                )
            )
    return [("shop.inventory", INVENTORY_COLUMNS, rows)]


MOVEMENT_COLUMNS = (
    "movement_id",
    "warehouse_id",
    "variant_id",
    "movement_type",
    "quantity",
    "reference_type",
    "reference_id",
    "created_at",
)


def inventory_movements(ctx: SeedContext, idx: int, lo: int, hi: int):
    """A synthetic ledger. It follows the right shapes (sales negative, receipts positive) but is not
    reconciled with inventory.quantity_on_hand or with the actual order lines."""
    s = ctx.scale
    rng = Random(hash3(ctx.seed, SALT_MOVEMENT, idx))
    rows = []
    for movement_id in range(lo, hi + 1):
        variant = 1 + int(s.variants * rng.random() ** 2.5)  # popular variants have low ids
        warehouses = inventory_warehouses(variant, s)
        warehouse = warehouses[rng.randrange(len(warehouses))]
        r = rng.random()
        if r < 0.70:
            kind, qty, ref = "sale", -rng.randrange(1, 6), ("order", 1 + rng.randrange(s.orders))
        elif r < 0.90:
            kind, qty, ref = (
                "receipt",
                rng.randrange(20, 501),
                ("purchase_order", 1 + rng.randrange(50_000)),
            )
        elif r < 0.95:
            kind, qty, ref = "adjustment", rng.choice((-1, 1)) * rng.randrange(1, 21), (None, None)
        elif r < 0.99:
            kind, qty, ref = "return", rng.randrange(1, 4), ("order", 1 + rng.randrange(s.orders))
        else:
            kind, qty, ref = (
                "transfer",
                rng.choice((-1, 1)) * rng.randrange(10, 101),
                ("transfer", 1 + rng.randrange(5_000)),
            )
        rows.append(
            (
                movement_id,
                warehouse,
                variant,
                kind,
                qty,
                ref[0],
                ref[1],
                fmt_ts(START_TS + rng.randrange(WINDOW)),
            )
        )
    return [("shop.inventory_movements", MOVEMENT_COLUMNS, rows)]


AUDIT_COLUMNS = (
    "audit_id",
    "created_at",
    "tenant_id",
    "table_name",
    "record_id",
    "action",
    "changed_by",
    "old_data",
    "new_data",
)
AUDIT_TABLES = ["orders"] * 9 + ["payments"] * 4 + ["customers"] * 4 + ["products"] * 3
AUDIT_USERS = ["app", "app", "app", "support", "batch_job", "admin", "api"]
ORDER_STATUS_NAMES = [
    "pending",
    "paid",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
    "on_hold",
]


def _audit_doc(table: str, rng: Random) -> str:
    """A small JSON document, built with string formatting (much faster than json.dumps for 30M rows)."""
    flag = rng.choice(("true", "false"))
    if table == "orders":
        status, amount = rng.choice(ORDER_STATUS_NAMES), cents(rng.randrange(599, 90_000))
        return f'{{"status": "{status}", "total_amount": "{amount}"}}'
    if table == "payments":
        status = rng.choice(("pending", "captured", "failed", "refunded"))
        amount = cents(rng.randrange(599, 90_000))
        return f'{{"status": "{status}", "amount": "{amount}"}}'
    if table == "customers":
        tier = rng.choice(("standard", "silver", "gold"))
        return f'{{"tier": "{tier}", "marketing_opt_in": {flag}}}'
    return f'{{"base_price": "{cents(rng.randrange(599, 50_000))}", "is_active": {flag}}}'


def audit_log(ctx: SeedContext, idx: int, lo: int, hi: int):
    """Rows are routed by created_at into the monthly partitions of shop.audit_log."""
    s, seed = ctx.scale, ctx.seed
    rng = Random(hash3(seed, SALT_AUDIT, idx))
    max_record = {
        "orders": s.orders,
        "payments": ctx.totals["payments"],
        "customers": s.customers,
        "products": s.products,
    }
    rows = []
    for audit_id in range(lo, hi + 1):
        table = rng.choice(AUDIT_TABLES)
        record = 1 + rng.randrange(max_record[table])
        if table in ("orders", "payments"):
            tenant = tenant_of(plan_order(min(record, s.orders), s, seed).customer_id, s, seed)
        elif table == "customers":
            tenant = tenant_of(record, s, seed)
        else:
            tenant = None
        r = rng.random()
        action = "I" if r < 0.35 else "U" if r < 0.98 else "D"
        old = None if action == "I" else _audit_doc(table, rng)
        new = None if action == "D" else _audit_doc(table, rng)
        rows.append(
            (
                audit_id,
                fmt_ts(START_TS + rng.randrange(WINDOW)),
                tenant,
                table,
                record,
                action,
                rng.choice(AUDIT_USERS),
                old,
                new,
            )
        )
    return [("shop.audit_log", AUDIT_COLUMNS, rows)]


PRICE_HISTORY_COLUMNS = (
    "price_history_id",
    "product_id",
    "old_price",
    "new_price",
    "changed_at",
    "changed_by",
)


def price_history(ctx: SeedContext, idx: int, lo: int, hi: int):
    s = ctx.scale
    rng = Random(hash3(ctx.seed, SALT_PRICE_HISTORY, idx))
    prices = ctx.product_prices()
    rows = []
    for history_id in range(lo, hi + 1):
        product = 1 + int(s.products * rng.random() ** 2)
        old = prices[product] * rng.randrange(80, 121) // 100
        new = max(99, old * rng.randrange(90, 111) // 100)
        rows.append(
            (
                history_id,
                product,
                cents(old) if rng.random() > 0.05 else None,
                cents(new),
                fmt_ts(START_TS + rng.randrange(WINDOW)),
                rng.choice(("pricing_bot", "admin", "supplier_feed")),
            )
        )
    return [("shop.price_history", PRICE_HISTORY_COLUMNS, rows)]
