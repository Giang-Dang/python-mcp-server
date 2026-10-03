# AGENTS.md

## Purpose

This repo is a learning project with two parts:

1. **`shop` database**: a realistic Postgres 17 e-commerce database (25 tables; profile S is
   4.6M rows / 0.9 GB, profile M is 105M rows / 19 GB) with triggers, stored procedures and deliberately planted performance
   problems. It runs in Docker and is filled by a Python seeder (`shopdb`).
2. **Guarded SQL MCP server** (`shopmcp`, implemented): authenticated Streamable HTTP server
   (Auth0) that bounds SQL reads, asks the human before mutations (MCP elicitation), calls only
   procedures from a reviewed registry (`config/procedures.yaml`) and records every operation in a
   separate `mcp_audit` database. Runbook: `docs/guarded-server.md`; status: `docs/roadmap.md`.

The original build plan lives in `C:\Users\dangv\.claude\plans\agreed-create-plan-to-atomic-pike.md`.

## Layout

- `db/init/` extensions and roles; `db/schema/` tables, partitions, views, RLS (run on first container start)
- `db/post_load/` indexes, triggers, functions, procedures (applied after seeding)
- `db/workload/` pgbench scripts; `db/observability/` diagnostic SQL
- `db/mcp/` explicit provisioning of the MCP monitor/audit roles and audit database (not run by container init)
- `db/audit/migrations/` versioned migrations for `mcp_audit`
- `src/shopdb/` seeder and CLI (`poetry run shopdb ...`); `src/mcp_server/` MCP server (`poetry run shopmcp ...`)
- Both packages are feature-first: `core/<feature>/` (domain, ports, application) plus `adapters/`
  (postgres, generation, identity, mcp, registry, ...), a `bootstrap`/composition root and their own settings
- `config/procedures.yaml` reviewed procedure registry; `.env.mcp` (git-ignored) runtime config, from `.env.mcp.example`
- `tests/` pytest suite and the isolated test Compose file; `docs/` documentation

## Commands

```powershell
poetry install                         # create .venv and install dependencies
docker compose up -d --wait           # start Postgres (needs Docker Desktop running)
poetry run shopdb seed --scale S      # load data (S default, M for the big profile)
poetry run shopdb verify              # seed checks (valid only on a freshly seeded database)
poetry run shopdb post-load           # indexes, functions, triggers, procedures, ANALYZE, grants (db/post_load)
poetry run shopdb docs                # regenerate docs/data-dictionary.md and docs/erd.md from the live catalog
poetry run shopmcp serve              # guarded SQL server on http://127.0.0.1:8000/mcp (needs .env.mcp and Auth0)
poetry run shopmcp inspect-registry   # read-only: live procedure definitions and hashes
poetry run shopmcp audit status       # audit migrations (needs SHOPMCP_MIGRATION_URL; `audit migrate` applies them)
poetry run pytest                     # default suite; database tests are skipped
docker compose -f tests/compose.yml up -d --wait   # isolated test Postgres on port 55439
poetry run python tests/seed_isolated.py           # seed it (S) and apply post-load
$env:SHOP_TEST_DATABASE='isolated'; poetry run pytest   # database tests (see docs/guarded-server.md#isolated-tests)
.\db\workload\run.ps1 -Scenario browse|orders|hot|deadlock|mixed   # pgbench load, rolled back unless -Commit
poetry run ruff check . ; poetry run ruff format .
```

Poetry is installed with `uv tool install poetry`; its executable is in `~/.local/bin`
(add it to PATH with `uv tool update-shell` if `poetry` is not found).
Postgres client tools are not on the host: use `docker compose exec db psql -U postgres -d shop`
(live, port 5433) or `docker compose -f tests/compose.yml exec db psql -U postgres -d shop` (test, port 55439).

## Conventions

- ASCII only in source, SQL and docs. Never use the en-dash U+2013 or other look-alikes of ASCII
  punctuation; use `-` (including date ranges).
- SQL: schema-qualified names (`shop.orders`), snake_case, numbered files that run in order,
  `COMMENT ON` for every table and important column (the data dictionary is generated from them).
- MCP server data access: SQLAlchemy Core (async, psycopg) in `src/mcp_server/adapters/postgres/`; no
  hand-written SQL strings for the server's own queries. Raw SQL is for `db/**/*.sql`, the seeder and tests,
  and for validated pass-through SQL (run with `exec_driver_sql`). No ORM.
- Core packages import no FastMCP, SQLAlchemy, psycopg, Faker, YAML or Pydantic types; `shopdb` and
  `mcp_server` never import each other. `src/mcp_server/db.py` and `server.py` are thin compatibility re-exports.
- Python 3.12+, ruff formatting (line length 100), type hints.
- Seed data must be deterministic: fixed seeds, no wall-clock dependence.

## Safety rules

- Once `shopdb post-load` has run, triggers exist and `shopdb seed` refuses to run (it would fire them for every row).
  To start over: `docker compose down -v` (ask first), `docker compose up -d --wait`, `shopdb seed`, `shopdb post-load`.
- `tests/sql/step4_checks.sql` is safe (one rolled-back transaction); it still advances sequences. Never run `archive_old_orders`,
  `bulk_update_prices`, `purge_abandoned_carts` or `recalc_customer_tiers` against the real data without asking.
- Ask before `docker compose down -v`, `shopdb reset` or anything else that destroys the data volume.
- The planted performance problems (P01-P13 in `docs/planted-problems.md`; `tests/test_planted.py` fails if one disappears) are intentional.
  Do not "fix" them with extra indexes or rewrites unless asked.
- Default scale in the repo is S. M is 105M rows, 19 GB and about 5 minutes to seed; do not start an M seed without asking.
  The local `.env` may say `SHOP_SCALE=M` (it is git-ignored). Database tests never read `.env`: they need
  `SHOP_TEST_DATABASE=isolated` and the test instance on port 55439.
- Mutation acceptance of the MCP server runs against the test instance (`SHOPMCP_POSTGRES_PORT=55439`), not the live
  database on 5433. Ask before pointing `shopmcp serve` at 5433 or applying `db/mcp/000_roles.sql` to it.
- Workload scripts in `db/workload` roll back by default. Ask before using `run.ps1 -Commit` (it changes stock, orders and audit rows).
- Never commit `.env` or `.env.mcp`. Keep audit migration-owner credentials (`SHOPMCP_MIGRATION_URL`) out of the
  server's environment. Do not run mutating SQL against the database without the user's approval.

## Documentation rule (important)

The user is learning from this project. Whenever you run a setup or build step:

1. Say in the chat reply why the step is being done.
2. In the same turn, append a numbered section to `docs/setup-guide.md` with: goal and why
   (including alternatives rejected), exact commands, what each command does and why, files
   created, real expected output, troubleshooting (errors actually hit), and concepts with links.
3. Record failures and their fixes honestly. A step is not done until its section exists.

## Status and next work

The server is implemented and verified by automated tests (isolated PostgreSQL, controlled Auth0 keys) and a real
Auth0 + Inspector login. See `docs/roadmap.md` section 6 for what was verified by hand and what was not.
