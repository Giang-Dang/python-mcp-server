-- 100_indexes.sql
-- Secondary indexes, created AFTER the bulk load (building an index once on finished data is much cheaper
-- than maintaining it for every inserted row). Primary keys and UNIQUE constraints already exist.
-- Safe to re-run: every statement is IF NOT EXISTS.
--
-- Deliberately MISSING (planted problems, see docs/planted-problems.md):
--   P02  shop.order_items (product_id)   foreign key without an index
--   P04  no trigram (pg_trgm) index on shop.products (name, description)
--   P05  no GIN index on shop.products (attributes)
--   P06  no partial indexes "WHERE deleted_at IS NULL" on tables that soft-delete
--   P03  shop.audit_log has no index starting with created_at, other than its primary key (audit_id, created_at)

SET ROLE shop_owner;

-- Speed up the index builds a little (per session only).
SET maintenance_work_mem = '256MB';
SET max_parallel_maintenance_workers = 4;

-- Reference and core entities
CREATE INDEX IF NOT EXISTS idx_categories_parent       ON shop.categories (parent_id);
CREATE INDEX IF NOT EXISTS idx_addresses_customer      ON shop.addresses (customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_name          ON shop.customers (last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_employees_warehouse     ON shop.employees (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager       ON shop.employees (manager_id);
CREATE INDEX IF NOT EXISTS idx_products_supplier       ON shop.products (supplier_id);
CREATE INDEX IF NOT EXISTS idx_products_category       ON shop.products (category_id);
CREATE INDEX IF NOT EXISTS idx_variants_product        ON shop.product_variants (product_id);

-- Orders and what hangs off them. (tenant_id, placed_at) matters because row-level security adds
-- "tenant_id = <this session's tenant>" to every query on orders.
CREATE INDEX IF NOT EXISTS idx_carts_customer          ON shop.carts (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_placed  ON shop.orders (customer_id, placed_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_placed    ON shop.orders (tenant_id, placed_at);
CREATE INDEX IF NOT EXISTS idx_orders_status           ON shop.orders (status_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order       ON shop.order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_variant     ON shop.order_items (variant_id);
CREATE INDEX IF NOT EXISTS idx_payments_order          ON shop.payments (order_id);
CREATE INDEX IF NOT EXISTS idx_payments_tenant_status  ON shop.payments (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_shipments_order         ON shop.shipments (order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_warehouse     ON shop.shipments (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_shipment_items_shipment ON shop.shipment_items (shipment_id);
CREATE INDEX IF NOT EXISTS idx_shipment_items_line     ON shop.shipment_items (order_item_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order           ON shop.refunds (order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_payment         ON shop.refunds (payment_id);

-- Stock and history
CREATE INDEX IF NOT EXISTS idx_inventory_variant       ON shop.inventory (variant_id);
CREATE INDEX IF NOT EXISTS idx_movements_variant_time  ON shop.inventory_movements (variant_id, created_at);
-- Partial index: only the rows that point at an order. cancel_order and the reserve trigger look rows up this way.
CREATE INDEX IF NOT EXISTS idx_movements_order_ref     ON shop.inventory_movements (reference_id) WHERE reference_type = 'order';
-- On a partitioned table this creates one index per monthly partition.
CREATE INDEX IF NOT EXISTS idx_audit_table_record      ON shop.audit_log (table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_price_history_product   ON shop.price_history (product_id, changed_at);
