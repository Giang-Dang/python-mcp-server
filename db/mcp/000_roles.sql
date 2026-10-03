-- Apply explicitly as postgres; does not modify the shop fixture or its grants.
\getenv monitor_pw MCP_MONITOR_PASSWORD
\getenv audit_owner_pw MCP_AUDIT_OWNER_PASSWORD
\getenv audit_pw MCP_AUDIT_PASSWORD
CREATE ROLE mcp_monitor LOGIN PASSWORD :'monitor_pw';
GRANT CONNECT ON DATABASE shop TO mcp_monitor;
GRANT pg_read_all_stats TO mcp_monitor;
ALTER ROLE mcp_monitor SET default_transaction_read_only = on;
ALTER ROLE mcp_monitor SET statement_timeout = '15s';
CREATE ROLE mcp_audit_owner LOGIN PASSWORD :'audit_owner_pw';
CREATE ROLE mcp_audit_runtime LOGIN PASSWORD :'audit_pw';
CREATE DATABASE mcp_audit OWNER mcp_audit_owner;
REVOKE ALL ON DATABASE mcp_audit FROM PUBLIC;
GRANT CONNECT ON DATABASE mcp_audit TO mcp_audit_runtime;
ALTER ROLE mcp_audit_runtime SET statement_timeout = '5s';
ALTER ROLE mcp_audit_runtime SET lock_timeout = '2s';
