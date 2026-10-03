-- table_sizes.sql
-- Row estimates and on-disk size per table (data, indexes, total), largest first, plus database totals.
-- Read-only. Pipe it into psql inside the container (this folder is not mounted into it):
--   PowerShell:  Get-Content db/observability/table_sizes.sql | docker compose exec -T db psql -U postgres -d shop
--   Git Bash:    MSYS_NO_PATHCONV=1 docker compose exec -T db psql -U postgres -d shop < db/observability/table_sizes.sql
-- est_rows is the planner's estimate (reltuples); use count(*) when you need an exact number.
-- A partitioned table (audit_log) stores nothing itself, so its size is the sum of its partitions.

WITH tables AS (
    SELECT c.oid, c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'shop' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
),
sizes AS (
    SELECT t.relname,
           CASE WHEN t.relkind = 'p'
                THEN (SELECT sum(c2.reltuples) FROM pg_partition_tree(t.oid) p JOIN pg_class c2 ON c2.oid = p.relid WHERE p.isleaf)
                ELSE (SELECT reltuples FROM pg_class WHERE oid = t.oid)
           END AS est_rows,
           CASE WHEN t.relkind = 'p'
                THEN (SELECT sum(pg_table_size(p.relid)) FROM pg_partition_tree(t.oid) p WHERE p.isleaf)
                ELSE pg_table_size(t.oid)
           END AS table_bytes,
           CASE WHEN t.relkind = 'p'
                THEN (SELECT sum(pg_indexes_size(p.relid)) FROM pg_partition_tree(t.oid) p WHERE p.isleaf)
                ELSE pg_indexes_size(t.oid)
           END AS index_bytes
    FROM tables t
)
SELECT relname AS table_name,
       est_rows::bigint AS est_rows,
       pg_size_pretty(table_bytes) AS table_size,
       pg_size_pretty(index_bytes) AS index_size,
       pg_size_pretty(table_bytes + index_bytes) AS total_size
FROM sizes
ORDER BY table_bytes + index_bytes DESC;

SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size,
       (SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'shop') AS index_count,
       (SELECT pg_size_pretty(sum(pg_relation_size(i.indexrelid))) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid
         JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'shop') AS all_indexes_size;
