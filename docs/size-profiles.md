# Size profiles

Two profiles exist, selected with `--scale S` or `--scale M` (default from `SHOP_SCALE` in `.env`). Both use the same 25 tables and
the same generators; only the row counts differ. Row counts are defined in one place: `src/shopdb/config.py`.

All numbers below were **measured**, not estimated, on one machine (Windows 11, 28 CPUs, Docker Desktop with 47 GB RAM, Postgres 17
in a container capped at 4 GB with `shared_buffers=1GB`). Use them as orders of magnitude, not guarantees: your CPU count, disk
and Docker memory change timings a lot.

## Row counts

| Table | S | M |
|---|---:|---:|
| tenants | 5 | 20 |
| customers | 50,000 | 1,000,000 |
| addresses | 100,000 | 2,000,000 |
| products | 10,000 | 100,000 |
| product_variants | 40,000 | 400,000 |
| orders | 200,000 | 5,000,000 |
| order_items | 599,268 | 14,998,089 |
| payments | 211,509 | 5,286,765 |
| shipments | 190,534 | 4,770,656 |
| shipment_items | 519,216 | 13,008,069 |
| invoices | 183,356 | 4,586,554 |
| refunds | 15,804 | 398,932 |
| carts | 100,000 | 2,000,000 |
| inventory | 80,000 | 800,000 |
| inventory_movements | 800,000 | 20,000,000 |
| audit_log | 1,500,000 | 30,000,000 |
| price_history | 30,000 | 400,000 |
| lookups, suppliers, warehouses, employees, categories | ~600 | ~7,300 |
| **Total rows** | **4,630,316** | **104,756,389** |

The order child tables (lines, payments, shipments, ...) are derived from the order plan, so their counts follow from the seed (42) and the
profile. A different `--seed` gives different, equally consistent numbers.

## Timings

| Step | S | M |
|---|---:|---:|
| Planning pass (reserve ids, count orders per customer) | 0.6 s | 14.9 s |
| `shopdb seed` (workers) | 24.9 s (8) | 307 s, about 5 min (12) |
| `shopdb verify` (39 checks, before post-load) | a few seconds | 45 s |
| `post-load`: indexes (`100`) | 1.8 s | 57.7 s |
| `post-load`: ANALYZE and first materialized-view fill (`140`) | 5.0 s | 40.9 s |
| `post-load`: everything else | under 1 s | under 1 s |
| `pytest` (11 tests, includes the full verifier) | 7 s | 46 s |
| Behaviour tests (`tests/sql/step4_checks.sql`, 39 checks) | a few seconds | 18 s |
| **Whole clean rebuild** (down -v, up, seed, post-load) | about 1 minute | about 8 minutes |

The original estimate for M was "1-3 hours". The real figure is far lower because the generator is deterministic Python that streams
`COPY` through many workers, and the planning pass makes every chunk independent of the others.

## Sizes

| | S | M |
|---|---:|---:|
| Database after the seed (primary keys and unique indexes only) | 741 MB | 16 GB |
| Database after post-load (137 indexes incl. partition children) | 889 MB | 19 GB |
| Of which indexes | about 340 MB | 7.6 GB |
| Write-ahead log in the container (`pg_wal`) | not measured | 4.1 GB |
| Data directory on disk | not measured | 24 GB |

Largest M tables (data + indexes): `audit_log` 7.1 GB (36 monthly partitions plus a default), `inventory_movements` 3.2 GB, `order_items` 2.1 GB,
`shipment_items` 1.6 GB, `orders` 1.5 GB. Regenerate with `db/observability/table_sizes.sql`.

The earlier plan estimated 8-10 GB for M. The real figure is about twice that, mostly because of wide `audit_log` rows (two JSONB columns)
and `inventory_movements`.

## What M shows that S does not

Measured on M, warm cache, as the `postgres` superuser (so row-level security does not apply):

| Planted problem | Query | M |
|---|---|---|
| P02 missing FK index | `order_items WHERE product_id = 42` vs the same by indexed `variant_id` | 840 ms vs 126 ms |
| P03 no partition pruning | `audit_log` by `(table_name, record_id)` with and without a one-month `created_at` filter | 12.8 ms vs 0.08 ms |
| P04 no trigram index | `products.description ILIKE '%wool%'` (100k products) | 173 ms, sequential scan |
| P07 stale statistics | `carts WHERE status = 'open'` | planner expects 677k rows, 1.92M returned |
| P09 unbounded queries | `count(*)` on `audit_log`; `orders JOIN order_items` count | 2.8 s; 2.5 s |
| P13 slow trigger | `UPDATE shipments SET status = ...` | 310 ms per updated row (8.8 ms at S) |
| P01 skew | planner estimate for `orders WHERE customer_id = 1` | 40 rows expected, 160 returned |

Honest caveat: these are warm-cache numbers. The Docker VM has 47 GB of RAM for its page cache, so almost everything is served from memory
(buffer hit ratio 99%). On a smaller machine, or with a cold cache, the same queries are slower, and the container's 4 GB limit
(3.4 GB in use after the load) becomes the real constraint.

## Not built

The original plan described profile M as about 60 tables (about 35 extra tables such as reviews, coupons, wishlists, tags, web sessions,
support tickets, returns, notifications). **That is not implemented.** M here is the same 25 tables with about 25 times the rows.
