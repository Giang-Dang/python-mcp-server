# Python MCP Server

A learning project for building a Model Context Protocol (MCP) server around a realistic
PostgreSQL e-commerce database. The `shop` database includes generated data, tenant-aware
queries, stored procedures, and deliberate performance and security pitfalls to experiment with.

**Current status:** the database, feature-first seeder, and authenticated guarded SQL server
are implemented. `shopmcp serve` exposes nine tools over Streamable HTTP with Auth0,
bounded SQL, human-approved mutations, a reviewed procedure registry, and a separate audit
database. Automated HTTP and isolated PostgreSQL acceptance tests pass. A real Auth0
tenant and Inspector login still need to be configured and verified.

Start with [the server runbook](docs/guarded-server.md) for Auth0, audit provisioning,
runtime configuration, and the Inspector walkthrough.

## What is included

- PostgreSQL 17 in Docker, with 25 logical tables covering customers, products, orders,
  payments, shipping, inventory, and audit history.
- Deterministic Python data generation using Faker, multiprocessing, and PostgreSQL `COPY`.
  The same scale and seed reproduce the generated data with the locked dependencies.
- Two dataset sizes, monthly audit-log partitions, JSONB product attributes, two views,
  and a materialized daily-sales view.
- Separate database roles, row-level security (RLS) on customers, orders, and payments,
  plus indexes, triggers, reporting functions, and write procedures.
- Intentional exercises such as skewed data, missing indexes, stale statistics, a slow
  trigger, and routines whose names conceal side effects.
- Seed consistency checks, pytest tests, and SQL checks for permissions and routine behavior.

The [setup guide](docs/setup-guide.md) records the implementation steps, design decisions,
commands, measured results, and troubleshooting in detail.

## Requirements

- Python 3.12 or 3.13.
- Poetry 2.x for dependencies and the project virtual environment.
- Docker with Compose; on Windows, start Docker Desktop with Linux containers enabled.
- Enough memory for the database container's configured 4 GB limit, plus Python and Docker.

The commands below use PowerShell and run from the repository root. No host installation
of PostgreSQL or `psql` is needed; the database image includes the SQL client.

## Quick start

### 1. Configure and install

For a fresh checkout, copy the settings template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace every `*_PASSWORD` placeholder before starting the database.
Keep an existing `.env` when returning to the project. It is ignored by Git.

```powershell
poetry install
poetry run shopdb version
```

Poetry uses the committed `poetry.lock` and creates the environment in `.venv/`.
If you already use `uv`, you can install Poetry with `uv tool install poetry`.

### 2. Start PostgreSQL and load the default dataset

```powershell
docker compose up -d --wait
poetry run shopdb seed --scale S
poetry run shopdb verify --scale S
poetry run shopdb post-load
```

Keep this order:

1. Docker initializes extensions, roles, and the schema on an empty data volume.
2. `seed` loads the data, using eight worker processes by default.
3. `verify` checks row counts, relationships, totals, sequences, and expected data distributions.
4. `post-load` applies indexes, functions, triggers, procedures, statistics, and grants from
   `db/post_load/` in filename order. It also fills the materialized view and deliberately
   changes cart statuses to create a stale-statistics exercise.

Once post-load triggers exist, `seed` refuses to run, even with `--force`. Verification
describes the seeded baseline; after you modify data through SQL or procedures, its checks
may legitimately fail.

### 3. Explore the database

Open a SQL session as the reader role:

```powershell
docker compose exec db psql -U mcp_reader -d shop
```

Inside `psql`:

```sql
-- Reader sessions default to tenant 1.
SELECT current_setting('app.tenant_id');
SELECT order_id, placed_at, total_amount
FROM shop.orders
ORDER BY placed_at DESC
LIMIT 10;

-- Available after post-load.
SELECT * FROM shop.monthly_sales_report(2025, 6);
```

Use `\q` to exit. For a host-side database client, connect to `localhost:5433`, database
`shop`, with user `mcp_reader` and the `MCP_READER_PASSWORD` from `.env`.

## Configuration

The seeder reads settings from environment variables or `.env`; environment variables take
precedence. Docker Compose also uses `.env`. The server independently reads `.env.mcp`
and `SHOPMCP_*` variables and never loads seeder or migration-owner credentials.

| Setting | Default in the template | Purpose |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | Host used by the Python tools |
| `POSTGRES_PORT` | `5433` | Published host port; PostgreSQL listens on 5432 inside the container |
| `POSTGRES_DB` | `shop` | Database name; initialization SQL expects `shop` |
| `POSTGRES_USER` | `postgres` | Bootstrap superuser |
| `POSTGRES_PASSWORD` | Placeholder | Bootstrap superuser password |
| `SHOP_OWNER_PASSWORD`, `LOADER_PASSWORD` | Placeholders | Schema owner and seeder passwords |
| `MCP_READER_PASSWORD`, `MCP_WRITER_PASSWORD`, `MCP_PROC_EXEC_PASSWORD` | Placeholders | Application role passwords |
| `SHOP_SCALE` | `S` | Default profile for `seed` and `verify` |
| `SHOP_SEED` | `42` | Default random seed |

Role creation and schema initialization run only when the Docker data volume is empty.
Editing passwords in `.env` does not change passwords already stored in PostgreSQL.

## Dataset sizes

Both profiles currently use the same schema. Counts below come from
[`src/shopdb/config.py`](src/shopdb/config.py); child-table counts are derived by the generator.

