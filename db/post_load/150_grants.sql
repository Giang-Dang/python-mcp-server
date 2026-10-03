-- 150_grants.sql
-- Who may EXECUTE which routine. Declarative and re-runnable: it first takes EXECUTE away from everyone, then grants.
-- New routines are not executable by PUBLIC (default privileges, see db/init/001_roles.sql), so anything not listed
-- here can only be run by shop_owner.
--
-- The grants are deliberately BROADER than what the MCP server should allow, as in many real databases. The server's
-- own allowlist (next phase) is the narrower gate; the database role is the backstop.
--   mcp_reader     pure helpers, report functions, order_snapshot       (read-only, row-level security applies)
--   mcp_writer     pure helpers, report functions, archive_old_orders   (it holds table privileges, which that invoker procedure needs)
--   mcp_proc_exec  pure helpers, write procedures, batch procedures that run as the owner, AND all adversarial
--                  routines except order_snapshot (an invoker procedure that would fail: this role has no table access)

SET ROLE shop_owner;

REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA shop FROM PUBLIC, mcp_reader, mcp_writer, mcp_proc_exec, loader;

DO $$
DECLARE
    helpers     text[] := ARRAY['current_tenant', 'calc_tax', 'shipping_cost', 'line_total', 'format_order_number',
                                'display_name', 'tier_for_orders', 'order_age_days', 'is_business_day', 'safe_divide',
                                'random_between'];
    reports     text[] := ARRAY['monthly_sales_report', 'customer_lifetime_value', 'low_stock_items', 'top_products'];
    write_procs text[] := ARRAY['create_order', 'cancel_order', 'refund_order', 'adjust_inventory',
                                'update_customer_email', 'apply_discount'];
    owner_batch text[] := ARRAY['recalc_customer_tiers', 'rebuild_daily_aggregates', 'purge_abandoned_carts'];
    adversarial text[] := ARRAY['get_next_invoice_number', 'search_orders', 'warm_cache', 'bulk_update_prices'];

    grants jsonb := jsonb_build_object(
        'mcp_reader',    to_jsonb(helpers || reports || ARRAY['order_snapshot']),
        'mcp_writer',    to_jsonb(helpers || reports || ARRAY['archive_old_orders']),
        'mcp_proc_exec', to_jsonb(helpers || write_procs || owner_batch || adversarial)
    );
    r record;
BEGIN
    FOR r IN
        SELECT g.key AS role_name, p.oid::regprocedure AS signature
        FROM jsonb_each(grants) g
        JOIN LATERAL jsonb_array_elements_text(g.value) AS routine(name) ON true
        JOIN pg_proc p ON p.proname = routine.name
        JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'shop'
    LOOP
        EXECUTE format('GRANT EXECUTE ON ROUTINE %s TO %I', r.signature, r.role_name);
    END LOOP;
END
$$;
