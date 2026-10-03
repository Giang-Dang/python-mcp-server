"""Public guidance content is useful without configuration or external services."""

from mcp_server.core.guidance.resources import render_schema_guide
from mcp_server.core.sql_access.domain import Limits


def test_schema_guide_describes_domains_and_live_catalog_workflow():
    text = render_schema_guide()
    assert text == render_schema_guide()
    assert text.isascii()
    assert len(text.encode("utf-8")) <= 16384
    for term in (
        "guidance-v1",
        "customers",
        "catalog",
        "orders",
        "payments",
        "fulfillment",
        "inventory",
        "shop.orders",
        "list_tables",
        "describe_table",
        "unqualified",
        "tenant-isolation guarantee",
        "P01-P13",
    ):
        assert term.lower() in text.lower()


def test_relationships_guide_explains_join_keys_and_child_multiplication():
    from mcp_server.core.guidance.resources import render_relationships_guide

    text = render_relationships_guide()
    assert text.isascii()
    assert len(text.encode("utf-8")) <= 16384
    for term in (
        "guidance-v1",
        "customers.customer_id = orders.customer_id",
        "orders.order_id = order_items.order_id",
        "products.product_id = order_items.product_id",
        "product_variants.variant_id = order_items.variant_id",
        "orders.order_id = payments.order_id",
        "orders.order_id = shipments.order_id",
        "product_variants.variant_id = inventory.variant_id",
        "warehouse_id, variant_id",
        "double counting",
        "2 lines",
        "3 payments",
        "6 rows",
        "tenant-isolation guarantee",
    ):
        assert term in text


def test_sql_policy_reports_all_effective_limits_and_approval_rules():
    from mcp_server.core.guidance.resources import render_sql_policy

    text = render_sql_policy(
        Limits(
            request_bytes=1024,
            result_rows=2,
            result_bytes=256,
            read_seconds=3,
            write_seconds=4,
            procedure_seconds=5,
            affected_rows=6,
            approval_seconds=7,
            plan_cost=8.5,
        )
    )
    assert text.isascii()
    assert 1024 < len(text.encode("utf-8")) <= 16384
    for row in (
        "| request_bytes | 1024 |",
        "| result_rows | 2 |",
        "| result_bytes | 256 |",
        "| read_seconds | 3 |",
        "| write_seconds | 4 |",
        "| procedure_seconds | 5 |",
        "| affected_rows | 6 |",
        "| approval_seconds | 7 |",
        "| plan_cost | 8.5 |",
    ):
        assert row in text
    for rule in (
        "non-ANALYZE",
        "WHERE",
        "human approval",
        "cannot override",
        "trigger effects",
        "transaction modes",
        "never retry",
        "tenant-isolation guarantee",
        "P01-P13",
    ):
        assert rule in text
    assert render_sql_policy(Limits()) != text
