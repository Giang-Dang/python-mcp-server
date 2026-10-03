# Roadmap: the guarded SQL MCP server

This is the next phase. The database, workload and diagnostics from steps 1-9 exist so that this server can be built and tested against a
system that behaves like a real one. Everything below is a **design to review and change**, not something already built. Section 8 lists
the questions I would settle first.

## 1. What the server does

A model connected over MCP can read the `shop` database freely, but cannot change anything without a human saying yes, and can only run
stored procedures that a human has registered and described.

| Request | What happens |
|---|---|
| Read-only SQL | Parsed, classified as read, run as `mcp_reader` with timeouts and result caps. No question asked. |
| SQL that changes data (or that cannot be proven read-only) | Not run. The human is asked through MCP **elicitation** with the SQL, the reason it was classified as a mutation and the expected effect. Run as `mcp_writer` only on explicit approval. |
| Stored procedure | Only through the **registry**: allowlisted name, definition hash, declared effect, typed parameters. Anything else is refused. |

## 2. Safety model: layers, and which one is real

| Layer | Purpose | Strength |
|---|---|---|
| **Database privileges** (`mcp_reader` SELECT only; `mcp_writer` DML on six tables; `mcp_proc_exec` EXECUTE only) | The actual barrier. Holds even if every other layer has a bug. | Hard |
| Role timeouts (`statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`) | Stops runaway and blocking statements (P08, P09, P12). | Hard, but a session may `SET` them to another value |
| `default_transaction_read_only = on` for `mcp_reader` | Convenience: a stray write fails early. | **Advisory**: a session can switch it off (a test proves this, `tests/test_mcp_stub.py`) |
| SQL classifier (sqlglot AST, fail closed) | Decides **whether to ask the human**, and gives a clear message. | Soft: it can be wrong, so it must never be the only protection |
| Elicitation (human approval) | Authorizes a specific change. | Only as good as what is shown to the human |
| Procedure registry | Limits which routines can be called and with what arguments. | Hard for the allowlist, soft for the declared effect (a human wrote it) |
| Tool annotations (`read_only_hint`, ...) | Hints for the client UI. | None; never rely on them |

Design rule: **the classifier may only make the server stricter than the database, never more permissive.** If the classifier says
"read" and the role could still write, the role's privileges must stop it. If the classifier is unsure it says "mutation".

## 3. Component A: the SQL classifier

