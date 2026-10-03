-- 130_procedures.sql
-- The "stored procedure API": procedures that change data. Called with CALL shop.create_order(...).
-- Re-runnable (CREATE OR REPLACE).
--
-- WHO RUNS WITH WHOSE RIGHTS
--   Write procedures are SECURITY DEFINER: they run as shop_owner, so the calling role (mcp_proc_exec) needs no
--   table privileges at all. The price is that row-level security does NOT apply inside them, because the owner
--   bypasses it. Every procedure below therefore enforces the tenant itself:  tenant_id = shop.current_tenant().
--   Forgetting that check is the classic bug of this pattern. Each also pins its search_path.
--
--   archive_old_orders is SECURITY INVOKER on purpose: it commits after every batch, and Postgres does not allow
--   transaction control (COMMIT) inside a SECURITY DEFINER procedure or one with a SET clause. It must also be
--   called outside an explicit transaction (autocommit on), or COMMIT fails with "invalid transaction termination".
--
-- Status ids (order_statuses): 1 pending, 2 paid, 3 processing, 4 shipped, 5 delivered, 6 cancelled, 7 refunded, 8 on_hold.

SET ROLE shop_owner;

-- ---------------------------------------------------------------------------------------------
-- create_order: customer + parallel arrays of variant ids and quantities -> new pending order, lines, payment
-- Example:  CALL shop.create_order(7, ARRAY[101, 205], ARRAY[1, 2], NULL);   -- returns the new order id
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.create_order(
    p_customer_id bigint,
    p_variant_ids bigint[],
    p_quantities  int[],
    INOUT p_order_id bigint DEFAULT NULL
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_tenant       int := shop.current_tenant();
    v_cust_tenant  int;
    v_lines        int;
    v_total        numeric;
BEGIN
    IF v_tenant IS NULL THEN
        RAISE EXCEPTION 'app.tenant_id is not set for this session';
    END IF;
    IF p_variant_ids IS NULL OR p_quantities IS NULL
       OR cardinality(p_variant_ids) = 0 OR cardinality(p_variant_ids) <> cardinality(p_quantities) THEN
        RAISE EXCEPTION 'p_variant_ids and p_quantities must be non-empty arrays of the same length';
    END IF;

    SELECT tenant_id INTO v_cust_tenant FROM shop.customers WHERE customer_id = p_customer_id AND deleted_at IS NULL;
    IF v_cust_tenant IS DISTINCT FROM v_tenant THEN
        RAISE EXCEPTION 'customer % not found', p_customer_id;       -- same message whether missing or another tenant's
    END IF;

    p_order_id := nextval(pg_get_serial_sequence('shop.orders', 'order_id'));
    INSERT INTO shop.orders (order_id, tenant_id, customer_id, status_id, order_number, channel, currency_code,
                             subtotal, total_amount, shipping_address_id, billing_address_id, placed_at)
    VALUES (p_order_id, v_tenant, p_customer_id, 1, shop.format_order_number(v_tenant, p_order_id), 'api', 'USD',
            0, 0, 2 * p_customer_id - 1, 2 * p_customer_id, now());

    -- One INSERT for all lines, so the statement-level trigger recalculates the order totals once.
    INSERT INTO shop.order_items (order_id, product_id, variant_id, quantity, unit_price, discount, line_total)
    SELECT p_order_id, v.product_id, v.variant_id, u.qty,
           p.base_price + v.price_delta, 0, shop.line_total(p.base_price + v.price_delta, u.qty)
    FROM unnest(p_variant_ids, p_quantities) AS u(variant_id, qty)
    JOIN shop.product_variants v ON v.variant_id = u.variant_id AND v.is_active
    JOIN shop.products p ON p.product_id = v.product_id AND p.deleted_at IS NULL;
    GET DIAGNOSTICS v_lines = ROW_COUNT;
    IF v_lines <> cardinality(p_variant_ids) THEN
        RAISE EXCEPTION 'one or more variants do not exist or are discontinued';
    END IF;

    SELECT total_amount INTO v_total FROM shop.orders WHERE order_id = p_order_id;
    INSERT INTO shop.payments (tenant_id, order_id, payment_method_id, amount, currency_code, status)
    VALUES (v_tenant, p_order_id, 1, v_total, 'USD', 'pending');
END
$$;
COMMENT ON PROCEDURE shop.create_order(bigint, bigint[], int[], bigint) IS
    'Create a pending order with its lines and a pending payment for a customer of the session tenant. Reserves stock.';

-- ---------------------------------------------------------------------------------------------
-- cancel_order: only before shipping. Releases reserved stock; pending payments fail, captured ones get a refund request.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.cancel_order(p_order_id bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_tenant int := shop.current_tenant();
    v_status smallint;
    m record;
BEGIN
    SELECT status_id INTO v_status
    FROM shop.orders
    WHERE order_id = p_order_id AND tenant_id = v_tenant AND deleted_at IS NULL
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'order % not found', p_order_id;
    END IF;
    IF v_status NOT IN (1, 2, 3, 8) THEN
        RAISE EXCEPTION 'order % cannot be cancelled in status %', p_order_id, v_status;
    END IF;

    FOR m IN SELECT warehouse_id, variant_id, -quantity AS qty
             FROM shop.inventory_movements
             WHERE reference_type = 'order' AND reference_id = p_order_id AND movement_type = 'sale'
    LOOP
        UPDATE shop.inventory SET quantity_reserved = greatest(quantity_reserved - m.qty, 0)
         WHERE warehouse_id = m.warehouse_id AND variant_id = m.variant_id;
        INSERT INTO shop.inventory_movements (warehouse_id, variant_id, movement_type, quantity, reference_type, reference_id)
        VALUES (m.warehouse_id, m.variant_id, 'return', m.qty, 'order', p_order_id);
    END LOOP;

    UPDATE shop.payments SET status = 'failed' WHERE order_id = p_order_id AND status IN ('pending', 'authorized');
    INSERT INTO shop.refunds (order_id, payment_id, amount, reason, status)
    SELECT order_id, payment_id, amount, 'order cancelled', 'approved'
    FROM shop.payments WHERE order_id = p_order_id AND status = 'captured';

    UPDATE shop.orders SET status_id = 6 WHERE order_id = p_order_id;
END
$$;
COMMENT ON PROCEDURE shop.cancel_order(bigint) IS 'Cancel an order that has not shipped; releases stock and handles payments.';

-- ---------------------------------------------------------------------------------------------
-- refund_order: delivered orders only. Full refund (amount NULL) marks the order refunded.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.refund_order(
    p_order_id bigint,
    p_amount   numeric DEFAULT NULL,
    p_reason   text DEFAULT 'customer request'
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_tenant     int := shop.current_tenant();
    v_order      shop.orders%ROWTYPE;
    v_payment_id bigint;
    v_refunded   numeric;
    v_amount     numeric;
BEGIN
    SELECT * INTO v_order FROM shop.orders
    WHERE order_id = p_order_id AND tenant_id = v_tenant AND deleted_at IS NULL
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'order % not found', p_order_id;
    END IF;
    IF v_order.status_id <> 5 THEN
        RAISE EXCEPTION 'only delivered orders can be refunded (order % has status %)', p_order_id, v_order.status_id;
    END IF;

    SELECT payment_id INTO v_payment_id FROM shop.payments
    WHERE order_id = p_order_id AND status = 'captured' ORDER BY payment_id DESC LIMIT 1;
    IF v_payment_id IS NULL THEN
        RAISE EXCEPTION 'order % has no captured payment', p_order_id;
    END IF;

    SELECT coalesce(sum(amount), 0) INTO v_refunded FROM shop.refunds WHERE order_id = p_order_id AND status <> 'rejected';
    v_amount := coalesce(p_amount, v_order.total_amount - v_refunded);
    IF v_amount <= 0 OR v_amount > v_order.total_amount - v_refunded THEN
        RAISE EXCEPTION 'refund amount % is not allowed (still refundable: %)', v_amount, v_order.total_amount - v_refunded;
    END IF;

    INSERT INTO shop.refunds (order_id, payment_id, amount, reason, status)
    VALUES (p_order_id, v_payment_id, v_amount, p_reason, 'processed');

    IF v_refunded + v_amount = v_order.total_amount THEN
        UPDATE shop.payments SET status = 'refunded' WHERE payment_id = v_payment_id;
        UPDATE shop.orders SET status_id = 7 WHERE order_id = p_order_id;
    END IF;
END
$$;
COMMENT ON PROCEDURE shop.refund_order(bigint, numeric, text) IS 'Refund a delivered order, fully (default) or partially.';

-- ---------------------------------------------------------------------------------------------
-- adjust_inventory: manual stock correction. Inventory is shared by all tenants, so there is no tenant check.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.adjust_inventory(
    p_warehouse_id smallint,
    p_variant_id   bigint,
    p_delta        int
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
BEGIN
    IF p_delta = 0 THEN
        RAISE EXCEPTION 'p_delta must not be zero';
    END IF;
    UPDATE shop.inventory SET quantity_on_hand = quantity_on_hand + p_delta
     WHERE warehouse_id = p_warehouse_id AND variant_id = p_variant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no inventory row for warehouse % and variant %', p_warehouse_id, p_variant_id;
    END IF;
    INSERT INTO shop.inventory_movements (warehouse_id, variant_id, movement_type, quantity, reference_type)
    VALUES (p_warehouse_id, p_variant_id, 'adjustment', p_delta, 'manual');
END
$$;
COMMENT ON PROCEDURE shop.adjust_inventory(smallint, bigint, int) IS 'Add or remove stock in one warehouse (positive or negative delta); logs a movement.';

-- ---------------------------------------------------------------------------------------------
-- update_customer_email
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.update_customer_email(p_customer_id bigint, p_new_email text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_email text := lower(trim(p_new_email));      -- normalise first, then validate what will actually be stored
BEGIN
    IF v_email IS NULL OR v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' THEN
        RAISE EXCEPTION 'invalid email address';
    END IF;
    UPDATE shop.customers SET email = v_email
     WHERE customer_id = p_customer_id AND tenant_id = shop.current_tenant() AND deleted_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'customer % not found', p_customer_id;
    END IF;
END
$$;
COMMENT ON PROCEDURE shop.update_customer_email(bigint, text) IS 'Change the email of a customer of the session tenant (must be unique per tenant).';

-- ---------------------------------------------------------------------------------------------
-- apply_discount: percent off the subtotal of an order that has not been paid yet (pending or on hold)
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.apply_discount(p_order_id bigint, p_percent numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_discount numeric;
BEGIN
    IF p_percent IS NULL OR p_percent < 0 OR p_percent > 50 THEN
        RAISE EXCEPTION 'p_percent must be between 0 and 50';
    END IF;
    UPDATE shop.orders
       SET discount_amount = round(subtotal * p_percent / 100, 2),
           total_amount    = subtotal + tax_amount + shipping_amount - round(subtotal * p_percent / 100, 2)
     WHERE order_id = p_order_id AND tenant_id = shop.current_tenant()
       AND status_id IN (1, 8) AND deleted_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'order % not found or no longer discountable', p_order_id;
    END IF;
END
$$;
COMMENT ON PROCEDURE shop.apply_discount(bigint, numeric) IS 'Give 0-50 percent off a pending or on-hold order of the session tenant.';

-- ---------------------------------------------------------------------------------------------
-- Batch procedures (long-running, touch many rows)
-- ---------------------------------------------------------------------------------------------

-- Soft-deletes finished orders placed before a date, in batches, COMMITting after each one so locks are released
-- and a failure keeps the finished batches. SECURITY INVOKER (see the header). Call it with autocommit on:
--   CALL shop.archive_old_orders(DATE '2024-03-01', 5000, 10);
CREATE OR REPLACE PROCEDURE shop.archive_old_orders(p_before date, p_batch_size int DEFAULT 5000, p_max_batches int DEFAULT 10)
LANGUAGE plpgsql AS $$
DECLARE
    v_batch int := 0;
    v_rows  int;
BEGIN
    WHILE v_batch < p_max_batches LOOP
        UPDATE shop.orders SET deleted_at = now()
         WHERE order_id IN (SELECT order_id FROM shop.orders
                             WHERE placed_at < p_before AND deleted_at IS NULL AND status_id IN (5, 6, 7)
                             ORDER BY order_id LIMIT p_batch_size);
        GET DIAGNOSTICS v_rows = ROW_COUNT;
        EXIT WHEN v_rows = 0;
        v_batch := v_batch + 1;
        RAISE NOTICE 'archived batch % (% orders)', v_batch, v_rows;
        COMMIT;
    END LOOP;
END
$$;
COMMENT ON PROCEDURE shop.archive_old_orders(date, int, int) IS
    'Soft-delete finished orders older than a date in committed batches. Needs autocommit; runs with the caller''s rights.';

-- Full-table maintenance across ALL tenants (it runs as the owner, so RLS does not limit it): repairs the
-- denormalized order_count, then recomputes tiers.
CREATE OR REPLACE PROCEDURE shop.recalc_customer_tiers()
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_counts int;
    v_tiers  int;
BEGIN
    UPDATE shop.customers c SET order_count = o.n
      FROM (SELECT customer_id, count(*)::int AS n FROM shop.orders GROUP BY customer_id) o
     WHERE o.customer_id = c.customer_id AND c.order_count <> o.n;
    GET DIAGNOSTICS v_counts = ROW_COUNT;

    UPDATE shop.customers SET tier = shop.tier_for_orders(order_count)
     WHERE tier <> shop.tier_for_orders(order_count);
    GET DIAGNOSTICS v_tiers = ROW_COUNT;

    RAISE NOTICE 'order_count repaired for % customers, tier changed for % customers', v_counts, v_tiers;
END
$$;
COMMENT ON PROCEDURE shop.recalc_customer_tiers() IS 'Repair customers.order_count and recompute every customer''s tier (all tenants).';

-- Refreshes the daily-sales snapshot. The materialized view is built as the owner, so it contains ALL tenants.
CREATE OR REPLACE PROCEDURE shop.rebuild_daily_aggregates()
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
BEGIN
    REFRESH MATERIALIZED VIEW shop.mv_daily_sales;
END
$$;
COMMENT ON PROCEDURE shop.rebuild_daily_aggregates() IS 'Refresh shop.mv_daily_sales (all tenants).';

-- Deletes abandoned carts that have not changed for N days; returns how many through the INOUT parameter.
CREATE OR REPLACE PROCEDURE shop.purge_abandoned_carts(p_older_than_days int DEFAULT 90, INOUT p_deleted bigint DEFAULT 0)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
BEGIN
    IF p_older_than_days < 7 THEN
        RAISE EXCEPTION 'refusing to purge carts newer than 7 days';
    END IF;
    DELETE FROM shop.carts
     WHERE status = 'abandoned' AND updated_at < now() - make_interval(days => p_older_than_days);
    GET DIAGNOSTICS p_deleted = ROW_COUNT;
END
$$;
COMMENT ON PROCEDURE shop.purge_abandoned_carts(int, bigint) IS 'Delete abandoned carts untouched for N days (minimum 7); returns the count.';
