"""Chunk generators for the core entity tables.

Every generator has the signature  fn(ctx, chunk_index, first_id, last_id)  and returns a list of
(table, columns, rows) to COPY, in foreign-key order. Rows are tuples of strings, numbers, bools or None.
"""

from __future__ import annotations

import json
from random import Random

from ..context import SeedContext
from ..model import (
    CUSTOMER_END_TS,
    CUSTOMER_START_TS,
    DATA_NOW_TS,
    PRODUCT_START_TS,
    SALT_ADDRESS,
    SALT_CUSTOMER,
    SALT_PRODUCT,
    SALT_STATIC,
    START_TS,
    cents,
    clamp_ts,
    country_of,
    fmt_ts,
    hash3,
    tenant_of,
    variant_delta_cents,
)
from .fake import faker_by_country, faker_for, slug

EMAIL_DOMAINS = (
    "mail.example.test",
    "post.example.test",
    "inbox.example.test",
    "web.example.test",
    "net.example.test",
)

CUSTOMER_COLUMNS = (
    "customer_id",
    "tenant_id",
    "email",
    "first_name",
    "last_name",
    "phone",
    "tier",
    "order_count",
    "marketing_opt_in",
    "created_at",
    "updated_at",
    "deleted_at",
)


def customers(ctx: SeedContext, idx: int, lo: int, hi: int):
    s = ctx.scale
    fake = faker_for("en_US", ctx.seed, SALT_CUSTOMER, idx)
    rng = Random(hash3(ctx.seed, SALT_CUSTOMER, idx))
    span = CUSTOMER_END_TS - CUSTOMER_START_TS
    rows = []
    for cid in range(lo, hi + 1):
        first, last = fake.first_name(), fake.last_name()
        created = CUSTOMER_START_TS + rng.randrange(span)
        updated = clamp_ts(created + rng.randrange(0, 900 * 86400))
        # Planted problem P06: about 6% of customers are soft-deleted but stay in the table.
        deleted = (
            fmt_ts(clamp_ts(updated + rng.randrange(86400, 400 * 86400)))
            if rng.random() < 0.06
            else None
        )
        n_orders = ctx.order_counts[cid]
        tier = (
            "platinum"
            if n_orders >= 100
            else "gold"
            if n_orders >= 30
            else "silver"
            if n_orders >= 12
            else "standard"
        )
        rows.append(
            (
                cid,
                tenant_of(cid, s, ctx.seed),
                f"{slug(first)}.{slug(last)}.{cid}@{EMAIL_DOMAINS[cid % len(EMAIL_DOMAINS)]}",
                first,
                last,
                fake.phone_number() if rng.random() < 0.8 else None,
                tier,
                n_orders,
                rng.random() < 0.35,
                fmt_ts(created),
                fmt_ts(updated),
                deleted,
            )
        )
    return [("shop.customers", CUSTOMER_COLUMNS, rows)]


ADDRESS_COLUMNS = (
    "address_id",
    "customer_id",
    "kind",
    "line1",
    "line2",
    "city",
    "region",
    "postal_code",
    "country_code",
    "is_default",
    "created_at",
    "updated_at",
)


def addresses(ctx: SeedContext, idx: int, lo: int, hi: int):
    """Customer c owns address 2c-1 (shipping) and 2c (billing); lo..hi are customer ids."""
    fakes = faker_by_country(ctx.seed, SALT_ADDRESS, idx)
    rng = Random(hash3(ctx.seed, SALT_ADDRESS, idx))
    rows = []
    for cid in range(lo, hi + 1):
        country = country_of(cid, ctx.seed)
        fake = fakes[country]
        created = fmt_ts(START_TS - rng.randrange(86400, 900 * 86400))
        for n, kind in ((1, "shipping"), (0, "billing")):
            try:
                region = fake.administrative_unit()
            except AttributeError:
                region = None
            rows.append(
                (
                    2 * cid - n,
                    cid,
                    kind,
                    fake.street_address().replace("\n", ", "),
                    f"Apt {rng.randrange(1, 400)}" if rng.random() < 0.15 else None,
                    fake.city(),
                    region,
                    fake.postcode(),
                    country,
                    True,
                    created,
                    created,
                )
            )
    return [("shop.addresses", ADDRESS_COLUMNS, rows)]


PRODUCT_COLUMNS = (
    "product_id",
    "supplier_id",
    "category_id",
    "sku",
    "name",
    "description",
    "brand",
    "base_price",
    "currency_code",
    "attributes",
    "is_active",
    "created_at",
    "updated_at",
    "deleted_at",
)
MATERIALS = [
    "cotton",
    "steel",
    "oak",
    "recycled plastic",
    "aluminium",
    "leather",
    "bamboo",
    "glass",
    "ceramic",
    "wool",
]


