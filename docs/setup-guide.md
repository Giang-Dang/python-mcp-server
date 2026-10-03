# Setup guide

A step-by-step log of how this project was set up, written as each step was executed. Each step
says what was done, **why**, the exact commands, what to expect, and what went wrong. Commands are
PowerShell unless noted; the shell used while building was Git Bash, so a few snippets use Bash syntax.

## Prerequisites (versions found on the build machine)

| Tool | Version found | Needed for | Notes |
|---|---|---|---|
| Windows | 11 Pro | host | |
| Git | 2.56.0 | version control | |
| Python | 3.13.12 | seeder and MCP server | Project accepts 3.12 or 3.13 (`requires-python`) |
| uv | 0.9.26 | installing Poetry in isolation | https://docs.astral.sh/uv/ |
| Poetry | 2.5.1 (installed in step 1) | dependency and virtualenv management | not present at the start |
| Docker Desktop | CLI 29.7.2, Compose 5.5.0 | runs Postgres 17 | daemon was **not running** at the start |
| psql | not installed on host | SQL shell | we use `docker compose exec db psql` instead |
| Free disk on F: | 813 GB | M profile needs 10-15 GB | |

---

## Step 1: Scaffold the repository and Python environment

### Goal and why

Create an empty but working project skeleton before any database work: version control, a Python
environment with pinned dependencies, linting, a CLI entry point, and the rules for future sessions.

Why first: every later step adds files and commands. If git, the environment and the conventions
exist from the start, each later step is a small, reviewable change, and a broken environment is
discovered now instead of in the middle of a 30-minute data load.

Alternatives considered:
- **pip + venv**: simpler, but you chose Poetry. Poetry also gives a lock file (`poetry.lock`), so
  the exact dependency versions can be reproduced.
- **Install Poetry with pip/pipx**: `uv tool install` puts Poetry in its own isolated environment, so it
  cannot conflict with project dependencies or the global Python, and `uv` was already installed.

### Commands

```powershell
# 0. Check the tools the plan depends on
git --version; docker --version; poetry --version; python --version; uv --version

# 1. Install Poetry in an isolated environment (Poetry was missing)
uv tool install poetry
#    If 'poetry' is not found afterwards, add uv's tool bin dir to PATH:  uv tool update-shell

# 2. Initialise git (no commit yet)
git init -b main

# 3. Create folders
mkdir docs, db\init, db\schema, db\post_load, db\workload, db\observability, src\shopdb\generators, src\mcp_server, tests

# 4. Write the project files (see "Files created"), then validate the Poetry file
poetry config virtualenvs.in-project true --local
poetry check

# 5. Create .venv and install dependencies (also writes poetry.lock)
poetry env use python
poetry install

# 6. Verify
poetry run shopdb version
poetry run python -c "import psycopg, faker, fastmcp, typer"
poetry run ruff check . ; poetry run ruff format --check .
```

### What each command does and why

- `uv tool install poetry`: installs the `poetry` executable into `C:\Users\<you>\.local\bin` with its own
  private virtualenv.
- `git init -b main`: creates the repository with `main` as the first branch. We do not commit yet; you decide when.
- `poetry config virtualenvs.in-project true --local`: writes `poetry.toml` so the virtualenv is created
  in `./.venv`. Why: it is easy to find, delete and select in an IDE, and it keeps this project's packages out of
  your user profile. `--local` limits the setting to this project.
- `poetry check`: validates `pyproject.toml` before the slower install.
- `poetry install`: resolves dependency versions, writes `poetry.lock`, creates `.venv`, installs everything
  including the project itself in editable mode (that is what makes the `shopdb` command exist).
- `poetry run ...`: runs a command inside the project's virtualenv without activating it.

### Files created

| File | Purpose |
|---|---|
| `.gitattributes` | Forces LF line endings for `.sql`, `.sh`, `.yml`, `.py`, `.md`, `.toml`. Why: Git on Windows can convert files to CRLF, and CRLF in an SQL or shell script that runs inside a Linux container causes confusing errors. |
| `.gitignore` | Keeps `.env` (passwords), `.venv/`, caches and logs out of git. |
| `.env.example` | Template for local settings and role passwords. The real `.env` is created in step 2 and never committed. Port 5433 avoids clashing with any local Postgres on 5432. |
| `pyproject.toml` | Project metadata, dependencies (`psycopg[binary]`, `faker`, `typer`, `pydantic-settings`, `fastmcp`), dev tools (`pytest`, `ruff`), and the `shopdb` command. |
| `poetry.toml`, `poetry.lock` | In-project virtualenv setting; exact resolved versions. Commit both. |
| `src/shopdb/cli.py` (+ package stubs) | Minimal Typer CLI with a `version` command so we can prove the install works. |
| `CLAUDE.md` | Instructions for future Claude sessions: layout, commands, conventions, safety rules, the documentation rule. |
| `docs/setup-guide.md` | This file. |
| `README.md` | Empty placeholder (`pyproject.toml` references it); written in the final step. |

### Expected output

```text
$ poetry --version
Poetry (version 2.5.1)

$ poetry install
...
  - Installing psycopg-binary (3.3.6)
  - Installing fastmcp (4.0.10)
  - Installing psycopg (3.3.6)
  - Installing faker (40.40.0)
  - Installing pytest (9.1.1)
  - Installing ruff (0.16.10)
Writing lock file
Installing the current project: python-mcp-server (0.1.0)

$ poetry run shopdb version
0.1.0

$ poetry run ruff check .
All checks passed!
```

If you re-run this later without the lock file you may get newer versions; `poetry.lock` pins the ones used here.

### Troubleshooting

- **`shopdb version` failed with "Got unexpected extra argument(s) (version)".** When a Typer app has only one
  command, Typer makes that command the root command, so there is no `version` subcommand. Fix: add an
  `@app.callback()` function in `cli.py`, which tells Typer the app is a group of subcommands. This would have
  fixed itself once a second command existed, but the callback makes it behave correctly from the start.
- **`poetry: command not found` after `uv tool install`.** The tool directory is not on PATH in the current
  shell. Run `uv tool update-shell` and open a new terminal, or call it by full path.
- **Docker daemon not running** (`failed to connect to the docker API ... dockerDesktopLinuxEngine`).
  Start Docker Desktop and wait until it says "Engine running". Step 1 does not need it; step 2 does.
- **A long heredoc in Git Bash failed with "unexpected EOF while looking for matching `'`".** Nested quotes and
  backticks inside a shell heredoc are fragile. For long Markdown files, write the file with an editor or a
  file-writing tool instead of a shell heredoc.

