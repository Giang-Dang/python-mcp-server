-- deadlock_a.sql + deadlock_b.sql: P11. A locks variant 1 then variant 2; B locks variant 2 then variant 1.
-- If both transactions are open at the same time each waits for the other; after deadlock_timeout (1 s) Postgres aborts one of them
-- with "deadlock detected" (SQLSTATE 40P01). Run them together:  run.ps1 -Scenario deadlock
-- The sleep between the two locks widens the window so that the collision is almost certain.
-- Rolled back unless  -D commit=1  (the updates are no-ops either way).
BEGIN;
UPDATE shop.inventory SET reorder_point = reorder_point WHERE variant_id = 1;
SELECT pg_sleep(0.3);
UPDATE shop.inventory SET reorder_point = reorder_point WHERE variant_id = 2;
\if :commit
COMMIT;
\else
ROLLBACK;
\endif
