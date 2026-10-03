-- bloat.sql: dead rows and wasted space, from the statistics views (cheap and approximate: no table scan).
-- dead_pct high + last_autovacuum old/null = vacuum is not keeping up (P05) or is blocked by an old transaction (P12).
-- bytes_per_live_row far above the real row width = the table is mostly dead versions. (A tiny table has no useful ratio.)
\echo '--- Tables with the most dead rows ---'
SELECT s.relname,
       s.n_live_tup,
       s.n_dead_tup,
       round(100.0 * s.n_dead_tup / nullif(s.n_live_tup + s.n_dead_tup, 0), 1) AS dead_pct,
       pg_size_pretty(pg_table_size(s.relid))                                   AS table_size,
       round(pg_table_size(s.relid) / nullif(s.n_live_tup, 0))                  AS bytes_per_live_row,
       s.last_autovacuum,
       s.last_autoanalyze,
       coalesce((SELECT 'autovacuum off' FROM pg_class c
                  WHERE c.oid = s.relid AND 'autovacuum_enabled=false' = ANY (c.reloptions)), '') AS note
FROM pg_stat_user_tables s
WHERE s.schemaname = 'shop' AND s.n_live_tup > 1000
ORDER BY s.n_dead_tup DESC
LIMIT 12;

\echo '--- Oldest snapshot holders (what stops VACUUM from removing dead rows) ---'
SELECT pid, usename, state, backend_xmin, age(backend_xmin) AS xmin_age, now() - xact_start AS txn_age
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL AND datname = current_database()
ORDER BY age(backend_xmin) DESC LIMIT 5;
