-- 135_adversarial.sql
-- ADVERSARIAL ROUTINES: written to be risky on purpose, so the guarded SQL server (next phase) has realistic traps
-- to detect and refuse. Do not "fix" them. Each one is documented in docs/planted-problems.md.
-- Re-runnable.

SET ROLE shop_owner;

-- ---------------------------------------------------------------------------------------------
-- A1. The name says "get", the effect is a write. Every call advances a sequence (sequences are not rolled back).
--     SECURITY DEFINER so any caller with EXECUTE can advance it without any sequence privilege.
--     Lesson: a read-sounding name proves nothing; effects must be declared by a human, not guessed from the name.
-- ---------------------------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS shop.invoice_number_seq;

DO $$
BEGIN
    -- Start after the highest seeded invoice, but only if nobody has used the sequence yet.
    IF NOT (SELECT is_called FROM shop.invoice_number_seq) THEN
        PERFORM setval('shop.invoice_number_seq', (SELECT max(invoice_id) FROM shop.invoices));
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION shop.get_next_invoice_number() RETURNS text
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = shop, pg_temp
AS $$ SELECT 'INV-' || lpad(nextval('shop.invoice_number_seq')::text, 9, '0') $$;
COMMENT ON FUNCTION shop.get_next_invoice_number() IS 'ADVERSARIAL: sounds like a read but advances a sequence on every call.';

-- ---------------------------------------------------------------------------------------------
-- A2. Dynamic SQL built by string concatenation, running as the owner. Two problems at once:
--     SQL injection (p_filter is pasted into the query) and a tenant leak (the owner bypasses RLS, so even the
--     plain filter 'true' returns every tenant's orders).
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.search_orders(p_filter text DEFAULT 'true') RETURNS SETOF shop.orders
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
BEGIN
    RETURN QUERY EXECUTE 'SELECT * FROM shop.orders WHERE ' || coalesce(nullif(p_filter, ''), 'true') || ' LIMIT 100';
END
$$;
COMMENT ON FUNCTION shop.search_orders(text) IS 'ADVERSARIAL: concatenates p_filter into SQL and runs as the owner (injection and cross-tenant leak).';

-- ---------------------------------------------------------------------------------------------
-- A3. Sleeps. Stands in for a slow job; exceeds any reasonable statement_timeout when called with a big number.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.warm_cache(p_seconds int DEFAULT 5)
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_sleep(p_seconds);
    RAISE NOTICE 'cache warmed after % seconds', p_seconds;
END
$$;
COMMENT ON PROCEDURE shop.warm_cache(int) IS 'ADVERSARIAL: sleeps for p_seconds (tests timeouts and cancellation).';

-- ---------------------------------------------------------------------------------------------
-- A4. OUT parameters plus a cursor: the result is not a simple table. After the CALL, the lines are read with
--     FETCH ALL FROM <cursor name> inside the same transaction.
--       BEGIN; CALL shop.order_snapshot(123, NULL, NULL, 'lines'); FETCH ALL FROM lines; COMMIT;
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.order_snapshot(
    p_order_id bigint,
    OUT o_status text,
    OUT o_total numeric,
    INOUT o_lines refcursor
)
LANGUAGE plpgsql AS $$
BEGIN
    SELECT s.code, o.total_amount INTO o_status, o_total
      FROM shop.orders o JOIN shop.order_statuses s ON s.status_id = o.status_id
     WHERE o.order_id = p_order_id;
    OPEN o_lines FOR
        SELECT order_item_id, product_id, variant_id, quantity, line_total
          FROM shop.order_items WHERE order_id = p_order_id ORDER BY order_item_id;
END
$$;
COMMENT ON PROCEDURE shop.order_snapshot(bigint, text, numeric, refcursor) IS
    'ADVERSARIAL (shape): OUT parameters and an open cursor instead of a result set; read with FETCH in the same transaction.';

-- ---------------------------------------------------------------------------------------------
-- A5. Mass update with no safeguard. With p_category_id = NULL it changes EVERY product price and logs history.
--     Runs as the owner. Lesson: a single innocent-looking CALL can rewrite a whole table.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE shop.bulk_update_prices(p_percent numeric, p_category_id int DEFAULT NULL)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = shop, pg_temp AS $$
DECLARE
    v_rows int;
BEGIN
    IF p_percent IS NULL OR p_percent <= -100 THEN
        RAISE EXCEPTION 'p_percent must be greater than -100';
    END IF;
    INSERT INTO shop.price_history (product_id, old_price, new_price, changed_at, changed_by)
    SELECT product_id, base_price, round(base_price * (1 + p_percent / 100), 2), now(), session_user
      FROM shop.products WHERE p_category_id IS NULL OR category_id = p_category_id;

    UPDATE shop.products SET base_price = round(base_price * (1 + p_percent / 100), 2)
     WHERE p_category_id IS NULL OR category_id = p_category_id;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'updated % product prices', v_rows;
END
$$;
COMMENT ON PROCEDURE shop.bulk_update_prices(numeric, int) IS
    'ADVERSARIAL: with no category it rewrites the price of every product, as the owner.';
