-- 140_analyze.sql
-- Planner statistics, the materialized view's first fill, and planted problem P07 (stale statistics).
-- Re-runnable, except that the carts migration below only changes anything the first time (it is idempotent:
-- a second run finds nothing left to change).

SET ROLE shop_owner;

-- Without statistics the planner guesses. ANALYZE samples each table so it knows value distributions.
-- Analyzing a partitioned parent (audit_log) also covers its partitions' parent-level statistics.
ANALYZE shop.currencies;
ANALYZE shop.countries;
ANALYZE shop.order_statuses;
ANALYZE shop.payment_methods;
ANALYZE shop.categories;
ANALYZE shop.tenants;
ANALYZE shop.customers;
ANALYZE shop.addresses;
ANALYZE shop.suppliers;
ANALYZE shop.warehouses;
ANALYZE shop.employees;
ANALYZE shop.products;
ANALYZE shop.product_variants;
ANALYZE shop.orders;
ANALYZE shop.order_items;
ANALYZE shop.payments;
ANALYZE shop.shipments;
ANALYZE shop.shipment_items;
ANALYZE shop.invoices;
ANALYZE shop.refunds;
ANALYZE shop.inventory;
ANALYZE shop.inventory_movements;
ANALYZE shop.audit_log;
ANALYZE shop.price_history;

-- P07: stale statistics on shop.carts.
--   1. Stop autovacuum from ever re-analyzing this table (otherwise Postgres would fix the problem by itself).
--   2. Analyze it now, while about 20% of carts are 'open'.
--   3. Run a "bulk status migration" that makes 95% of carts 'open'. The statistics still say 20%, so the planner
--      underestimates "WHERE status = 'open'" by almost 5x and may choose a bad plan.
ALTER TABLE shop.carts SET (autovacuum_enabled = false);
ANALYZE shop.carts;
UPDATE shop.carts SET status = 'open' WHERE status <> 'open' AND cart_id % 20 <> 0;

-- First fill of the daily-sales snapshot. From now on it ages until somebody calls rebuild_daily_aggregates().
REFRESH MATERIALIZED VIEW shop.mv_daily_sales;
