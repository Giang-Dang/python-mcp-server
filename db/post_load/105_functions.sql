-- 105_functions.sql
-- Helper functions (pure, safe to expose) and read-only report functions.
-- Applied before the triggers (110) because triggers and procedures call these helpers.
--
-- Volatility is declared on purpose, because Postgres relies on it:
--   IMMUTABLE  same inputs always give the same output, no database access (pure maths and formatting)
--   STABLE     constant within one statement; may read tables or settings
--   VOLATILE   may change between calls or have side effects (the default if you say nothing)
-- All functions are SECURITY INVOKER (the default): they run with the caller's privileges, so row-level
-- security still applies to anything they read.

SET ROLE shop_owner;

-- ---------------------------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.current_tenant() RETURNS int
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT nullif(current_setting('app.tenant_id', true), '')::int $$;
COMMENT ON FUNCTION shop.current_tenant() IS 'Tenant id of this session (from app.tenant_id), or NULL when unset.';

CREATE OR REPLACE FUNCTION shop.calc_tax(p_amount numeric, p_country text DEFAULT 'US') RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT round(p_amount * CASE p_country WHEN 'GB' THEN 0.20 WHEN 'DE' THEN 0.19 WHEN 'FR' THEN 0.20 ELSE 0.08 END, 2)
$$;
COMMENT ON FUNCTION shop.calc_tax(numeric, text) IS 'Sales tax for an amount; 8% by default (the rate used by the seeder).';

