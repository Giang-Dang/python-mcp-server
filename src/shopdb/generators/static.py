"""Small tables loaded once by the main process: lookups, tenants, categories, suppliers, warehouses.

Returned in foreign-key order (a table appears after every table it references).
"""

from __future__ import annotations

from random import Random

from ..context import SeedContext
from ..model import SALT_STATIC, country_of, hash3
from .fake import faker_for, slug

COUNTRIES = [
    ("US", "United States", "North America"),
    ("CA", "Canada", "North America"),
    ("MX", "Mexico", "North America"),
    ("GB", "United Kingdom", "Europe"),
    ("DE", "Germany", "Europe"),
    ("FR", "France", "Europe"),
    ("ES", "Spain", "Europe"),
    ("IT", "Italy", "Europe"),
    ("NL", "Netherlands", "Europe"),
    ("SE", "Sweden", "Europe"),
    ("NO", "Norway", "Europe"),
    ("PL", "Poland", "Europe"),
    ("IE", "Ireland", "Europe"),
    ("CH", "Switzerland", "Europe"),
    ("AU", "Australia", "Oceania"),
    ("NZ", "New Zealand", "Oceania"),
    ("JP", "Japan", "Asia"),
    ("KR", "South Korea", "Asia"),
    ("CN", "China", "Asia"),
    ("IN", "India", "Asia"),
    ("SG", "Singapore", "Asia"),
    ("VN", "Vietnam", "Asia"),
    ("TH", "Thailand", "Asia"),
    ("ID", "Indonesia", "Asia"),
    ("BR", "Brazil", "South America"),
    ("AR", "Argentina", "South America"),
    ("CL", "Chile", "South America"),
    ("ZA", "South Africa", "Africa"),
    ("EG", "Egypt", "Africa"),
    ("AE", "United Arab Emirates", "Asia"),
]

CURRENCIES = [
    ("USD", "US Dollar", 2),
    ("EUR", "Euro", 2),
    ("GBP", "Pound Sterling", 2),
    ("CAD", "Canadian Dollar", 2),
    ("AUD", "Australian Dollar", 2),
    ("JPY", "Japanese Yen", 0),
    ("CHF", "Swiss Franc", 2),
    ("SEK", "Swedish Krona", 2),
    ("INR", "Indian Rupee", 2),
    ("VND", "Vietnamese Dong", 0),
]

# Ids must match the constants in model.py (PENDING=1 ... ON_HOLD=8).
ORDER_STATUSES = [
    (1, "pending", "Order created, awaiting payment", False),
    (2, "paid", "Payment captured", False),
    (3, "processing", "Being picked and packed", False),
    (4, "shipped", "Handed to the carrier", False),
    (5, "delivered", "Received by the customer", True),
    (6, "cancelled", "Cancelled before shipping", True),
    (7, "refunded", "Returned and refunded", True),
    (8, "on_hold", "Waiting for manual review", False),
]

PAYMENT_METHODS = [
    (1, "card", "Credit or debit card", True),
    (2, "paypal", "PayPal", True),
    (3, "bank_transfer", "Bank transfer", True),
    (4, "apple_pay", "Apple Pay", True),
    (5, "gift_card", "Gift card", True),
    (6, "cash_on_delivery", "Cash on delivery", False),
]

TENANT_NAMES = [
    "Alder and Finch",
    "Bluebird Supply",
    "Copperline Goods",
    "Driftwood Trading",
    "Evergreen Outfitters",
]

TOP_CATEGORIES = [
    "Electronics",
    "Home and Kitchen",
    "Sports and Outdoors",
    "Toys and Games",
    "Beauty",
    "Books",
    "Clothing",
    "Garden",
    "Automotive",
    "Pet Supplies",
    "Office Supplies",
    "Health",
    "Music",
    "Tools",
    "Jewelry",
    "Baby",
    "Grocery",
    "Art and Craft",
    "Travel",
    "Furniture",
]
CHILD_WORDS = [
    "Accessories",
    "Premium",
    "Basics",
    "Bestsellers",
    "Clearance",
    "Gifts",
    "Kits",
    "Essentials",
    "Professional",
    "Outdoor",
    "Indoor",
    "Kids",
    "Compact",
    "Deluxe",
]

