-- place_order.sql: the write path of a checkout, through shop.create_order (SECURITY DEFINER, 5+ tables, triggers, stock reservation).
-- Runs as shop_owner because only the owner can both look up valid ids and EXECUTE the procedure; mcp_proc_exec has no table access.
-- The tenant is set the way an application would: SET app.tenant_id for the session.
--
-- SAFE BY DEFAULT: the transaction is rolled back unless you pass  -D commit=1  (run.ps1 -Commit). A rolled-back run still costs
-- CPU, WAL and sequence numbers and leaves dead rows, but changes no visible data.
--
-- pgbench has no :'name' quoting (that is psql), so the SQL returns an already-quoted literal in :vids.
-- Only variants with at least 6 units available are chosen: the stock validation trigger rejects an order for an empty variant
-- (correctly), and pgbench aborts a client on any error other than a deadlock or serialization failure. With -Commit the stock
-- shrinks as orders commit, so a long committed run will eventually abort for that reason.
-- Start points stay away from the end of the id ranges so the next valid row at or after the start always exists.
-- The first variant is Zipf-skewed (popular items), so concurrent clients reserve stock on the same inventory rows (P08).
SET app.tenant_id = '1';
\set c random(1, 990000)
\set v random_zipfian(1, 300000, 1.3)
\set q1 random(1, 3)
\set q2 random(1, 2)
SELECT customer_id AS cid FROM shop.customers
 WHERE tenant_id = 1 AND deleted_at IS NULL AND customer_id >= :c ORDER BY customer_id LIMIT 1 \gset
SELECT quote_literal(array_agg(variant_id)::text) AS vids FROM (
    SELECT v.variant_id FROM shop.product_variants v JOIN shop.products p ON p.product_id = v.product_id
     WHERE v.variant_id >= :v AND v.is_active AND p.deleted_at IS NULL
       AND EXISTS (SELECT 1 FROM shop.inventory i WHERE i.variant_id = v.variant_id
                   AND i.quantity_on_hand - i.quantity_reserved >= 6)
     ORDER BY v.variant_id LIMIT 2) s \gset
BEGIN;
CALL shop.create_order(:cid, :vids::bigint[], ARRAY[:q1, :q2], NULL);
\if :commit
COMMIT;
\else
ROLLBACK;
\endif
