-- 110_triggers.sql
-- Triggers, applied after the bulk load so that seeding did not fire any of them.
-- Re-runnable: functions use CREATE OR REPLACE and each trigger is dropped before it is created.
--
-- Kinds, and why each exists:
--   trg_touch_updated_at      BEFORE UPDATE, 11 tables       keeps updated_at current (one generic function)
--   trg_audit                 AFTER I/U/D on orders, payments writes shop.audit_log (SECURITY DEFINER)
--   trg_reserve_inventory     AFTER INSERT on order_items    reserves stock: a hot-row / deadlock source (P08, P11)
--   trg_validate_*            BEFORE ...                     business rules that raise errors
--   trg_order_count           AFTER INSERT/DELETE on orders  denormalized counter on customers: contention
--   trg_soft_delete_cascade   AFTER UPDATE of deleted_at     cascades a customer's soft delete
--   trg_recalc_order_totals   AFTER INSERT, STATEMENT level  uses a transition table to recompute order totals
--   trg_carrier_sla           AFTER UPDATE on shipments      deliberately slow (P13)
--
-- SECURITY DEFINER functions run with the privileges of their owner (shop_owner) instead of the caller's.
-- They are needed here because mcp_writer may change orders but may not write audit_log or inventory.
-- A definer function MUST pin its search_path (SET search_path = ...), otherwise a caller could put their own
-- objects first in the path and have this code call them with owner privileges.

SET ROLE shop_owner;

-- ---------------------------------------------------------------------------------------------
-- 1. updated_at maintenance
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['customers', 'addresses', 'suppliers', 'employees', 'products', 'product_variants',
                             'carts', 'orders', 'payments', 'shipments', 'inventory']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_updated_at ON shop.%I', t);
        EXECUTE format('CREATE TRIGGER trg_touch_updated_at BEFORE UPDATE ON shop.%I '
                       'FOR EACH ROW EXECUTE FUNCTION shop.touch_updated_at()', t);
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------------------------
-- 2. Audit trail. The primary-key column name is passed as the trigger argument (TG_ARGV[0]).
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.audit_row_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_row jsonb := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
BEGIN
    INSERT INTO shop.audit_log (created_at, tenant_id, table_name, record_id, action, changed_by, old_data, new_data)
    VALUES (now(),
            (v_row ->> 'tenant_id')::int,
            TG_TABLE_NAME,
            (v_row ->> TG_ARGV[0])::bigint,
            left(TG_OP, 1),                                      -- 'I', 'U' or 'D'
            session_user,                                        -- the role that connected, not the definer
            CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END,
            CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END);
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_audit ON shop.orders;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON shop.orders
    FOR EACH ROW EXECUTE FUNCTION shop.audit_row_change('order_id');

DROP TRIGGER IF EXISTS trg_audit ON shop.payments;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON shop.payments
    FOR EACH ROW EXECUTE FUNCTION shop.audit_row_change('payment_id');

-- ---------------------------------------------------------------------------------------------
-- 3. Stock reservation when an order line is added (hot rows: popular variants are updated by many orders)
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.reserve_inventory() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_warehouse smallint;
BEGIN
    -- Take the warehouse with the most available stock for this variant.
    SELECT warehouse_id INTO v_warehouse
    FROM shop.inventory
    WHERE variant_id = NEW.variant_id
    ORDER BY quantity_on_hand - quantity_reserved DESC, warehouse_id
    LIMIT 1;

    IF v_warehouse IS NULL THEN
        RETURN NULL;        -- variant is not stocked anywhere; nothing to reserve
    END IF;

    UPDATE shop.inventory
       SET quantity_reserved = quantity_reserved + NEW.quantity
     WHERE warehouse_id = v_warehouse AND variant_id = NEW.variant_id;

    INSERT INTO shop.inventory_movements (warehouse_id, variant_id, movement_type, quantity, reference_type, reference_id)
    VALUES (v_warehouse, NEW.variant_id, 'sale', -NEW.quantity, 'order', NEW.order_id);
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_reserve_inventory ON shop.order_items;
CREATE TRIGGER trg_reserve_inventory AFTER INSERT ON shop.order_items
    FOR EACH ROW EXECUTE FUNCTION shop.reserve_inventory();

-- ---------------------------------------------------------------------------------------------
-- 4. Validation rules
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.validate_inventory() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.quantity_on_hand < 0 OR NEW.quantity_reserved > NEW.quantity_on_hand THEN
        RAISE EXCEPTION 'insufficient stock for variant % in warehouse % (on hand %, reserved %)',
            NEW.variant_id, NEW.warehouse_id, NEW.quantity_on_hand, NEW.quantity_reserved
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_validate_inventory ON shop.inventory;
CREATE TRIGGER trg_validate_inventory BEFORE UPDATE ON shop.inventory
    FOR EACH ROW EXECUTE FUNCTION shop.validate_inventory();

