-- top_queries.sql: the statements that cost the most, from pg_stat_statements. Run as postgres (or a role with pg_read_all_stats).
--   docker compose exec -T db psql -U postgres -d shop -f /db/observability/top_queries.sql   (or pipe it with Get-Content)
-- Read it like this: total_ms = where the server spent its time overall (fix these first); mean_ms = how slow one call is;
-- stddev_ms much larger than mean_ms = sometimes fast, sometimes terrible (skew, P01); hit_pct low = reads going to disk.
-- Reset the counters before an experiment with:  SELECT pg_stat_statements_reset();
\echo '--- Top 15 by total time ---'
SELECT round(total_exec_time::numeric, 0)                     AS total_ms,
       calls,
       round(mean_exec_time::numeric, 2)                      AS mean_ms,
       round(stddev_exec_time::numeric, 2)                    AS stddev_ms,
       rows,
       round(100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0), 1) AS hit_pct,
       r.rolname                                               AS role,
       left(regexp_replace(query, '\s+', ' ', 'g'), 110)       AS query
FROM pg_stat_statements s
JOIN pg_roles r ON r.oid = s.userid
WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND query NOT ILIKE '%pg_stat_statements%'
ORDER BY total_exec_time DESC
LIMIT 15;

\echo '--- Top 10 by mean time (calls >= 3) ---'
SELECT round(mean_exec_time::numeric, 2)  AS mean_ms,
       round(max_exec_time::numeric, 0)   AS max_ms,
       calls,
       left(regexp_replace(query, '\s+', ' ', 'g'), 130) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND calls >= 3 AND query NOT ILIKE '%pg_stat_statements%'
ORDER BY mean_exec_time DESC
LIMIT 10;