### Concepts

- **Virtual environment**: a private folder of installed packages for one project. See https://docs.python.org/3/tutorial/venv.html
- **Lock file**: records the exact version of every dependency so every install is identical. See https://python-poetry.org/docs/basic-usage/#installing-with-poetrylock
- **Entry point**: `[project.scripts] shopdb = "shopdb.cli:app"` makes `shopdb` a command that calls `app` in `shopdb/cli.py`.
- **FastMCP** is installed now but unused until the MCP stub step. The installed version is 4.x, newer than most
  tutorials, so check its docs at that step instead of trusting older examples.

---

## Step 2: Postgres in Docker, roles, schema, row-level security

### Goal and why

Start an empty-but-complete `shop` database: Postgres 17 in a container, five roles with different powers, the
25 profile-S tables (plus 37 monthly partitions of the audit log), three views, and row-level security (RLS).
No data yet; the seeder comes in step 3.

Why now, and in this order:
- **The database has to exist before the seeder can be written**, because the seeder's generators must match real
  column names and constraints.
- **Roles and permissions come with the schema, not later.** The whole point of the next project phase is a server
  that is safe to point at this database. If the roles exist from day one, every later step is tested the way the MCP
  server will actually connect (as `mcp_reader`, `mcp_writer`, ...) and not as a superuser that can do anything.
- **Schema before indexes and triggers.** Bulk-loading into a table that already has secondary indexes and triggers
  is much slower, and triggers would write audit rows during seeding. So this step creates only tables, primary
  keys, unique constraints and foreign keys. Indexes, triggers and procedures arrive in step 4, after the load.

Alternatives considered:
- **Create the schema from Python at seed time**: rejected. SQL files are readable, diffable, and reusable by anyone
  with `psql`; Python would hide the schema inside code.
- **A migration tool (Alembic/sqitch)**: rejected for this project. It adds a tool to learn that is not the goal.
- **The `postgres:17-alpine` image (already on the machine)**: rejected. Alpine uses musl instead of glibc, which sorts
  text differently from most production Linux servers.
- **Testing directly on the real container**: rejected. Init scripts run only once per data volume, so a typo leaves a
  half-built volume that must be deleted. I tested on a throwaway copy first (see Commands).

### Commands

```powershell
# 1. Create .env from the template and give every password a random value (never commit .env)
copy .env.example .env      # then replace each *_PASSWORD value, e.g. with:  python -c "import secrets; print(secrets.token_hex(16))"

# 2. Validate the compose file and download the image (first time only, ~450 MB)
docker compose config --quiet
docker pull postgres:17

# 3. Dry run on a throwaway copy: different project name and port, so it cannot touch the real stack
$env:POSTGRES_PORT = "5434"
docker compose -p shopdb_scratch up -d --wait
docker compose -p shopdb_scratch logs db          # look for ">>> applying ..." lines and no ERROR
docker compose -p shopdb_scratch exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 < tests/sql/step2_checks.sql
docker compose -p shopdb_scratch down -v          # removes ONLY the scratch volume
Remove-Item Env:POSTGRES_PORT

# 4. Start the real stack and run the same checks
docker compose up -d --wait
docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 < tests/sql/step2_checks.sql
```

(In PowerShell the `<` redirect is not supported; use `Get-Content tests/sql/step2_checks.sql | docker compose exec -T db psql ...`.
In Git Bash, prefix commands that pass `/paths` to a container with `MSYS_NO_PATHCONV=1`.)

### What each command does and why it is needed

- `docker compose config --quiet`: parses the compose file and prints nothing if it is valid. Catches YAML mistakes before a container starts.
- `docker compose up -d --wait`: starts in the background (`-d`) and blocks until the container's healthcheck passes (`--wait`).
  That is what makes the next command safe to run immediately.
- `-p shopdb_scratch`: the Compose **project name**. Container, network and volume names are prefixed with it, so the scratch copy is
  fully separate from the real stack (`shopdb`). Port 5434 avoids clashing with the real stack on 5433.
- `psql -v ON_ERROR_STOP=1`: stop at the first SQL error and return a non-zero exit code.
- `down -v`: stops the stack **and deletes its volumes**. Safe here only because the project is the scratch one. On the real
  stack this deletes all data; never run it there without meaning to.
- Port **5433** on the host maps to 5432 in the container, so it does not collide with any Postgres you may install later.

### Files created

| File | Purpose |
|---|---|
| `.env` (not committed) | Real passwords and ports. |
| `docker-compose.yml` | Postgres 17, 4 GB memory cap, `shared_buffers=1GB`, `pg_stat_statements` + `auto_explain`, named volume, TCP healthcheck. |
| `db/init/000_extensions.sql` | `pg_stat_statements` (query statistics) and `pg_trgm` (trigram search; installed but deliberately unused, see problem P04). |
| `db/init/001_roles.sql` | Creates `shop_owner`, `loader`, `mcp_reader`, `mcp_writer`, `mcp_proc_exec`; the `shop` schema; default privileges; per-role timeouts and tenant. |
| `db/init/010_schema.sh` | The image only runs files directly inside `docker-entrypoint-initdb.d`, not sub-folders, so this wrapper applies `db/schema/*.sql` in order. |
| `db/schema/010_reference.sql` ... `070_grants.sql` | 5 lookup tables, 8 core tables, 8 order tables, 4 append-heavy tables (one partitioned), 2 views + 1 materialized view, RLS policies, writer grants. |
| `tests/sql/step2_checks.sql` | The verification queries used below. Reused by pytest later. |

### Expected output

Start-up logs show each init script running, in order, with no errors:

```text
/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/000_extensions.sql
/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/001_roles.sql
/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/010_schema.sh
>>> applying /db/schema/010_reference.sql
...
>>> applying /db/schema/070_grants.sql
PostgreSQL init process complete; ready for start up.
```

The verification script prints (trimmed):

```text
PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2) ...        shared_preload_libraries = pg_stat_statements,auto_explain
extensions: pg_stat_statements 1.11, pg_trgm 1.6, plpgsql 1.0
tables = 25, partitions = 37                           views: v_low_stock, v_order_summary; matview: mv_daily_sales
roles: loader (bypassrls = t); shop_owner, mcp_reader, mcp_writer, mcp_proc_exec; nobody is a superuser
RLS enabled on: customers, orders, payments            tables without a comment: 0 rows
new function executable by owner = t, mcp_reader = f, mcp_proc_exec = f
RLS test: no tenant set -> 0 rows, tenant 1 -> 1 row, tenant 2 -> 1 row
```

Logging in as each role (password read inside the container, never typed or printed) gave the expected results:

