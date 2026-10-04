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
- **FastMCP** is installed now but unused until the MCP server steps (8 and later). The installed version is 4.x, newer than most
  tutorials, so check its docs at that step instead of trusting older examples.

---

## Step 2: Postgres in Docker, roles, schema, row-level security

### Goal and why

Start an empty-but-complete `shop` database: Postgres 17 in a container, five roles with different powers, the
25 profile-S tables (plus 36 monthly partitions and a default partition of the audit log), three views, and row-level security (RLS).
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

---

## Step 7: Workload and diagnostics (generate load, then read it back)

### Goal and why

Step 5 proved each planted problem with a one-off query or test. Real problems do not arrive as one query: they show up as **load**, a
mix of statements from many sessions at once, and you find them with **diagnostic views**. This step adds both halves:

1. `db/workload/` - [pgbench](https://www.postgresql.org/docs/17/pgbench.html) scripts that generate traffic (reads, orders, hot rows, deadlocks).
2. `db/observability/` - SQL that answers "what is slow", "who is blocked" and "where are the dead rows" (`pg_stat_statements`, `pg_stat_activity`, `pg_stat_user_tables`).

Why it matters for the MCP server: its job will be to run SQL for someone who is looking at exactly these views. The server needs realistic
load and realistic diagnostics to be tested against, and statement timeouts, lock timeouts and result caps only mean something under contention.

Alternatives rejected:
- **A Python load generator**: pgbench is already in the image, speaks the protocol natively, handles client threads and latency
  statistics, and its scripts are plain SQL (readable, and reusable later as the workload the MCP server's SQL is compared to).
- **Mounting `db/workload` into the container** (a compose volume): it would force a container recreate. `docker compose cp` copies the files in
  at run time instead.
- **Letting write scripts commit by default**: they would change the data (stock, orders, audit rows) and make the database drift away from
  the deterministic seed. Every write script ends in `ROLLBACK` unless you pass `-Commit` (`-D commit=1`).

### Commands

```powershell
# from the repo root, with the container running
.\db\workload\run.ps1 -Scenario browse   -Seconds 20 -Clients 8      # reads as mcp_reader
.\db\workload\run.ps1 -Scenario orders   -Seconds 20 -Clients 8      # create_order, rolled back
.\db\workload\run.ps1 -Scenario hot      -Seconds 12 -Clients 16     # P08 contention
.\db\workload\run.ps1 -Scenario deadlock -Seconds 15                 # P11
.\db\workload\run.ps1 -Scenario mixed    -Seconds 15 -Clients 10     # readers and order writers together

# read the evidence (run.ps1 resets pg_stat_statements first, so the report shows only the last run)
Get-Content db\observability\top_queries.sql | docker compose exec -T db psql -U postgres -d shop -f -
Get-Content db\observability\locks.sql       | docker compose exec -T db psql -U postgres -d shop -f -   # run WHILE a workload runs
Get-Content db\observability\bloat.sql       | docker compose exec -T db psql -U postgres -d shop -f -
```

### What each part does and why it is needed

- **`docker compose cp db/workload db:/tmp/`** - pgbench is in the container, not on the host, so the scripts go in first (done on every run, so edits are picked up).
- **`pgbench -n -r -P 5 -T 20 -c 8 -j 4 -D commit=0 --failures-detailed -f script`** -
  `-n` skip pgbench's own table maintenance (it expects its own tables); `-r` latency per statement; `-P 5` progress line every 5 s; `-T` duration;
  `-c` clients (connections); `-j` worker threads; `-D commit=0` sets the variable the scripts test with `\if :commit`; `--failures-detailed` counts deadlocks separately.
- **Passwords** are read from `.env` by `run.ps1` and passed as `PGPASSWORD` to that one command; they are never printed or written to a file.
- **Which role runs what, and why**
  - `browse_read.sql` runs as **mcp_reader**: tenant 1 through RLS, read-only, 15 s statement timeout (the same constraints the MCP server will have).
  - `place_order.sql` runs as **shop_owner**: only the owner can both look up valid ids and `EXECUTE shop.create_order`. `mcp_proc_exec` has no table access at all (least privilege), so it cannot choose valid customers and variants. The script sets `app.tenant_id` itself, as an application would.
  - `hot_inventory.sql` and `deadlock_*.sql` run as **loader** (the role the tests use for the same two problems).
- **`browse_read.sql`**: a weighted mix with `\if`. IDs come from `random_zipfian`, so a few customers and orders are requested far more than others (real traffic, and what makes P01 visible).
- **`place_order.sql`**: `\gset` runs a query and stores the result columns as pgbench variables. It picks the first valid tenant-1 customer at or after a random id and two in-stock variants, then calls `create_order`. `quote_literal(...)` is used because pgbench has no psql-style `:'name'` quoting.
- **`hot_inventory.sql`**: Zipf-distributed variants, a no-op `UPDATE ... SET reorder_point = reorder_point` (takes the row lock and writes a new row version, changes no value) and `pg_sleep(0.005)` to stand for application work done while holding the lock.
- **`deadlock_a.sql` / `deadlock_b.sql`**: lock variant 1 then 2, and variant 2 then 1, with a 0.3 s pause between. Run together, they deadlock about a third of the time.
- **`top_queries.sql`**: `pg_stat_statements` ordered by total time (where the server spends its life) and by mean time (what one call costs). `stddev_ms` far above `mean_ms` means skew.
- **`locks.sql`**: `pg_blocking_pids(pid)` joined back to `pg_stat_activity`: one row per (waiting session, blocker). Also long open transactions and the deadlock counter.
- **`bloat.sql`**: `pg_stat_user_tables` (no table scan): dead rows, dead %, bytes per live row, last autovacuum, and a note when autovacuum is off. Also the oldest snapshot holders (P12).

### Files created

- `db/workload/browse_read.sql`, `place_order.sql`, `hot_inventory.sql`, `deadlock_a.sql`, `deadlock_b.sql`, `run.ps1`
- `db/observability/top_queries.sql`, `locks.sql`, `bloat.sql` (`table_sizes.sql` already existed)

### Expected output (from the real runs on profile M, rolled back)

| Scenario | Result |
|---|---|
| browse, 8 clients | about 177 to 237 tps, 0 failures. Slowest statement: `low_stock_items(10, 20)` at about 255 ms; ILIKE search about 71 ms (P04); category listing about 11 ms |
| orders, 8 clients | about 3,165 tps, `create_order` 1.5 ms average, 0 failures |
| hot, 16 clients | about 474 tps; the UPDATE takes about 28 ms against a 5 ms sleep, the rest is waiting for row locks (P08) |
| deadlock, 2 clients, 15 s | 9 of 29 transactions failed with `deadlock detected` (5 in script a, 4 in script b); the other side always finished |
| mixed (10 clients: 7 readers, 3 writers) | readers about 143 tps, writers about 969 tps, 0 failures |

`top_queries.sql` after the mixed run ranked `low_stock_items` first by total time (60 s over 212 calls), then `create_order`, the category listing and the ILIKE search.
It also showed work nobody wrote: `SELECT ... FROM ONLY "shop"."addresses" ... FOR KEY SHARE` (58,140 calls) is Postgres checking a foreign key on every order insert, and the `UPDATE shop.orders ... SET subtotal` is the statement trigger recomputing totals.

`locks.sql` during the hot scenario listed the queue: 16 sessions, each waiting on the one holding the popular variant's row, and some waiting behind another waiter.

Nothing visible changed after all of this (rollbacks): orders 5,000,000, order_items 14,998,089, inventory_movements 20,000,000, audit_log 30,000,000, the same as the seed.

### Troubleshooting and things that were not obvious

- **`syntax error at or near ":"`** in `place_order.sql`: I used `:'vids'` (psql quoting). pgbench only understands plain `:vids`. The query now returns an already-quoted literal.
- **`insufficient stock for variant 60 ... (on hand 0, reserved 1)`**: the stock validation trigger from step 4 correctly rejects orders for empty variants, and pgbench aborts a client on any error that is not a deadlock or serialization failure. Zipf picks popular variants, which are often empty. The script now picks variants with at least 6 units available.
- **`expected one row, got 0`**: a random start near the end of the id range had no valid row after it. The starts now stay below 990,000 and 300,000.
- **Half of the category listings returned nothing**: categories 1 to 20 are parents with no products; the products are in 21 to 200. With an empty match the planner walked the primary key and filtered all 100,000 rows (112 ms): a classic `ORDER BY pk LIMIT n` plan trap, and a useful thing to know. With real category ids the same statement takes about 11 ms.
- **The mixed scenario failed when it called `run.ps1` twice at once** (two simultaneous `docker compose cp`, and the jobs' output vanished). It now copies once and starts two `docker compose exec` jobs directly.
- **Some in-place `sed -i` edits silently did not apply** (patterns containing a backslash and parentheses); I switched to a small Python replacement and checked the file afterwards. Lesson: always re-read after an in-place edit.
- **Rolled-back work still leaves marks**: sequences advance, and rolled-back inserts leave dead rows (`bloat.sql` showed about 150k to 240k dead rows in `orders`, `order_items`, `inventory_movements`; autovacuum cleans them, except where it is switched off on purpose: `carts`, `products`). The planted-problem tests still pass (20 of 20).
- **Committed write runs are possible but you must ask for them**: `-Commit` makes stock shrink and rows accumulate; after that the database no longer matches the seed and `shopdb verify` is not meaningful.

### Concepts

- **pgbench custom scripts, `\set`, `\gset`, `\if`, Zipf**: https://www.postgresql.org/docs/17/pgbench.html
- **pg_stat_statements**: https://www.postgresql.org/docs/17/pgstatstatements.html
- **Monitoring views (`pg_stat_activity`, `pg_locks`, `pg_blocking_pids`)**: https://www.postgresql.org/docs/17/monitoring-stats.html
- **Explicit locking and deadlocks**: https://www.postgresql.org/docs/17/explicit-locking.html

---

## Step 8: MCP stub (prove the whole chain before adding any logic)

> **Historical.** The stub, its `fastmcp dev|list|call|run` commands and `tests/test_mcp_stub.py`
> were replaced by the authenticated guarded server in Steps 14-16 (`poetry run shopmcp serve`).
> `src/mcp_server/server.py` is now only a compatibility entry point. The reasoning in this step
> (prove each link of the chain before adding logic) still applies.

### Goal and why

The next project phase is a "guarded SQL" server with real logic (classify SQL, ask before mutating, allowlisted procedures). Before writing any of that,
this step builds the smallest possible server and checks that **every link of the chain works**:

`MCP client -> FastMCP server -> shopdb.db.connect("mcp_reader") -> Postgres 17 (RLS, grants, comments)`

If something fails later, you will know it is the new logic and not the setup. It also teaches the three FastMCP basics (server object, tool decorator, annotations)
on something too small to hide mistakes.

Design choices (and what was rejected):
- **Two tools only**: `ping` (no database) and `list_tables` (read-only). `ping` separates "the server works" from "the database works".
- **`list_tables` uses `pg_class.reltuples`, not `count(*)`**: counting `audit_log` takes seconds (P09). The estimate is instant and good enough for "what exists".
- **It connects as `mcp_reader`**, the role the real server will use for reads, so the stub already runs under the same restrictions: SELECT only, RLS on tenant 1, 15 s statement timeout.
- **A connection per call, no pool**: simplest correct thing for a stub. A pool belongs to the real server.
- **Reusing `shopdb.db.connect`** instead of a second connection module: one place knows how to build the connection string and read passwords. (Later the MCP server may get its own settings; that is a decision for the next phase.)
- **FastMCP version**: 4.0.10 is installed. It is newer than most tutorials, so the API was read from the installed package (`.venv/Lib/site-packages/fastmcp`) rather than from memory.
  It sits on the MCP Python SDK v2 (`mcp_types`), which renamed annotation fields to snake_case: `ToolAnnotations(read_only_hint=True)`, not `readOnlyHint`.

### Commands

```powershell
poetry run pytest tests/test_mcp_stub.py -v                       # in-memory client, 4 tests
poetry run fastmcp list src/mcp_server/server.py                  # launches the server over stdio and lists its tools
poetry run fastmcp call src/mcp_server/server.py list_tables      # calls a tool over stdio
poetry run fastmcp dev src/mcp_server/server.py                   # opens the MCP Inspector in a browser (interactive)
```

### What each part does and why it is needed

- **`FastMCP("shop-db", instructions=...)`** creates the server. `instructions` is text the client shows to the model about how to use the server.
- **`@mcp.tool(annotations=ToolAnnotations(...))`** registers a function as a tool. The type hints become the input schema, the docstring becomes the description the model reads (so write it for the model).
  `read_only_hint`, `destructive_hint`, `idempotent_hint`, `open_world_hint` are **hints** for the client's UI (for example whether to ask for confirmation). They are not enforcement.
  The enforcement is the database role: `mcp_reader` has no write privileges.
- **`mcp.run()`** serves over **stdio** (the client starts the server as a subprocess and talks over its stdin/stdout). Because stdout is the protocol channel, never `print()` in a server; logs go to stderr.
- **`Client(mcp)`** in the tests connects a real MCP client to the server object **in memory**: same protocol messages, no subprocess, fast and deterministic.
- **`fastmcp list|call`** starts the server for real as a stdio subprocess: this is what Claude Code or Claude Desktop will do.
- **`asyncio.run(...)` in the tests**: the client is async; wrapping it avoids adding a pytest plugin for one test file.

### Files created

- `src/mcp_server/server.py` - the stub server (`ping`, `list_tables`)
- `tests/test_mcp_stub.py` - 4 tests: tools and annotations, ping, the 25 tables (no partitions, all with comments), and the write barrier

### Expected output (real)

```
$ poetry run pytest tests/test_mcp_stub.py -q
4 passed in 2.19s
$ poetry run pytest -q
35 passed
$ poetry run fastmcp list src/mcp_server/server.py
Tools (2)
  ping() -> dict
  list_tables() -> dict
$ poetry run fastmcp call src/mcp_server/server.py list_tables
{"result": [{"table": "addresses", "partitioned": false, "approx_rows": 2000004, "comment": "Shipping and billing addresses owned by a customer."},
            {"table": "audit_log", "partitioned": true, "approx_rows": 29993916, ...}, ...]}
```

### Troubleshooting and things that were not obvious

- **The write-barrier test failed first**, with `ReadOnlySqlTransaction` instead of `InsufficientPrivilege`. Two lessons:
  1. `mcp_reader` has `default_transaction_read_only = on`, and Postgres checks that **before** privileges, so a plain UPDATE is refused for the advisory reason and proves nothing about grants.
  2. Running `SET default_transaction_read_only = off` inside psycopg's default transaction did not help either: psycopg had already issued `BEGIN` (read-only), and the setting does not change a transaction in progress.
  The test now uses an `autocommit=True` connection, switches the setting off, and then the UPDATE fails with `InsufficientPrivilege`. That proves the missing privilege is the real barrier. This is exactly the "defence in depth" point for the guarded server: the read-only default is a convenience, **grants are the guarantee**.
- **A list return value is wrapped** as `{"result": [...]}` and the CLI shows `-> dict`: FastMCP builds an output schema that must be an object, so non-object returns are wrapped.
- **Formatting**: ruff wanted a long assert message wrapped; run `poetry run ruff format .` before committing.
- **Not done on purpose**: the server is not registered in any MCP client config (Claude Code, Claude Desktop, VS Code). To try it from Claude Code later: `claude mcp add shop-db -- poetry run fastmcp run src/mcp_server/server.py` run from the repo root. That edits your client configuration, so it is your call.

### Concepts

- **MCP tools and annotations**: https://modelcontextprotocol.io/specification/ (Tools section)
- **FastMCP**: https://gofastmcp.com
- **stdio transport**: https://modelcontextprotocol.io/specification/ (Transports section)
- **`pg_class.reltuples`** (planner row estimate): https://www.postgresql.org/docs/17/catalog-pg-class.html

---

## Step 9: Final documentation (generated data dictionary and ERD, hand-written roadmap)

### Goal and why

Three documents were still missing, and they are different in kind, so they are produced differently:

| Document | Kind | How |
|---|---|---|
| `docs/data-dictionary.md` | Facts about the database | **Generated** by `poetry run shopdb docs` from the live catalog and `COMMENT ON` text |
| `docs/erd.md` | Facts (the foreign keys) | **Generated** (Mermaid) from `pg_constraint` |
| `docs/roadmap.md` | Decisions and plans for the next phase | **Written by hand** |

Why generate instead of writing: a hand-written dictionary starts to drift the day after it is written (a column is added, a comment changes). A generated one is correct by construction, and
`tests/test_docgen.py` fails if a table or column loses its description. An ERD drawn by hand can show a relationship that does not exist; this one is built from the real foreign keys.
The roadmap is the opposite case: it records choices and open questions, which no catalog can tell you.

Alternatives rejected: a schema-documentation tool such as SchemaSpy (a Java dependency and a heavy HTML output for something that fits in two markdown files); drawing the ERD in an image editor (cannot be regenerated, cannot be diffed).

### The prerequisite that was missing: column comments

The generator can only print what is in the database, and **only 8 of the 193 columns had a `COMMENT ON`** (tables were all commented in step 2). A dictionary built from that would have been mostly empty.
This matters beyond documentation: a model writing SQL through the MCP server has only names and comments to go on. So the first part of the step was `db/post_load/160_comments.sql`.

- Why a **post_load** file and not an edit of `db/schema/*.sql`: schema files only run when the data volume is created, so editing them would not reach the running database without a rebuild (about 8 minutes at M). Comments are metadata; the file applies in a second and is re-runnable (an existing comment is left alone).
- Every description was checked against the database before being written. Several of my first drafts were wrong and were corrected: invoice numbers have 9 digits not 8; `provider_ref`, `tracking_number`, `shipped_at`, `size` and `color` are never NULL in the data; barcodes are distinct but no constraint enforces it; the products' category ids are 21-200.
  Lesson: a comment that sounds plausible and is wrong is worse than none.

### Commands

```powershell
poetry run shopdb post-load --only 160     # add the column comments (applied 193/193; second run changes nothing)
poetry run shopdb docs                     # writes docs/data-dictionary.md and docs/erd.md (use --out DIR for another folder)
poetry run pytest tests/test_docgen.py -v  # 4 tests
```

### What each part does and why it is needed

- **`src/shopdb/docgen.py`** reads the catalog with six queries and renders markdown. The ones worth understanding:
  - `pg_class` / `pg_attribute` / `pg_attrdef`: tables, columns, types (`format_type`), defaults. `NOT relispartition` hides the 37 `audit_log` partitions behind their parent.
  - `pg_constraint` with `conparentid = 0`: Postgres copies constraints onto every partition; this keeps only the original.
  - `obj_description` / `col_description`: read the `COMMENT ON` text.
  - `pg_get_constraintdef`, `pg_get_indexdef`, `pg_get_triggerdef`, `pg_get_function_identity_arguments`: Postgres prints its own definitions, so the doc shows what the database really has.
  - `pg_policies`: the row-level security policies.
- **Deterministic output**: no timestamps and sorted queries, so regenerating on an unchanged database gives byte-identical files (clean `git diff`; tested).
- **ERD cardinality**: a nullable foreign key column draws `|o--o{` (parent optional), a NOT NULL one draws `||--o{`.
- **`shopdb docs` runs as `shop_owner`** (it only reads catalogs, which any role can read).

### Files created

- `db/post_load/160_comments.sql`, `src/shopdb/docgen.py`, `tests/test_docgen.py`
- `docs/data-dictionary.md` (25 tables, 3 views, 40 routines, 3 RLS policies), `docs/erd.md` (38 foreign keys), `docs/roadmap.md`
- `src/shopdb/cli.py`: new `docs` command

### Expected output (real)

```
$ poetry run shopdb post-load --only 160
applied 160_comments.sql (0.0s)
1 file(s) applied
$ poetry run shopdb docs
wrote docs\data-dictionary.md
wrote docs\erd.md
$ poetry run pytest tests/test_docgen.py -q
4 passed
```

The ERD was also checked with Mermaid's own parser (mermaid 11 run under Node, `mermaid.parse`): `PARSE OK`, diagram type `er`. That proves the syntax is valid; it was not rendered to an image here.
GitHub renders ` ```mermaid ` blocks, as do VS Code (with a Mermaid extension) and most markdown viewers.

### Troubleshooting and things that were not obvious

- **Doubled backslashes are collapsed by the tool layer I work through**, which broke one generator edit (a `\n` became a real newline inside a string literal and ruff reported `missing closing quote`) and earlier put a carriage return into `CLAUDE.md`.
  Not a Postgres or Python issue; the fix was to edit with a tool that does not process escapes and to re-read every edited file. If you ever see `\r` or a stray line break where a Windows path or `\n` should be, suspect this.
- **`Path(...)` as a typer default** triggers lint rule B008 (a function call in an argument default). The option is a plain string converted inside the function, like the other commands.
- **A table of 25 may look like 28**: `shop` also contains three views (`v_order_summary`, `v_low_stock`, and the materialized view `mv_daily_sales`). The dictionary lists them separately.
- **Row counts in the dictionary are estimates** (`pg_class.reltuples`) and depend on the loaded profile, so regenerating at S gives different numbers than at M. That is stated at the top of the file.
- **Comment coverage is now a test.** If you add a table or column, add its `COMMENT ON` (in `db/schema` for a new table, or `160_comments.sql`), or `tests/test_docgen.py` fails.

### Concepts

- **System catalogs (`pg_class`, `pg_attribute`, `pg_constraint`, `pg_description`)**: https://www.postgresql.org/docs/17/catalogs.html
- **COMMENT**: https://www.postgresql.org/docs/17/sql-comment.html
- **Mermaid entity-relationship diagrams**: https://mermaid.js.org/syntax/entityRelationshipDiagram.html

---

## Step 10: Move the MCP server's data access to SQLAlchemy Core

> **Partly superseded.** The rule (SQLAlchemy Core for the server's own queries, `exec_driver_sql` for
> pass-through SQL) still holds. The code described here (`src/mcp_server/db.py` with `engine_for`, the stub's
> `list_tables`, `tests/test_mcp_stub.py`) was reorganized in Steps 14-15 into `src/mcp_server/adapters/postgres/`
> (async engines in `engines.py`, queries in `queries.py`); `db.py` now only re-exports `tables_query`.
> Also, the roadmap sections referenced here (`section 4a`, open question 5) were replaced when
> `docs/roadmap.md` was rewritten as an implementation status.

### Goal and why

Until now `list_tables` in the MCP stub was a hand-written SQL string run through psycopg. You asked why: raw SQL should belong to the seeding phase, not to the server's tools.
For the server's **own** queries that is the better design, so the stub was changed and the rule was recorded (`CLAUDE.md`, `docs/roadmap.md` section 4a).

What SQLAlchemy gives the server:
- **A connection pool per role** (`engine_for("mcp_reader")`). The stub opened a new connection on every call; the real server needs a pool anyway (it was open question 5 in the roadmap).
- **Queries as Python expressions** (`select(...)`) over described tables, so the compiler builds the SQL and every value is a bound parameter. Nobody can build a query by pasting strings.
- **Helpers** such as `pool_pre_ping` (drops dead connections) and a single place to reset session state later.

Which part of SQLAlchemy: **Core, not the ORM.** The ORM maps tables to Python classes. This server has no domain objects; it relays whatever a query returns. There is nothing to map, so the ORM would add weight and no value.

**Where SQLAlchemy cannot help (important):** SQL that a person or a model writes and asks the server to run (`execute_sql` in the next phase) is text, not something the server builds.
SQLAlchemy cannot make that safe. The protections there stay what the roadmap says: the classifier, the role privileges, and human approval. It will be executed with
`Connection.exec_driver_sql`, because the plain `text()` wrapper treats `:name` inside the SQL as a bind parameter and would corrupt valid queries.

Alternatives rejected: `psycopg_pool` alone (a pool but no query building); the ORM (see above); keeping raw SQL strings (works, but every new tool would repeat the string-building risks).

### Commands

```powershell
poetry add "sqlalchemy>=2.0"                    # installed SQLAlchemy 2.1.3; psycopg 3 was already present (dialect "postgresql+psycopg")
poetry run pytest tests/test_mcp_stub.py -v     # 5 tests
poetry run fastmcp call src/mcp_server/server.py list_tables
```

### What changed and why

- **`src/mcp_server/db.py`** (new)
  - `engine_for(role)`: builds the connection URL with `URL.create(...)` (not string formatting, so special characters in a password are safe) and caches one engine per role.
    `pool_size=3, max_overflow=2` keeps the number of connections small (the container allows 50); `pool_reset_on_return="rollback"` means a connection is never returned to the pool inside an open transaction.
  - `pg_class` and `pg_namespace` described as `Table` objects in the `pg_catalog` schema. SQLAlchemy does not need them created: it only needs to know their columns to build a query.
  - `tables_query()`: the same query as before, as a `select()`. It hides partitions (`relispartition IS false`), reports `reltuples` clamped at zero, and reads the comment with `obj_description`.
- **`src/mcp_server/server.py`**: `list_tables` now calls `engine_for("mcp_reader")` and `tables_query()`. The SQL string constant is gone.
- **`tests/test_mcp_stub.py`**: a fifth test checks that each engine connects as the role it was asked for (`current_user`) and that there is one pool per role.

The SQL that SQLAlchemy generates (for the record; all values are bound):

```sql
SELECT pg_catalog.pg_class.relname AS table_name, pg_catalog.pg_class.relkind = %(relkind_1)s::VARCHAR AS is_partitioned,
       CAST(greatest(pg_catalog.pg_class.reltuples, %(greatest_1)s::INTEGER) AS BIGINT) AS approx_rows,
       obj_description(pg_catalog.pg_class.oid, %(obj_description_1)s::VARCHAR) AS comment
FROM pg_catalog.pg_class JOIN pg_catalog.pg_namespace ON pg_catalog.pg_namespace.oid = pg_catalog.pg_class.relnamespace
WHERE pg_catalog.pg_namespace.nspname = %(nspname_1)s::VARCHAR AND pg_catalog.pg_class.relkind IN (...)
  AND pg_catalog.pg_class.relispartition IS false
ORDER BY pg_catalog.pg_class.relname
```

### Expected output (real)

```
$ poetry run pytest tests/test_mcp_stub.py -q
5 passed
$ poetry run fastmcp call src/mcp_server/server.py list_tables
{"result": [{"table": "addresses", "partitioned": false, "approx_rows": 2000004, "comment": "Shipping and billing addresses owned by a customer."}, ...
```

Same 25 tables and comments as before the change: the behaviour did not change, only how the query is built.

### Troubleshooting and things that were not obvious

- **Use an absolute import (`from mcp_server.db import ...`) in `server.py`.** `fastmcp run src/mcp_server/server.py` loads the file by path, where a relative import (`from .db import ...`) fails because the file is not part of a package at that moment. The package is installed in the virtualenv (editable), so the absolute form works both ways.
- **`ruff --fix` replaced `lru_cache(maxsize=None)` with `functools.cache`.** Same behaviour, newer spelling.
- **A pooled connection keeps session state.** `SET something` run on a pooled connection stays set for the next caller. Rolling back on return does not undo a `SET`. This is harmless for `list_tables`, but matters for pass-through SQL (a client could `SET app.tenant_id`). Recorded as roadmap question 5.
- **The tests and the seeder still use plain psycopg and SQL.** That is intended: the rule is about the server's own queries, and the SQL files define the database.

### Concepts

- **SQLAlchemy Core and the engine/pool**: https://docs.sqlalchemy.org/en/20/core/engines.html
- **Core vs ORM**: https://docs.sqlalchemy.org/en/20/tutorial/index.html
- **Table metadata and `select()`**: https://docs.sqlalchemy.org/en/20/tutorial/data_select.html
- **Connection pooling**: https://docs.sqlalchemy.org/en/20/core/pooling.html

## Step 11: Audit imported Codex configuration and diagnose terminal popups

### Goal and why

Audit the Claude Code import without changing Claude's configuration, chat bodies,
database data, branches, or unrelated repository edits. The import history records
87 items across eight roots: 21 skills, 2 instruction files, 4 plugins, 1 MCP
configuration, 16 subagents, and 43 sessions.

During the audit, the user reported many Git Bash popup windows. Their process
command lines identified Codex's imported Warp notification scripts. Warp's hook
commands invoke `.sh` files directly. Windows associates `.sh` with
`"C:\Program Files\Git\git-bash.exe" --no-cd "%L" %*`, so each hook opens a GUI
terminal. The observed events included session start, prompt submission,
permission requests, and post-tool use. This also means audit tool calls can
trigger additional windows while an old session retains cached hooks.

The chosen repair disables Warp and security-guidance in Codex using its native
configuration writer, as authorized in the cleanup plan. Changing system file
associations, changing PATH, editing plugin caches, and disabling all hooks were
rejected because they affect more than the imported plugins. Claude settings and
the installed Warp application remain unchanged.

### Commands and operations

```powershell
Get-CimInstance Win32_Process
Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\.sh'
Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\sh_auto_file\shell\open\command'
codex --version
codex app-server generate-json-schema --experimental --out <temporary-directory>\schema
codex app-server daemon version
```

Process inspection compared executable names, command lines, creation times, and
parents. Registry reads confirmed the shell association without modifying it.
The generated schema established the installed runtime's supported RPC fields.
The installed CLI and managed daemon both reported version `0.160.0`.

A hidden, temporary Python stdio client called `initialize`, `config/read`,
`config/batchWrite`, `skills/list`, `hooks/list`, and
`externalAgentConfig/detect`. It did not start a model turn or run a workflow.
The configuration write used the user's layer version as `expectedVersion` and
set only these keys to `false`:

```text
plugins."warp@claude-code-warp".enabled
plugins."security-guidance@claude-plugins-official".enabled
```

After explicit user approval, only `git-bash.exe`, `mintty.exe`, and `bash.exe`
processes whose command lines pointed to Warp plugin `scripts/on-*.sh` were
stopped. Creation-time checks guarded against process-ID reuse. Normal terminals
and application processes were excluded.

### Files and real results

- Temporary audit helpers and generated schemas:
  `C:\Users\dangv\AppData\Local\Temp\codex-import-cleanup-20261003`.
- Original config backup and hash manifest:
  `C:\Users\dangv\.codex\maintenance\import-cleanup\runs\20261003T101455650223Z-popup-fix`.
- `config/batchWrite` returned `status: ok`; parsed TOML comparison confirmed that
  only the two approved flags changed.
- A fresh runtime reported zero hooks from the two disabled plugins in all eight
  roots. GitNexus and Vercel hooks remained present and trusted.
- The initial focused process snapshot contained 132 Warp-related `mintty.exe`
  windows, 132 `git-bash.exe` processes, and 128 `bash.exe` processes. Counts rose
  while cached hooks remained active. The accumulated matching processes were
  closed, but replacement windows were observed afterward.
- Live repository status at the start contained only untracked `AGENTS.md` in
  this repository. The previously reported roadmap modification was absent.
  `docs/roadmap.md` was hashed for preservation and was not edited by this audit.

### Troubleshooting and open validation

- The first metadata read used the Windows default text encoding and failed with
  `UnicodeDecodeError`; subsequent reads explicitly used UTF-8.
- A PowerShell diagnostic piped a bare `foreach` statement and failed with
  `An empty pipe element is not allowed`; collecting the rows before piping fixed it.
- Sandbox Git inspection could not read the host ignore file. Host-visible
  inspection succeeded, so this was not treated as a repository failure.
- The fresh runtime loaded the disabled-plugin settings, but existing sessions
  retained Warp hooks. An attempted connection through `app-server proxy` timed
  out during initialization. No successful live reload is claimed.
- A runtime restart requires coordination with other active tasks. Until that
  restart and a subsequent normal synchronization are observed, popup recurrence
  and import-persistence validation remain open.

### Concepts

- Path-specific skill controls:
  https://learn.chatgpt.com/docs/build-skills
- Structured configuration writes and external-agent imports:
  https://learn.chatgpt.com/docs/app-server
- Windows process inspection:
  https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process

## Step 12: Characterize and separate the seeder (2026-10-03)

Goal: preserve generated data while separating pure dataset rules and workflows
from Faker, PostgreSQL, files, and Windows worker processes. Moving code without
a baseline was rejected because it would hide changes to deterministic values.

Commands run from the repository root:

```powershell
$env:PYTHONPATH='src;tests'
.venv/Scripts/python.exe -c "import json; from pathlib import Path; from characterization import snapshot; Path('tests/fixtures/generation-original.json').write_text(json.dumps(snapshot(), indent=2, ensure_ascii=True)+'\n', encoding='ascii')"
poetry lock
poetry install
.venv/Scripts/python.exe .scratch/refactor_seeder.py
.venv/Scripts/python.exe -m ruff check src/shopdb --fix
.venv/Scripts/python.exe -m ruff format src/shopdb tests/characterization.py
.venv/Scripts/python.exe -c "import json; from pathlib import Path; from characterization import snapshot; assert snapshot()==json.loads(Path('tests/fixtures/generation-original.json').read_text()); print('Original generator snapshot matches')"
```

The first command captures representative rows from every generator and all static
tables, child totals, and a hash of order counts before changing generation code.
Poetry locked and installed SQLGlot 30.21.0 (one installation, no upgrades).
The refactor script created feature Core and adapters; compatibility imports retain
old Python entry points. It is a local implementation helper, not a setup prerequisite.
The snapshot comparison printed `Original generator snapshot matches`.

Failures: a four-order sample violated the original generator's chunk-layout check;
using the full original 25,000-order chunk fixed capture. Sandbox Poetry returned
`Failed to canonicalize script path`; the approved host execution succeeded. Ruff
found a missing `defaultdict` import after extracting the renderer; it was restored.
Docker inspection initially lacked pipe/config permissions; approved host inspection
found Docker 29.7.2 and the existing database on port 5433. No existing data was changed.

Files: `tests/fixtures/generation-original.json`, `tests/characterization.py`, the
new `shopdb/core` and `shopdb/adapters` packages, bootstrap, and settings. Workers
now receive the selected Settings object through the process initializer.

Concepts: [spawn](https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods),
[COPY](https://www.postgresql.org/docs/17/sql-copy.html),
[SQLGlot](https://sqlglot.com/sqlglot.html).

## Step 13: Install the manual import audit and repair command (2026-10-03)

### Goal and why

Make the approved import repairs repeatable without a background watcher or
changes to Claude's originals. Path-specific overrides preserve preferred
personal skills and Vercel wrappers while keeping installed plugin files intact.
Name-only deduplication was rejected because project skills contain legitimate
differences. Whole-file replacement of imported instructions was rejected in
favor of narrow substitutions with exclusive file locks and content checks.

### Commands

```powershell
$cleanup = "$env:USERPROFILE\.codex\maintenance\import-cleanup\Import-Cleanup.ps1"
& $cleanup -Mode Apply -WhatIf
& $cleanup -Mode Apply
& $cleanup -Mode Apply
& $cleanup
python -X utf8 -m unittest discover -s "$env:USERPROFILE\.codex\maintenance\import-cleanup" -p test_cleanup.py -v
```

The first command previews repairs. Apply backs up affected configuration and
instructions, uses Codex's `config/batchWrite` with `expectedVersion` for supported
settings, and verifies each imported text file's hash and resolved target before
writing. The repeated Apply checks idempotence. The default Audit only writes a
redacted findings report. The tests use disposable files to check race refusal,
restoration, new plugin-version discovery, and preservation of distinct skills.

### Files and real output

The command, Python implementation, stdio RPC client, tests, README, reports,
and timestamped backup manifests are installed under
`C:\Users\dangv\.codex\maintenance\import-cleanup`, outside skill discovery.
The script discovers runtime and plugin paths each time and requires no package
installation. It adds no scheduled task or background watcher.

- Initial Apply changed one configuration array and 15 instruction files.
- A follow-up repaired a pre-existing assumption that every runtime exposes SQL
  task tables in one skill and one planner definition. It preserves task status
  and dependencies using the available tracker or a checklist in the plan.
- The final Apply printed `changes: 0`.
- In total, 19 duplicate skills were disabled: 2 old PR-comment skills,
  7 overlapping Matt Pocock skills, and 10 nested Vercel entries. Their preferred
  personal/wrapper counterparts remained enabled. No skill files were deleted.
- The desktop runtime is `0.159.2`; the managed CLI is `0.160.0`. Skill discovery
  passed for all eight roots in both runtimes. Neither disabled plugin appeared
  in fresh runtime hook lists; retained hooks remained trusted.
- All 43 imported thread IDs, their source hashes in the import ledger, and
  existing source-file hashes were preserved across Apply. Conversation bodies
  were not read or copied. `docs/roadmap.md` retained its initial hash.
- GitNexus accepted a harmless `git status` hook fixture. All five retained Vercel
  hook modules loaded, and parser fixtures passed without invoking their main
  functions, telemetry senders, or cleanup actions against real sessions.

### Troubleshooting and remaining limits

- A generated `__pycache__` file initially made the PR-comment skill copies look
  different. Their actual scripts and metadata match; the comparison now ignores
  generated Python bytecode.
- Windows stores imported thread paths with a `\\?\` prefix. Comparing raw
  strings falsely reported different destinations. Canonical comparison handles
  that prefix and UNC paths; a disposable test covers it.
- A sandbox write to the maintenance report directory was denied. The approved
  host-visible route saved the report successfully.
- Static reference scanning found `scripts/run.py`, `references/finance.md`, and
  `references/sales.md` in the skill-authoring examples. These are illustrative
  examples, not missing dependencies, so they were preserved.
- Another active task removed five imported skills, five imported agent files,
  and the project MCP configuration in the main `dangvngiang.dev` checkout.
  This audit did not recreate them. The Supabase project binding therefore
  cannot be confirmed in the effective configuration and remains open.
- Claude's subagent tool allowlists were omitted by import. Existing role prose,
  inherited models, and permissions were preserved; equivalent tool-level
  enforcement is not claimed.
- Other tasks changed seeder files and appended Step 12 during this audit.
  Those changes were left intact. This audit changed this repository's imported
  `AGENTS.md` plan pointer and added its own documentation sections only.
- The user explicitly deferred a Codex restart because other tasks are active.
  Existing sessions can retain Warp hooks and open replacement windows. A normal
  synchronization and persistence check remain outstanding.

### Rollback and future imports

```powershell
& $cleanup -Mode Restore -Backup '<run-directory>\manifest.json' -WhatIf
& $cleanup -Mode Restore -Backup '<run-directory>\manifest.json'
```

Restore successive repair runs in reverse order. Restore refuses to overwrite
later edits or a changed junction. Restoring the original popup-fix backup would
re-enable Warp, so only do that deliberately. After future imports or plugin
updates, run Audit and inspect Apply -WhatIf. Keep synchronization enabled.
When other Codex tasks are idle, restart the relevant runtime, observe a normal
synchronization, and repeat Audit and Apply to complete persistence verification.

Controls and protocol:
[skill overrides](https://learn.chatgpt.com/docs/build-skills),
[native configuration and import API](https://learn.chatgpt.com/docs/app-server).

## Step 13b: Isolated S verification (2026-10-03)

Goal: verify real Windows worker behavior and database integrity without using the
existing port 5433 database. Reusing that volume was rejected. The dedicated Compose
project uses port 55439 and volume `shopmcp-test_test_pgdata`.

```powershell
docker compose -f tests/compose.yml up -d --wait
.venv/Scripts/python.exe tests/seed_isolated.py
.venv/Scripts/python.exe -m pytest tests/test_model.py tests/test_characterization.py -q
```

Compose created the separate network, volume, and `shopmcp-test-db-1` container and
reported it healthy. The seed runner passes explicit settings with `_env_file=None`
to both the parent and Windows-spawned workers, loads S, runs integrity checks
before mutations, then applies post-load scripts. It loaded **4,630,316 rows in
27.6 seconds**; all 39 fresh-data checks passed. All nine post-load files applied.
The pure model, CLI, and characterization suite reported **10 passed**.

Files: `tests/compose.yml`, `tests/support.py`, `tests/seed_isolated.py`, and
`tests/conftest.py`. The test flag `SHOP_TEST_DATABASE=isolated` explicitly selects
these connection settings. Without it, database tests are skipped. No test falls
back to the project's local database. Retain the test volume for inspection;
deleting it is a separate destructive action.

Troubleshooting: sandbox pytest could not write its cache and emitted a warning;
the assertions passed. Later runs can disable the cache provider with
`-p no:cacheprovider`. The S runner itself had no database or worker failures.

Concepts: [Compose project isolation](https://docs.docker.com/compose/how-tos/project-name/),
[PostgreSQL transactions](https://www.postgresql.org/docs/17/tutorial-transactions.html).

## Step 14: Async server dependencies and isolated audit storage (2026-10-03)

Goal: use separate runtime roles and an append-only audit database. Reusing the
shop transaction for audit was rejected: rollback must not erase the request trail.
Migration credentials are accepted only by the audit CLI, never by server Settings.

```powershell
docker compose -f tests/compose.yml exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 -f /db/mcp/000_roles.sql
$env:SHOPMCP_MIGRATION_URL='postgresql+psycopg://mcp_audit_owner:test_audit_owner@127.0.0.1:55439/mcp_audit'
.venv/Scripts/python.exe -m mcp_server.cli audit migrate
$env:SHOP_TEST_DATABASE='isolated'
.venv/Scripts/python.exe -m pytest tests/test_seed_integrity.py tests/test_planted.py tests/test_docgen.py -q -p no:cacheprovider
poetry lock
poetry install
$env:PYTHONPATH='src;tests'
.venv/Scripts/python.exe .scratch/inspect_definitions.py
```

The provisioning script created the monitoring role, audit owner/runtime roles,
and separate database only in the test instance. Migration output was
`{"applied": ["001_operations.sql"], "pending": []}`. Existing integration checks
reported **27 passed**, covering the seed, documentation, and all planted P01-P13
checks before mutation acceptance tests.

Initial async inspection failed because SQLAlchemy needed `greenlet`. Declaring
`sqlalchemy[asyncio]` and reinstalling added greenlet 3.5.6. The next attempt found
that psycopg cannot run on Windows' default Proactor loop. `mcp_server.runtime.run_async`
now chooses a Selector loop explicitly at startup. The read-only inspection then
succeeded and printed names, signatures and definition hashes. The initial YAML
contains the ten ordinary procedures from `130_procedures.sql`; adversarial and
refcursor procedures were excluded. No existing reviewed hash was replaced.

Files: `db/mcp/000_roles.sql`, `db/audit/migrations/001_operations.sql`,
`config/procedures.yaml`, server Core/adapters/bootstrap/runtime, and
`.env.mcp.example`. Local inspection output stays in ignored `.scratch`.

Concepts: [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html),
[psycopg asynchronous connections](https://www.psycopg.org/psycopg3/docs/advanced/async.html),
[sequence rollback behavior](https://www.postgresql.org/docs/17/functions-sequence.html).

## Step 15: Guarded SQL, HTTP acceptance, and final verification (2026-10-03)

Goal: exercise the actual authentication/provider, MCP elicitation, streaming,
transaction, registry, and audit boundaries. Mock-only validation was insufficient
for commit uncertainty, Windows spawning, and procedures with internal COMMITs.
Tests use controlled signing keys for Auth0 and a real, isolated PostgreSQL instance;
no real Auth0 tenant has been configured in this session.

### Commands and purpose

```powershell
# Default suite: pure Core/adapters, characterization, controlled Auth0 HTTP, MCP elicitation.
poetry run pytest -q -p no:cacheprovider

# Explicit isolated-database acceptance, after the fresh baseline checks in step 14.
$env:SHOP_TEST_DATABASE='isolated'
poetry run pytest tests/test_guarded_integration.py tests/test_guarded_failures.py tests/test_http_integration.py tests/test_worker_configuration.py -q -p no:cacheprovider
Remove-Item Env:SHOP_TEST_DATABASE

# Installed CLI and dependency metadata.
poetry run shopmcp --help
poetry check

# A new migration preserves the original applied migration's checksum.
$env:SHOPMCP_MIGRATION_URL='postgresql+psycopg://mcp_audit_owner:test_audit_owner@127.0.0.1:55439/mcp_audit'
poetry run shopmcp audit migrate
poetry run shopmcp audit status
Remove-Item Env:SHOPMCP_MIGRATION_URL

poetry run ruff check .
poetry run ruff format --check .
git -c core.safecrlf=false diff --check
```

The agent invoked pytest and Ruff through `.venv/Scripts/python.exe -m` with the
same arguments, adding `--tb=short --maxfail=1` on targeted regression runs.
Formatting fixes used `.venv/Scripts/python.exe -m ruff check . --fix` and
`.venv/Scripts/python.exe -m ruff format .` before the final read-only checks.
The final isolated suite ran after both audit migrations were applied.

The migration commands returned both `001_operations.sql` and
`002_expiry_and_comments.sql` in `applied`, with an empty `pending` list. Migration
002 converts token expiry to timestamptz and documents the audit tables/columns.
The CLI help exposes `serve`, `inspect-registry`, and `audit`; Poetry reported
`All set!`.

### Results

- Default suite: **81 passed, 48 skipped**. The skips are database tests requiring
  the explicit isolation flag, not hidden failures.
- Final guarded-database/HTTP/worker suite: **21 passed**. This includes a real
  loopback HTTP client, approved and declined writes, streamed row/byte caps,
  cost rejection before approval, statement timeouts, cancellation, audit outages,
  live definition drift, INOUT output, and connection cleanup.
- Earlier pristine-baseline suite: **27 passed** (step 14), after all **39 fresh
  S integrity checks** passed (step 13). Baseline checks precede mutations because
  the acceptance tests intentionally change the disposable fixture and sequences.
- Cancellation during archive's second batch and an injected second-batch failure
  both left the first batch committed and produced `partially_completed`, with no
  retry. A simulated lost commit acknowledgement produced `uncertain`; a final
  audit failure after a confirmed commit retained `committed`.
- A Windows-spawned worker successfully connected using supplied test settings
  while default POSTGRES_PORT was deliberately set to unreachable port 9.
  Reseeding with post-load triggers was refused even with `force=True`.
- Ruff check passed; format check reported **127 files already formatted**;
  `git diff --check` passed. An ASCII scan passed for **123** Python, registry,
  migration, and new documentation files.

A final architecture review moved the remaining seeder verification acceptance
rules into Core. Before that extraction, a read-only run saved all 39 current
check results to ignored `.scratch/verification-before.json`. After extraction,
the same command compared each name, verdict, and detail and printed:
`All 39 verification results exactly match before extraction`. This comparison
preserves behavior on the already-mutated test dataset; it is not a second claim
that the dataset remained pristine. The original generator fixture still matches.

### Failures found and corrected

- SQLGlot represents unrecognized cast types differently from built-in types.
  A direct attribute access failed; unknown types now produce policy rejection.
  Parsing uses the actual `ErrorLevel.RAISE` enum.
- SQLGlot also represents AND/OR as function nodes. The initial positive function
  list rejected a legitimate targeted predicate; both pure boolean forms are now
  explicitly reviewed, with an integration regression test.
- FastMCP's public Host/Origin option accepts `True`, `False`, or `auto`, not the
  internal label `strict`. The runtime uses `True`; malicious host/origin tests pass.
- The archive-cancellation test initially polled pg_stat_activity as shop_owner,
  which could not observe another role's wait details. The test now uses its
  explicit test-admin observer; production roles were not broadened.
- Poetry generated `shopmcp.cmd` on Windows, not `shopmcp.exe`. A direct `.exe`
  probe failed; `poetry run shopmcp --help` succeeded.
- The final formatting check caught an unformatted audit metadata loop. Formatting
  was applied and both lint and formatting were checked again.
- A final pass-through SQL regression using `SELECT '100%:name', 5 % 2` failed:
  the driver interpreted percent characters as parameter syntax. Raw SQL now uses
  `no_parameters=True` for preview, streaming, and mutation execution. The test
  covers both the read and an approved update containing `LIKE '%'`. The final
  21-test database suite and 81-test default suite passed after this correction.

### Files, decisions, and remaining manual acceptance

New server features live in `src/mcp_server/core`; external concerns live in
`src/mcp_server/adapters`. The registry is `config/procedures.yaml`. Runtime
configuration is `.env.mcp.example`, with local `.env.mcp` ignored. Audit migrations
and separate provisioning scripts are in `db/audit` and `db/mcp`. Tests and fixtures
are under `tests`; the operating instructions are in `docs/guarded-server.md`.
README and roadmap describe implemented behavior and the outstanding manual check.

The user confirmed Auth0 is not configured and requested implementation plus setup
documentation. The real Inspector login/consent walkthrough is therefore pending.
Use the runbook to provision the API, compatibility settings, developer account,
and static PKCE client. No real login or consent success is claimed. The existing
port 5433 database, local credentials, and prior setup-guide edits were preserved.
The isolated test container and volume remain available for inspection.

Concepts:
[Auth0 resource profile](https://auth0.com/ai/docs/mcp/guides/resource-param-compatibility-profile),
[Auth0 Inspector setup](https://auth0.com/ai/docs/mcp/guides/test-your-mcp-server-with-mcp-inspector),
[SQLAlchemy streaming](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncConnection.stream),
[PostgreSQL transaction control in procedures](https://www.postgresql.org/docs/17/plpgsql-transactions.html).

## Step 16: Connect Auth0 and MCP Inspector (2026-10-03)

Goal: sign in through Auth0 and use the guarded SQL tools in Inspector. Use the
already-provisioned test database on port **55439** for acceptance testing.

### Auth0 configuration

The full [Auth0 setup instructions](guarded-server.md#configure-auth0-and-inspector)
cover account creation. These are the settings used for this walkthrough:

| Setting | Value |
| --- | --- |
| Auth0 domain | `dev-*.us.auth0.com` |
| API name / identifier | `Shop MCP Server` / `http://127.0.0.1:8000/mcp` |
| API signing algorithm | RS256 |
| Tenant Settings > Advanced | Enable Resource Parameter Compatibility Profile and Include Issuer in Authorization Responses |
| Inspector application | `MCP Inspector`, Regular Web Application |
| OAuth flow / token endpoint authentication | Authorization Code with PKCE / Client Secret (Post) |
| Allowed callback URL | `http://localhost:6274/oauth/callback` |
| Login connection | Enable the developer's database connection for Inspector; disable open signup |

**The missing configuration was the application's user-delegated API grant:**

1. Open **Applications > APIs > Shop MCP Server > Settings**. Under Application
   Access Policy, set **User-Delegated Access** to **Per-app authorization**.
2. Open that API's **Application Access** tab, find **MCP Inspector**, select
   **Edit**, and authorize **User-Delegated Access**. Save the change.
3. In Inspector, select **Re-authenticate** and sign in.

A green check and a Grant ID confirm the grant. `0 / 0 permissions granted` is
normal: this server requires no custom API scopes. Leave **Always grant all
permissions** unchecked. Machine-to-machine Client Access is a separate grant.

### Start the server and Inspector

In `.env.mcp`, set `SHOPMCP_AUTH0_DOMAIN` to the domain above and
`SHOPMCP_POSTGRES_PORT=55439`. Use the test instance's runtime database passwords;
see [runtime configuration](guarded-server.md#configure-and-start-the-runtime).
Keep the Inspector client ID and secret in **Inspector's OAuth Settings**.
`.env.mcp` belongs to the SQL server, which validates tokens and does not perform
Inspector's login. No migration-owner credentials belong in the runtime file.

From the repository root, use two terminals:

```powershell
# Terminal 1: start the authenticated HTTP server on 127.0.0.1:8000.
poetry run shopmcp serve

# Terminal 2: start Inspector 2.9.0 with the existing editable local catalog.
npx.cmd --yes @modelcontextprotocol/inspector@2.9.0 --catalog .scratch/inspector-catalog.json
```

Open `http://localhost:6274`. The catalog entry is **shop-mcp**, transport
**Streamable HTTP**, URL `http://127.0.0.1:8000/mcp`. For a new catalog, add that
entry in the UI. Save the client ID and secret under its **Settings > OAuth
Settings**, leave custom API scopes empty, and connect. Use the legacy protocol
mode for mutation elicitation with this server.

Local files created during setup: `.env.mcp` (runtime configuration) and
`.scratch/inspector-catalog.json` (Inspector catalog), both Git-ignored. Inspector
stores the client secret through its OS keychain.

### Troubleshooting

| Symptom | Fix |
| --- | --- |
| Auth0 says `Client ... is not authorized to access resource server ...` | Add the **User-Delegated Access** grant above, then re-authenticate. |
| Inspector says the session is read-only | Launch with `--catalog`; `--config` and ad-hoc `--server-url` launches do not allow saved edits. |
| Saving settings fails with `Invalid id` | Use catalog key `shop-mcp`, without spaces. |
| Connection times out before Auth0 opens | In this session, adding `Accept: text/event-stream` to Inspector's internal `/api/mcp/events` request resolved the stall. The running Inspector uses the local `.scratch/inspector_sse_accept.mjs` launch hook; the plain `npx` command above does **not** load it. This machine-specific workaround is separate from the Auth0 grant. |
| Opening `/api/mcp/events` directly says `Unauthorized` | Use the Inspector UI; direct navigation omits its required `x-mcp-remote-auth` header. |

Refresh/InPrivate, stream padding, and antivirus exceptions did not fix the
stall. Restore any antivirus settings changed during troubleshooting; the cause
was not established. Diagnostic hooks and logs remain under ignored `.scratch/`.

### Verified result

The user connected Inspector through Auth0. A subsequent authenticated HTTP check
using that session's token discovered all **nine tools**: `ping` returned `pong`,
read-only database tools succeeded with operation IDs, and `SELECT pg_sleep(10)`
was rejected with `policy_rejection`. No shop data was changed by these checks.
The Inspector mutation-approval and batch walkthrough was done in Step 17.

References: [Auth0 Inspector setup](https://auth0.com/ai/docs/mcp/guides/test-your-mcp-server-with-mcp-inspector),
[Auth0 application access policies](https://auth0.com/blog/developers-guide-api-access-policies-auth0/),
[Inspector catalog configuration](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/configuration).

## Step 17: Inspector mutation, rejection and batch acceptance (2026-10-03)

### Goal and why

Step 16 proved login and read-only tools. The automated tests (Steps 14-15) use a fake Auth0 and a
scripted MCP client, so none of them showed that a **real person** is asked, through a real client, before a
change is made, or that the audit trail records what that person decided. This step does that walkthrough
once, by hand, with Inspector. It is the last item `docs/guarded-server.md` listed as pending.

It runs against the **disposable test instance (port 55439)**, never the live database on 5433. Reason: the
steps change data (an updated row, an advanced timestamp, audit rows) and the test fixture is already
documented as mutated by the integration tests. Alternative rejected: the live M database, because a mistake there
would mean an 8-minute reseed or a `down -v` (both need your approval).

### Preflight (read-only)

```powershell
# 1. Which database will the server use? Print only the non-secret keys.
Select-String -Path .env.mcp -Pattern '^SHOPMCP_(POSTGRES_PORT|SHOP_DATABASE|AUDIT_DATABASE|TENANT_ID)='
# 2. Audit migrations applied? (the migration URL is set for this one command only)
$env:SHOPMCP_MIGRATION_URL='postgresql+psycopg://mcp_audit_owner:test_audit_owner@127.0.0.1:55439/mcp_audit'
poetry run shopmcp audit status; Remove-Item Env:SHOPMCP_MIGRATION_URL
# 3. Baseline of the row the test will touch (customer 3, tenant 1)
docker compose -f tests/compose.yml exec -T db psql -U postgres -d shop -Atc "select customer_id, marketing_opt_in, updated_at from shop.customers where customer_id=3"
```

Real output: port `55439`; `{"applied": ["001_operations.sql", "002_expiry_and_comments.sql"], "pending": []}`;
customer 3 had `marketing_opt_in = false` and `updated_at = 2022-12-10 22:24:15+00`. The live database on 5433
showed 5,000,000 orders and 1,000,000 customers before and after.

**Why customer 3 and `marketing_opt_in`:** the update `SET marketing_opt_in = marketing_opt_in` does not change the value, so
the data is provably the same afterwards. It is still a real UPDATE: the trigger `trg_touch_updated_at` sets `updated_at` on every
update, so that column is the visible proof that the statement ran (or did not).

### What was run in Inspector

Two things were already running from the earlier session, so no new terminals were needed: `shopmcp serve` (port 8000, three
connections to 55439) and Inspector launched **with the `.scratch/inspector_sse_accept.mjs` hook** (port 6274). A second
`shopmcp serve` fails with `[Errno 10048] ... only one usage of each socket address`, and a second plain `npx` Inspector lacks
the hook from Step 16.

| # | Tool | Input | Result | Audit events |
|---|---|---|---|---|
| 1 | `execute` | `UPDATE shop.customers SET tier = tier` | `rejected`, `policy_rejection`: "UPDATE and DELETE require WHERE." No prompt. | `error` |
| 2 | `execute` | `SELECT 1; SELECT 2` | rejected before any prompt | `error` |
| 3 | `execute` | `UPDATE shop.customers SET marketing_opt_in = marketing_opt_in WHERE customer_id = 3`, **approved** | `committed`, 1 row | `approval` > `execution_intent` > `commit_intent` > `outcome` |
| 4 | `call_procedure` | `archive_old_orders`, args `{"p_before": "1900-01-01", "p_batch_size": 1, "p_max_batches": 1}`, **approved** | `committed` (`affected_rows` is null: the procedure reports no row count) | the same four events; the execution event carries the registry hash `c5a72128...` and `autocommit_batches`, the commit event `internal_commits: true` |
| 5 | `execute` | the update from 3, **declined** | `declined`, `policy_rejection`: "Mutation approval declined." | `approval` (decision `declined`) > `error`; **no** `execution_intent` |

The two responses pasted in full (rows 1 and 5) both had `audit_status: recorded` and `retry_safe: true`.

### How it was checked

```powershell
# Operations and their event sequence (test instance, as the superuser)
docker compose -f tests/compose.yml exec -T db psql -U postgres -d mcp_audit -c "select o.operation_id, o.tool, o.inputs, (select string_agg(e.kind,' > ' order by e.event_id) from audit.events e where e.operation_id=o.operation_id) events from audit.operations o where o.created_at > '2026-10-03 14:50' and o.tool <> 'ping' order by o.created_at"
# Did the row change?
docker compose -f tests/compose.yml exec -T db psql -U postgres -d shop -Atc "select customer_id, marketing_opt_in, updated_at from shop.customers where customer_id=3"
```

- Customer 3 after the approved update: `marketing_opt_in = false`, `updated_at = 2026-10-03 14:53:58.98+00`. After the **declined** run it
  was still `14:53:58.98`: the decline changed nothing.
- The approval event stores the decision, the Auth0 issuer and subject of the person, an expiry and a **fingerprint of the exact
  request**. No token and no result set is stored.
- The rejected operations (1, 2) have an `error` event but no `execution_intent`, so nothing reached the database.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)` from `shopmcp serve` | A server from the earlier session is still running. Find it with `Get-NetTCPConnection -LocalPort 8000 -State Listen` and `Get-CimInstance Win32_Process`; reuse it (check its database port with `Get-NetTCPConnection -OwningProcess <pid>`: connections to 55439 mean the test instance). |
| `MCP Inspector PORT IS IN USE at http://127.0.0.1:6274` | Same cause. Open `http://localhost:6274` and use the running Inspector, which already has the SSE hook from Step 16. |
| Operation 2 was sent to `execute`, not `query` | Not an error. It is rejected by the same SQL policy either way; recorded as run. |
| The audit table has `detail`, not `payload` | My first inspection query used a column that does not exist; `\d audit.events` shows `event_id, operation_id, kind, detail, created_at`. |

### What this step does not prove

- The text of the approval prompts was not captured, so "the person saw the complete preview and the partial-commit warning" is **reported by the user
  ("ask for permission then run completely"), not recorded here**. The audit proves a decision was made by the Auth0 user, bound to a request fingerprint.
- The archive call matched no rows (cutoff 1900-01-01), so a partial commit across several batches was not exercised by hand. The automated
  tests cover cancellation and an injected second-batch failure (Step 15).
- The test instance is not the live database. Nothing was run against 5433.

### Concepts

- **MCP elicitation** (the server asks the client to ask the human): https://modelcontextprotocol.io/specification/draft/client/elicitation
- **Append-only audit with intent events**: the commit intent is recorded *before* the commit, so a crash leaves evidence rather than silence (see `docs/guarded-server.md`, "Inspect audit and uncertain operations").

## Step 18: Load resources and prompts; client acceptance preflight (2026-10-03)

### Goal and why

Load the new packaged guidance into the existing authenticated runtime so Inspector
can discover nine tools, three resources and two prompts. An existing Python process
does not automatically reload these registrations. The verified runtime uses the
isolated PostgreSQL instance on port 55439. Inspector is reused with its existing
catalog and SSE hook from Step 16.

Alternatives rejected: starting a second server would conflict on port 8000; a
plain new Inspector process would omit the working hook; the live database on
5433 is outside this acceptance scope. Reinstalling dependencies was unnecessary:
the existing virtual environment works even though the Poetry launcher fails.

### Preflight commands and observations

From `F:\repo\python-mcp-server`:

```powershell
Select-String -Path .env.mcp -Pattern '^SHOPMCP_POSTGRES_PORT='
Get-NetTCPConnection -LocalPort 8000,6274 -State Listen |
    Select-Object LocalAddress,LocalPort,OwningProcess
Get-CimInstance Win32_Process -Filter 'ProcessId=19016' |
    Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress
Get-NetTCPConnection -OwningProcess 19016 |
    Select-Object LocalPort,RemotePort,State | ConvertTo-Json -Compress
```

The first command prints only the nonsecret database port: **55439**. The host-level
process queries identified `127.0.0.1:8000` owned by PID **19016**, and Inspector on
`127.0.0.1:6274` owned by PID **67792**. PID 19016's exact command was
`"F:\repo\python-mcp-server\.venv\Scripts\python.exe" -m mcp_server.cli serve`.
Its PostgreSQL connections targeted **55439**. Process IDs are this run's evidence,
not stable values to copy into a future restart.

### Restart command actually run

```powershell
$runtimeCommand = (Get-CimInstance Win32_Process -Filter 'ProcessId=19016').CommandLine
if ($runtimeCommand -ne '"F:\repo\python-mcp-server\.venv\Scripts\python.exe" -m mcp_server.cli serve') {
    throw 'Runtime changed; refusing to stop an unidentified process.'
}
$env:SHOPMCP_POSTGRES_PORT='55439'
Remove-Item Env:SHOPMCP_MIGRATION_URL -ErrorAction SilentlyContinue
Stop-Process -Id 19016 -ErrorAction Stop
$guidanceRuntime = Start-Process `
    -FilePath 'F:\repo\python-mcp-server\.venv\Scripts\python.exe' `
    -ArgumentList @('-m','mcp_server.cli','serve') `
    -WorkingDirectory 'F:\repo\python-mcp-server' -WindowStyle Hidden `
    -RedirectStandardOutput 'F:\repo\python-mcp-server\.scratch\guidance-server.out.log' `
    -RedirectStandardError 'F:\repo\python-mcp-server\.scratch\guidance-server.err.log' -PassThru
$guidanceRuntime.Id | Set-Content -LiteralPath 'F:\repo\python-mcp-server\.scratch\guidance-server.pid'
Write-Output "Started isolated guidance runtime PID $($guidanceRuntime.Id)"
```

The command rechecks the identified process before stopping it, pins the test port,
removes any migration-owner environment variable, and starts the runtime hidden.
Runtime passwords continue to come from the existing ignored `.env.mcp`; no secret
was copied into source or documentation. Inspector was not restarted.

Real output: `Started isolated guidance runtime PID 15460`. The virtual-environment
launcher spawned the actual server process **77020**. Its startup log reported:

```text
Starting MCP server 'shop-db' with transport 'http' on http://127.0.0.1:8000/mcp
Started server process [77020]
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

Ignored runtime files created: `.scratch/guidance-server.out.log`,
`.scratch/guidance-server.err.log`, `.scratch/guidance-server.pid`.
Feature source, tests and documentation are listed in
[the implementation plan](mcp-resources-prompts-plan.md).

### HTTP checks actually run

```powershell
@'
import urllib.request
for url in ('http://127.0.0.1:8000/.well-known/oauth-protected-resource/mcp', 'http://localhost:6274'):
 try:
  with urllib.request.urlopen(url, timeout=3) as response:
   print(url, response.status)
 except Exception as exc:
  print(url, type(exc).__name__, str(exc))
req = urllib.request.Request('http://127.0.0.1:8000/mcp', data=b'{"jsonrpc":"2.0","id":1,"method":"resources/list","params":{}}', headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}, method='POST')
try:
 urllib.request.urlopen(req, timeout=3)
except urllib.error.HTTPError as exc:
 print('Unauthenticated resources/list:', exc.code)
'@ | .\.venv\Scripts\python.exe -
Get-Content .scratch/guidance-server.err.log | Select-Object -Last 12
```

Real output: protected-resource discovery **200**, existing Inspector page **200**,
unauthenticated `resources/list` **401**. These checks prove reachability and
authentication rejection, not authenticated Inspector resource/prompt acceptance.
No SQL tool or procedure was called by this step.

### Automated verification and actual failures

The database-independent suite passed: **170 passed, 48 deselected in 45.82s**.
Ruff check passed and **139 files** were already formatted. The documented SDK
helper returned `{'tools': 9, 'resources': 3, 'prompts': 2}` with a legacy in-process
client. These automated results use injected services/controlled JWT keys; they
are separate from the real-tenant UI walkthrough.

| Failure encountered | Resolution or remaining limitation |
|---|---|
| Poetry reported `Failed to canonicalize script path` | Used the existing `.venv/Scripts/python.exe -m pytest` and `-m ruff`; no installation or dependency change. |
| Existing pytest cache and host temporary directory denied access (WinError 5) | Used `-o cache_dir=.scratch/pytest-cache` and `PYTEST_DEBUG_TEMPROOT=F:\repo\python-mcp-server\.scratch`. |
| Ordinary process inspection reported `Get-CimInstance: Access denied` | Read-only host-level queries succeeded; the exact process and isolated connections were verified before restart. |
| FastMCP masked missing required prompt SQL with a generic error | Prompt argument middleware now returns a sanitized `sql is required` error. Tests passed. |
| Computer-use inventory contained no enabled browsers; opening Inspector returned `Browser is not available: iab` | The user performed the manual check and confirmed it worked. The assistant did not independently observe the UI. |

### Manual acceptance: confirmed by the user

After the restart and the request for manual results, the user confirmed:
"I checked, it worked". This completes
[T12](mcp-resources-prompts-plan.md#t12-perform-and-record-manual-acceptance)
as user-reported manual client acceptance. The requested walkthrough covered the
9/3/2 inventories, three resource reads, both schema prompt variants, the slow-query
prompt and argument errors. The confirmation did not include per-method responses,
screenshots or a negotiated protocol, so those details are not claimed as separately
observed. The automated checks above provide detailed behavioral evidence.
Optional LLM-host context inclusion remains unverified and is separate from the
required manual client acceptance.

### Concepts

- [MCP resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources): listing metadata and reading content are separate operations.
- [MCP prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts): retrieval renders messages for the host/user to use.
- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle): legacy initialization negotiates capabilities, not counts.
- [FastMCP middleware](https://gofastmcp.com/servers/middleware): identity/session checks span all MCP surfaces.


## Step 19: MCP evolution, modern approval and frontend build (2026-10-04)

### Goal and why

Implement native discovery pagination and bounded table resources before the
protocol migration, then verify modern MRTR approval, typed output and the App.
Use the installed Python environment rather than reinstalling working locked
dependencies. Bundle the official Apps SDK locally; CDN scripts would require
external network permissions at runtime. Tasks stay disabled.

### Commands actually run

All Python commands below ran from F:\repo\python-mcp-server. The temporary
root/cache stays inside the workspace because host cache directories deny access.

```powershell
$env:PYTEST_DEBUG_TEMPROOT='F:\repo\python-mcp-server\.scratch'
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_catalog.py tests/test_mcp_resources.py -q -o cache_dir=.scratch/pytest-cache
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_tools.py tests/test_mcp_catalog.py tests/test_mcp_resources.py tests/test_guarded_core.py -q -o cache_dir=.scratch/pytest-cache
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_tools.py tests/test_mcp_catalog.py tests/test_mcp_resources.py -q -o cache_dir=.scratch/pytest-cache --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_mrtr.py tests/test_mcp_http.py tests/test_mcp_prompts.py -q -o cache_dir=.scratch/pytest-cache --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_schemas.py tests/test_mcp_http.py -q -o cache_dir=.scratch/pytest-cache --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_schemas.py tests/test_mcp_http.py tests/test_mcp_mrtr.py -q -o cache_dir=.scratch/pytest-cache --tb=short
```

These execute behavioral checks without a live database. First milestone:
6 passed in 11.03s. Modern client checks: 7 passed in 2.25s. Modern HTTP,
schema and MRTR checks after fixes: 85 passed in 19.48s.

Frontend commands ran from src/mcp_server/adapters/mcp/query_plan_viewer:

```powershell
npm.cmd install --cache F:\repo\python-mcp-server\.scratch\npm-cache --no-audit --no-fund
npm.cmd test
npm.cmd run build
```

Install created node_modules (ignored) and package-lock.json: added 37 packages
in 4s. Node tests exercise the DOM with linkedom. Build bundles the SDK and the
viewer into viewer.html, with all styles/scripts inline. First build succeeded:
Built viewer.html (603395 script bytes; no external assets).

### Actual failures and fixes

- FastMCP rejects cache_ttl=0 and cache_scope without a positive TTL. Omit cache
  hints: the SDK emits ttlMs=0/cacheScope=private by default, preserving no caching.
- Client mode="modern" is invalid in this SDK. Use mode="2026-07-28".
- Raw modern HTTP requires MCP-Method and MCP-Name matching the request method
  and name/URI. Tests now supply them alongside per-request _meta.
- FastMCP simplifies JSON Schema discriminator metadata into oneOf branches.
  Verify each branch's kind const instead of expecting the discriminator keyword.
- npm view initially failed with EPERM in the host npm cache. Repeated it with
  --cache .scratch/npm-cache; resolved versions: ext-apps 2.0.3, esbuild 0.28.2,
  linkedom 0.18.13. No escalation or global configuration change was needed.
- npm blocked esbuild's postinstall script under its allowScripts policy.
  The platform binary dependency was present and build worked without approving
  additional install scripts.
- First frontend run: 3 passed, 1 failed because cyclic fixture JSON serialization
  threw. Safe JSON display now catches this; verification is recorded below.

### Files and concepts

The plan is docs/mcp-evolution-plan.md. New production files include the MRTR
adapter, output schemas, App adapter and bundled frontend. Tests and subsequent
verification results are recorded with the implementation milestones.
No environment secret, live mutation, seed, migration or volume reset was run.

- https://gofastmcp.com/servers/pagination
- https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
- https://modelcontextprotocol.io/extensions/apps/overview
- https://skills.extensions.modelcontextprotocol.io/specification/stable/skills


## Step 20: Reproducible package and isolated acceptance (2026-10-04)

### Goal and why

Verify the final code through the real Postgres adapters and loopback HTTP, then
check the distributable assets. Start the existing isolated container rather than
rebuilding, resetting or seeding its volume. Do not run fresh-seed integrity
checks against a database already used by procedures. Keep live port 5433 out of
the acceptance workflow. The implementation request authorizes the planned
isolated acceptance; host access was granted by automatic sandbox review.

### Commands actually run

From F:\repo\python-mcp-server:

```powershell
poetry run pytest -q -o cache_dir=.scratch/pytest-cache
$env:PYTEST_DEBUG_TEMPROOT='F:\repo\python-mcp-server\.scratch'
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.scratch/pytest-cache --tb=short
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
poetry build --output dist
```

The Poetry launcher initially failed to canonicalize its script path in the
sandbox. Tests used the installed .venv directly. The package build succeeded
with host access to Poetry's existing tool environment; no backend installation
or dependency upgrade was required. Outputs: dist/python_mcp_server-0.1.0.tar.gz
and dist/python_mcp_server-0.1.0-py3-none-any.whl. An archive inspection using
Python zipfile/tarfile verified viewer.html, SKILL.md and references/checklist.md
in both archives and the absence of node_modules. The first wheel was 250231 bytes.

The first full suite found one old inventory assertion (3 resources); the new
inventory is 6. After fixing it, the suite passed 201 tests with 49 database tests
skipped in 33.86s. A further cancellation regression test was added before the
final run below. Ruff initially reported import order/unused locals, then mixed
line endings in three edited tests; targeted fix/format commands resolved them.
No formatter changed the SQL fixtures or planted problems.

Docker startup/status commands:

```powershell
docker compose -f tests/compose.yml ps --format json
docker desktop start --help
docker desktop start --detach
docker compose -f tests/compose.yml ps --all --format json
docker compose -f tests/compose.yml start --wait
```

Initial Docker inspection failed because the engine pipe was absent. The default
sandbox also could not read Docker's host config; host inspection confirmed the
Docker Desktop Linux engine was stopped. Starting Docker Desktop returned
Starting Docker Desktop. The existing shopmcp-test-db-1 container was stopped;
its verified binding was 127.0.0.1:55439 -> 5432. start --wait brought this same
container to Healthy without creating or deleting a volume. No server was pointed
at live port 5433, and no seed or migration was run.

Isolated checks use controlled credentials from tests/support.py, not .env:

```powershell
$env:SHOP_TEST_DATABASE='isolated'
$env:PYTEST_DEBUG_TEMPROOT='F:\repo\python-mcp-server\.scratch'
.\.venv\Scripts\python.exe -m pytest tests/test_guarded_integration.py tests/test_http_integration.py tests/test_guarded_failures.py tests/test_planted.py -q -o cache_dir=.scratch/pytest-cache --tb=short
```

Real first result: 40 passed in 11.64s. This covers table resource/catalog parity,
Core prefix lookup, real explain/diagnostics DTO validation, modern authenticated
HTTP approvals/procedure calls, transaction failures and unchanged planted
problems. One cache warning reported WinError 5 when concurrent runs shared the
same cache directory; final runs use distinct cache directories below.

Frontend commands, from src/mcp_server/adapters/mcp/query_plan_viewer:

```powershell
npm.cmd ci --cache F:\repo\python-mcp-server\.scratch\npm-cache --no-audit --no-fund
npm.cmd test
npm.cmd run build
```

The clean lockfile install added 37 packages in 2s. esbuild postinstall remained
blocked; the installed platform binary built successfully without new script
approval. Four tests passed; build produced viewer.html with 603488 script bytes.
The artifact uses ASCII, inline styles/scripts and no external assets.

Final rerun commands (separate PowerShell processes):

```powershell
$env:PYTEST_DEBUG_TEMPROOT='F:\repo\python-mcp-server\.scratch'
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.scratch/pytest-cache-default --tb=short
$env:SHOP_TEST_DATABASE='isolated'
.\.venv\Scripts\python.exe -m pytest tests/test_guarded_integration.py tests/test_http_integration.py tests/test_guarded_failures.py tests/test_planted.py -q -o cache_dir=.scratch/pytest-cache-isolated --tb=short
poetry build --output dist
```

Final results: default suite 202 passed / 49 skipped in 37.24s; isolated MCP
acceptance 40 passed in 13.68s, without the earlier cache warning. Ruff check
passed, 151 files were already formatted, and git diff --check passed. The final
wheel and sdist build succeeded. The additional targeted MRTR/tools/HTTP run
passed 88 tests in 12.89s after cancellation/expiry fixes.

### Verification boundaries and concepts

The computer-use inventory returned apps=[] and browsers=[]. DOM tests and
protocol metadata checks do not prove rendering in a real Inspector iframe or
host skill activation. Those manual checks remain pending. Inspector must use
protocolEra=modern; SDK clients use mode="2026-07-28". Existing runtime processes
were not restarted as part of these tests. Tasks remain disabled by design.

- https://docs.docker.com/reference/cli/docker/desktop/start/
- https://docs.docker.com/reference/cli/docker/compose/start/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr
- https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/recipes
- https://apps.extensions.modelcontextprotocol.io/api/classes/app.App.html
- https://skills.extensions.modelcontextprotocol.io/specification/stable/skills