Library: [sqlglot](https://sqlglot.com) with the Postgres dialect. Output: `read`, `mutate` or `reject`, with a reason list.

Fail-closed rules (an unknown or unparsable statement is never `read`):

1. Exactly **one** statement. Multiple statements (`SELECT 1; DROP TABLE x`) are rejected.
2. Parse failure, or any node type not on the **read allowlist** (`Select`, `Union`, `Subquery`, ordinary expressions): `mutate` (or `reject`).
3. A `SELECT` is still not automatically read-only. Treat as mutation or reject:
   - `SELECT ... INTO` (creates a table), `FOR UPDATE` / `FOR SHARE` (takes row locks);
   - a **data-modifying CTE** (`WITH d AS (DELETE ... RETURNING *) SELECT ...`);
   - **functions with side effects**: `nextval`, `setval`, `pg_sleep`, `pg_advisory_lock`, `set_config`, `lo_*`, `pg_read_file`, `dblink*`, `pg_terminate_backend`, ...
     Use a function **allowlist** (known-safe built-ins), not a denylist.
   - calling a **user-defined function** at all: `SELECT shop.get_next_invoice_number()` is a write that looks like a read (adversarial routine A1).
4. `EXPLAIN` is read only without `ANALYZE`; `EXPLAIN ANALYZE <mutation>` executes the mutation.
5. Utility statements (`SET`, `RESET`, `BEGIN`/`COMMIT`, `COPY`, `DO`, `CALL`, `VACUUM`, `LISTEN`, `PREPARE`, ...) are not read. `CALL` goes through the registry, never through free SQL.
6. Comments, quoted identifiers, unicode tricks and dollar-quoting must not change the verdict (the AST, not a regex, decides).

Testing: a table of (SQL, expected verdict) cases, including the traps above, plus a differential check: for every case classified `read`, run it as `mcp_reader` inside a
transaction and confirm that no row version changes (compare `pg_stat_xact_user_tables` or the table counts).

## 4. Component B: execution policy

- **Reads**: `mcp_reader`, one short transaction, `statement_timeout` from the role (15 s), plus:
  - a **row cap** and a **byte cap** on the result, enforced while streaming (P10: `SELECT *` on 30 million rows must not be materialized);
  - optional **cost guard**: `EXPLAIN (FORMAT JSON)` first and refuse plans whose estimated cost or rows exceed a limit (P09: the cross join, `count(*)` on `audit_log`). Estimates can be wrong (P07), so the timeout stays as the backstop.
  - a hint to the model when a query is unbounded, naming the fix (filter on `created_at` for `audit_log`, P03).
- **Mutations**: after approval, `mcp_writer`, one transaction, `lock_timeout` 5 s, row-count check against what was shown to the human (abort and roll back if the real count is much larger).
- **Tenant**: the connection sets `app.tenant_id` on the server side. The classifier must reject `SET`/`set_config` of `app.tenant_id`, because the setting is client-settable (known gap, section 6).
- **Cancellation and timeouts** must be tested with `warm_cache(60)`.

## 4a. Data access: SQLAlchemy Core (decided)

Decision: the server reaches the database through **SQLAlchemy Core** (`src/mcp_server/db.py`), not the ORM and not hand-written SQL strings.
Raw SQL strings are limited to (a) the database definition (`db/**/*.sql`, the seeder's `COPY`) and (b) pass-through SQL that a human or model wrote.

| What | How |
|---|---|
| Connections | One pooled `Engine` per role (`engine_for("mcp_reader")`), chosen by the server, never by the model |
| Server's own fixed queries (list tables, describe a table, diagnostics, registry hash lookup) | Core expressions: `select(...)` over `Table` objects, or the inspector for ordinary tables. Parameters are always bound |
| Registered procedure calls | The procedure name comes from the reviewed registry (a name cannot be a bind parameter); the arguments are bound parameters validated by their declared types |
| Pass-through SQL (`execute_sql`) | Cannot be built by SQLAlchemy: it is text. Run with `Connection.exec_driver_sql`, so `:name` inside the user's SQL is not mistaken for a bind parameter. The classifier (section 3) runs first |
| ORM models | Not used. The server has no domain objects; it relays whatever the SQL returns |

What this buys: typed, parameterized queries for everything the server itself asks; pooling with `pool_pre_ping`; reflection helpers; one place to reset session state.
What it does not buy: any protection for pass-through SQL. That protection is the classifier, the role privileges and the human approval.

## 5. Component C: the procedure registry

A registry entry is data a human reviews and commits, for example (YAML or a table):

```yaml
- name: cancel_order
  signature: "shop.cancel_order(bigint)"
  definition_sha256: "<hash of pg_get_functiondef at review time>"
  effect: write            # read | write | batch | admin, declared by a human
  needs_approval: true     # elicitation before calling
  params:
    - {name: p_order_id, type: int, minimum: 1}
```

At call time the server: (1) looks the name up in the registry, refusing anything else; (2) recomputes the hash of the routine in the database and **refuses if it changed**
(someone redefined the procedure after review); (3) validates the arguments against the declared types (pydantic) and passes them as **bind parameters**, never by string building;
(4) asks for approval when `effect` is not `read`; (5) calls it through `mcp_proc_exec`.

The adversarial routines in `db/post_load/135_adversarial.sql` are the test cases, and each shows why a rule exists:

| Routine | Trap | Rule it motivates |
|---|---|---|
| `get_next_invoice_number()` | Sounds like a read, advances a sequence on every call (not rolled back). | Effect is **declared by a human**, never guessed from the name. |
| `search_orders(text)` | Pastes its argument into SQL and runs as owner: injection plus cross-tenant leak. | Do not register routines that take SQL fragments; definer routines bypass RLS, so they need tenant checks written by hand. |
| `warm_cache(int)` | Sleeps for N seconds. | Per-procedure maximum duration and argument bounds; cancellation must work. |
| `order_snapshot(...)` | OUT parameters and a refcursor: the result is read with `FETCH` inside the same transaction. | The executor must support multi-statement shapes for registered routines, or refuse them. |
| `bulk_update_prices(numeric, int)` | With a NULL category it rewrites every product price. | `effect: batch`, mandatory approval, and a **parameter rule** (category required). |
| `archive_old_orders(...)` | Invoker procedure that `COMMIT`s per batch: partial effects survive a failure. | A caller cannot wrap it in a rolled-back transaction; mark non-transactional and say so to the human. |

Surface to the model: either one generic `call_procedure(name, args)` tool, or one tool **per registered procedure** (better schemas and descriptions for the model, more code). Decide in section 8.

## 6. Known gaps in the test database (deliberate, to be handled or documented by the server)

- `order_items` has no row-level security: a reader can see other tenants' lines unless it filters through `orders`.
- `mv_daily_sales` is a materialized view; it cannot have RLS and leaks across tenants.
- `app.tenant_id` is settable by the session (`SET app.tenant_id = '2'`). The server must hold the connection and refuse that statement.
- SECURITY DEFINER routines and views without `security_invoker` bypass RLS.
- Grants are broader than the planned allowlist (`mcp_proc_exec` can execute 24 routines, including four adversarial ones: `bulk_update_prices`, `get_next_invoice_number`, `search_orders`, `warm_cache`). The registry, not the grants, is what narrows them today; tightening the grants to match the registry is a task.
- The inventory ledger is synthetic, and `shopdb verify` is valid only on a freshly seeded database.

## 7. Milestones

| # | Deliverable | Done when |
|---|---|---|
| M1 | Read path: execute a SELECT as `mcp_reader` with timeout, row cap, byte cap | Tests for P09 (cross join), P10 (huge `SELECT *`), timeout and cap messages |
| M2 | Classifier with a table-driven test suite | All cases pass, including every trap in section 3; differential check against the real database |
| M3 | Elicitation flow for mutations | Approve / decline / cancel paths tested with a scripted client; a client **without** elicitation support gets a refusal, not a silent run |
| M4 | Procedure registry and `call_procedure` | Hash mismatch refused; each adversarial routine handled as in section 5 |
| M5 | Cost guard and diagnostics tools | `EXPLAIN` guard; tools wrapping `db/observability/*.sql` (top queries, locks, bloat) as read-only tools |
| M6 | Audit and hardening | Every approved action recorded with who approved what; red-team pass; documentation |

Client support for elicitation: Claude Code and VS Code support it; Claude Desktop does not. The Inspector (`fastmcp dev`) is the easiest place to watch the prompts.

## 8. Questions to settle before M1

1. **Tool surface**: one `execute_sql` tool that returns "needs approval" for mutations, or separate `query` and `execute` tools? Separate tools make the intent visible to the client and its permission UI.
2. **Preview for mutations**: show an `EXPLAIN` estimate before asking, or execute inside a transaction, show the real row count, and ask to commit? The second is more truthful but holds locks while a human thinks (P08/P12).
3. **Registry storage**: a YAML file in the repo (reviewed in pull requests, simple) or a table in the database (queryable, but the server then trusts the database it is protecting).
4. **Tenant model**: fixed tenant 1 per server process, or a tenant chosen per session by configuration (never by the model)?
5. **Pool session state**: the pool itself is decided (section 4a). Open: how session state (`app.tenant_id`, any `SET` run by pass-through SQL) is reset when a connection returns to the pool. `pool_reset_on_return="rollback"` does not undo a `SET`; `DISCARD ALL` or `RESET ALL` on checkin does, and returns the role-level defaults.
6. **Where the code lives**: `src/mcp_server/db.py` reads connection settings from `shopdb.config`. Keep that, or give the server its own settings module?

## 9. Useful commands for this phase

```powershell
poetry run fastmcp dev src/mcp_server/server.py                      # Inspector UI
poetry run pytest tests/test_planted.py                              # the planted problems still exist
.\db\workload\run.ps1 -Scenario mixed -Seconds 30 -Clients 10        # load while testing the server
Get-Content db\observability\locks.sql | docker compose exec -T db psql -U postgres -d shop -f -
```