CREATE OR REPLACE FUNCTION shop.shipping_cost(p_subtotal numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT CASE WHEN p_subtotal >= 100 THEN 0.00 ELSE 5.99 END $$;
COMMENT ON FUNCTION shop.shipping_cost(numeric) IS 'Free shipping from 100.00, otherwise 5.99.';

CREATE OR REPLACE FUNCTION shop.line_total(p_unit_price numeric, p_quantity int, p_discount numeric DEFAULT 0) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT p_unit_price * p_quantity - p_discount $$;
COMMENT ON FUNCTION shop.line_total(numeric, int, numeric) IS 'unit price x quantity minus the line discount.';

CREATE OR REPLACE FUNCTION shop.format_order_number(p_tenant_id int, p_order_id bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT 'ORD-' || lpad(p_tenant_id::text, 2, '0') || '-' || lpad(p_order_id::text, 8, '0') $$;
COMMENT ON FUNCTION shop.format_order_number(int, bigint) IS 'Builds order numbers like ORD-03-00000001.';

CREATE OR REPLACE FUNCTION shop.display_name(p_first text, p_last text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT trim(coalesce(p_first, '') || ' ' || coalesce(p_last, '')) $$;
COMMENT ON FUNCTION shop.display_name(text, text) IS 'First and last name joined with one space.';

CREATE OR REPLACE FUNCTION shop.tier_for_orders(p_orders int) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN p_orders >= 100 THEN 'platinum' WHEN p_orders >= 30 THEN 'gold' WHEN p_orders >= 12 THEN 'silver' ELSE 'standard' END
$$;
COMMENT ON FUNCTION shop.tier_for_orders(int) IS 'Loyalty tier for a number of orders (the thresholds used by the seeder).';

CREATE OR REPLACE FUNCTION shop.order_age_days(p_placed_at timestamptz) RETURNS int
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT (now()::date - p_placed_at::date) $$;
COMMENT ON FUNCTION shop.order_age_days(timestamptz) IS 'Whole days between an order date and today (STABLE: depends on now()).';

CREATE OR REPLACE FUNCTION shop.is_business_day(p_day date) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT extract(isodow FROM p_day) < 6 $$;
COMMENT ON FUNCTION shop.is_business_day(date) IS 'True for Monday to Friday (no holiday calendar).';

CREATE OR REPLACE FUNCTION shop.safe_divide(p_numerator numeric, p_denominator numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT p_numerator / nullif(p_denominator, 0) $$;
COMMENT ON FUNCTION shop.safe_divide(numeric, numeric) IS 'Division that returns NULL instead of failing on zero.';

CREATE OR REPLACE FUNCTION shop.random_between(p_low int, p_high int) RETURNS int
LANGUAGE sql VOLATILE
AS $$ SELECT p_low + floor(random() * (p_high - p_low + 1))::int $$;
COMMENT ON FUNCTION shop.random_between(int, int) IS 'Random integer in [low, high]. VOLATILE: a different value on every call.';

-- ---------------------------------------------------------------------------------------------
-- Report functions: read-only, SECURITY INVOKER, so RLS limits them to the caller's tenant.
-- Called with SELECT * FROM shop.monthly_sales_report(2025, 6)
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION shop.monthly_sales_report(p_year int, p_month int)
RETURNS TABLE (sales_date date, orders bigint, units bigint, revenue numeric)
LANGUAGE sql STABLE
AS $$
    SELECT o.placed_at::date,
           count(*),
           coalesce(sum(u.units), 0)::bigint,
           sum(o.total_amount)
    FROM shop.orders o
    LEFT JOIN LATERAL (SELECT sum(i.quantity) AS units FROM shop.order_items i WHERE i.order_id = o.order_id) u ON true
    WHERE o.placed_at >= make_date(p_year, p_month, 1)
      AND o.placed_at <  make_date(p_year, p_month, 1) + interval '1 month'
      AND o.deleted_at IS NULL
      AND o.status_id <> 6                      -- cancelled orders are not sales
    GROUP BY o.placed_at::date
    ORDER BY 1
$$;
COMMENT ON FUNCTION shop.monthly_sales_report(int, int) IS 'Orders, units and revenue per day for one month (cancelled and soft-deleted orders excluded).';

CREATE OR REPLACE FUNCTION shop.customer_lifetime_value(p_customer_id bigint)
RETURNS TABLE (customer_id bigint, orders bigint, units bigint, gross numeric, refunded numeric, net numeric,
               first_order timestamptz, last_order timestamptz)
LANGUAGE sql STABLE
AS $$
    SELECT c.customer_id,
           count(o.order_id),
           coalesce(sum(u.units), 0)::bigint,
           coalesce(sum(o.total_amount), 0),
           coalesce(sum(r.refunded), 0),
           coalesce(sum(o.total_amount), 0) - coalesce(sum(r.refunded), 0),
           min(o.placed_at),
           max(o.placed_at)
    FROM shop.customers c
    LEFT JOIN shop.orders o ON o.customer_id = c.customer_id AND o.deleted_at IS NULL AND o.status_id <> 6
    LEFT JOIN LATERAL (SELECT sum(i.quantity) AS units FROM shop.order_items i WHERE i.order_id = o.order_id) u ON true
    LEFT JOIN LATERAL (SELECT sum(f.amount) AS refunded FROM shop.refunds f WHERE f.order_id = o.order_id AND f.status <> 'rejected') r ON true
    WHERE c.customer_id = p_customer_id
    GROUP BY c.customer_id
$$;
COMMENT ON FUNCTION shop.customer_lifetime_value(bigint) IS 'Orders, units, gross, refunded and net revenue for one customer.';

CREATE OR REPLACE FUNCTION shop.low_stock_items(p_threshold int DEFAULT 10, p_limit int DEFAULT 100)
RETURNS TABLE (warehouse_id smallint, variant_id bigint, variant_sku text, product_name text, available int)
LANGUAGE sql STABLE
AS $$
    SELECT i.warehouse_id, i.variant_id, v.sku, p.name, i.quantity_on_hand - i.quantity_reserved
    FROM shop.inventory i
    JOIN shop.product_variants v ON v.variant_id = i.variant_id
    JOIN shop.products p ON p.product_id = v.product_id
    WHERE i.quantity_on_hand - i.quantity_reserved <= p_threshold
    ORDER BY i.quantity_on_hand - i.quantity_reserved, i.variant_id
    LIMIT least(p_limit, 1000)
$$;
COMMENT ON FUNCTION shop.low_stock_items(int, int) IS 'Variants whose available stock (on hand minus reserved) is at or below the threshold; capped at 1000 rows.';

CREATE OR REPLACE FUNCTION shop.top_products(p_days int DEFAULT 30, p_limit int DEFAULT 10)
RETURNS TABLE (product_id int, product_name text, units bigint, revenue numeric)
LANGUAGE sql STABLE
AS $$
    SELECT p.product_id, p.name, sum(i.quantity)::bigint, sum(i.line_total)
    FROM shop.orders o
    JOIN shop.order_items i ON i.order_id = o.order_id
    JOIN shop.products p ON p.product_id = i.product_id
    WHERE o.placed_at >= (SELECT max(placed_at) FROM shop.orders) - make_interval(days => p_days)
      AND o.deleted_at IS NULL
      AND o.status_id <> 6
    GROUP BY p.product_id, p.name
    ORDER BY sum(i.line_total) DESC
    LIMIT least(p_limit, 1000)
$$;
COMMENT ON FUNCTION shop.top_products(int, int) IS 'Best sellers by revenue over the last N days, counted back from the newest order (not from today).';
