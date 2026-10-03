from .context import SeedContext
from .domain import ORDER_CHUNK, compute_order_layout, ranges
from .scales import Scale

CHUNK_SIZES = {
    "customers": 50_000,
    "addresses": 50_000,
    "products": 25_000,
    "product_variants": 100_000,
    "employees": 100_000,
    "carts": 100_000,
    "inventory": 100_000,
    "inventory_movements": 200_000,
    "audit_log": 250_000,
    "price_history": 100_000,
    # "orders" is chunked by model.ORDER_CHUNK because its ids depend on the planning pass.
}


def build_context(scale: Scale, seed: int) -> SeedContext:
    offsets, totals, order_counts = compute_order_layout(scale, seed)
    return SeedContext(
        scale=scale, seed=seed, order_offsets=offsets, totals=totals, order_counts=order_counts
    )


def tasks(ctx: SeedContext, kind: str) -> list[tuple[str, int, int, int]]:
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