def _attributes(fake, rng: Random) -> str:
    """A deliberately large JSONB document (about 1-2 KB). Planted problem P05 updates these often."""
    return json.dumps(
        {
            "material": rng.choice(MATERIALS),
            "origin": fake.country(),
            "dimensions_cm": {
                "w": rng.randrange(1, 120),
                "h": rng.randrange(1, 120),
                "d": rng.randrange(1, 80),
            },
            "tags": [fake.word() for _ in range(rng.randint(4, 10))],
            "specs": {fake.word(): fake.sentence(nb_words=6) for _ in range(rng.randint(5, 12))},
            "care": fake.paragraph(nb_sentences=3),
            "warranty_months": rng.choice([0, 12, 24, 36]),
            "seo": {
                "title": fake.sentence(nb_words=6),
                "keywords": [fake.word() for _ in range(8)],
            },
        }
    )


def products(ctx: SeedContext, idx: int, lo: int, hi: int):
    s = ctx.scale
    fake = faker_for("en_US", ctx.seed, SALT_PRODUCT, idx)
    rng = Random(hash3(ctx.seed, SALT_PRODUCT, idx))
    leaf_categories = s.categories - s.categories_top
    prices = ctx.product_prices()
    rows = []
    for pid in range(lo, hi + 1):
        created = PRODUCT_START_TS + rng.randrange(START_TS - PRODUCT_START_TS)
        updated = clamp_ts(created + rng.randrange(0, 1200 * 86400))
        deleted = rng.random() < 0.04
        rows.append(
            (
                pid,
                1 + hash3(ctx.seed, SALT_PRODUCT + 100, pid) % s.suppliers,
                s.categories_top + 1 + hash3(ctx.seed, SALT_PRODUCT + 200, pid) % leaf_categories,
                f"SKU-{pid:07d}",
                f"{fake.word().title()} {fake.word().title()} {rng.choice(MATERIALS).title()}",
                fake.paragraph(nb_sentences=3),
                fake.company().split(",")[0],
                cents(prices[pid]),
                "USD",
                _attributes(fake, rng),
                not deleted and rng.random() > 0.03,
                fmt_ts(created),
                fmt_ts(updated),
                fmt_ts(clamp_ts(updated + rng.randrange(86400, 300 * 86400))) if deleted else None,
            )
        )
    return [("shop.products", PRODUCT_COLUMNS, rows)]


VARIANT_COLUMNS = (
    "variant_id",
    "product_id",
    "sku",
    "size",
    "color",
    "weight_grams",
    "price_delta",
    "barcode",
    "is_active",
    "created_at",
    "updated_at",
)
SIZES = ["S", "M", "L", "XL"]
COLORS = ["black", "white", "red", "blue", "green", "grey", "navy", "beige", "orange", "purple"]


def product_variants(ctx: SeedContext, idx: int, lo: int, hi: int):
    """Product p owns variants 4p-3 .. 4p. No randomness needed: everything derives from the ids."""
    rows = []
    for vid in range(lo, hi + 1):
        pid = (vid - 1) // ctx.scale.variants_per_product + 1
        slot = (vid - 1) % ctx.scale.variants_per_product
        stamp = fmt_ts(
            PRODUCT_START_TS
            + hash3(ctx.seed, SALT_PRODUCT + 300, vid) % (START_TS - PRODUCT_START_TS)
        )
        rows.append(
            (
                vid,
                pid,
                f"SKU-{pid:07d}-{slot + 1}",
                SIZES[slot],
                COLORS[(pid + slot) % len(COLORS)],
                100 + (pid * 13 + slot * 50) % 2000,
                cents(variant_delta_cents(vid)),
                f"{4_000_000_000_000 + vid}",
                True,
                stamp,
                stamp,
            )
        )
    return [("shop.product_variants", VARIANT_COLUMNS, rows)]


EMPLOYEE_COLUMNS = (
    "employee_id",
    "warehouse_id",
    "manager_id",
    "full_name",
    "email",
    "role",
    "hired_at",
    "updated_at",
)
ROLES = [
    "Picker",
    "Packer",
    "Shift Lead",
    "Inventory Analyst",
    "Customer Support",
    "Warehouse Manager",
    "Buyer",
]


def employees(ctx: SeedContext, idx: int, lo: int, hi: int):
    s = ctx.scale
    fake = faker_for("en_US", ctx.seed, SALT_STATIC + 200, idx)
    rng = Random(hash3(ctx.seed, SALT_STATIC + 200, idx))
    managers = min(20, s.employees)
    rows = []
    for eid in range(lo, hi + 1):
        name = fake.name()
        hired = START_TS - rng.randrange(30 * 86400, 2500 * 86400)
        rows.append(
            (
                eid,
                rng.randrange(1, s.warehouses + 1) if rng.random() < 0.8 else None,
                None
                if eid <= managers
                else 1 + eid % managers,  # employees 1..20 are top-level managers
                name,
                f"{slug(name)}.{eid}@shop.example.test",
                rng.choice(ROLES),
                fmt_ts(hired)[:10],
                fmt_ts(DATA_NOW_TS),
            )
        )
    return [("shop.employees", EMPLOYEE_COLUMNS, rows)]
