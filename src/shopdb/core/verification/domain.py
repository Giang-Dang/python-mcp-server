from dataclasses import dataclass

from shopdb.core.dataset.context import SeedContext
from shopdb.core.dataset.domain import inventory_row_count
from shopdb.core.dataset.lookups import COUNTRIES, CURRENCIES, ORDER_STATUSES, PAYMENT_METHODS


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


@dataclass(frozen=True)
class IntegrityRule:
    name: str
    unit: str
    low: float
    high: float


@dataclass
class Measurements:
    counts: dict[str, int]
    values: dict[str, float]
    sequences: list[tuple[str, int | None, int | None]]


INTEGRITY_RULES = (
    IntegrityRule("order total = subtotal + tax + shipping - discount", "mismatching orders", 0, 0),
    IntegrityRule("order subtotal = sum of its lines", "mismatching orders", 0, 0),
    IntegrityRule("every order has at least one line", "orders without lines", 0, 0),
    IntegrityRule("order tenant = customer tenant", "mismatching orders", 0, 0),
    IntegrityRule("payment tenant = order tenant", "mismatching payments", 0, 0),
    IntegrityRule("customers.order_count = real number of orders", "mismatching customers", 0, 0),
    IntegrityRule("refund payment belongs to the refunded order", "mismatching refunds", 0, 0),
    IntegrityRule("invoice total = order total", "mismatching invoices", 0, 0),
    IntegrityRule(
        "P01 skew: share of orders placed by the top 1% of customers (%)", "percent", 25, 40
    ),
    IntegrityRule(
        "orders placed inside 2024-01-01 .. 2026-09-30", "orders outside the window", 0, 0
    ),
    IntegrityRule(
        "no order or shipment timestamp after 'now' (2026-10-02)", "rows in the future", 0, 0
    ),
    IntegrityRule(
        "audit_log default partition is empty (every row fits a monthly partition)",
        "rows in default partition",
        0,
        0,
    ),
    IntegrityRule("P06 soft-deleted customers (%)", "percent", 4, 8),
)