| Data | S (default) | M |
| --- | ---: | ---: |
| Tenants | 5 | 20 |
| Customers | 50,000 | 1,000,000 |
| Products | 10,000 | 100,000 |
| Product variants | 40,000 | 400,000 |
| Orders | 200,000 | 5,000,000 |
| Carts | 100,000 | 2,000,000 |
| Inventory movements | 800,000 | 20,000,000 |
| Audit-log rows | 1,500,000 | 30,000,000 |

Order timestamps cover January 2024 through September 2026, independent of the date you
run the seeder. The setup guide records about 4.6 million total rows and an 889 MB database
after post-load for S with seed 42. These are recorded measurements, not size or speed guarantees.
M was measured on the build machine (28 CPUs, Docker with 47 GB RAM): 104,756,389 rows seeded in
about 5 minutes with 12 workers, a 16 GB database after the seed and 19 GB after post-load.
See [docs/size-profiles.md](docs/size-profiles.md) for the full numbers and caveats.

To choose M on a fresh database, replace the S seed and verification commands in the quick start:

```powershell
poetry run shopdb seed --scale M --confirm-large
poetry run shopdb verify --scale M
```

Set `SHOP_SCALE=M` in `.env` for subsequent seeder commands. Integration tests use their
own explicit S settings on port 55439. Pass a matching `--seed` to `verify` after seeding.

## CLI reference

All commands run through `poetry run shopdb`. Use `--help` on any command for its options.

| Command | Purpose |
| --- | --- |
| `version` | Print the installed package version |
| `seed --scale S --seed 42 --workers 8` | Generate and load a dataset |
| `verify --scale S --seed 42` | Check the database against the seeded baseline |
| `post-load` | Apply every post-load SQL file, one transaction per file |
| `post-load --only 100` | Apply only files whose names start with `100` (indexes) |
| `reset` | Delete all table data and restart identity sequences, with a confirmation prompt |

`seed --force` can truncate existing data before loading when post-load triggers are absent.
`reset` leaves the schema and triggers in place, so it does not enable reseeding after post-load.

To stop the database while preserving its data:

```powershell
docker compose down
```

A complete rebuild after post-load requires deleting the volume with `docker compose down -v`,
then repeating the start, seed, verify, and post-load steps. **Deleting the volume permanently
removes the database contents.** Use it only when you intend to discard them.

## Tests and development

```powershell
# Model and generator tests; no database required.
poetry run pytest tests/test_model.py

# Core, adapter, authentication and HTTP tests; database tests skip by default.
poetry run pytest

# Lint and check formatting without changing files.
poetry run ruff check .
poetry run ruff format --check .
```

Integration tests require `SHOP_TEST_DATABASE=isolated` and the dedicated Compose instance
on port 55439. Follow the two-phase [test procedure](docs/guarded-server.md#isolated-tests):
fresh-seed checks first, mutation tests afterward. They never select the local `.env` database.

Additional SQL checks live in [`tests/sql/`](tests/sql/). See the setup guide for how to run
them. `step4_checks.sql` exercises routines in a rolled-back transaction, but still advances
sequences; run it against a disposable learning database.

## Database roles and learning pitfalls

| Role | Intended use |
| --- | --- |
| `shop_owner` | Own schema objects and apply post-load SQL |
| `loader` | Load and verify data across tenants, with `BYPASSRLS` |
| `mcp_reader` | Read tables and selected routines; defaults to read-only transactions |
| `mcp_writer` | Read tables and modify selected tables |
| `mcp_proc_exec` | Execute granted routines without direct table privileges |
| `mcp_monitor` | Fixed read-only diagnostic reports |
| `mcp_audit_runtime` | Insert-only audit operations and events in `mcp_audit` |
| `mcp_audit_owner` | Audit migrations and read-only history inspection; absent from runtime settings |

This is a local learning database with intentional weaknesses, not a production security
template. RLS covers only `customers`, `orders`, and `payments`. The client can change
`app.tenant_id`, order lines and daily-sales aggregates expose cross-tenant data, and
`search_orders` deliberately uses unsafe dynamic SQL. Routine grants are broader than the
MCP server's allowlist. A `SELECT` or a routine named `get_*` is not necessarily free
of side effects.

The performance problems are also intentional. Adding indexes, analyzing tables, or rerunning
the statistics step can change the exercise. See the setup guide's known gaps and the comments
in [`db/post_load/`](db/post_load/) before experimenting.

## Repository layout

```text
db/
  init/                 Extensions, roles, and first-start schema loader
  schema/               Tables, partitions, views, RLS, and table grants
  post_load/            Indexes, functions, triggers, procedures, and statistics
src/
  shopdb/               Independent Core, adapters, settings, bootstrap, and CLI
  mcp_server/           Feature Core, async adapters, Auth0, settings, bootstrap, and CLI
config/procedures.yaml  Reviewed signatures, hashes, effects, and parameter limits
db/mcp/                 Explicit monitoring/audit provisioning (not fixture initialization)
db/audit/migrations/    Versioned audit migrations
tests/
  test_model.py         Database-independent generator tests
  test_seed_integrity.py Seed and permission integration tests
  sql/                  Schema and routine checks
docs/
  setup-guide.md        Implementation log and detailed troubleshooting
.env.example            Local configuration template
.env.mcp.example        Runtime-only server configuration template
docker-compose.yml      PostgreSQL service and persistent volume
pyproject.toml          Package metadata, dependencies, and tool configuration
poetry.lock             Locked dependency versions
```