```text
mcp_reader   -> tenant=1, default_transaction_read_only=on, statement_timeout=15s
mcp_reader   -> SELECT ok;  INSERT: "cannot execute INSERT in a read-only transaction"
mcp_writer   -> DML on refunds ok; payments: "permission denied for table payments"; CREATE TABLE: "permission denied for schema shop"
mcp_proc_exec-> SELECT on customers: "permission denied for table customers"
loader       -> can INSERT and TRUNCATE; DROP TABLE: "must be owner of table countries"
```

### Troubleshooting and things that were not obvious

- **The healthcheck must use TCP.** `pg_isready` without `-h 127.0.0.1` talks to the Unix socket. During first-time
  initialization the image runs a *temporary* server that listens only on that socket, so the check would report
  "healthy" before the schema exists and `--wait` would return too early. The compose file uses `-h 127.0.0.1`.
- **Init scripts run once.** They run only when the data volume is empty. If you change a file in `db/init` or `db/schema`
  and want it applied, you must recreate the volume: `docker compose down -v` (this deletes all data; for a not-yet-seeded
  database that is harmless, but afterwards it means a full re-seed). For quick iteration use the scratch project from step 3 above.
- **No `restart:` policy on purpose.** If an init script fails, the container exits. With `restart: unless-stopped` it
  would restart in a loop and hide the error.
- **Identity column on a partitioned table worked.** I was not sure Postgres 17 allowed `GENERATED BY DEFAULT AS IDENTITY` on a
  partitioned table (older versions refuse). It does, so no workaround was needed.
- **`SET ROLE` does not apply the role's saved defaults; a real login does.** In check 10 the tenant was unset after
  `SET LOCAL ROLE mcp_reader`, so the reader saw 0 rows. That is the fail-closed RLS design working, and also a reminder to
  test with real logins (as done above).
- **`default_transaction_read_only = on` is advisory.** A client can run `SET default_transaction_read_only = off`. What
  actually stops `mcp_reader` from writing is that it has no INSERT/UPDATE/DELETE privilege: after turning the setting off,
  the INSERT still failed with `permission denied for table countries`. Use both layers.
- **Rolled-back test rows still consume identity numbers.** Sequences are not transactional, so the RLS test advanced the
  `customers` sequence by 2 even though the rows were rolled back. The seeder resets sequences after loading anyway.
- **Git Bash rewrites `/paths`.** Passing `/db/...` to a container command from Git Bash can turn it into a Windows path.
  Prefix with `MSYS_NO_PATHCONV=1` (or use PowerShell).
- **A Go-template function was missing** (`docker info --format '{{div ...}}'`): Docker's templates have no `div`. Read the raw
  byte count instead and divide in Python.

### Concepts

- **`/docker-entrypoint-initdb.d`**: the official Postgres image runs `*.sql` and `*.sh` files here in alphabetical order on first start.
  https://hub.docker.com/_/postgres (section "Initialization scripts")
- **Roles and privileges**: a role is a user or group; `GRANT` gives it rights on objects. https://www.postgresql.org/docs/17/user-manag.html
- **Default privileges**: `ALTER DEFAULT PRIVILEGES` pre-sets the grants for objects an owner creates in the future, so new tables are
  readable by the right roles without extra GRANTs. https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html
- **Why `REVOKE EXECUTE ... FROM PUBLIC`**: by default Postgres lets everyone run any new function. For a server that must only run allowlisted
  routines, that default is turned off.
- **Row-level security**: policies that add a hidden `WHERE` to every query by a role. Superusers, `BYPASSRLS` roles and (without `FORCE`) the table
  owner skip it, and so do `SECURITY DEFINER` functions and views without `security_invoker`. https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- **Declarative partitioning**: `audit_log` is split into one table per month by `created_at`; queries that filter on that column read only the matching
  partitions ("partition pruning"). https://www.postgresql.org/docs/17/ddl-partitioning.html
- **psql `\getenv`**: reads an environment variable into a psql variable so passwords come from `.env`, not from SQL files. https://www.postgresql.org/docs/17/app-psql.html
- **Compose healthcheck and `--wait`**: https://docs.docker.com/reference/compose-file/services/#healthcheck

---

## Step 3: The seeder (Faker + COPY + parallel workers)

### Goal and why

Fill the empty database with about 4.6 million rows of realistic, deterministic data (profile S), and prove the data is
correct. The same code scales to profile M by changing one option.

Why now: the next steps (indexes, triggers, procedures, planted performance problems) all need real rows to act on. A
trigger you cannot fire or a missing index you cannot feel is not much of a lesson.

The design choices, and why each was made:

1. **Every value is a pure function of `(seed, id)`** (`src/shopdb/model.py`). Which customer placed order 1234, how many
   lines it has, its status, its date: all computed by hashing, never looked up. Why: parallel workers can each generate any
   slice of any table without talking to each other or reading the database, and the same seed always gives identical data
   (a test proves it). Alternative rejected: generate rows randomly and read parent ids back from the database. That is slow,
   serializes the workers, and makes runs unrepeatable.
2. **A planning pass before loading.** `compute_order_layout` walks all orders once (0.6 s for 200k) and works out how many
   child rows each order produces. Why: child tables use identity ids, so every parallel chunk needs a guaranteed
   non-overlapping id range, and `customers.order_count` has to be correct at load time, before orders exist. The planner gives both.
3. **Stages in foreign-key order.** Lookups, then customers/products, then addresses/variants, then orders and everything else.
   Why: a stage can only start once the parents it references are committed. Inside a stage all chunks run in parallel.
4. **One transaction per chunk.** An order chunk loads orders, lines, payments, shipments, invoices and refunds together. Why: if a
   worker fails, its chunk rolls back entirely, so you never end up with an order that has no lines.
5. **`COPY ... FROM STDIN`, not INSERT.** Why: COPY is the fastest way to load rows (one command, streamed), typically 10-50x
   faster than row-by-row INSERT.
6. **Faker where text quality matters, plain `random` where volume matters.** Names, emails, addresses and product text come
   from Faker (with US, GB, DE, FR, CA and AU locales so addresses look right per country). The 30-million-row tables (audit log,
   stock movements) are built from `random` and small pools, because Faker costs tens of microseconds per call. You asked for
   "Faker + COPY streaming with multiprocessing"; this keeps that design and only avoids Faker on the rows where it would
   not add realism.
7. **The `loader` role, not a superuser.** It has `BYPASSRLS` (it must insert rows for every tenant) and INSERT/UPDATE/TRUNCATE, nothing else.
   Why: the seeder then exercises the same permission model as everything else.
