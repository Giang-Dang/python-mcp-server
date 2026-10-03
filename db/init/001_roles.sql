-- 001_roles.sql
-- Runs as the postgres superuser, once, after 000_extensions.sql.
-- Creates the application schema and five roles with different powers. Passwords are read from the
-- container environment (set from .env) with psql's \getenv, so they never appear in a SQL file.

\getenv owner_pw SHOP_OWNER_PASSWORD
\getenv loader_pw LOADER_PASSWORD
\getenv reader_pw MCP_READER_PASSWORD
\getenv writer_pw MCP_WRITER_PASSWORD
\getenv proc_pw MCP_PROC_EXEC_PASSWORD

-- ---------------------------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------------------------
-- shop_owner: owns every object in the 'shop' schema and applies DDL (schema, indexes, triggers, procs).
CREATE ROLE shop_owner LOGIN PASSWORD :'owner_pw';

-- loader: used by the seeder. BYPASSRLS so it can insert rows for every tenant.
CREATE ROLE loader LOGIN PASSWORD :'loader_pw' BYPASSRLS;

-- mcp_reader: what the MCP server uses for read-only queries. SELECT only, subject to row-level security.
CREATE ROLE mcp_reader LOGIN PASSWORD :'reader_pw';

-- mcp_writer: what the MCP server uses for approved INSERT/UPDATE/DELETE on selected tables.
CREATE ROLE mcp_writer LOGIN PASSWORD :'writer_pw';

-- mcp_proc_exec: may only EXECUTE allowlisted routines (grants are added when routines are created).
CREATE ROLE mcp_proc_exec LOGIN PASSWORD :'proc_pw';

-- ---------------------------------------------------------------------------------------------
-- Database and schema access
-- ---------------------------------------------------------------------------------------------
-- By default every role may connect to every database (PUBLIC has CONNECT). Close that, then open it
-- only for the roles above.
REVOKE ALL ON DATABASE shop FROM PUBLIC;
GRANT CONNECT ON DATABASE shop TO shop_owner, loader, mcp_reader, mcp_writer, mcp_proc_exec;

CREATE SCHEMA shop AUTHORIZATION shop_owner;
GRANT USAGE ON SCHEMA shop TO loader, mcp_reader, mcp_writer, mcp_proc_exec;

-- ---------------------------------------------------------------------------------------------
-- Default privileges: apply to every object shop_owner creates LATER (tables, sequences, routines).
-- ---------------------------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner IN SCHEMA shop
    GRANT SELECT ON TABLES TO mcp_reader, mcp_writer;

ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner IN SCHEMA shop
    GRANT SELECT, INSERT, UPDATE, TRUNCATE ON TABLES TO loader;

ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner IN SCHEMA shop
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO loader, mcp_writer;

-- Postgres grants EXECUTE on every new function/procedure to PUBLIC unless told otherwise. Turn that off
-- so a routine is callable only by roles we explicitly grant. (No "IN SCHEMA": the built-in PUBLIC
-- default is global, so it can only be removed globally for this owner.)
ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner
    REVOKE EXECUTE ON ROUTINES FROM PUBLIC;

-- ---------------------------------------------------------------------------------------------
-- Per-role session defaults. These apply automatically each time the role logs in.
-- ---------------------------------------------------------------------------------------------
-- app.tenant_id is read by the row-level-security policies (db/schema/060_rls.sql). A role with no
-- value set sees no rows in tenant tables (fail closed).
ALTER ROLE shop_owner     SET search_path = shop, public;
ALTER ROLE loader         SET search_path = shop, public;

ALTER ROLE mcp_reader     SET search_path = shop, public;
ALTER ROLE mcp_reader     SET app.tenant_id = '1';
ALTER ROLE mcp_reader     SET default_transaction_read_only = on;
ALTER ROLE mcp_reader     SET statement_timeout = '15s';
ALTER ROLE mcp_reader     SET lock_timeout = '3s';
ALTER ROLE mcp_reader     SET idle_in_transaction_session_timeout = '30s';

ALTER ROLE mcp_writer     SET search_path = shop, public;
ALTER ROLE mcp_writer     SET app.tenant_id = '1';
ALTER ROLE mcp_writer     SET statement_timeout = '30s';
ALTER ROLE mcp_writer     SET lock_timeout = '5s';
ALTER ROLE mcp_writer     SET idle_in_transaction_session_timeout = '60s';

ALTER ROLE mcp_proc_exec  SET search_path = shop, public;
ALTER ROLE mcp_proc_exec  SET app.tenant_id = '1';
ALTER ROLE mcp_proc_exec  SET statement_timeout = '60s';
ALTER ROLE mcp_proc_exec  SET lock_timeout = '5s';
ALTER ROLE mcp_proc_exec  SET idle_in_transaction_session_timeout = '60s';
