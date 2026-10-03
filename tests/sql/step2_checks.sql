-- step2_checks.sql
-- Read-only verification of the database right after first start (before any data is loaded).
-- Run as the postgres superuser:
--   docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 < tests/sql/step2_checks.sql
-- The last block creates temporary rows inside a transaction and rolls it back.
--
-- EMPTY DATABASE ONLY: check 10 inserts tenants 1 and 2, so on a seeded database it stops with
-- "duplicate key value violates unique constraint tenants_pkey". Checks 1-9 are still valid then.
-- For row-level security against real data use tests/test_seed_integrity.py instead.

\echo '== 1. server and preload libraries'
SELECT version();
SHOW shared_preload_libraries;

\echo '== 2. extensions (expect pg_stat_statements, pg_trgm, plpgsql)'
SELECT extname, extversion FROM pg_extension ORDER BY extname;

\echo '== 3. tables in schema shop (expect 25 regular/partitioned parents, 37 partitions)'
SELECT count(*) FILTER (WHERE NOT c.relispartition) AS tables,
       count(*) FILTER (WHERE c.relispartition) AS partitions
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shop' AND c.relkind IN ('r', 'p');

\echo '== 4. views and materialized views'
SELECT c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shop' AND c.relkind IN ('v', 'm') ORDER BY 1;

\echo '== 5. roles (expect 5 application roles; loader has BYPASSRLS; nobody is superuser)'
SELECT rolname, rolcanlogin AS login, rolsuper AS super, rolbypassrls AS bypassrls
FROM pg_roles WHERE rolname IN ('shop_owner', 'loader', 'mcp_reader', 'mcp_writer', 'mcp_proc_exec')
ORDER BY rolname;

\echo '== 6. per-role session defaults'
SELECT r.rolname, s.setconfig
FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
ORDER BY r.rolname;

\echo '== 7. row-level security (expect customers, orders, payments = true)'
SELECT c.relname, c.relrowsecurity AS rls_enabled
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shop' AND c.relrowsecurity ORDER BY 1;

\echo '== 8. tables without a table comment (expect none)'
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shop' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND obj_description(c.oid, 'pg_class') IS NULL;

\echo '== 9. a new function is NOT executable by PUBLIC or the mcp roles (expect all false except owner)'
BEGIN;
SET LOCAL ROLE shop_owner;
CREATE FUNCTION shop.tmp_check() RETURNS int LANGUAGE sql AS 'SELECT 1';
RESET ROLE;
SELECT has_function_privilege('shop_owner', 'shop.tmp_check()', 'EXECUTE') AS owner,
       has_function_privilege('mcp_reader', 'shop.tmp_check()', 'EXECUTE') AS mcp_reader,
       has_function_privilege('mcp_proc_exec', 'shop.tmp_check()', 'EXECUTE') AS mcp_proc_exec;
ROLLBACK;

\echo '== 10. row-level security in action (expect 0 rows with no tenant set, 1 row for tenant 1, 1 row for tenant 2)'
BEGIN;
INSERT INTO shop.tenants (tenant_id, name) VALUES (1, 'tenant one'), (2, 'tenant two');
INSERT INTO shop.customers (tenant_id, email, first_name, last_name)
VALUES (1, 'a@example.test', 'A', 'One'), (2, 'b@example.test', 'B', 'Two');
SET LOCAL ROLE mcp_reader;
SELECT 'no tenant set' AS scenario, count(*) AS visible_customers FROM shop.customers;
SET LOCAL app.tenant_id = '1';
SELECT 'tenant 1' AS scenario, count(*) AS visible_customers FROM shop.customers;
SET LOCAL app.tenant_id = '2';
SELECT 'tenant 2' AS scenario, count(*) AS visible_customers FROM shop.customers;
RESET ROLE;
ROLLBACK;
