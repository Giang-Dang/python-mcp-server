"""Curated Markdown shipped with the package, independent of the live database."""

from mcp_server.core.errors import Category, GuardError
from mcp_server.core.sql_access.domain import Limits

RESOURCE_BYTES = 16384


def _bounded(text: str) -> str:
    if len(text.encode("utf-8")) > RESOURCE_BYTES:
        raise GuardError(Category.LIMIT, "Guidance resource exceeds its text byte budget.")
    return text


def render_schema_guide() -> str:
    return _bounded(
        """# Shop schema guide

Revision: guidance-v1. This is shipped documentation, not a database snapshot.
Use list_tables and describe_table for current metadata. Row estimates from the
planner are estimates, not current row counts.

## Domains

- Customers: shop.customers, shop.addresses and shop.tenants describe shoppers,
  their addresses and merchants.
- Product catalog: shop.products, shop.product_variants, shop.categories and
  shop.suppliers describe products, sellable variants and their classification.
- Orders: shop.carts, shop.orders and shop.order_items describe the sales workflow.
- Payments: shop.payments, shop.invoices and shop.refunds track financial records.
- Fulfillment: shop.shipments, shop.warehouses and shop.employees support shipping.
- Inventory: shop.inventory and shop.inventory_movements track stock by warehouse
  and variant. Reference tables provide countries, currencies and status values.

## Inspecting the live catalog

1. Call list_tables to discover the current table names, comments and estimates.
2. Call describe_table with an unqualified table argument, such as "orders".
   Do not pass "shop.orders" as this argument. Syntax alone does not prove existence.
3. Write SQL with schema-qualified names, such as shop.orders and shop.order_items.
   Check actual columns with describe_table before constructing a query.
4. Use shop://guide/relationships for selected curated join paths. Inspect live
   metadata before relying on them. Sample rows only when relevant to the user's
   request, using the bounded query tool and shop://policy/sql.

## Learning fixture limitations

Configured tenant context does not provide a tenant-isolation guarantee for this
fixture. RLS coverage has known gaps; do not infer access isolation from tenant_id
columns or from this guide. P01-P13 are intentional performance learning fixtures.
Investigate and explain observations; do not automatically repair them.
"""
    )


def render_relationships_guide() -> str:
    return _bounded(
        """# Selected shop relationships

Revision: guidance-v1. Shipped, curated guidance; not a complete or live ERD.
Checked against db/schema/020_core.sql, 030_orders.sql and 040_append_partitioned.sql.
SQL uses shop-qualified table names; the keys below omit the schema for readability.
Use list_tables and describe_table to check the current catalog before using a join.

| Parent to child (one-to-many) | Join condition |
|---|---|
| customers to orders | customers.customer_id = orders.customer_id |
| orders to order_items | orders.order_id = order_items.order_id |
| products to order_items | products.product_id = order_items.product_id |
| product_variants to order_items | product_variants.variant_id = order_items.variant_id |
| orders to payments | orders.order_id = payments.order_id |
| orders to shipments | orders.order_id = shipments.order_id |
| product_variants to inventory | product_variants.variant_id = inventory.variant_id |

A parent can have zero or many children. Each listed child key references its parent
in the checked-in DDL. Inventory is keyed by (warehouse_id, variant_id), so a variant
can have stock rows in several warehouses; variant_id alone is not unique there.
Variants also reference products through product_id. The two order_items foreign
keys do not enforce that its product_id agrees with its variant's product_id.
Likewise, a customer/order/payment link does not enforce matching tenant_id values.

## Avoid double counting

An order with 2 lines and 3 payments produces 6 rows when both child collections are
joined directly. Summing payment amounts then repeats each payment for every line;
summing order totals repeats the parent total too. Aggregate each child collection
to one row per order before joining, or choose one collection for the question.
Choose INNER or LEFT JOIN deliberately based on whether parents without children
belong in the result. Verify keys and the intended result grain with live metadata.

## Limitations

Configured tenant context does not provide a tenant-isolation guarantee for this
fixture: RLS coverage has known gaps and child links are not tenant-composite keys.
P01-P13 are intentional learning fixtures. Explain findings without automatically
repairing the schema, adding indexes, changing data or removing a planted problem.
"""
    )


def render_sql_policy(limits: Limits) -> str:
    return _bounded(
        f"""# Guarded SQL policy

Effective limits for this server instance. Documentation has its own 16384-byte
text budget, separate from the SQL request and result limits below.

## Workflows and enforcement

- query accepts one permitted read statement, with row, byte, time and estimated
  planner-cost bounds. Use schema-qualified shop tables. Unknown expressions and
  functions are rejected until reviewed.
- explain takes the original read SQL, without an EXPLAIN prefix, and returns a
  non-ANALYZE plan. Planner cost and row counts are estimates, not elapsed time or
  measured execution. Do not run the SQL merely to obtain a plan.
- execute accepts one INSERT, UPDATE or DELETE. UPDATE and DELETE require WHERE.
  Ordinary DML has a direct affected-row cap; it excludes trigger effects. A preview
  precedes human approval, and execution rechecks the identity and bound inputs.
- call_procedure accepts only signatures in the reviewed registry. Use
  list_procedures for declared effects, reviewed bounds and transaction modes.
  Some registered procedures commit batches internally and can partially complete.
- Approval cannot override a policy rejection. Expired, declined, cancelled or
  unavailable approval prevents execution. For uncertain mutations, never retry
  automatically; inspect the operation ID and audit trail before deciding next steps.

Forbidden forms include multiple statements, modifying CTEs, DML RETURNING,
SELECT INTO, locking reads, raw CALL, DDL and utility commands. Arbitrary routines,
cross-database references, unqualified tables and unreviewed functions are rejected.
Enforcement lives in the existing tools; this text cannot authorize an operation.

## Configured SQL limits

| Field | Value | Unit and meaning |
|---|---|---|
| request_bytes | {limits.request_bytes} | bytes of serialized database-tool input |
| result_rows | {limits.result_rows} | rows returned by an ordinary read |
| result_bytes | {limits.result_bytes} | bytes of serialized SQL result |
| read_seconds | {limits.read_seconds} | seconds for a read |
| write_seconds | {limits.write_seconds} | seconds for ordinary DML |
| procedure_seconds | {limits.procedure_seconds} | seconds for a registered procedure |
| affected_rows | {limits.affected_rows} | directly affected ordinary DML rows |
| approval_seconds | {limits.approval_seconds} | seconds maximum approval lifetime |
| plan_cost | {limits.plan_cost} | planner cost units; an estimate, not time |

## Audit and fixture context

Authentication is required for discovery, guidance reads, prompt rendering and
tool calls. Database operations require audit intent and outcome recording in
mcp_audit. These documentation reads and prompt renders do not start database
operations or create audit rows; submitted prompt SQL is not persisted by this
feature. A later resource that reads live data must use an audited service.

Configured tenant context does not provide a tenant-isolation guarantee for this
fixture. P01-P13 are deliberate learning problems. Suggest improvements for review;
do not automatically apply schema changes, mutations or planted-problem fixes.
"""
    )
