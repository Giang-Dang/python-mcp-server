"""Representative original generator outputs; capture before moving generation code."""

import hashlib
import itertools
import json

from shopdb.config import get_scale
from shopdb.generators import REGISTRY
from shopdb.generators.static import static_tables
from shopdb.loader import build_context


def snapshot() -> dict:
    ctx = build_context(get_scale("S"), 42)
    result = {}
    groups = {"static": static_tables(ctx)}
    groups.update({k: fn(ctx, 0, 1, 25_000 if k == "orders" else 4) for k, fn in REGISTRY.items()})
    for kind, batches in groups.items():
        sample = [
            [table, list(columns), list(itertools.islice(rows, 3))]
            for table, columns, rows in batches
        ]
        result[kind] = json.loads(json.dumps(sample, default=str, ensure_ascii=True))
    result["totals"] = ctx.totals
    result["order_counts_sha256"] = hashlib.sha256(ctx.order_counts.tobytes()).hexdigest()
    return result
