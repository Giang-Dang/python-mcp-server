"""Row generators, one function per chunk kind.

REGISTRY maps a task kind to a function  fn(ctx, chunk_index, first_id, last_id)  that returns a list of
(table, columns, rows). CHUNK_SIZES says how many ids each chunk covers.
"""

from . import append, core, orders

REGISTRY = {
    "customers": core.customers,
    "addresses": core.addresses,
    "products": core.products,
    "product_variants": core.product_variants,
    "employees": core.employees,
    "orders": orders.order_chunk,
    "carts": append.carts,
    "inventory": append.inventory,
    "inventory_movements": append.inventory_movements,
    "audit_log": append.audit_log,
    "price_history": append.price_history,
}

from shopdb.core.dataset.application import CHUNK_SIZES  # noqa: F401
