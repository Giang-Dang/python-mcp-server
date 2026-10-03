"""Order chunk generator: orders plus every table that hangs off an order, in one pass.

One chunk is loaded in a single transaction, so an order never appears without its lines, payments,
shipments, invoice or refund. Child ids come from the offsets computed by model.compute_order_layout.
"""

from __future__ import annotations

from random import Random

from ..context import SeedContext
from ..model import (
    CANCELLED,
    DELIVERED,
    ON_HOLD,
    ORDER_CHILDREN,
    PAID,
    PENDING,
    PROCESSING,
    REFUNDED,
    SALT_ORDER_DETAIL,
    SHIPPED,
    cents,
    clamp_ts,
    fmt_ts,
    hash3,
    plan_order,
    tenant_of,
    variant_delta_cents,
)
from .fake import faker_for
from .static import CARRIERS

ORDER_COLUMNS = (
    "order_id",
    "tenant_id",
    "customer_id",
    "status_id",
    "order_number",
    "channel",
    "currency_code",
    "subtotal",
    "tax_amount",
    "shipping_amount",
    "discount_amount",
    "total_amount",
    "shipping_address_id",
    "billing_address_id",
    "notes",
    "placed_at",
    "created_at",
    "updated_at",
    "deleted_at",
)
ITEM_COLUMNS = (
    "order_item_id",
    "order_id",
    "product_id",
    "variant_id",
    "quantity",
    "unit_price",
    "discount",
    "line_total",
    "created_at",
)
PAYMENT_COLUMNS = (
    "payment_id",
    "tenant_id",
    "order_id",
    "payment_method_id",
    "amount",
    "currency_code",
    "status",
    "provider_ref",
    "paid_at",
    "created_at",
    "updated_at",
)
SHIPMENT_COLUMNS = (
    "shipment_id",
    "order_id",
    "warehouse_id",
    "carrier",
    "tracking_number",
    "status",
    "shipped_at",
    "delivered_at",
    "created_at",
    "updated_at",
)
SHIPMENT_ITEM_COLUMNS = ("shipment_item_id", "shipment_id", "order_item_id", "quantity")
INVOICE_COLUMNS = (
    "invoice_id",
    "order_id",
    "invoice_number",
    "status",
    "total_amount",
    "issued_at",
    "due_at",
)
REFUND_COLUMNS = ("refund_id", "order_id", "payment_id", "amount", "reason", "status", "created_at")

CHANNEL_POOL = ["web"] * 11 + ["mobile"] * 6 + ["store"] * 2 + ["api"]
PAYMENT_METHOD_POOL = [1] * 10 + [2] * 4 + [3] * 2 + [4] * 3 + [5]  # card is the most common
PAYMENT_STATUS = {
    PENDING: "pending",
    PAID: "captured",
    PROCESSING: "captured",
    SHIPPED: "captured",
    DELIVERED: "captured",
    CANCELLED: "failed",
    REFUNDED: "refunded",
    ON_HOLD: "authorized",
}
REFUND_REASONS = [
    "damaged in transit",
    "wrong size",
    "not as described",
    "changed mind",
    "arrived late",
    "defective",
]


