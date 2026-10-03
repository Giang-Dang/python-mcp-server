# Planted problems

Thirteen deliberate weaknesses make the `shop` database behave like a real, slightly neglected production system. They exist so that
the guarded SQL MCP server (`shopmcp`, see [guarded-server.md](guarded-server.md)) has realistic things to detect, limit and survive. **Do not "fix" them by accident.**
Each one has a guard in `tests/test_planted.py` that fails if the problem disappears.

All numbers are from profile M (104.7M rows) on the build machine, warm cache, as the superuser (no row-level security).
At profile S the same problems exist but are smaller; the guard tests work at both.

| ID | Problem | Kind | Where |
|---|---|---|---|
| [P01](#p01-skewed-data) | Skewed data | planner | data (`model.py`) |
| [P02](#p02-foreign-key-without-an-index) | Foreign key without an index | missing index | `order_items.product_id` |
| [P03](#p03-partitioned-table-queried-without-the-partition-key) | No partition pruning | partitioning | `audit_log` |
| [P04](#p04-infix-text-search-without-a-trigram-index) | `LIKE '%x%'` without a trigram index | missing index | `products` |
| [P05](#p05-jsonb-bloat) | JSONB bloat | storage | `products.attributes` |
| [P06](#p06-soft-deleted-rows-everywhere) | Soft-deleted rows | design | customers, orders, products |
| [P07](#p07-stale-statistics) | Stale statistics | planner | `carts` |
| [P08](#p08-hot-row-contention) | Hot-row contention | concurrency | `inventory` |
| [P09](#p09-unbounded-queries) | Unbounded queries | resource use | any large table |
| [P10](#p10-huge-result-sets) | Huge result sets | resource use | any large table |
| [P11](#p11-deadlock) | Deadlock | concurrency | `inventory` |
| [P12](#p12-long-transaction-blocks-vacuum) | Long transaction blocks vacuum | maintenance | any table |
| [P13](#p13-slow-trigger) | Slow trigger | design | `shipments` |

Other deliberate traps are not numbered here but are listed in `docs/setup-guide.md` (step 4): the five adversarial routines
(`get_next_invoice_number`, `search_orders`, `warm_cache`, `order_snapshot`, `bulk_update_prices`) and the seven "known gaps"
(for example `order_items` having no row-level security, and the tenant being a setting any session can change).

---

## P01 Skewed data

**What:** 1% of customers place about 30% of the orders. Planner statistics assume values are spread evenly, so it cannot know a customer is "hot".

**Planted by:** `plan_order` in `src/shopdb/model.py` (77 of every 256 orders go to the first 1% of customers).

**Evidence:** top 1% of customers place 30.8% of the orders (at S and M). The planner estimates 40 orders for *any* customer id; customer 1 has 160 (4x under)
and customer 700,000 has 4 (10x over).

```sql
EXPLAIN (ANALYZE) SELECT * FROM shop.orders WHERE customer_id = 1;       -- rows=40 estimated, 160 actual
EXPLAIN (ANALYZE) SELECT * FROM shop.orders WHERE customer_id = 700000;  -- rows=40 estimated, 4 actual
```

**Why it matters for the MCP server:** plan quality depends on the parameter. A query that is fast for one customer can be slow for another, so one test run proves little.

**The usual fix (not applied):** extended statistics, a partial or composite index, or rewriting the query for the heavy hitters.

**Guard:** `test_p01_*`

## P02 Foreign key without an index

**What:** `order_items.product_id` references `products`, but nothing indexes it, so every lookup by product reads the whole 15M-row table, and so does deleting a product.

**Planted by:** a comment and a gap in `db/post_load/100_indexes.sql`.

**Evidence:** `WHERE product_id = 42`: 840 ms (parallel sequential scan); the same query by the indexed `variant_id`: 126 ms.

```sql
EXPLAIN (ANALYZE) SELECT count(*), sum(quantity) FROM shop.order_items WHERE product_id = 42;
```

**Why it matters:** the classic "works on the dev database" problem. An LLM writing a reasonable report query hits it at production size.

**The usual fix (not applied):** `CREATE INDEX ON shop.order_items (product_id);` (not timed on its own; the whole 28-index build took 58 s at M).

**Guard:** `test_p02_*`

## P03 Partitioned table queried without the partition key

**What:** `audit_log` is split into 36 monthly partitions (plus a default partition) by `created_at`. A query that does not mention `created_at` must look in every partition.

**Planted by:** `db/schema/040_append_partitioned.sql`; the only secondary index is `(table_name, record_id)`.

**Evidence:** by record id only: 12.8 ms, probes 37+ partition indexes; with a one-month `created_at` filter: 0.08 ms and exactly one partition (150x faster).

```sql
EXPLAIN (ANALYZE) SELECT count(*) FROM shop.audit_log WHERE table_name = 'orders' AND record_id = 123456;
EXPLAIN (ANALYZE) SELECT count(*) FROM shop.audit_log WHERE table_name = 'orders' AND record_id = 123456
                  AND created_at >= '2026-09-01' AND created_at < '2026-10-01';
```

**Why it matters:** the cost grows with the number of partitions, and an unbounded date range scans everything. A server could require or inject a date range.

**The usual fix (not applied):** always filter on the partition key; keep partitions few; detach and archive old ones.

**Guard:** `test_p03_*`

## P04 Infix text search without a trigram index

**What:** `ILIKE '%wool%'` cannot use a normal B-tree index. The `pg_trgm` extension is installed (it could make this fast) but no trigram index exists.

**Planted by:** `db/init/000_extensions.sql` installs it; `100_indexes.sql` deliberately omits the index.

**Evidence:** 173 ms, sequential scan of 100k products (the table is also bloated, see P05). It grows linearly with the table.

```sql
EXPLAIN (ANALYZE) SELECT count(*) FROM shop.products WHERE description ILIKE '%wool%';
```

**The usual fix (not applied):** `CREATE INDEX ON shop.products USING gin (description gin_trgm_ops);`

**Guard:** `test_p04_*`

## P05 JSONB bloat

**What:** each product has a ~1.2 KB JSONB document. A "catalog sync" rewrote every document three times while autovacuum was disabled, so the table holds about four versions of every row.

**Planted by:** `db/post_load/145_bloat.sql` (re-run safe: it does nothing if autovacuum is already off for the table).

**Evidence:** `products` grew from 120 MB to **496 MB** (4.1x) with 299,508 dead row versions: 5,202 bytes on disk per live row, where the real row is 1,229 bytes.
Every scan of the table reads about four times the pages it needs to.

```sql
SELECT pg_size_pretty(pg_table_size('shop.products')), n_live_tup, n_dead_tup
FROM pg_stat_user_tables WHERE relname = 'products';
```

**Why it matters:** size on disk is not row count times row width. Metadata queries about a table can mislead, and bloat explains "the table got slow although nothing changed".

**The usual fix (not applied):** `ALTER TABLE shop.products RESET (autovacuum_enabled);` then `VACUUM FULL shop.products;` (locks the table).

**Guard:** `test_p05_*`

## P06 Soft-deleted rows everywhere

**What:** customers (6%), orders (4%) and products (4%) are "deleted" by setting `deleted_at`, but the rows stay. Every query must remember `WHERE deleted_at IS NULL`, and no index excludes them.

**Planted by:** the generators in `src/shopdb/generators/` and the absence of partial indexes in `100_indexes.sql`.

**Evidence:** 6.1% of customers and about 4% of orders are soft-deleted. A query that forgets the filter silently counts deleted rows; `v_order_summary` and most procedures do filter them.

```sql
SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS active, count(*) AS total FROM shop.orders;
```

**Why it matters:** an LLM that writes `SELECT count(*) FROM shop.customers` gets a plausible but wrong answer. The schema comment on the column is the only warning.

**The usual fix (not applied):** partial indexes (`WHERE deleted_at IS NULL`), views that hide deleted rows, or moving deleted rows to an archive table.

**Guard:** `test_p06_*`

## P07 Stale statistics

**What:** `carts` was analyzed while about 20% of carts were `open`, then a "status migration" made 95% of them open, with autovacuum switched off so nothing refreshes the statistics.

**Planted by:** `db/post_load/140_analyze.sql`.

**Evidence:** the planner expects 677,494 open carts; 1,920,028 are open (2.8x under). The migration also doubled the table's pages and refreshed every cart's `updated_at`.

```sql
EXPLAIN (ANALYZE) SELECT * FROM shop.carts WHERE status = 'open';
```

**The usual fix (not applied):** `ALTER TABLE shop.carts RESET (autovacuum_enabled);` and `ANALYZE shop.carts;`.

**Guard:** `test_p07_*`

## P08 Hot-row contention

**What:** popular variants live in a few `inventory` rows, and every order line updates one (the `trg_reserve_inventory` trigger). Updates to the same row wait for each other, so throughput on a hot item is limited to one transaction at a time.

**Planted by:** `db/post_load/110_triggers.sql` and the skewed product popularity in the generators.

**Evidence:** while one session holds an update on an inventory row, a second one waits and, with `lock_timeout = 500ms`, fails with `LockNotAvailable` (SQLSTATE 55P03). The `mcp_*` roles carry `lock_timeout` of 3-5 s for exactly this reason.

**Why it matters:** a tool call can hang on someone else's transaction. The server needs timeouts and a clear "busy, retry" error.

**Guard:** `test_p08_*`

## P09 Unbounded queries

**What:** nothing stops `SELECT count(*)` over 30M rows, a join without a filter, or an accidental cross join.

**Evidence:** `count(*)` on `audit_log` takes 2.8 s; `orders JOIN order_items` count: 2.5 s; `orders CROSS JOIN customers` never finishes. Only `statement_timeout` ends it (15 s for `mcp_reader`; the test lowers it to 1.5 s).

```sql
SELECT count(*) FROM shop.orders a CROSS JOIN shop.customers b;   -- cancelled by statement_timeout
```

**Why it matters:** the server must set a timeout per call (and remember that `statement_timeout` is read when a statement starts), and ideally refuse high-cost plans using `EXPLAIN` before running them.

**Guard:** `test_p09_*`

## P10 Huge result sets

**What:** `SELECT * FROM shop.order_items` is 15M rows; returning it to an LLM is impossible and hurts the database.

**Evidence:** the planner's row estimate for that query is about 15M (600k at S).

**Why it matters:** the server needs a row cap and a byte cap with a "truncated" flag, and should fetch with a server-side cursor.

**Guard:** `test_p10_*`

## P11 Deadlock

**What:** two transactions that lock the same two rows in opposite order wait for each other forever. Postgres notices after `deadlock_timeout` (1 s here) and aborts one of them.

**Evidence:** the guard runs two threads over two `inventory` rows; exactly one gets `DeadlockDetected` (SQLSTATE 40P01), the other finishes. In real use this happens when two orders contain the same two variants in a different order.

**Why it matters:** a deadlock error is safe to retry; the server should classify it as retryable, unlike a constraint violation.

**Guard:** `test_p11_*`

## P12 Long transaction blocks vacuum

**What:** while any transaction with an old snapshot is open, `VACUUM` may not remove row versions that transaction could still see.

**Evidence:** on a scratch table, after updating 5,000 rows: while a `REPEATABLE READ` transaction was open, `VACUUM` left **5,000 dead rows**; after the transaction ended, **0**. The test creates and drops its own table (`shop._p12_scratch`).

**Why it matters:** an MCP session that opens a transaction and stays idle can quietly bloat the whole database. `idle_in_transaction_session_timeout` (30-60 s for the `mcp_*` roles) is the defence.

**Guard:** `test_p12_*`

## P13 Slow trigger

**What:** every shipment whose status changes runs `trg_carrier_sla`, which scans the entire `shipments` table (no index on `carrier`) to compute a delivery rate nobody reads.

**Planted by:** `db/post_load/110_triggers.sql`.

**Evidence:** 8.8 ms per updated row at S, **310 ms per updated row at M** (35x slower for 25x the rows). Updating 10,000 shipments would take about 50 minutes.

```sql
BEGIN;
UPDATE shop.shipments SET status = 'returned' WHERE shipment_id IN (SELECT shipment_id FROM shop.shipments WHERE status = 'delivered' LIMIT 20);
ROLLBACK;
```

**Why it matters:** the cost of an `UPDATE` is not visible in the statement. The server cannot see triggers by reading the SQL.

**The usual fix (not applied):** index `shipments (carrier, status)`, or compute the rate in a scheduled job.

**Guard:** `test_p13_*`

---

## If a problem was fixed by accident

Run `poetry run pytest tests/test_planted.py`; the failing test names the problem. To bring one back without rebuilding everything:

| Problem | Restore |
|---|---|
| P02 | `DROP INDEX shop.<the new index>;` |
| P05 | `ALTER TABLE shop.products SET (autovacuum_enabled = false);` then `poetry run shopdb post-load --only 145` rewrites the documents again |
| P07 | `ALTER TABLE shop.carts SET (autovacuum_enabled = false);` and rerun the `UPDATE` in `140_analyze.sql` after `ANALYZE shop.carts` |
| anything else | rebuild: `docker compose down -v` (ask first), `up -d --wait`, `shopdb seed`, `shopdb post-load` |
