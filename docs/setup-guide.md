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
