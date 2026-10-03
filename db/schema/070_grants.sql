-- 070_grants.sql
-- Table-specific privileges that default privileges (001_roles.sql) cannot express.
--
-- Already granted by default privileges to every new table: SELECT to mcp_reader and mcp_writer;
-- SELECT/INSERT/UPDATE/TRUNCATE to loader.
-- Here: the only tables the MCP writer role may modify. It has no DELETE on payments, no DDL, and no
-- access to audit_log or inventory writes. mcp_proc_exec gets no table privileges at all.

SET ROLE shop_owner;

GRANT INSERT, UPDATE, DELETE ON
    shop.customers,
    shop.addresses,
    shop.carts,
    shop.orders,
    shop.order_items,
    shop.refunds
TO mcp_writer;