8. **Money in integer cents** (`cents()` formats them). Why: floating point cannot represent 0.10 exactly, and the verifier compares sums exactly.

### Commands

```powershell
# Pure-logic unit tests (no database needed) and the integration test (skips itself if the DB is down)
poetry run pytest -q

# Load the S profile into the empty database (about 30 seconds)
poetry run shopdb seed --scale S --workers 8

# Check the result against the model
poetry run shopdb verify --scale S
```

Other commands that now exist:

| Command | What it does |
|---|---|
| `shopdb seed --scale M --confirm-large` | The large profile. Needs the explicit flag because it loads about 10-15 GB. Not run yet. |
| `shopdb seed --force` | Truncates existing data first. Without `--force`, seeding refuses to run on a non-empty database. |
| `shopdb reset [--yes]` | Truncates every table and restarts identity sequences. Destroys all data, so it asks for confirmation. |
| `--seed N` | Different seed, different (but internally consistent) data. Default comes from `SHOP_SEED` in `.env`. |

### What each part does and why it is needed

- `--workers 8`: eight loader processes. More than the number of CPU cores gains nothing, and a single Postgres container
  also has a limit on how many parallel COPY streams help.
- `shopdb verify` re-runs the planner to know what to expect, then compares: 25 exact row counts (the lookups included),
  13 consistency queries, and the identity sequences. It exits non-zero on any failure, so it can gate a script or CI.
- `SET synchronous_commit = off` (inside each worker): Postgres will not wait for the WAL flush at commit. A crash could lose the
  last few chunks, which only means seeding again. This is a loader-only setting; normal sessions keep durable commits.

### Files created

| File | Purpose |
|---|---|
| `src/shopdb/config.py` | `.env` settings (pydantic-settings) and the S/M row-count profiles. One place to change sizes. |
| `src/shopdb/model.py` | The pure, deterministic rules: hashing, the order plan, tenants, prices, the planning pass. |
| `src/shopdb/context.py` | The read-only data sent once to every worker process. |
| `src/shopdb/generators/` | `static.py` (lookups, tenants, suppliers...), `core.py` (customers, addresses, products...), `orders.py` (an order and all its children), `append.py` (carts, inventory, movements, audit log, price history), `fake.py` (cached Faker instances). |
| `src/shopdb/loader.py` | COPY helper, worker pool, stages, sequence reset, truncate. |
| `src/shopdb/verify.py` | The 39 checks. |
| `src/shopdb/db.py`, `cli.py` | Connection helper; the `seed`, `verify`, `reset`, `version` commands. |
| `tests/test_model.py`, `tests/test_seed_integrity.py` | 11 tests: determinism, planted skew, id layout, then the full verification and tenant isolation against the live database. |

### Expected output

```text
Planning orders for scale S (seed 42) ...
  planned 200,000 orders -> 599,268 lines, 211,509 payments (0.6s)
Loaded lookups, tenants, categories, suppliers, warehouses (0.2s)
Stage B: customers, products, employees: 3 chunks on 8 workers
  [3/3] customers chunk 0: 50,000 rows in 4.8s
Stage C: addresses, product variants: 2 chunks on 8 workers
Stage D: orders and children, carts, inventory, movements, audit log, price history: 21 chunks on 8 workers
  [1/21] orders chunk 3: 244,965 rows in 5.4s
  ...
Reset 19 identity sequences
Done: 4,630,316 rows in 27.0s
```

```text
PASS  rows in orders: 200,000 (expected 200,000)
PASS  rows in order_items: 599,268 (expected 599,268)
PASS  order total = subtotal + tax + shipping - discount: 0 mismatching orders (allowed 0..0)
PASS  customers.order_count = real number of orders: 0 mismatching customers (allowed 0..0)
PASS  P01 skew: share of orders placed by the top 1% of customers (%): 30.8 percent (allowed 25..40)
PASS  identity sequences are past max(id) (19 tables): all ok
39 passed, 0 failed
```

What the data looks like afterwards: database size 741 MB (only primary-key and unique indexes exist so far); tenant 1 sees 19,905
customers and 78,208 orders through row-level security (about 40%); a session with no tenant set sees 0 rows; the biggest table is
`inventory_movements` at 95 MB.

### Troubleshooting and things that were not obvious

- **A smoke test failed with "order chunk 0: id layout drifted".** That was the safety assertion doing its job. I had cut the first
  order chunk down to 200 orders to test quickly, so the ids handed out could not match the plan for the full 25,000. Re-running with
  the full chunk passed. The assertion exists to catch a real bug (generator and planner disagreeing) before it becomes a
  confusing primary-key collision.
- **Lint complaints about `%` formatting and implicit string concatenation.** Fixed in code instead of silencing the rules: f-strings for
  the audit JSON, parentheses around multi-line SQL strings, `enumerate()` for a counter. The `{{` `}}` in f-strings are literal braces.
- **`ruff format` rewrote the files after I wrote them.** Harmless, and the reason the editor reported "file changed on disk".
- **`est_rows = -1` in `pg_class.reltuples`.** Nobody has run `ANALYZE` yet, so the planner has no statistics. Step 4 runs it (except on
  one table, on purpose, for planted problem P07).
- **Windows multiprocessing starts fresh interpreters** ("spawn"), so worker functions must live at module level and everything sent to a
  worker must be picklable. That is why shared data is in a small dataclass (`SeedContext`) passed to the pool once.
- **COPY and row-level security.** `COPY ... FROM` is not allowed on a table with RLS for a normal role. It works for the `loader` because
  it has `BYPASSRLS`. If you ever see "COPY FROM not supported with row-level security", that is the cause.

### Known simplifications (so they do not surprise you later)

- All prices and orders are in USD; the other currencies exist only as lookup rows.
- Orders per month are flat (about 6,000 a month) instead of growing.
- Addresses follow Faker's per-country format, but state or region names can be odd for a country (a US-style postcode in a GB address, etc.).
- `inventory_movements` has the right shape (sales negative, receipts positive) but is not reconciled with `inventory.quantity_on_hand` or with order lines.
- `order_items` has no tenant column and no RLS, so a tenant-1 reader can read every tenant's lines (seen in the test above). It is a deliberate,
  realistic gap to test the MCP server against.
- Speed: S loaded 4.6 million rows in 27 s, far faster than the 1-3 hours estimated for M. M has about 25 times the rows, so expect roughly
  10-15 minutes. It will be measured in step 6, not assumed.

### Concepts