-- Status ids (see order_statuses): 5 delivered, 6 cancelled, 7 refunded.
-- Cancelled and refunded orders are final; a delivered order can only become refunded.
CREATE OR REPLACE FUNCTION shop.validate_order_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status_id <> OLD.status_id
       AND (OLD.status_id IN (6, 7) OR (OLD.status_id = 5 AND NEW.status_id <> 7)) THEN
        RAISE EXCEPTION 'invalid status change % -> % for order %', OLD.status_id, NEW.status_id, OLD.order_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_validate_order_status ON shop.orders;
CREATE TRIGGER trg_validate_order_status BEFORE UPDATE OF status_id ON shop.orders
    FOR EACH ROW EXECUTE FUNCTION shop.validate_order_status();

CREATE OR REPLACE FUNCTION shop.validate_order_item() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.quantity > 100 THEN
        RAISE EXCEPTION 'quantity % exceeds the limit of 100 per line', NEW.quantity
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_validate_order_item ON shop.order_items;
CREATE TRIGGER trg_validate_order_item BEFORE INSERT OR UPDATE ON shop.order_items
    FOR EACH ROW EXECUTE FUNCTION shop.validate_order_item();

-- ---------------------------------------------------------------------------------------------
-- 5. Denormalized counter. SECURITY INVOKER: it runs with the caller's rights, so RLS applies.
--    The first 1% of customers receive 30% of orders, so their rows are updated constantly (contention).
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.bump_customer_order_count() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE shop.customers SET order_count = order_count + 1 WHERE customer_id = NEW.customer_id;
    ELSE
        UPDATE shop.customers SET order_count = order_count - 1 WHERE customer_id = OLD.customer_id;
    END IF;
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_order_count ON shop.orders;
CREATE TRIGGER trg_order_count AFTER INSERT OR DELETE ON shop.orders
    FOR EACH ROW EXECUTE FUNCTION shop.bump_customer_order_count();

-- ---------------------------------------------------------------------------------------------
-- 6. Soft-delete cascade: when a customer is marked deleted, their orders are too and open carts are abandoned
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.cascade_customer_soft_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE shop.orders SET deleted_at = NEW.deleted_at WHERE customer_id = NEW.customer_id AND deleted_at IS NULL;
    UPDATE shop.carts SET status = 'abandoned' WHERE customer_id = NEW.customer_id AND status = 'open';
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_soft_delete_cascade ON shop.customers;
CREATE TRIGGER trg_soft_delete_cascade AFTER UPDATE OF deleted_at ON shop.customers
    FOR EACH ROW WHEN (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
    EXECUTE FUNCTION shop.cascade_customer_soft_delete();

-- ---------------------------------------------------------------------------------------------
-- 7. Statement-level trigger with a transition table.
--    "new_rows" holds every row inserted by ONE INSERT statement, so a 20-line order costs one recalculation,
--    not twenty. Inserting several orders' lines in one statement recalculates each affected order once.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.recalc_order_totals() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE shop.orders o
       SET subtotal        = s.subtotal,
           tax_amount      = shop.calc_tax(s.subtotal),
           shipping_amount = shop.shipping_cost(s.subtotal),
           total_amount    = s.subtotal + shop.calc_tax(s.subtotal) + shop.shipping_cost(s.subtotal) - o.discount_amount
      FROM (SELECT i.order_id, sum(i.line_total) AS subtotal
              FROM shop.order_items i
             WHERE i.order_id IN (SELECT DISTINCT order_id FROM new_rows)
             GROUP BY i.order_id) s
     WHERE o.order_id = s.order_id;
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_recalc_order_totals ON shop.order_items;
CREATE TRIGGER trg_recalc_order_totals AFTER INSERT ON shop.order_items
    REFERENCING NEW TABLE AS new_rows
    FOR EACH STATEMENT EXECUTE FUNCTION shop.recalc_order_totals();

-- ---------------------------------------------------------------------------------------------
-- 8. Deliberately slow (planted problem P13): a "real-time carrier SLA check" that scans the whole shipments
--    table (no index on carrier) for EVERY shipment whose status changes. Updating 1,000 shipments scans the
--    table 1,000 times.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.carrier_sla_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_delivered bigint;
    v_total bigint;
BEGIN
    SELECT count(*) FILTER (WHERE status = 'delivered'), count(*)
      INTO v_delivered, v_total
      FROM shop.shipments
     WHERE carrier = NEW.carrier;

    IF v_total > 0 AND v_delivered::numeric / v_total < 0.01 THEN
        RAISE WARNING 'carrier % has a delivery rate below 1%%', NEW.carrier;
    END IF;
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_carrier_sla ON shop.shipments;
CREATE TRIGGER trg_carrier_sla AFTER UPDATE OF status ON shop.shipments
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION shop.carrier_sla_check();
