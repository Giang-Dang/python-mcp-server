-- step4_checks.sql
-- Behaviour tests for indexes, triggers, routines and grants. Everything runs in ONE transaction that is rolled
-- back at the end, so the data is left untouched (sequences do advance; they are never rolled back).
-- Run as the postgres superuser against a freshly seeded database after `shopdb post-load`:
--   docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 < tests/sql/step4_checks.sql
-- Output: one row per check with PASS or FAIL. Checks named "(expected)" prove a deliberate weakness exists.

BEGIN;

CREATE TEMP TABLE t_results (n serial, name text, ok boolean, detail text);
CREATE TEMP TABLE t_ctx (k text PRIMARY KEY, v bigint);
CREATE FUNCTION pg_temp.rec(p_name text, p_ok boolean, p_detail text DEFAULT '') RETURNS void
LANGUAGE sql AS $$ INSERT INTO t_results (name, ok, detail) VALUES (p_name, p_ok, p_detail) $$;

-- ---------------------------------------------------------------------------------------------
-- Structure
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM pg_indexes WHERE schemaname = 'shop' AND tablename = 'order_items' AND indexdef ILIKE '%(product_id)%';
    PERFORM pg_temp.rec('P02 order_items(product_id) has no index (expected)', n = 0, n || ' indexes');
    SELECT count(*) INTO n FROM pg_indexes WHERE schemaname = 'shop' AND indexdef ILIKE '%gin_trgm_ops%';
    PERFORM pg_temp.rec('P04 no trigram index anywhere (expected)', n = 0, n || ' trigram indexes');
END
$$;

DO $$
DECLARE n int;
BEGIN
    SELECT count(DISTINCT t.tgname) INTO n FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'shop' AND NOT t.tgisinternal AND NOT c.relispartition;
    PERFORM pg_temp.rec('10 distinct trigger kinds exist', n = 10, n || ' kinds');
    SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace
     WHERE s.nspname = 'shop' AND p.prorettype <> 'trigger'::regtype;
    PERFORM pg_temp.rec('30 callable routines exist', n = 30, n || ' routines');
    SELECT count(*) INTO n FROM pg_stat_user_tables WHERE schemaname = 'shop' AND relname = 'carts' AND last_analyze IS NOT NULL;
    PERFORM pg_temp.rec('carts has autovacuum disabled (P07, expected)',
        coalesce((SELECT 'autovacuum_enabled=false' = ANY (reloptions) FROM pg_class WHERE oid = 'shop.carts'::regclass), false), '');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Pick test data
-- ---------------------------------------------------------------------------------------------
INSERT INTO t_ctx
SELECT 'cust', min(customer_id) FROM shop.customers WHERE tenant_id = 1 AND deleted_at IS NULL AND order_count < 10;
INSERT INTO t_ctx
SELECT 'other_cust', min(customer_id) FROM shop.customers WHERE tenant_id = 2 AND deleted_at IS NULL;
INSERT INTO t_ctx
SELECT 'v' || row_number() OVER (ORDER BY variant_id), variant_id FROM (
    SELECT DISTINCT variant_id FROM shop.inventory WHERE quantity_on_hand - quantity_reserved >= 20 ORDER BY variant_id LIMIT 2
) s;

-- ---------------------------------------------------------------------------------------------
-- create_order: tenant check, lines, totals, payment, stock reservation, audit, counter
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE
    v_cust bigint := (SELECT v FROM t_ctx WHERE k = 'cust');
    v1 bigint := (SELECT v FROM t_ctx WHERE k = 'v1');
    v2 bigint := (SELECT v FROM t_ctx WHERE k = 'v2');
    v_order bigint; v_count_before int; v_res_before bigint; o shop.orders%ROWTYPE;
    v_lines int; v_sum numeric; v_pay int; v_audit int; v_moves int;
