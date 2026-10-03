-- hot_inventory.sql: P08 hot-row contention. Many clients update stock for the same few variants (Zipf, exponent 1.5).
-- An UPDATE locks its row until the transaction ends, so clients queue behind each other on popular variants.
-- pg_sleep(0.005) stands for the application work done while the lock is held (calling a payment API, etc.).
-- Runs as loader. The UPDATE is a no-op write (reorder_point = reorder_point): it takes the row lock and writes a new
-- row version, so contention and bloat are real, but no value changes. Rolled back unless  -D commit=1.
\set v random_zipfian(1, 400000, 1.5)
BEGIN;
UPDATE shop.inventory SET reorder_point = reorder_point WHERE variant_id = :v;
SELECT pg_sleep(0.005);
\if :commit
COMMIT;
\else
ROLLBACK;
\endif
