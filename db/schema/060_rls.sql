-- 060_rls.sql
-- Row-level security (RLS): the database itself filters rows by tenant.
--
-- Each session says which tenant it acts for with:   SET app.tenant_id = '1';
-- The mcp_* roles get a default of '1' (see 001_roles.sql). If the setting is missing or empty,
-- nullif() turns it into NULL, "tenant_id = NULL" is never true, and the session sees NO rows.
-- That "fail closed" behaviour is deliberate.
--
-- Who is NOT filtered: superusers, roles with BYPASSRLS (loader), and the table owner (shop_owner),
-- because we do not use FORCE ROW LEVEL SECURITY. SECURITY DEFINER routines run as the owner, so they
-- bypass RLS too.

SET ROLE shop_owner;

ALTER TABLE shop.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop.orders    ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop.payments  ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON shop.customers
    USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::int);

CREATE POLICY tenant_isolation ON shop.orders
    USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::int);

CREATE POLICY tenant_isolation ON shop.payments
    USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::int);
