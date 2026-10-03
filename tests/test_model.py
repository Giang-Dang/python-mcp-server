"""Tests for the deterministic model. No database needed."""

import pytest

from shopdb.config import get_scale
from shopdb.generators.orders import order_chunk
from shopdb.loader import build_context
from shopdb.model import (
    ORDER_CHILDREN,
    compute_order_layout,
    hash3,
    plan_order,
    ranges,
    tenant_of,
)

SEED = 42


@pytest.fixture(scope="module")
def scale():
    return get_scale("S")


@pytest.fixture(scope="module")
def layout(scale):
    return compute_order_layout(scale, SEED)


def test_hash_is_deterministic_and_seed_sensitive():
    assert hash3(1, 2, 3) == hash3(1, 2, 3)
    assert hash3(1, 2, 3) != hash3(2, 2, 3)
    assert hash3(1, 2, 3) != hash3(1, 3, 3)


def test_plan_order_is_deterministic(scale):
    assert plan_order(1234, scale, SEED) == plan_order(1234, scale, SEED)
    assert plan_order(1234, scale, SEED) != plan_order(1234, scale, SEED + 1)


def test_ranges_cover_every_id_exactly_once():
    chunks = ranges(103, 25)
    ids = [i for _, lo, hi in chunks for i in range(lo, hi + 1)]
    assert ids == list(range(1, 104))


def test_layout_totals_match_the_plans(scale, layout):
    _offsets, totals, order_counts = layout
    plans = [plan_order(o, scale, SEED) for o in range(1, scale.orders + 1)]
    assert totals["items"] == sum(p.n_items for p in plans)
    assert totals["payments"] == sum(p.n_payments for p in plans)
    assert totals["shipments"] == sum(p.n_shipments for p in plans)
    assert totals["invoices"] == sum(p.has_invoice for p in plans)
    assert sum(order_counts) == scale.orders


def test_planted_skew_p01(scale, layout):
    """About 30% of orders belong to the first 1% of customers."""
    order_counts = layout[2]
    hot = scale.customers // 100
    share = sum(order_counts[1 : hot + 1]) / scale.orders
    assert 0.25 < share < 0.40


def test_tenant_1_is_the_biggest_tenant(scale):
    counts = {t: 0 for t in range(1, scale.tenants + 1)}
    for customer in range(1, 5001):
        counts[tenant_of(customer, scale, SEED)] += 1
    assert counts[1] == max(counts.values())


def test_order_chunk_ids_follow_the_layout(scale):
    """The first order chunk must hand out exactly the child ids that the planning pass reserved for chunk 1."""
    ctx = build_context(scale, SEED)
    # order_chunk raises RuntimeError if the generated ids drift from the plan.
    batches = order_chunk(ctx, 0, 1, 25_000)
    assert batches[0][0] == "shop.orders"
    items = batches[1][2]
    assert len(items) == ctx.order_offsets[1]["items"] - ctx.order_offsets[0]["items"]
    assert set(ctx.order_offsets[0]) == set(ORDER_CHILDREN)


def test_same_seed_gives_identical_rows(scale):
    ctx = build_context(scale, SEED)
    first = order_chunk(ctx, 0, 1, 25_000)
    second = order_chunk(ctx, 0, 1, 25_000)
    assert first == second