def order_chunk(ctx: SeedContext, idx: int, lo: int, hi: int):
    s, seed = ctx.scale, ctx.seed
    fake = faker_for("en_US", seed, SALT_ORDER_DETAIL, idx)
    rng = Random(hash3(seed, SALT_ORDER_DETAIL, idx))
    prices = ctx.product_prices()
    notes = [fake.sentence(nb_words=9) for _ in range(40)]

    off = ctx.order_offsets[idx]
    item_id, pay_id, ship_id, shi_id, inv_id, ref_id = (off[name] for name in ORDER_CHILDREN)

    orders, items, payments, shipments, shipment_items, invoices, refunds = ([] for _ in range(7))

    for oid in range(lo, hi + 1):
        p = plan_order(oid, s, seed)
        cid = p.customer_id
        tenant = tenant_of(cid, s, seed)
        placed = p.placed_ts
        placed_s = fmt_ts(placed)

        # Order lines. Popular products have low ids: u**3 piles probability onto small values.
        subtotal = 0
        lines = []
        for _ in range(p.n_items):
            product = 1 + int(s.products * rng.random() ** 3)
            variant = (
                (product - 1) * s.variants_per_product + 1 + rng.randrange(s.variants_per_product)
            )
            qty = 1 + (rng.randrange(1, 4) if rng.random() < 0.3 else 0)
            unit = prices[product] + variant_delta_cents(variant)
            discount = unit * qty // 10 if rng.random() < 0.1 else 0
            line_total = unit * qty - discount
            subtotal += line_total
            items.append(
                (
                    item_id,
                    oid,
                    product,
                    variant,
                    qty,
                    cents(unit),
                    cents(discount),
                    cents(line_total),
                    placed_s,
                )
            )
            lines.append((item_id, qty))
            item_id += 1

        tax = (subtotal * 8 + 50) // 100
        shipping = 0 if subtotal >= 10_000 else 599
        order_discount = subtotal * 5 // 100 if rng.random() < 0.1 else 0
        total = subtotal + tax + shipping - order_discount

        updated = clamp_ts(placed + (rng.randrange(0, 7 * 86400) if p.status_id != PENDING else 0))
        # Planted problem P06: about 4% of orders are soft-deleted but stay in the table.
        deleted = (
            fmt_ts(clamp_ts(updated + rng.randrange(86400, 200 * 86400)))
            if rng.random() < 0.04
            else None
        )
        orders.append(
            (
                oid,
                tenant,
                cid,
                p.status_id,
                f"ORD-{tenant:02d}-{oid:08d}",
                rng.choice(CHANNEL_POOL),
                "USD",
                cents(subtotal),
                cents(tax),
                cents(shipping),
                cents(order_discount),
                cents(total),
                2 * cid - 1,
                2 * cid,
                rng.choice(notes) if rng.random() < 0.1 else None,
                placed_s,
                placed_s,
                fmt_ts(updated),
                deleted,
            )
        )

        # Payments: a retry means the first attempt failed and the second one carries the real status.
        final_status = PAYMENT_STATUS[p.status_id]
        last_payment = pay_id
        for k in range(p.n_payments):
            status = "failed" if p.n_payments == 2 and k == 0 else final_status
            paid_at = (
                fmt_ts(clamp_ts(placed + rng.randrange(5, 600)))
                if status in ("captured", "refunded")
                else None
            )
            payments.append(
                (
                    pay_id,
                    tenant,
                    oid,
                    rng.choice(PAYMENT_METHOD_POOL),
                    cents(total),
                    "USD",
                    status,
                    f"pi_{rng.getrandbits(64):016x}",
                    paid_at,
                    placed_s,
                    paid_at or placed_s,
                )
            )
            last_payment = pay_id
            pay_id += 1

        # Shipments, and which order lines travel in which parcel.
        if p.n_shipments:
            shipment_ids = []
            for _ in range(p.n_shipments):
                shipped = clamp_ts(placed + rng.randrange(86400, 3 * 86400))
                delivered = None
                status = "in_transit"
                if p.status_id in (DELIVERED, REFUNDED):
                    delivered = clamp_ts(shipped + rng.randrange(2 * 86400, 7 * 86400))
                    status = "delivered" if p.status_id == DELIVERED else "returned"
                shipments.append(
                    (
                        ship_id,
                        oid,
                        rng.randrange(1, s.warehouses + 1),
                        rng.choice(CARRIERS),
                        f"1Z{rng.getrandbits(48):012X}",
                        status,
                        fmt_ts(shipped),
                        fmt_ts(delivered) if delivered else None,
                        fmt_ts(shipped),
                        fmt_ts(delivered or shipped),
                    )
                )
                shipment_ids.append(ship_id)
                ship_id += 1
            for j, (line_id, qty) in enumerate(lines):
                shipment_items.append((shi_id, shipment_ids[j % len(shipment_ids)], line_id, qty))
                shi_id += 1

        if p.has_invoice:
            issued = clamp_ts(placed + rng.randrange(60, 3600))
            invoices.append(
                (
                    inv_id,
                    oid,
                    f"INV-{inv_id:09d}",
                    "paid" if p.status_id in (DELIVERED, REFUNDED) else "issued",
                    cents(total),
                    fmt_ts(issued),
                    fmt_ts(issued + 30 * 86400),
                )
            )
            inv_id += 1

        if p.has_refund:
            amount = (
                total if p.status_id == REFUNDED else max(1, total * rng.randrange(20, 101) // 100)
            )
            created = clamp_ts(placed + rng.randrange(7 * 86400, 30 * 86400))
            refunds.append(
                (
                    ref_id,
                    oid,
                    last_payment,
                    cents(amount),
                    rng.choice(REFUND_REASONS),
                    "processed",
                    fmt_ts(created),
                )
            )
            ref_id += 1

    # Safety net: the ids we handed out must line up with the layout the planning pass computed.
    if idx + 1 < len(ctx.order_offsets):
        nxt = ctx.order_offsets[idx + 1]
        got = {
            "items": item_id,
            "payments": pay_id,
            "shipments": ship_id,
            "shipment_items": shi_id,
            "invoices": inv_id,
            "refunds": ref_id,
        }
        if got != nxt:
            raise RuntimeError(
                f"order chunk {idx}: id layout drifted: generated {got}, planned {nxt}"
            )

    return [
        ("shop.orders", ORDER_COLUMNS, orders),
        ("shop.order_items", ITEM_COLUMNS, items),
        ("shop.payments", PAYMENT_COLUMNS, payments),
        ("shop.shipments", SHIPMENT_COLUMNS, shipments),
        ("shop.shipment_items", SHIPMENT_ITEM_COLUMNS, shipment_items),
        ("shop.invoices", INVOICE_COLUMNS, invoices),
        ("shop.refunds", REFUND_COLUMNS, refunds),
    ]