- **`COPY`** loads rows in bulk through the protocol instead of one INSERT per row. https://www.postgresql.org/docs/17/sql-copy.html and psycopg's
  [copy support](https://www.psycopg.org/psycopg3/docs/basic/copy.html).
- **Identity columns and sequences**: after loading explicit ids, the sequence must be moved past the maximum with `setval`, or the next INSERT would
  collide. https://www.postgresql.org/docs/17/sql-createtable.html#SQL-CREATETABLE-PARMS-GENERATED-IDENTITY
- **Determinism**: same seed, same data. Useful for tests, for comparing performance before and after a change, and for sharing a reproducible problem.
- **splitmix64 hashing** (`mix` in `model.py`): a tiny, fast integer hash with good distribution; used so that "random" choices depend only on the id.
- **Skewed (Zipf-like) data**: real data is rarely uniform. Here 1% of customers place about 30% of orders, which later breaks query-planner assumptions (P01).
- **Python multiprocessing on Windows**: https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods

---

## Step 4: Indexes, functions, triggers, procedures, statistics, grants

### Goal and why

Turn the loaded data into something that behaves like a real industry database: secondary indexes (some deliberately missing),
10 kinds of triggers (21 trigger objects), 30 routines (helpers, reports, write procedures, batch jobs, and adversarial traps), fresh
planner statistics (one table deliberately stale), and a precise list of who may run what.

Why it is a separate layer applied **after** the load (`db/post_load/`, not `db/schema/`):
- **Indexes** are far cheaper to build once on finished data than to maintain for every row of a 4.6-million-row `COPY`.
- **Triggers** would fire for every seeded row: writing 4.6 million audit rows, reserving stock for every historic order line, and
  rewriting `updated_at` on every row. Seeded history must stay as the generator made it.
- **Procedures** can only be tested against data that exists.

Because triggers now exist, **re-seeding on top of this layer would corrupt the data**. `shopdb seed` therefore refuses to run once any
trigger exists in schema `shop`. To start over: `docker compose down -v`, `docker compose up -d --wait`, `shopdb seed`, `shopdb post-load`.

Order of the files (the number is the order they run in):

| File | Contents | Why here |
|---|---|---|
| `100_indexes.sql` | 28 secondary indexes (137 including per-partition children) | before anything that queries by those columns |
| `105_functions.sql` | 11 pure helpers, 4 report functions | triggers and procedures call the helpers, so they must exist first |
| `110_triggers.sql` | 10 trigger kinds on 15 tables, 21 trigger objects | needs the helpers |
| `130_procedures.sql` | 6 write procedures, 4 batch procedures | needs helpers and triggers (they rely on the triggers firing) |
| `135_adversarial.sql` | 5 deliberately risky routines | separate file so they are easy to find, and easy to remove |
| `140_analyze.sql` | `ANALYZE` of every table, the P07 stale-statistics setup, first refresh of the materialized view | after all data-changing steps |
| `150_grants.sql` | who may EXECUTE which routine | last, because every routine must exist |

### Commands

```powershell
# Apply everything, or one file at a time with a prefix
poetry run shopdb post-load
poetry run shopdb post-load --only 100

# Behaviour tests: run inside one transaction that is rolled back, so no data changes (needs `docker compose`)
Get-Content tests/sql/step4_checks.sql | docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1
#   Git Bash:  MSYS_NO_PATHCONV=1 docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 < tests/sql/step4_checks.sql

# Confirm the seeded data is still pristine afterwards
poetry run shopdb verify --scale S
```

### What each part does and why it is needed

**`shopdb post-load`** runs each `*.sql` file as the `shop_owner` role, in file-name order, one transaction per file, so a failing file
leaves nothing half-applied. Every file is re-runnable (`IF NOT EXISTS`, `CREATE OR REPLACE`, `DROP TRIGGER IF EXISTS` first). It runs from Python
(psycopg) rather than `psql` so it works without `psql` installed on Windows.

**Indexes (`100`).** One per foreign key and common lookup. `orders (tenant_id, placed_at)` exists because row-level security adds
`tenant_id = <session tenant>` to every query on `orders`. Two partial and composite indexes serve the stock ledger. Left out on purpose:
P02 (`order_items.product_id`), P04 (no trigram index on product text), P05 (no GIN index on `products.attributes`), P06 (no partial
indexes on `deleted_at IS NULL`). Building all of them took 1.8 s; the database grew from 741 MB to 889 MB.

**Functions (`105`).** Volatility is declared deliberately: `IMMUTABLE` for pure maths (`calc_tax`), `STABLE` for anything reading settings or
tables (`current_tenant`, the reports), `VOLATILE` for `random_between`. Reports are `SECURITY INVOKER`, so row-level security limits them to the
caller's tenant. They are called with `SELECT * FROM shop.monthly_sales_report(2025, 6)`.

**Triggers (`110`)** and why each exists:

| Trigger | Fires | Why it exists / lesson |
|---|---|---|
| `trg_touch_updated_at` (11 tables) | BEFORE UPDATE | one generic function reused across tables |
| `trg_audit` (orders, payments) | AFTER I/U/D | writes `audit_log`. `SECURITY DEFINER` because `mcp_writer` cannot write `audit_log`; records `session_user`, not the definer |
| `trg_reserve_inventory` | AFTER INSERT on order lines | reserves stock and logs a movement. Popular variants are updated by many orders at once (hot rows, P08) |
| `trg_validate_inventory` / `_order_status` / `_order_item` | BEFORE | business rules that raise errors with SQLSTATE `23514` |
| `trg_order_count` | AFTER INSERT/DELETE on orders | denormalized counter; the busiest 1% of customers are updated constantly |
| `trg_soft_delete_cascade` | AFTER UPDATE OF deleted_at | deleting a customer soft-deletes their orders |
| `trg_recalc_order_totals` | AFTER INSERT, once per **statement** | uses a *transition table* (`new_rows`): one multi-line `INSERT` triggers one recalculation, not one per line |
| `trg_carrier_sla` | AFTER UPDATE on shipments | deliberately slow (P13): scans the whole table for every row updated. Measured 8.8 ms per updated row |

Why `SECURITY DEFINER` appears here, and why the `SET search_path` line is not optional: a definer function runs with its owner's rights.
If it did not pin `search_path`, a caller could create their own object with the same name earlier in their own path and make the
function call it with owner privileges.

**Procedures (`130`).** The key design decision is *whose rights they run with*:
- The six **write procedures** are `SECURITY DEFINER`: `mcp_proc_exec` has **no table privileges at all**, so the procedures are its only door
  into the data. The price: the owner bypasses row-level security, so **every procedure re-implements the tenant check itself**
  (`tenant_id = shop.current_tenant()`). Forgetting that line in one procedure is the classic bug of this pattern. Cross-tenant requests
  get the same "customer N not found" message as non-existent ones, so they cannot be used to probe other tenants.
- `archive_old_orders` is `SECURITY INVOKER` and commits after each batch. Postgres does **not** allow `COMMIT` inside a `SECURITY DEFINER`
  procedure or one with a `SET` clause. It must also be called with autocommit on; inside an explicit transaction it fails with SQLSTATE `2D000`
  "invalid transaction termination" (verified below, and it left no data behind).

**Adversarial routines (`135`), each proven by a test to misbehave as intended:**

| Routine | Trap | Evidence |
|---|---|---|
| `get_next_invoice_number()` | name says "get", effect is a write (advances a sequence, which a rollback does not undo) | sequence went 183358 to 183360 across a rolled-back savepoint |
| `search_orders(p_filter)` | string-concatenated dynamic SQL, running as the owner | a tenant-1 session saw all 5 tenants' orders; an injected subquery returned 32,223 tenant-2 rows |
| `warm_cache(n)` | sleeps; tests timeouts | cancelled by `statement_timeout` |
| `order_snapshot(id, OUT, OUT, INOUT cursor)` | result is OUT parameters plus an open cursor, not a table | read with `FETCH` in the same transaction |
| `bulk_update_prices(percent, category)` | with no category, rewrites every product price as the owner | not run (it would change data); documented |

**Statistics (`140`).** `ANALYZE` gives the planner the value distributions it needs. P07 is built in three steps: (1) switch autovacuum off for `carts`,
otherwise Postgres would quietly repair the problem; (2) `ANALYZE` it while about 20% of carts are `open`; (3) run a "status migration" that makes
95% `open`. Result: the plan says `rows=33722` but the scan returns `actual rows=95972`. The estimate is higher than the 20% I predicted because the update
roughly doubled the table's size, and Postgres scales its row estimate from the table size. Side effects of that migration, worth knowing:
every cart's `updated_at` moved to today (the `updated_at` trigger fired), and the table is now 21 MB with a lot of dead rows (bloat).

**Grants (`150`).** First `REVOKE EXECUTE` from everyone, then grant by role. The grants are **deliberately broader than what the MCP server should allow**,
as in many real databases; the server's own allowlist (next phase) is the narrower gate:

| Role | May EXECUTE | Count |
|---|---|---|
| `mcp_reader` | pure helpers, 4 reports, `order_snapshot` | 16 |
| `mcp_writer` | pure helpers, 4 reports, `archive_old_orders` (it holds the table rights that invoker procedure needs) | 16 |
| `mcp_proc_exec` | helpers, 6 write procedures, 3 owner-run batch procedures, 4 adversarial routines | 24 |

### Files created

`db/post_load/100_indexes.sql`, `105_functions.sql`, `110_triggers.sql`, `130_procedures.sql`, `135_adversarial.sql`, `140_analyze.sql`,
`150_grants.sql`; `src/shopdb/postload.py` (the runner and the "triggers exist" check); the `post-load` CLI command; the seed guard in
`loader.py`; `tests/sql/step4_checks.sql` (37 behaviour checks).

### Expected output

```text
$ poetry run shopdb post-load
applied 100_indexes.sql (1.8s)    applied 105_functions.sql (0.0s)    applied 110_triggers.sql (0.0s)
applied 130_procedures.sql (0.0s) applied 135_adversarial.sql (0.0s)  applied 140_analyze.sql (5.1s)
applied 150_grants.sql (0.0s)
7 file(s) applied

$ ... step4_checks.sql
 PASS | create_order: pending order with 2 lines for the session tenant        | status 1, tenant 1, lines 2
 PASS | create_order refuses a customer of another tenant                      | customer 12 not found
 PASS | mcp_writer UPDATE on orders succeeds although it cannot write audit_log (definer trigger)
 PASS | A2 search_orders leaks other tenants' orders (expected)                | 5 tenants visible to a tenant-1 session
 PASS | archive_old_orders cannot COMMIT inside an explicit transaction ...    | 2D000 invalid transaction termination
 PASS | P13 slow trigger: 20 shipment updates took 176 ms (informational)      | 8.8 ms per row
 passed | failed
     39 |      0
```

### Troubleshooting and things that were not obvious

- **No role can create temporary tables.** Step 2 ran `REVOKE ALL ON DATABASE shop FROM PUBLIC`, which also removes the default `TEMP` privilege, so
  even `shop_owner` gets "permission denied to create temporary tables". That is good least privilege for the MCP roles. It means routines must not
  rely on temp tables, and test scripts that need them must run as the superuser.
- **A multi-statement script works in one `psycopg` call**, including `ANALYZE` and `DO` blocks, but the cursor is positioned on the *first*
  statement's result. Only `conn.execute(text)` plus `commit()` is needed for a file runner.
- **Test failures that were bugs in the tests, not the database:** an `INOUT` argument to `CALL` inside PL/pgSQL must be a *variable* (not `NULL`); `CALL`
  does not accept a subquery as an argument; a role that has been switched to cannot read the superuser's temp tables, so read test values into variables
  *before* `SET ROLE`; and an error caught by an **outer** `EXCEPTION` block rolls back everything recorded inside that block (so each scenario got its own `DO`).
- **A real bug the tests found:** `update_customer_email` validated the address *before* trimming it, rejecting `'  New@Example.test '` even though it is meant to
  normalise input. Fixed by trimming and lowercasing first, then validating what is stored.
- **`statement_timeout` is read when a statement starts.** `SET LOCAL statement_timeout` inside a `DO` block has no effect on that same block. Set it in a
  separate statement beforehand (the MCP server must do the same).
- **A scare worth recording:** the log showed `archived batch 1 (10 orders)` from inside the test transaction, which looked as if the procedure's `COMMIT` had saved
  everything. It had not: the `COMMIT` raised `2D000`, the test caught it, and the batch was rolled back. Row counts afterwards were exactly the seed's. Always check the data
  after a test that exercises transaction control.
- **The test run consumes invoice numbers.** Sequences are never rolled back, so each run of the test script advances `invoice_number_seq` by 2. Harmless gaps.

### Known gaps (so they do not surprise you later; several are the point)

1. `order_items` has no tenant column and no RLS: any reader sees every tenant's order lines.
2. `mv_daily_sales` (a materialized view) cannot have RLS and is built as the owner: any reader sees every tenant's daily revenue.
3. **Tenant isolation rests on a client-settable session value.** Any session can run `SET app.tenant_id = '2'`. The MCP server must forbid `SET` in raw SQL and set the
   tenant itself on connect. A SQL-capable client plus a custom setting is not a security boundary on its own.
4. Definer procedures bypass RLS. The tenant checks in them are hand-written, and `search_orders` shows what happens without them.
5. Roles are granted more routines than the MCP server should expose (see Grants).
6. The seeded `inventory_movements` ledger is synthetic, so `cancel_order` on a seeded order may release stock for a "sale" that never really reserved it.
7. `shopdb verify` describes a **freshly seeded** database. After real use of the procedures, row counts and the order window will no longer match.

### Concepts

- **Triggers and transition tables**: https://www.postgresql.org/docs/17/sql-createtrigger.html and https://www.postgresql.org/docs/17/plpgsql-trigger.html
- **Function volatility** (IMMUTABLE / STABLE / VOLATILE): https://www.postgresql.org/docs/17/xfunc-volatility.html
- **SECURITY DEFINER and writing it safely** (pin `search_path`): https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY
- **Procedures and transaction control** (why `COMMIT` is restricted): https://www.postgresql.org/docs/17/plpgsql-transactions.html
- **ANALYZE and planner statistics; autovacuum**: https://www.postgresql.org/docs/17/sql-analyze.html and https://www.postgresql.org/docs/17/routine-vacuuming.html
- **Default privileges and `REVOKE ... FROM PUBLIC`**: https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html
- **Why a rolled-back sequence stays advanced**: sequences are non-transactional by design: https://www.postgresql.org/docs/17/functions-sequence.html

---

## Step 4b: Rebuild from scratch (the clean-start flow)

### Goal and why

Prove that the documented path from nothing to a finished database works end to end, and start the next phase from a database with no leftovers from
test runs (advanced sequences, an advanced invoice number). This is also the only way to re-seed once triggers exist, so it is worth having run once.

Alternatives considered: `shopdb reset` (truncate and re-seed) is not possible any more, because the seeder refuses to run while triggers exist. Dropping only the
triggers by hand would be fragile. Recreating the volume is simple and deterministic: same seed, same data.

### Commands

```powershell
docker compose down -v                    # DESTRUCTIVE: deletes the pgdata volume. Only this project's volume (shopdb_pgdata).
docker compose up -d --wait               # init scripts run: extensions, roles, schema (about 6 s)
poetry run shopdb seed --scale S          # about 25 s
poetry run shopdb verify --scale S        # 39 checks, valid only before the procedures are used
poetry run shopdb post-load               # about 7 s
poetry run pytest -q                      # 11 tests
Get-Content tests/sql/step4_checks.sql | docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1
```

### What each command does and why

- `down -v` removes the container, the network and (because of `-v`) the named volume that holds all the data. Nothing outside the project is touched; `.env` and the
  source tree are not part of the volume. Docker re-runs the init scripts only because the volume is empty afterwards.
- The order matters: schema (empty tables) -> seed (no triggers, no secondary indexes) -> post-load (indexes, triggers, procedures, statistics, grants).
- `verify` runs between seed and post-load on purpose: it describes the data exactly as generated, before any procedure can change it.

### Expected output (from the real run)

```text
Volume shopdb_pgdata Removed
Container shopdb-db-1 Healthy                  (6 s)
Done: 4,630,316 rows in 24.9s                  (identical row count to the first load: the seed is deterministic)
39 passed, 0 failed                            (shopdb verify)
applied 100_indexes.sql (1.8s) ... applied 150_grants.sql (0.0s)    7 file(s) applied
11 passed                                      (pytest)
 passed | failed
     39 |      0                               (step4_checks.sql)
```

### Troubleshooting and things worth knowing

- `shopdb seed --force` after post-load prints "Triggers exist in schema shop ..." and exits 1. That is the guard working, not an error to work around.
- `tests/sql/step2_checks.sql` check 10 inserts tenants 1 and 2, so on a seeded database it stops with `duplicate key ... tenants_pkey`. It is meant for an empty database
  (checks 1-9 still run). Use `tests/test_seed_integrity.py` for row-level security against real data.
- The whole rebuild takes under a minute on this machine at profile S. Profile M has not been run.

---

## Step 6: Profile M (105 million rows)

### Goal and why

Replace the small S dataset with the large one, so the planted problems and the guarded SQL server are tested against data that is big enough
to hurt: 5 million orders, 15 million order lines, 30 million audit rows, a 19 GB database.

Why it needed a rebuild and not an upgrade: the seed only works on an empty database, and post-load triggers exist, so the only way from S to M is
a fresh volume (`down -v`, which deletes the S data; S is reproducible in about a minute, so nothing was lost). M uses the same code, the same tables and the same
seed as S: only the counts in `src/shopdb/config.py` change.

Why a background job: the seed takes about 5 minutes and the foreground limit is 10, so the long commands ran in the background and were checked when they finished.

Alternatives considered: running M on top of S (impossible, see above); lowering the data volume to make it faster (defeats the purpose).

### Commands

```powershell
docker compose down -v                                  # S data deleted (the volume shopdb_pgdata)
docker compose up -d --wait
poetry run shopdb seed --scale M --confirm-large --workers 12     # about 5 minutes
poetry run shopdb verify --scale M                      # 45 seconds, 39 checks
poetry run shopdb post-load                             # about 100 seconds
# point the local .env at M so verify and the integration tests follow it
#   SHOP_SCALE=M       (the file is git-ignored)
poetry run pytest -q                                    # 46 seconds at M
Get-Content tests/sql/step4_checks.sql | docker compose exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1
Get-Content db/observability/table_sizes.sql | docker compose exec -T db psql -U postgres -d shop
```

### What each part does and why it is needed

- `--confirm-large` is a deliberate speed bump on the CLI; it stops an accidental M seed.
- `--workers 12`: Postgres handles many concurrent `COPY` streams, and the machine has 28 CPUs. 12 was chosen over S's 8 to use more of them; more than that gains little because
  commits and WAL are shared.
- `SHOP_SCALE=M` in `.env`: `shopdb verify` and the integration tests read their expected row counts from the active profile. If they disagree with the database, they fail.
- `table_sizes.sql` is a repeatable way to record sizes instead of ad-hoc queries; the numbers go into `docs/size-profiles.md`.

### Files created

`docs/size-profiles.md` (all measurements and caveats); `db/observability/table_sizes.sql`; small wording updates in `README.md`, `CLAUDE.md` and the `seed` CLI message (they still said
"potentially hours" and "10-15 GB").

### Expected output

```text
Planning orders for scale M (seed 42) ...
  planned 5,000,000 orders -> 14,998,089 lines, 5,286,765 payments (14.9s)
...
Done: 104,756,389 rows in 307.4s
39 passed, 0 failed                                         (verify, 45 s)
applied 100_indexes.sql (57.7s)  ...  applied 140_analyze.sql (40.9s)   7 file(s) applied
11 passed in 46.01s                                         (pytest)
 passed | failed
     39 |      0                                            (behaviour tests, 18 s)
```

### Troubleshooting and things that were not obvious

- **The size surprised me.** I estimated 8-10 GB and the database is 19 GB (24 GB on disk with 4.1 GB of WAL). `audit_log` alone is 7 GB because each row carries two JSONB documents.
- **The time surprised me in the good direction.** I estimated 1-3 hours, then 10-15 minutes. The real seed took 5 minutes. The planning pass and the chunk-independent design are why.
- **`table_sizes.sql` first showed `audit_log` as 0 bytes.** A partitioned table stores nothing itself; its data is in the 37 partitions. The script now sums the partitions.
- **A trigger that is cheap at S is expensive at M.** The deliberately slow shipment trigger went from 8.8 ms to 310 ms per updated row (35x slower for 25x the rows), because each call scans a table that grew.
- **Warm cache hides a lot.** Docker's VM has 47 GB of RAM, so even the "bad" queries finish in under a few seconds. See the caveat in `docs/size-profiles.md`.
- **Disk:** the data directory is 24 GB. Keep 30+ GB free in Docker's virtual disk before rebuilding M.

### Concepts

- **Cardinality estimation and skew**: the planner assumes values are spread evenly. https://www.postgresql.org/docs/17/planner-stats.html
- **Buffer cache vs OS page cache**: https://www.postgresql.org/docs/17/runtime-config-resource.html#GUC-SHARED-BUFFERS
- **Write-ahead log (`pg_wal`) and `max_wal_size`**: https://www.postgresql.org/docs/17/wal-configuration.html

---

## Step 5: Planted problems you can prove

### Goal and why

Turn thirteen deliberate weaknesses (P01-P13) from "things I put in the data" into things that are **documented, measurable and guarded**.

Why it is needed: until now nothing would notice if a problem vanished. A well-meant `CREATE INDEX`, a manual `ANALYZE` or switching autovacuum back on would
quietly remove a trap, and the guarded SQL server would then be tested against a gentler database than intended. Each guard test turns that into a failing test with
the problem's name in it.

Why it came after M (step 6) in practice: the problems are only convincing at scale, so their evidence was collected on the M profile.

Alternatives considered: documenting the problems only in prose (nothing enforces it); making the tests destructive (for example really deadlocking and really bloating a
table). Instead the concurrency tests use rolled-back transactions, and the one test that needs real dead rows (P12) uses a throwaway table that it drops.

### Commands

```powershell
# P05 needs real data work: it rewrites every product document three times with autovacuum off (about 8 s at M)
poetry run shopdb post-load --only 145

# the guards (4 seconds at M)
poetry run pytest tests/test_planted.py -v

# the whole suite (31 tests; 60 seconds at M because it includes the full verifier)
poetry run pytest -q
```

### What each part does and why it is needed

- `145_bloat.sql` (new, re-run safe): disables autovacuum on `products`, then runs three `UPDATE`s over all 100,000 rows. Each update writes a new copy of the whole row and leaves the old
  copy dead, so the table ends up four times its real size. It does nothing if autovacuum is already off, so running `post-load` again does not pile on more bloat.
- Single-session guards read the **query plan** as JSON (`EXPLAIN (FORMAT JSON)`) and assert on its shape ("a Seq Scan on order_items", "37 partitions probed", "the planner's row
  estimate is at least 2x too low"). That makes them independent of machine speed, which timings would not be.
- The concurrency guards (P08 lock wait, P11 deadlock) open two real connections. P11 uses two threads and a barrier so both hold one lock before asking for the other; the database
  detects the cycle after `deadlock_timeout` (1 s) and aborts exactly one of them. Everything is rolled back.
- P12 proves the vacuum effect on a scratch table with autovacuum disabled: an old snapshot is held open, 5,000 rows are updated, `VACUUM` is run (5,000 dead rows remain), the snapshot
  is released, `VACUUM` is run again (0 remain).

### Files created

`db/post_load/145_bloat.sql`; `tests/test_planted.py` (20 tests); `docs/planted-problems.md` (every problem: what, where it was planted, repro query, measured evidence, why it matters for the MCP server,
the usual fix that was deliberately not applied, and how to restore it).

### Expected output

```text
$ poetry run shopdb post-load --only 145
applied 145_bloat.sql (8.4s)         # products: 120 MB -> 496 MB, 299,508 dead row versions

$ poetry run pytest tests/test_planted.py -v
... 20 passed in 4.03s
$ poetry run pytest -q
31 passed in 60.25s
```

Negative controls (the same checks on a case that is not broken, to show the tests can tell the difference): lookup by the indexed `variant_id` uses an `Index Only Scan`; an ordinary customer's
order estimate is 40 vs 4 actual (a hot customer is 40 vs 160); `customers.tier` statistics are accurate (989,433 vs 989,724); two sessions on different inventory rows do not block each other.

### Troubleshooting and things that were not obvious

- **P13's test first failed with a syntax error.** It takes the query text out of the trigger function's source, and that text contains PL/pgSQL's `SELECT ... INTO a, b`, which is not valid plain SQL.
  The test now strips the `INTO` clause. Lesson: SQL inside a function body is not always runnable on its own.
- **A leftover line in the test** (an assertion on an unused import) was removed.
- **Timings were avoided as assertions** on purpose; they vary by machine and by cache. Plan shapes and ratios (for example "at least 2x") are stable at both profiles.
- **P05's bloat is bigger than the amount of data changed.** The documents only gained two small keys, but each update copies the whole ~1.2 KB row, hence 4x.
- **A transaction that is merely open can cause harm (P12).** Nothing in it has to write anything.

### Concepts

- **Dead tuples, MVCC and VACUUM**: https://www.postgresql.org/docs/17/routine-vacuuming.html
- **Reading plans (`EXPLAIN`, JSON format)**: https://www.postgresql.org/docs/17/using-explain.html
- **Deadlocks**: https://www.postgresql.org/docs/17/explicit-locking.html#LOCKING-DEADLOCKS
- **Partition pruning**: https://www.postgresql.org/docs/17/ddl-partitioning.html#DDL-PARTITION-PRUNING
- **Trigram indexes (`pg_trgm`)**: https://www.postgresql.org/docs/17/pgtrgm.html