BEGIN
    SELECT order_count INTO v_count_before FROM shop.customers WHERE customer_id = v_cust;
    SELECT sum(quantity_reserved) INTO v_res_before FROM shop.inventory WHERE variant_id IN (v1, v2);
    INSERT INTO t_ctx VALUES ('res_before', v_res_before);

    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.create_order(v_cust, ARRAY[v1, v2], ARRAY[1, 2], v_order);
    RESET ROLE;
    INSERT INTO t_ctx VALUES ('order', v_order);

    SELECT * INTO o FROM shop.orders WHERE order_id = v_order;
    SELECT count(*), sum(line_total) INTO v_lines, v_sum FROM shop.order_items WHERE order_id = v_order;
    PERFORM pg_temp.rec('create_order: pending order with 2 lines for the session tenant',
        o.status_id = 1 AND o.tenant_id = 1 AND v_lines = 2, format('status %s, tenant %s, lines %s', o.status_id, o.tenant_id, v_lines));
    PERFORM pg_temp.rec('create_order: statement trigger recomputed totals (subtotal = sum of lines, total adds tax and shipping)',
        o.subtotal = v_sum AND o.total_amount = v_sum + shop.calc_tax(v_sum) + shop.shipping_cost(v_sum) AND v_sum > 0,
        format('subtotal %s, total %s', o.subtotal, o.total_amount));
    SELECT count(*) INTO v_pay FROM shop.payments WHERE order_id = v_order AND status = 'pending' AND amount = o.total_amount;
    PERFORM pg_temp.rec('create_order: one pending payment for the order total', v_pay = 1, v_pay || ' payments');
    PERFORM pg_temp.rec('trigger: customers.order_count incremented',
        (SELECT order_count FROM shop.customers WHERE customer_id = v_cust) = v_count_before + 1, '');
    PERFORM pg_temp.rec('trigger: stock reserved for 1 + 2 units',
        (SELECT sum(quantity_reserved) FROM shop.inventory WHERE variant_id IN (v1, v2)) = v_res_before + 3, '');
    SELECT count(*) INTO v_moves FROM shop.inventory_movements WHERE reference_type = 'order' AND reference_id = v_order AND movement_type = 'sale';
    PERFORM pg_temp.rec('trigger: two sale movements logged', v_moves = 2, v_moves || ' movements');
    SELECT count(*) INTO v_audit FROM shop.audit_log WHERE table_name = 'orders' AND record_id = v_order AND action = 'I'
        AND tenant_id = 1 AND new_data IS NOT NULL;
    PERFORM pg_temp.rec('trigger: audit row written by the definer trigger', v_audit = 1, v_audit || ' rows');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('create_order scenario', false, SQLSTATE || ' ' || SQLERRM);
END
$$;