CARRIERS = ["UPS", "FedEx", "DHL", "USPS", "Royal Mail", "DPD"]


def static_tables(ctx: SeedContext):
    """Yield (table, columns, rows) in foreign-key order."""
    s, seed = ctx.scale, ctx.seed
    fake = faker_for("en_US", seed, SALT_STATIC, 0)
    rng = Random(hash3(seed, SALT_STATIC, 1))

    yield "shop.currencies", ("currency_code", "name", "minor_units"), CURRENCIES
    yield "shop.countries", ("country_code", "name", "region"), COUNTRIES
    yield "shop.order_statuses", ("status_id", "code", "description", "is_terminal"), ORDER_STATUSES
    yield (
        "shop.payment_methods",
        ("payment_method_id", "code", "name", "is_active"),
        PAYMENT_METHODS,
    )

    tenants = []
    for tid in range(1, s.tenants + 1):
        name = (
            TENANT_NAMES[tid - 1]
            if tid <= len(TENANT_NAMES)
            else f"{fake.last_name()} {fake.word().title()} Co"
        )
        plan = (
            "enterprise" if tid == 1 else rng.choice(["free", "standard", "standard", "enterprise"])
        )
        tenants.append((tid, name, plan, "2021-01-01 00:00:00+00"))
    yield "shop.tenants", ("tenant_id", "name", "plan", "created_at"), tenants

    # Top-level categories first, then children, so parents have lower ids than their children.
    categories = []
    for cid in range(1, s.categories_top + 1):
        name = TOP_CATEGORIES[(cid - 1) % len(TOP_CATEGORIES)]
        categories.append((cid, None, name, f"{slug(name)}-{cid}"))
    for cid in range(s.categories_top + 1, s.categories + 1):
        parent = 1 + (cid - s.categories_top - 1) % s.categories_top
        parent_name = categories[parent - 1][2]
        name = f"{parent_name} / {CHILD_WORDS[cid % len(CHILD_WORDS)]}"
        categories.append((cid, parent, name, f"{slug(name)}-{cid}"))
    yield "shop.categories", ("category_id", "parent_id", "name", "slug"), categories

    suppliers = []
    for sid in range(1, s.suppliers + 1):
        suppliers.append(
            (
                sid,
                fake.company(),
                country_of(sid, seed, SALT_STATIC),
                f"sales{sid}@supplier{sid}.example.test",
                rng.choice([3, 7, 7, 14, 14, 21, 30, 45]),
                f"{rng.uniform(2.5, 5.0):.2f}",
                "2024-01-01 00:00:00+00",
            )
        )
    yield (
        "shop.suppliers",
        (
            "supplier_id",
            "name",
            "country_code",
            "contact_email",
            "lead_time_days",
            "rating",
            "updated_at",
        ),
        suppliers,
    )

    warehouses = []
    for wid in range(1, s.warehouses + 1):
        code = country_of(wid, seed, SALT_STATIC + 100)
        city = faker_for(
            {
                "US": "en_US",
                "GB": "en_GB",
                "DE": "de_DE",
                "FR": "fr_FR",
                "CA": "en_CA",
                "AU": "en_AU",
            }[code],
            seed,
            SALT_STATIC,
            10 + wid,
        ).city()
        warehouses.append(
            (wid, f"{city} Fulfilment Centre {wid}", code, city, rng.randrange(50_000, 500_000))
        )
    yield (
        "shop.warehouses",
        ("warehouse_id", "name", "country_code", "city", "capacity_units"),
        warehouses,
    )
