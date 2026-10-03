-- locks.sql: who is blocked right now, and by whom. Run it in a second terminal WHILE a workload or a stuck session is running.
--   pg_blocking_pids(pid) lists the sessions that hold a lock this session is waiting for.
\echo '--- Blocked sessions and their blockers ---'
SELECT w.pid                                         AS waiting_pid,
       w.usename                                     AS waiting_user,
       now() - w.query_start                         AS waiting_for,
       left(regexp_replace(w.query, '\s+', ' ', 'g'), 70) AS waiting_query,
       b.pid                                         AS blocking_pid,
       b.usename                                     AS blocking_user,
       b.state                                       AS blocker_state,
       now() - b.xact_start                          AS blocker_txn_age,
       left(regexp_replace(b.query, '\s+', ' ', 'g'), 70) AS blocker_last_query
FROM pg_stat_activity w
JOIN LATERAL unnest(pg_blocking_pids(w.pid)) AS bp(pid) ON true
JOIN pg_stat_activity b ON b.pid = bp.pid
WHERE w.datname = current_database()
ORDER BY waiting_for DESC;

\echo '--- Open transactions older than 10 s (they hold locks and stop VACUUM, P12) ---'
SELECT pid, usename, state, now() - xact_start AS txn_age, wait_event_type, wait_event,
       left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS last_query
FROM pg_stat_activity
WHERE datname = current_database() AND xact_start IS NOT NULL
  AND now() - xact_start > interval '10 seconds' AND pid <> pg_backend_pid()
ORDER BY xact_start;

\echo '--- Deadlocks since the last stats reset ---'
SELECT datname, deadlocks, conflicts, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes
FROM pg_stat_database WHERE datname = current_database();