-- Wrong tenant: the customer exists, but belongs to tenant 2, and the session is tenant 1.
DO $$
DECLARE v1 bigint := (SELECT v FROM t_ctx WHERE k = 'v1'); v_other bigint := (SELECT v FROM t_ctx WHERE k = 'other_cust'); v_new bigint;
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.create_order(v_other, ARRAY[v1], ARRAY[1], v_new);
    RESET ROLE;
    PERFORM pg_temp.rec('create_order refuses a customer of another tenant', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('create_order refuses a customer of another tenant', SQLERRM LIKE 'customer % not found', SQLERRM);
END
$$;

-- Validation triggers
DO $$
DECLARE v_order bigint := (SELECT v FROM t_ctx WHERE k = 'order');
BEGIN
    BEGIN
        INSERT INTO shop.order_items (order_id, product_id, variant_id, quantity, unit_price, line_total)
        SELECT v_order, product_id, variant_id, 101, 1, 101 FROM shop.product_variants WHERE variant_id = (SELECT v FROM t_ctx WHERE k = 'v1');
        PERFORM pg_temp.rec('validate_order_item rejects quantity 101', false, 'no error raised');
    EXCEPTION WHEN check_violation THEN
        PERFORM pg_temp.rec('validate_order_item rejects quantity 101', true, SQLERRM);
    END;
    BEGIN
        UPDATE shop.orders SET status_id = 1 WHERE order_id = (SELECT order_id FROM shop.orders WHERE status_id = 5 LIMIT 1);
        PERFORM pg_temp.rec('validate_order_status blocks delivered -> pending', false, 'no error raised');
    EXCEPTION WHEN check_violation THEN
        PERFORM pg_temp.rec('validate_order_status blocks delivered -> pending', true, SQLERRM);
    END;
    BEGIN
        UPDATE shop.inventory SET quantity_reserved = quantity_on_hand + 1
         WHERE (warehouse_id, variant_id) = (SELECT warehouse_id, variant_id FROM shop.inventory LIMIT 1);
        PERFORM pg_temp.rec('validate_inventory blocks reserving more than on hand', false, 'no error raised');
    EXCEPTION WHEN check_violation THEN
        PERFORM pg_temp.rec('validate_inventory blocks reserving more than on hand', true, SQLERRM);
    END;
END
$$;

-- apply_discount, cancel_order
DO $$
DECLARE v_order bigint := (SELECT v FROM t_ctx WHERE k = 'order'); o shop.orders%ROWTYPE; v_expected numeric;
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.apply_discount(v_order, 10);
    RESET ROLE;
    SELECT * INTO o FROM shop.orders WHERE order_id = v_order;
    v_expected := round(o.subtotal * 0.10, 2);
    PERFORM pg_temp.rec('apply_discount: 10% off the subtotal', o.discount_amount = v_expected
        AND o.total_amount = o.subtotal + o.tax_amount + o.shipping_amount - v_expected, format('discount %s', o.discount_amount));
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('apply_discount scenario', false, SQLSTATE || ' ' || SQLERRM);
END
$$;

DO $$
DECLARE v_order bigint := (SELECT v FROM t_ctx WHERE k = 'order'); v1 bigint := (SELECT v FROM t_ctx WHERE k = 'v1'); v2 bigint := (SELECT v FROM t_ctx WHERE k = 'v2');
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.cancel_order(v_order);
    RESET ROLE;
    PERFORM pg_temp.rec('cancel_order: order cancelled', (SELECT status_id FROM shop.orders WHERE order_id = v_order) = 6, '');
    PERFORM pg_temp.rec('cancel_order: reserved stock released',
        (SELECT sum(quantity_reserved) FROM shop.inventory WHERE variant_id IN (v1, v2)) = (SELECT v FROM t_ctx WHERE k = 'res_before'), '');
    PERFORM pg_temp.rec('cancel_order: pending payment marked failed',
        (SELECT status FROM shop.payments WHERE order_id = v_order) = 'failed', '');
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.cancel_order(v_order);
    RESET ROLE;
    PERFORM pg_temp.rec('cancel_order twice is refused', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('cancel_order twice is refused', SQLERRM LIKE '%cannot be cancelled%', SQLERRM);
END
$$;

-- refund_order: partial refund keeps the order delivered, the remainder makes it refunded
DO $$
DECLARE v_order bigint; v_total numeric;
BEGIN
    SELECT o.order_id, o.total_amount INTO v_order, v_total
      FROM shop.orders o JOIN shop.payments p ON p.order_id = o.order_id AND p.status = 'captured'
     WHERE o.tenant_id = 1 AND o.status_id = 5 AND o.deleted_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM shop.refunds r WHERE r.order_id = o.order_id)
     ORDER BY o.order_id LIMIT 1;
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.refund_order(v_order, 1.00, 'test partial');
    RESET ROLE;
    PERFORM pg_temp.rec('refund_order: partial refund leaves the order delivered',
        (SELECT status_id FROM shop.orders WHERE order_id = v_order) = 5 AND (SELECT sum(amount) FROM shop.refunds WHERE order_id = v_order) = 1.00, '');
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.refund_order(v_order);
    RESET ROLE;
    PERFORM pg_temp.rec('refund_order: refunding the remainder marks the order refunded',
        (SELECT status_id FROM shop.orders WHERE order_id = v_order) = 7 AND (SELECT sum(amount) FROM shop.refunds WHERE order_id = v_order) = v_total, '');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('refund_order scenario', false, SQLSTATE || ' ' || SQLERRM);
END
$$;

-- update_customer_email, adjust_inventory
-- (Separate DO blocks: an error caught by an OUTER handler would roll back the rows recorded inside the block.)
DO $$
DECLARE v_cust bigint := (SELECT v FROM t_ctx WHERE k = 'cust');
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.update_customer_email(v_cust, 'not-an-email');
    RESET ROLE;
    PERFORM pg_temp.rec('update_customer_email rejects a bad address', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('update_customer_email rejects a bad address', SQLERRM = 'invalid email address', SQLERRM);
END
$$;

DO $$
DECLARE v_cust bigint := (SELECT v FROM t_ctx WHERE k = 'cust');
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.update_customer_email(v_cust, '  New.Address@Example.test ');
    RESET ROLE;
    PERFORM pg_temp.rec('update_customer_email trims, lowercases and saves',
        (SELECT email FROM shop.customers WHERE customer_id = v_cust) = 'new.address@example.test', '');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('update_customer_email trims, lowercases and saves', false, SQLERRM);
END
$$;

DO $$
DECLARE v_other bigint := (SELECT v FROM t_ctx WHERE k = 'other_cust');
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.update_customer_email(v_other, 'x@example.test');
    RESET ROLE;
    PERFORM pg_temp.rec('update_customer_email refuses another tenant''s customer', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('update_customer_email refuses another tenant''s customer', SQLERRM LIKE 'customer % not found', SQLERRM);
END
$$;

DO $$
DECLARE w smallint; v bigint; before_qty int;
BEGIN
    SELECT warehouse_id, variant_id, quantity_on_hand INTO w, v, before_qty FROM shop.inventory WHERE quantity_on_hand >= 50 ORDER BY variant_id LIMIT 1;
    SET LOCAL ROLE mcp_proc_exec;
    CALL shop.adjust_inventory(w, v, 5);
    RESET ROLE;
    PERFORM pg_temp.rec('adjust_inventory: +5 applied and logged',
        (SELECT quantity_on_hand FROM shop.inventory WHERE warehouse_id = w AND variant_id = v) = before_qty + 5
        AND EXISTS (SELECT 1 FROM shop.inventory_movements WHERE variant_id = v AND movement_type = 'adjustment' AND reference_type = 'manual'), '');
    SET LOCAL ROLE mcp_proc_exec;
    CALL shop.adjust_inventory(w, v, -(before_qty + 1000));
    RESET ROLE;
    PERFORM pg_temp.rec('adjust_inventory cannot take stock below zero', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('adjust_inventory cannot take stock below zero', SQLSTATE = '23514', SQLERRM);
END
$$;

-- Definer audit trigger works for a role that cannot write audit_log; updated_at trigger fires
DO $$
DECLARE v_order bigint; v_old timestamptz;
BEGIN
    SELECT order_id, updated_at INTO v_order, v_old FROM shop.orders WHERE tenant_id = 1 AND status_id = 5 AND deleted_at IS NULL ORDER BY order_id LIMIT 1 OFFSET 5;
    SET LOCAL ROLE mcp_writer;
    PERFORM set_config('app.tenant_id', '1', true);
    UPDATE shop.orders SET notes = 'touched by mcp_writer' WHERE order_id = v_order;
    RESET ROLE;
    PERFORM pg_temp.rec('mcp_writer UPDATE on orders succeeds although it cannot write audit_log (definer trigger)',
        EXISTS (SELECT 1 FROM shop.audit_log WHERE table_name = 'orders' AND record_id = v_order AND action = 'U'), '');
    PERFORM pg_temp.rec('trigger: updated_at advanced on UPDATE', (SELECT updated_at FROM shop.orders WHERE order_id = v_order) > v_old, '');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('mcp_writer audit scenario', false, SQLSTATE || ' ' || SQLERRM);
END
$$;

-- Soft-delete cascade
DO $$
DECLARE v_cust bigint; v_orders int;
BEGIN
    SELECT customer_id INTO v_cust FROM shop.customers WHERE tenant_id = 1 AND deleted_at IS NULL AND order_count BETWEEN 3 AND 6 ORDER BY customer_id OFFSET 3 LIMIT 1;
    UPDATE shop.customers SET deleted_at = now() WHERE customer_id = v_cust;
    SELECT count(*) INTO v_orders FROM shop.orders WHERE customer_id = v_cust AND deleted_at IS NULL;
    PERFORM pg_temp.rec('trigger: soft-deleting a customer soft-deletes their orders', v_orders = 0, v_orders || ' orders still active');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Privilege boundaries
-- ---------------------------------------------------------------------------------------------
DO $$
BEGIN
    SET LOCAL ROLE mcp_reader;
    PERFORM shop.calc_tax(100);
    RESET ROLE;
    PERFORM pg_temp.rec('mcp_reader may call a pure helper', true, '');
EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    PERFORM pg_temp.rec('mcp_reader may call a pure helper', false, SQLERRM);
END
$$;

DO $$
BEGIN
    SET LOCAL ROLE mcp_reader;
    CALL shop.cancel_order(1);
    RESET ROLE;
    PERFORM pg_temp.rec('mcp_reader may NOT call a write procedure', false, 'no error raised');
EXCEPTION WHEN insufficient_privilege THEN
    PERFORM pg_temp.rec('mcp_reader may NOT call a write procedure', true, SQLERRM);
END
$$;

DO $$
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM count(*) FROM shop.orders;
    RESET ROLE;
    PERFORM pg_temp.rec('mcp_proc_exec has no direct table access', false, 'no error raised');
EXCEPTION WHEN insufficient_privilege THEN
    PERFORM pg_temp.rec('mcp_proc_exec has no direct table access', true, SQLERRM);
END
$$;

DO $$
DECLARE n_top int; n_month int; n_other int; v_other bigint := (SELECT v FROM t_ctx WHERE k = 'other_cust');
BEGIN
    SET LOCAL ROLE mcp_reader;
    PERFORM set_config('app.tenant_id', '1', true);
    SELECT count(*) INTO n_top FROM shop.top_products(30, 5);
    SELECT count(*) INTO n_month FROM shop.monthly_sales_report(2025, 6);
    SELECT count(*) INTO n_other FROM shop.customer_lifetime_value(v_other);
    RESET ROLE;
    PERFORM pg_temp.rec('reports work for mcp_reader', n_top = 5 AND n_month > 0, format('top_products %s rows, monthly %s rows', n_top, n_month));
    PERFORM pg_temp.rec('report functions respect row-level security (other tenant''s customer is invisible)', n_other = 0, n_other || ' rows');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Adversarial routines: each proves its weakness exists
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE n_tenants int;
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    SELECT count(DISTINCT tenant_id) INTO n_tenants FROM shop.search_orders('true');
    RESET ROLE;
    PERFORM pg_temp.rec('A2 search_orders leaks other tenants'' orders (expected)', n_tenants > 1, n_tenants || ' tenants visible to a tenant-1 session');
    SET LOCAL ROLE mcp_proc_exec;
    PERFORM set_config('app.tenant_id', '1', true);
    SELECT count(*) INTO n_tenants FROM shop.search_orders('order_id IN (SELECT order_id FROM shop.orders WHERE tenant_id = 2) --');
    RESET ROLE;
    PERFORM pg_temp.rec('A2 search_orders accepts injected SQL (expected)', n_tenants > 0, n_tenants || ' rows from a subquery smuggled into the filter');
END
$$;

SELECT last_value AS v INTO TEMP t_seq_before FROM shop.invoice_number_seq;
SAVEPOINT sp_seq;
SET LOCAL ROLE mcp_proc_exec;
SELECT shop.get_next_invoice_number();
SELECT shop.get_next_invoice_number();
RESET ROLE;
ROLLBACK TO sp_seq;
DO $$
BEGIN
    PERFORM pg_temp.rec('A1 get_next_invoice_number advanced a sequence that a rollback does not undo (expected)',
        (SELECT last_value FROM shop.invoice_number_seq) >= (SELECT v FROM t_seq_before) + 2,
        format('before %s, after %s', (SELECT v FROM t_seq_before), (SELECT last_value FROM shop.invoice_number_seq)));
END
$$;

DO $$
BEGIN
    SET LOCAL ROLE mcp_writer;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.archive_old_orders(DATE '2024-02-01', 10, 1);
    RESET ROLE;
    PERFORM pg_temp.rec('A? archive_old_orders cannot COMMIT inside an explicit transaction', false, 'no error raised');
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_temp.rec('archive_old_orders cannot COMMIT inside an explicit transaction (needs autocommit)', SQLSTATE = '2D000', SQLSTATE || ' ' || SQLERRM);
END
$$;

-- statement_timeout is read when a statement STARTS, so it has to be set by a separate statement before the DO block.
SET LOCAL statement_timeout = '500ms';
DO $$
BEGIN
    SET LOCAL ROLE mcp_proc_exec;
    CALL shop.warm_cache(3);
    RESET ROLE;
    PERFORM pg_temp.rec('A3 warm_cache is stopped by statement_timeout', false, 'no error raised');
EXCEPTION WHEN query_canceled THEN
    PERFORM pg_temp.rec('A3 warm_cache is stopped by statement_timeout', true, SQLERRM);
END
$$;
SET LOCAL statement_timeout = 0;

DO $$
DECLARE v_status text; v_total numeric; v_cur refcursor := 'snap'; v_n int := 0; r record;
        v_id bigint := (SELECT order_id FROM shop.orders WHERE tenant_id = 1 AND status_id = 5 ORDER BY order_id LIMIT 1);
BEGIN
    SET LOCAL ROLE mcp_reader;
    PERFORM set_config('app.tenant_id', '1', true);
    CALL shop.order_snapshot(v_id, v_status, v_total, v_cur);
    LOOP
        FETCH v_cur INTO r;
        EXIT WHEN NOT FOUND;
        v_n := v_n + 1;
    END LOOP;
    RESET ROLE;
    PERFORM pg_temp.rec('A4 order_snapshot returns OUT values plus an open cursor', v_status = 'delivered' AND v_total > 0 AND v_n > 0,
        format('status %s, total %s, %s cursor rows', v_status, v_total, v_n));
END
$$;

DO $$
DECLARE n int; t timestamptz := clock_timestamp(); ms numeric;
BEGIN
    UPDATE shop.shipments SET status = 'returned' WHERE shipment_id IN (SELECT shipment_id FROM shop.shipments WHERE status = 'delivered' ORDER BY shipment_id LIMIT 20);
    GET DIAGNOSTICS n = ROW_COUNT;
    ms := round(extract(epoch FROM clock_timestamp() - t) * 1000);
    PERFORM pg_temp.rec('P13 slow trigger: ' || n || ' shipment updates took ' || ms || ' ms (informational)', n = 20, round(ms / n, 1) || ' ms per row');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Report
-- ---------------------------------------------------------------------------------------------
SELECT CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result, name, detail FROM t_results ORDER BY n;
SELECT count(*) FILTER (WHERE ok) AS passed, count(*) FILTER (WHERE NOT ok) AS failed FROM t_results;

ROLLBACK;
