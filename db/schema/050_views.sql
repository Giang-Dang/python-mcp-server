-- 050_views.sql
-- Reporting views and one materialized view.

SET ROLE shop_owner;

-- security_invoker = true makes the view run with the permissions (and row-level security) of the person
-- who queries it. Without it, a view runs as its owner, and the owner bypasses RLS, so a view over RLS
-- tables would show every tenant's rows to anyone who can read the view.
CREATE VIEW shop.v_order_summary WITH (security_invoker = true) AS
SELECT o.order_id,
       o.tenant_id,
       o.order_number,
       o.placed_at,
       s.code AS status,
       c.customer_id,
       c.email AS customer_email,
       o.currency_code,
       o.total_amount
FROM shop.orders o
JOIN shop.order_statuses s ON s.status_id = o.status_id
JOIN shop.customers c ON c.customer_id = o.customer_id
WHERE o.deleted_at IS NULL;
COMMENT ON VIEW shop.v_order_summary IS 'Orders with status code and customer email. Runs as the caller, so RLS applies.';

CREATE VIEW shop.v_low_stock AS
SELECT i.warehouse_id,
       v.variant_id,
       v.sku AS variant_sku,
       p.product_id,
       p.name AS product_name,
       i.quantity_on_hand,
       i.reorder_point
FROM shop.inventory i
JOIN shop.product_variants v ON v.variant_id = i.variant_id
JOIN shop.products p ON p.product_id = v.product_id
WHERE i.quantity_on_hand <= i.reorder_point;
COMMENT ON VIEW shop.v_low_stock IS 'Variants at or below their reorder point, per warehouse.';

-- WITH NO DATA: the table is empty at creation time, so there is nothing to compute yet. The first
-- REFRESH happens after seeding. Afterwards it goes stale until someone refreshes it again.
CREATE MATERIALIZED VIEW shop.mv_daily_sales AS
SELECT date_trunc('day', placed_at)::date AS sales_date,
       tenant_id,
       count(*) AS order_count,
       sum(total_amount) AS revenue
FROM shop.orders
WHERE deleted_at IS NULL
GROUP BY 1, 2
WITH NO DATA;
COMMENT ON MATERIALIZED VIEW shop.mv_daily_sales IS 'Daily revenue per tenant. A snapshot: only as fresh as its last REFRESH.';
