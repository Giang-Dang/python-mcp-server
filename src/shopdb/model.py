"""Deterministic business rules shared by the seeder, the verifier and the tests.

Nothing here touches the database. Every value is a pure function of (seed, id), so:
  - parallel workers can generate any slice of any table independently,
  - re-running with the same seed gives identical data,
  - child rows can refer to parent ids without looking them up.
"""

from __future__ import annotations

from array import array
from datetime import UTC, datetime
from typing import NamedTuple

from .config import Scale

MASK64 = (1 << 64) - 1

# Salts keep the hash streams for different purposes independent of each other.
SALT_ORDER = 1
SALT_TENANT = 2
SALT_COUNTRY = 3
SALT_PRICE = 4
SALT_CUSTOMER = 5
SALT_PRODUCT = 6
SALT_ADDRESS = 7
SALT_ORDER_DETAIL = 8
SALT_CART = 9
SALT_INVENTORY = 10
SALT_MOVEMENT = 11
SALT_AUDIT = 12
SALT_PRICE_HISTORY = 13
SALT_STATIC = 14
SALT_VARIANT = 15


def mix(x: int) -> int:
    """splitmix64 finalizer: a fast, well-distributed 64-bit hash of an integer."""
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


def hash3(seed: int, salt: int, i: int) -> int:
    """Deterministic 64-bit hash of (seed, salt, i)."""
    return mix((mix((seed << 20) ^ salt) + i) & MASK64)


# --------------------------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------------------------
def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


CUSTOMER_START_TS = _ts(2021, 1, 1)  # customers signed up before the order window opens
CUSTOMER_END_TS = _ts(2023, 12, 31)
PRODUCT_START_TS = _ts(2020, 1, 1)
START_TS = _ts(2024, 1, 1)  # first order
END_TS = _ts(2026, 10, 1)  # exclusive end of the order window
WINDOW = END_TS - START_TS
DATA_NOW_TS = _ts(2026, 10, 2)  # "now" for derived timestamps, so nothing lands in the future


def fmt_ts(ts: int) -> str:
    """Format epoch seconds as a Postgres timestamptz literal in UTC."""
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M:%S+00")


def clamp_ts(ts: int) -> int:
    return min(DATA_NOW_TS, ts)


def cents(value: int) -> str:
    """Integer cents -> '12.34'. Money is computed in integer cents to avoid rounding drift."""
    return f"{value // 100}.{value % 100:02d}"


# --------------------------------------------------------------------------------------------
# Order status ids (must match the rows in order_statuses, see generators/static.py)
# --------------------------------------------------------------------------------------------
PENDING, PAID, PROCESSING, SHIPPED, DELIVERED, CANCELLED, REFUNDED, ON_HOLD = range(1, 9)

HAS_INVOICE = frozenset({PAID, PROCESSING, SHIPPED, DELIVERED, REFUNDED})
HAS_SHIPMENT = frozenset({SHIPPED, DELIVERED, REFUNDED})
RETRYABLE_PAYMENT = frozenset({PAID, PROCESSING, SHIPPED, DELIVERED, REFUNDED})


# --------------------------------------------------------------------------------------------
# Per-entity rules
# --------------------------------------------------------------------------------------------
def tenant_of(customer_id: int, scale: Scale, seed: int) -> int:
    """Tenant 1 owns 40% of customers (it is the default tenant of the mcp_* roles); the rest share evenly."""
    h = hash3(seed, SALT_TENANT, customer_id)
    if scale.tenants == 1 or h % 100 < 40:
        return 1
    return 2 + (h >> 8) % (scale.tenants - 1)


COUNTRY_WEIGHTS = (("US", 55), ("GB", 12), ("DE", 10), ("FR", 8), ("CA", 8), ("AU", 7))


def country_of(entity_id: int, seed: int, salt: int = SALT_COUNTRY) -> str:
    r = hash3(seed, salt, entity_id) % 100
    total = 0
    for code, weight in COUNTRY_WEIGHTS:
        total += weight
        if r < total:
            return code
    return "US"


def price_cents(product_id: int, seed: int) -> int:
    """Base price in cents, 5.99 to 499.99, skewed towards cheap items."""
    u = (hash3(seed, SALT_PRICE, product_id) >> 11) / (1 << 53)
    return (5 + int(u * u * 495)) * 100 + 99


def variant_delta_cents(variant_id: int) -> int:
    """Bigger sizes cost a little more: slot 0..3 adds 0.00, 1.00, 2.00, 3.00."""
    return ((variant_id - 1) % 4) * 100


