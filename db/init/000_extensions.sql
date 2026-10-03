-- 000_extensions.sql
-- Runs as the postgres superuser against the 'shop' database, once, on first start.
--
-- pg_stat_statements: per-query timing and call counts (also needs shared_preload_libraries, set in
--                     docker-compose.yml). Used by db/observability/top_queries.sql.
-- pg_trgm:            trigram indexes for LIKE '%text%' searches. We install it so a fix for the planted
--                     problem P04 is possible, but we deliberately do NOT create the trigram index.
-- auto_explain is a module loaded through shared_preload_libraries; it needs no CREATE EXTENSION.

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