def inventory_warehouses(variant_id: int, scale: Scale) -> tuple[int, ...]:
    """The one or two warehouses that stock a variant."""
    a = 1 + variant_id % scale.warehouses
    b = 1 + (variant_id * 7 + 3) % scale.warehouses
    return (a,) if a == b else (a, b)


# --------------------------------------------------------------------------------------------
# The order plan: how an order looks, decided by hashing only
# --------------------------------------------------------------------------------------------
class OrderPlan(NamedTuple):
    customer_id: int
    status_id: int
    n_items: int
    n_payments: int
    n_shipments: int
    has_invoice: bool
    has_refund: bool
    placed_ts: int


def plan_order(order_id: int, scale: Scale, seed: int) -> OrderPlan:
    h1 = hash3(seed, SALT_ORDER, order_id)
    h2 = mix(h1)

    # Planted problem P01: 77/256 (about 30%) of orders go to the first 1% of customers.
    hot_customers = max(1, scale.customers // 100)
    if (h1 & 0xFF) < 77:
        customer_id = 1 + (h1 >> 8) % hot_customers
    else:
        customer_id = 1 + (h1 >> 8) % scale.customers

    # Older orders are almost all finished; the newest 7% are still moving through the pipeline.
    r = (h2 & 0xFFFF) / 65536.0
    if order_id <= scale.orders * 0.93:
        if r < 0.82:
            status = DELIVERED
        elif r < 0.88:
            status = CANCELLED
        elif r < 0.94:
            status = REFUNDED
        elif r < 0.97:
            status = SHIPPED
        elif r < 0.98:
            status = ON_HOLD
        elif r < 0.99:
            status = PROCESSING
        else:
            status = PAID
    else:
        if r < 0.20:
            status = PENDING
        elif r < 0.45:
            status = PAID
        elif r < 0.65:
            status = PROCESSING
        elif r < 0.85:
            status = SHIPPED
        elif r < 0.95:
            status = DELIVERED
        else:
            status = CANCELLED

    n_items = 1 + (h1 >> 40) % 5  # 1..5, average 3
    n_payments = 2 if ((h2 >> 16) & 15) == 0 and status in RETRYABLE_PAYMENT else 1
    n_shipments = 0
    if status in HAS_SHIPMENT:
        n_shipments = 2 if ((h2 >> 24) & 7) == 0 and n_items >= 2 else 1
    has_refund = status == REFUNDED or (status == DELIVERED and ((h2 >> 32) & 31) == 0)

    slot = max(1, WINDOW // scale.orders)
    placed_ts = START_TS + (order_id - 1) * WINDOW // scale.orders + (h2 >> 40) % slot

    return OrderPlan(
        customer_id=customer_id,
        status_id=status,
        n_items=n_items,
        n_payments=n_payments,
        n_shipments=n_shipments,
        has_invoice=status in HAS_INVOICE,
        has_refund=has_refund,
        placed_ts=placed_ts,
    )


# --------------------------------------------------------------------------------------------
# Chunking and the planning pass
# --------------------------------------------------------------------------------------------
ORDER_CHUNK = 25_000
ORDER_CHILDREN = ("items", "payments", "shipments", "shipment_items", "invoices", "refunds")


def ranges(n: int, size: int) -> list[tuple[int, int, int]]:
    """Split ids 1..n into (chunk_index, first_id, last_id) pieces of at most `size` ids."""
    return [(i, lo, min(lo + size - 1, n)) for i, lo in enumerate(range(1, n + 1, size))]


def compute_order_layout(scale: Scale, seed: int, chunk_size: int = ORDER_CHUNK):
    """Walk every order once to find out, without touching the database:

    - offsets[i]: the first id each child table must use for order chunk i (so parallel chunks never collide),
    - totals: the final row count of each child table,
    - order_counts[c]: how many orders customer c placed (stored in customers.order_count).
    """
    order_counts = array("i", [0]) * (scale.customers + 1)
    totals = dict.fromkeys(ORDER_CHILDREN, 0)
    offsets: list[dict[str, int]] = []
    for _idx, lo, hi in ranges(scale.orders, chunk_size):
        offsets.append({name: count + 1 for name, count in totals.items()})
        for order_id in range(lo, hi + 1):
            p = plan_order(order_id, scale, seed)
            order_counts[p.customer_id] += 1
            totals["items"] += p.n_items
            totals["payments"] += p.n_payments
            totals["shipments"] += p.n_shipments
            if p.n_shipments:
                totals["shipment_items"] += p.n_items
            if p.has_invoice:
                totals["invoices"] += 1
            if p.has_refund:
                totals["refunds"] += 1
    return offsets, totals, order_counts


def inventory_row_count(scale: Scale) -> int:
    return sum(len(inventory_warehouses(v, scale)) for v in range(1, scale.variants + 1))
