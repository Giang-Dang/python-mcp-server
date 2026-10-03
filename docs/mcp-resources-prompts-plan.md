# MCP resources and prompts: implementation plan

Status: T01-T12 complete. Manual client acceptance was confirmed by the user;
optional LLM-host context inclusion remains unverified.
Prepared: 2026-10-03.
Audience: the developer implementing one small task at a time.

## 1. Goal and assumptions

Add useful context and reusable learning workflows to the existing guarded SQL
server. A connected client should discover three resources and two prompts while
continuing to discover the existing nine tools.

Assumptions for this plan:

1. Extend the existing FastMCP server and authenticated Streamable HTTP endpoint.
2. Start with documentation resources that do not query either database.
3. Render prompts as instructions; fetching a prompt never runs its suggested tools.
4. Keep live database inspection behind the existing audited tools.
5. Keep the current SQL policy, mutation approval, procedure registry, and audit
   behavior. Do not expand database permissions for this feature.
6. Work with the locked FastMCP 4.0.10 dependency. A dependency or protocol upgrade
   is separate work.
7. Implement tasks in order, review each diff, and make small commits when ready.

This document supplies the specification, design, and task checklist for review.
Commands below are instructions for future implementation, not evidence that they
have already run. Preparing this plan did not run setup, builds, or database work.

### Completion criteria

- Authenticated discovery returns exactly nine tools, three resources, and two
  prompts, with the names and URIs specified below.
- Resources return bounded Markdown with useful descriptions and no credentials.
- Prompt arguments are documented, validated, and bounded; rendering has no
  database, filesystem, network, tool-call, or elicitation side effects.
- The policy resource reports the server instance's configured SQL limits.
- Invalid authentication and cross-user session reuse are rejected on the new
  methods as well as existing tools.
- Resource and prompt tests run without PostgreSQL or a real Auth0 tenant.
- Existing automated approval, SQL policy, and architecture checks still pass.
- A manual client walkthrough records what was actually observed, including any
  client limitation. It is not replaced by claims about unit tests.

## 2. Current implementation to build on

| Existing file | Why it matters |
|---|---|
| `src/mcp_server/bootstrap.py` | Creates FastMCP, installs tools, and owns lifecycle cleanup. |
| `src/mcp_server/adapters/mcp/tools.py` | Registers nine tools and currently installs the shared identity middleware. |
| `src/mcp_server/adapters/identity/auth0.py` | Verifies identity and produces the Core `Principal`. |
| `src/mcp_server/core/sql_access/domain.py` | Defines the plain Python `Limits` dataclass. |
| `src/mcp_server/core/sql_access/policy.py` | Enforces SQL policy; resource text must describe, not replace, it. |
| `src/mcp_server/core/catalog/application.py` | Provides audited `list_tables` and `describe_table` workflows. |
| `src/mcp_server/core/auditing/application.py` | Records database operation intent and outcome. |
| `tests/test_mcp_http.py` | Controlled Auth0/JWT tests, discovery, session binding, and inert imports. |
| `tests/test_mcp_tools.py` | Database-independent approval tests using an in-process MCP client. |
| `tests/test_guarded_core.py` | SQL/approval tests and `test_core_dependency_boundaries`. |
| `tests/test_http_integration.py` | Existing isolated-database HTTP test that checks nine tools. |
| `tests/support.py` | Explicit test settings that do not load `.env.mcp`. |

The nine tool names are:

```text
ping, list_tables, describe_table, query, execute, explain,
list_procedures, call_procedure, diagnostics
```

The current test clients use `mode="legacy"`, and HTTP tests negotiate protocol
`2025-11-25`. Preserve these choices for this work because the existing imperative
elicitation path depends on that client mode. See
[the current runbook](guarded-server.md).

## 3. Public interface contract

### 3.1 Resources

All three resources have MIME type `text/markdown`. The `shop://` URIs are MCP
identifiers, not HTTP endpoints or paths to local files.

| URI | Resource name | Content and source |
|---|---|---|
| `shop://guide/schema` | `schema_guide` | Curated overview of the shop domains, naming conventions, and how to inspect the live catalog. |
| `shop://guide/relationships` | `relationships_guide` | A small set of verified join paths, cardinality cautions, and the known tenant-isolation limitation. |
| `shop://policy/sql` | `sql_policy` | Permitted workflows, prohibited SQL categories, approval behavior, and current values from `Limits`. |

Content requirements:

- Schema guide: cover customers, catalog, orders, payments, fulfillment, and
  inventory. Explain schema-qualified SQL and the unqualified `table` argument
  expected by `describe_table`. Direct the model to `list_tables` and
  `describe_table` for current metadata. Do not claim current row counts.
- Relationships guide: verify the selected paths against `db/schema/020_core.sql`
  and `db/schema/030_orders.sql`, using `docs/erd.md` as a reading aid. Explain
  one-to-many joins and double counting. Do not call this a complete or live ERD.
- SQL policy: describe bounded reads, non-ANALYZE plans, targeted DML with human
  approval, and reviewed procedure calls. Explain that approval cannot override
  a policy rejection, and uncertain mutations must not be retried automatically.
- Include the existing limitation that configured tenant context does not provide
  a tenant-isolation guarantee for this fixture.
- Describe P01-P13 as intentional learning fixtures. Do not expose a full solution
  key or suggest automatically repairing them.
- Use a fixed content revision such as `guidance-v1` for the two curated guides.
  Describe them as shipped documentation, not a database snapshot.
- Keep each resource's UTF-8 text at or below 16,384 bytes. Test this content budget.
  This budget is separate from SQL query result limits.

There are no resource templates, subscriptions, or application-managed change
notifications in this first version. `resources/templates/list` should be empty;
leave capability handling to the framework rather than advertising unsupported
subscription behavior.

Clients discover resource metadata with `resources/list` and fetch selected
content with `resources/read`. Merely listing a resource does not put its content
into the model's context. See the
[MCP resources specification](https://modelcontextprotocol.io/specification/2025-11-25/server/resources).

### 3.2 Prompts

| Prompt name | Arguments | Expected workflow after the user chooses to use it |
|---|---|---|
| `explore_schema` | Optional `table: str = ""` | Start with the guides, inspect live table metadata, then explain relevant tables and joins. |
| `investigate_slow_query` | Required `sql: str` | Review policy and schema, request a non-ANALYZE plan, and distinguish evidence from hypotheses. |

Both prompts return one user-role text message. This keeps the first version easy
to inspect and compatible with simple prompt clients. Reference the resource URIs
in the instructions, but do not assume that a host will automatically read them.
If the host cannot load resources, the workflow can still use the existing tools.

`explore_schema` behavior:

1. If `table` is omitted or exactly empty, instruct the model to list tables and
   give a short map of the database before selecting a few relevant tables.
2. Otherwise accept only an unqualified ASCII identifier matching
   `[a-z_][a-z0-9_]{0,62}`. Reject qualified names, whitespace-only values, and
   malformed names with a useful error. Do not silently normalize the input.
3. Tell the model to call `describe_table` for the selected name. A syntactically
   valid name is not proof that the table exists; the catalog tool resolves that.
4. Prefer metadata inspection. Sample rows only when relevant to the user's
   request and through the bounded `query` tool.
5. Explain limitations and distinguish curated relationship guidance from live
   columns and planner row estimates.

`investigate_slow_query` behavior:

1. Require nonempty SQL; reject whitespace-only input. Preserve accepted SQL text.
2. Treat the supplied SQL and comments as untrusted material to analyze. Place it
   in a JSON-encoded data section, separate from the fixed workflow instructions.
   Delimiting input improves clarity; it is not a prompt-injection security boundary.
3. Ask the model to check that the statement is a suitable read before requesting
   `explain`. Prompt rendering itself does not parse, approve, or execute SQL.
4. Pass the original SQL to `explain`; do not ask the caller to add `EXPLAIN` or
   `ANALYZE`, and do not execute the query just to investigate it.
5. Optionally use the existing `diagnostics` reports when useful. Distinguish
   aggregate diagnostic statistics from a measurement of the supplied SQL.
6. Produce findings as: observed evidence, likely cause, suggested change, and
   what further verification would establish. Planner cost is not elapsed time.
7. Suggest improvements for review. Do not instruct the model to apply indexes,
   run DDL, change data, or remove a planted problem.

Argument and output bounds:

- Bound the UTF-8 byte length of canonical JSON for the public argument object
  to `min(limits.request_bytes, 8192)`. Reuse the existing pure `canonical` helper
  from `core/access_control/application.py`; measure serialized bytes, not
  Python character count. Apply this to both prompts.
- Bound each rendered message's UTF-8 text to 65,536 bytes. Include the fixed
  instructions when checking the output; reject rather than silently truncate.
- These are guidance-specific limits. SQL tools continue using their existing
  request and result limits.
- Return a sanitized argument/limit error for bad input. Never echo the full
  rejected SQL in the error message.

MCP clients discover templates with `prompts/list` and render one with
`prompts/get`. Arguments are strings in the protocol. Rendering produces messages;
the host and user decide whether to use them in a conversation. See the
[MCP prompts specification](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts).

### 3.3 Authentication, audit, and availability

Apply the same verified identity and session-binding middleware to every incoming
MCP request. Move its installation out of `register_tools` so it is visibly shared
by tools, resources, and prompts.

Make the audit boundary explicit in documentation:

| Operation | Authentication | Database operation audit |
|---|---|---|
| List tools/resources/prompts/templates | Required | No database operation is started. |
| Read these three documentation resources | Required | No database operation is started. |
| Render these two prompts | Required | No database operation is started; submitted SQL is not persisted by this feature. |
| Call existing database tools | Required | Existing audit intent/outcome behavior remains mandatory. |
| Call `ping` | Required | Existing database-independent behavior. |

This is a deliberate metadata-only scope: documentation reads and prompt rendering
do not create `mcp_audit` rows. The phrase "every operation is audited" must be
qualified as database operations in new documentation. A later live-data resource
must use an audited application service; it cannot inherit this metadata exception.

Given a running, authenticated server, rendering this guidance does not require a
healthy shop or audit database. Normal server construction still has its existing
configuration, registry, and Auth0 startup requirements; this feature does not
promise startup without them.

## 4. Technical design

### File layout

```text
src/mcp_server/
  core/guidance/
    __init__.py
    resources.py       # Pure Markdown renderers and curated guide text.
    prompts.py         # Pure prompt renderers and argument/output validation.
  adapters/mcp/
    middleware.py      # Existing identity/session middleware moved here.
    resources.py       # FastMCP resource registration.
    prompts.py         # FastMCP prompt registration and safe error mapping.
    tools.py           # Existing tools, no middleware installation.
  bootstrap.py         # Install middleware once and register all three surfaces.

tests/
  test_guidance_resources.py
  test_guidance_prompts.py
  test_mcp_resources.py
  test_mcp_prompts.py
  test_mcp_http.py      # Extend existing controlled-authentication tests.

docs/
  mcp-resources-prompts-plan.md
  mcp-discovery.md      # Added in T10: protocol and client walkthrough.
```

Core renderers accept ordinary strings and the existing `Limits` dataclass, and
return strings. Use `GuardError` with `Category.ARGUMENTS` or `Category.LIMIT` for
expected validation failures. Keep FastMCP and Pydantic types in adapters.

The composition root passes `settings.limits` to the registration functions. Their
closures pass this value to pure renderers; do not expose `Limits` as a public MCP
argument. Do not add a `Services` field or a repository interface for pure text
rendering. Preserve the injectable `identity` used by current tests.

Keep curated text in the installed Python package. Do not read arbitrary paths,
serve the entire `docs/` directory, or expose `.env.mcp` through a generic file
resource. This also makes the guidance independent of the working directory.

Build the policy resource from `Limits` plus reviewed explanatory text. Do not
serialize `Settings`, environment variables, engine objects, or connection URLs.

Use explicit resource URI, name, description, and MIME type. Use explicit prompt
names and docstrings describing arguments. Convert expected Core errors into
`ResourceError` or `PromptError` in the relevant adapter; preserve
`mask_error_details=True` for unexpected failures.

FastMCP already implements the protocol methods. Register components; do not write
custom JSON-RPC handlers or a tenth tool for discovery. See its
[resource decorators](https://gofastmcp.com/servers/resources),
[prompt decorators](https://gofastmcp.com/servers/prompts), and
[request middleware](https://gofastmcp.com/servers/middleware).
Check any API details against the locked installation before using newer examples.

### Style and existing pattern

Follow Python 3.12+, type hints, Ruff's 100-column format, and ASCII-only source and
documentation. Use snake_case names. This is an existing thin adapter to follow:

```python
@mcp.tool(annotations=READ)
async def list_tables() -> dict:
    """List shop tables with planner estimates and comments; data preserves table-list fields."""
    return await services.catalog.list_tables(identity())
```

The new adapters should be similarly small: validate through Core/render content,
then let FastMCP construct protocol results. A string prompt result becomes the
single text message; assert its role and shape in adapter tests.

### Alternatives deferred

| Alternative | Reason for deferring |
|---|---|
| Live table resources such as `shop://tables/{table}` | Require an explicit audit, freshness, error, and result-bound contract; catalog tools already serve this need. |
| Serve generated data dictionary and ERD files directly | Large content, file availability, and staleness need separate handling. Curated packaged guides are smaller. |
| Add `list_tools` or `server_info` as another tool | The protocol already exposes discovery; duplicating the list would introduce drift. |
| Automatically insert every resource into every prompt | The host controls context inclusion; large automatic context would obscure the small workflows. |
| Add mutation or procedure prompts immediately | First establish discovery and read-oriented workflows with the two prompts above. |
| Upgrade FastMCP or migrate elicitation | Unrelated to this feature and could change the verified approval path. |

## 5. Working rules and verification

### Before the first task

Run these from the repository root to inspect the starting state and establish a
database-independent baseline:

```powershell
git status --short
poetry run pytest -m "not integration" -q
poetry run ruff check .
poetry run ruff format --check .
```

`git status` identifies existing work to preserve. The pytest marker expression
excludes database tests even if the shell already has `SHOP_TEST_DATABASE=isolated`.
Ruff checks the current baseline without rewriting unrelated files. Record existing
failures before attributing any failure to this feature. A successful run exits 0;
record the actual test counts instead of copying expected counts from a plan.

If Poetry is not found, check the documented `~/.local/bin` installation. If the
environment needs installing, use `poetry install` and record that setup step in
`docs/setup-guide.md` as required below. Do not update the lockfile just to start
these tasks.

### For each task

1. Read its dependencies and only modify its listed files.
2. Implement the change and the relevant behavioral checks together.
3. Run its verification command and inspect the diff.
4. Record the command and actual result in the task's evidence line, then mark its
   checkbox complete. A skipped required check is not a pass.
5. Optionally commit that task as one focused change; suggested messages are below.
   Do not combine every task into one final implementation commit.

Every task also updates this plan's checkbox/evidence. File counts include that
update and stay at five or fewer. If additional setup/build work would exceed a
task's file budget, record and finish it as a separate small task first.

Whenever setup or a build is actually run, append the next numbered section to
`docs/setup-guide.md` in the same turn. Include goal, reason, rejected alternatives,
exact commands, command explanations, files created, real output, actual failures
and fixes, and concept links. Do not mark a setup/build task done without this
record. The next section number must be checked at implementation time.

### Boundaries

- Always: preserve existing work; use fake services and controlled Auth0 for these
  tests; keep Core independent of frameworks; check ASCII; report real evidence.
- Ask first: destructive volume/reset operations, scale M seeding, mutating SQL,
  live database provisioning, starting the server against port 5433, or committed
  workloads. This plan does not authorize those actions.
- Never: commit secrets, send migration-owner credentials to the server, bypass
  approval through guidance, automatically retry uncertain writes, or silently
  repair P01-P13.

## 6. Ordered task checklist

Implementation baseline (2026-10-03): the Poetry launcher failed with
`Failed to canonicalize script path`. The existing `.venv/Scripts/python.exe`
ran pytest and Ruff without installation or a lockfile change. Use
`.\.venv\Scripts\python.exe -m` in place of `poetry run` for the commands below.
Baseline: 81 passed, 48 deselected in 15.50s; Ruff check passed; 128 files formatted.
Pytest could not write its existing cache (WinError 5); subsequent runs use
`-o cache_dir=.scratch/pytest-cache`. No setup/build step was needed.
The plan's original "ten Limits fields" was corrected to the nine actual fields.

Each task is intended for one focused session. T02-T04 can be developed independently
of the middleware change, but they share a file and are simplest to do sequentially.
T06-T07 are pure rendering work and can start after T02 establishes the package.

| Done | Task | Depends on | Checkpoint |
|---|---|---|---|
| [x] | T01: Make identity middleware shared | Baseline | Existing tools still work. |
| [x] | T02: Write the schema guide renderer | Baseline | First resource content is testable without MCP. |
| [x] | T03: Write the relationships guide renderer | T02 | Join guidance is verified against schema source. |
| [x] | T04: Render runtime SQL policy and limits | T02 | Configured values are accurately described. |
| [x] | T05: Expose the three MCP resources | T01-T04 | Resources can be listed and read. |
| [x] | T06: Render the schema exploration prompt | T02 | Optional table input is validated. |
| [x] | T07: Render the slow-query prompt | T06 | SQL stays bounded analysis input. |
| [x] | T08: Expose the two MCP prompts | T01, T05-T07 | Prompts can be listed and fetched. |
| [x] | T09: Verify authenticated HTTP behavior | T05, T08 | All new methods respect authentication/session rules. |
| [x] | T10: Document discovery and client usage | T09 | A learner can inspect and count each interface. |
| [x] | T11: Run the automated completion checks | T09-T10 | Regressions and architecture checks pass. |
| [x] | T12: Perform and record manual acceptance | T11 | Actual client behavior and limitations are recorded. |

### T01: Make identity middleware shared

**Goal:** register authentication/session protection once, independently of tools.

**Files:** `adapters/mcp/middleware.py` (new), `adapters/mcp/tools.py`,
`bootstrap.py` (all under `src/mcp_server/`), and `tests/test_mcp_http.py`.
Together with this plan: five files.

**Steps:**

1. Move `IdentityMiddleware` into `adapters/mcp/middleware.py`.
2. Install it once in `create_server`, using `identity or current_principal`.
3. Remove middleware installation from `register_tools`; retain tool identity checks.
4. Preserve exception sanitization and session ownership checks. Moving the class
   does not require changing the auth provider or database services.

**Acceptance:** existing discovery still advertises exactly nine tools; both test
identities retain equal access; a swapped session remains rejected; all approval
outcomes in the existing in-process tests remain correct.

**Verify:**

```powershell
poetry run pytest tests/test_mcp_http.py tests/test_mcp_tools.py -q
```

**Suggested commit:** `refactor(mcp): register identity middleware in bootstrap`

**Evidence:** `.\.venv\Scripts\python.exe -m pytest tests/test_mcp_http.py
tests/test_mcp_tools.py -q -o cache_dir=.scratch/pytest-cache`: 13 passed in 2.46s.
Existing discovery/session and all four approval outcomes passed after the move.

### T02: Write the schema guide renderer

**Goal:** create the first pure guidance renderer and its package.

**Files:** `src/mcp_server/core/guidance/__init__.py`,
`src/mcp_server/core/guidance/resources.py`, `tests/test_guidance_resources.py`.
Together with this plan: four files.

**Steps:**

1. Add `render_schema_guide() -> str` with the content specified in section 3.1.
2. Keep the curated text in this module, with revision `guidance-v1`.
3. Add checks for the critical usage instructions, ASCII content, stable rendering,
   and the 16,384-byte resource content budget. Avoid a full-prose snapshot test.

**Acceptance:** a developer can render the guide without settings, Auth0, filesystem
reads, or databases. It points to the correct tools and explains their table-name
conventions without claiming current row counts or full tenant isolation.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_resources.py -q
poetry run pytest tests/test_guarded_core.py -k core_dependency_boundaries -q
```

**Suggested commit:** `feat(mcp): add curated schema guidance`

**Evidence:** Resource tests: 2 passed in 0.08s after adding the relationships slice (the schema check first failed on missing module, then case-sensitive wording). Core dependency boundary: 1 passed, 56 deselected in 0.23s. Commands used the baseline interpreter and cache override; pytest tests/test_guidance_resources.py -q (and the T02 Core boundary command).

### T03: Write the relationships guide renderer

**Goal:** provide concrete, accurate join guidance without querying PostgreSQL.

**Files:** `src/mcp_server/core/guidance/resources.py`,
`tests/test_guidance_resources.py`. Together with this plan: three files.

**Steps:**

1. Add `render_relationships_guide() -> str`.
2. Verify and describe these paths: customers to orders, orders to order_items,
   order_items to products/product_variants, orders to payments, orders to
   shipments, and product_variants to inventory.
3. Include key names, one-to-many direction, and one example of double counting
   when joining multiple child collections. Do not imply foreign keys enforce
   relationships or tenant isolation beyond what the DDL actually declares.
4. Keep the guide curated and short. Do not alter the generated ERD or dictionary.

**Acceptance:** every listed path has been compared to checked-in DDL; the content
identifies itself as shipped guidance and passes the same content budget checks.
Tests cover key semantics, not the full wording.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_resources.py -q
```

Also record the DDL files used for the manual relationship check in the evidence.

**Suggested commit:** `feat(mcp): add relationship guidance`

**Evidence:** Resource tests: 2 passed in 0.08s. Join keys and constraints manually compared with db/schema/020_core.sql, 030_orders.sql and 040_append_partitioned.sql; the last file owns inventory. No generated docs changed. Commands used the baseline interpreter and cache override; pytest tests/test_guidance_resources.py -q (and the T02 Core boundary command).

### T04: Render runtime SQL policy and limits

**Goal:** describe effective limits without duplicating default configuration.

**Files:** `src/mcp_server/core/guidance/resources.py`,
`tests/test_guidance_resources.py`. Together with this plan: three files.

**Steps:**

1. Add `render_sql_policy(limits: Limits) -> str`.
2. Include all nine `Limits` fields with units and meaning: request bytes, result
   rows, result bytes, read/write/procedure seconds, affected rows, approval
   seconds, and planner cost.
3. Explain that ordinary DML row caps exclude trigger effects and that registered
   procedures have their own reviewed bounds and transaction modes.
4. Match restrictions to `core/sql_access/policy.py` and the current runbook.
5. Test with nondefault `Limits`, including small configured budgets. Describe
   these SQL budgets without applying them to the documentation text itself.

**Acceptance:** changing configured limits changes the rendered values; no
`Settings` serialization is introduced; costs are labeled estimates; mutation
approval and uncertain-outcome guidance match existing behavior.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_resources.py -q
```

**Suggested commit:** `feat(mcp): describe effective SQL policy and limits`

**Evidence:** Resource tests: 3 passed in 0.32s with nondefault limits. Restrictions compared to the Core policy, SQL parser and runbook. All nine actual Limits fields are rendered. Commands used the baseline interpreter and cache override; pytest tests/test_guidance_resources.py -q (and the T02 Core boundary command).

### T05: Expose the three MCP resources

**Goal:** make the three resource renderers discoverable and readable through MCP.

**Files:** `src/mcp_server/adapters/mcp/resources.py`,
`src/mcp_server/bootstrap.py`, `tests/test_mcp_resources.py`.
Together with this plan: four files.

**Steps:**

1. Add `register_resources(mcp, limits)` with explicit metadata for the three URIs.
2. Register it in `create_server` after shared middleware is installed.
3. Test using `fastmcp.Client(server, mode="legacy")`, `server_settings()`, an
   injected test identity, and a service object with only `close()`.
4. Use the client's resource list/read/template-list methods. The minimal service
   object should make accidental database-service access fail the test.
5. Test an unknown URI and `file:///...` input: neither resolves to arbitrary
   content. Check responses for sentinel test credentials.
6. Construct two servers with different limits and verify each policy resource
   reflects its own settings. Also read resources from a temporary working
   directory to catch runtime dependence on repository documentation files.

**Acceptance:** exactly three resources, explicit Markdown MIME type, no resource
templates, nine tools, safe unknown-resource errors, and no database or file reads
caused by resource handlers. The pure renderers remain framework independent.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_resources.py tests/test_mcp_resources.py tests/test_mcp_http.py -q
```

**Suggested commit:** `feat(mcp): expose authenticated documentation resources`

**Evidence:** Resource discovery/read passed with a close-only service, sentinel secrets, different per-instance limits, no templates, arbitrary URI rejection and a temporary working directory. The first run could not use the host pytest temp root (WinError 5); PYTEST_DEBUG_TEMPROOT=F:\repo\python-mcp-server\.scratch resolved it. The SDK exposes MCPError (not McpError); tests use FastMCP's compatibility alias. Final command: pytest tests/test_guidance_resources.py tests/test_mcp_resources.py tests/test_mcp_http.py -q (baseline overrides): 17 passed in 2.11s.

### T06: Render the schema exploration prompt

**Goal:** implement a pure, validated workflow for exploring the schema.

**Files:** `src/mcp_server/core/guidance/prompts.py`,
`tests/test_guidance_prompts.py`. Together with this plan: three files.

**Steps:**

1. Add `render_explore_schema(table: str, limits: Limits) -> str`.
2. Add shared private helpers for the prompt argument-byte and output-byte limits
   specified in section 3.2. Use `GuardError` for expected failures.
3. Implement the empty-table and named-table workflows. Reference the guide URIs
   and give a tool-based fallback when the host cannot load resources.
4. Test empty input, `orders`, a maximum-length valid name, qualified names,
   whitespace-only input, invalid punctuation, and overlong names.

**Acceptance:** the result is an instruction message, never a tool result;
malformed names are rejected; valid names are not falsely claimed to exist; both
workflows follow the existing catalog tools and avoid automatic mutations.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_prompts.py -q
```

**Suggested commit:** `feat(mcp): add schema exploration prompt renderer`

**Evidence:** pytest tests/test_guidance_prompts.py -q: 13 passed in 0.09s. Empty/named/max-length workflow, invalid names and exact 18-byte argument envelope tested. Commands used the baseline interpreter/cache overrides.

### T07: Render the slow-query prompt

**Goal:** guide plan investigation while preserving supplied SQL as bounded data.

**Files:** `src/mcp_server/core/guidance/prompts.py`,
`tests/test_guidance_prompts.py`. Together with this plan: three files.

**Steps:**

1. Add `render_investigate_slow_query(sql: str, limits: Limits) -> str`.
2. Reuse T06's validation helpers and JSON-encode the supplied SQL as a data section.
3. Implement the workflow in section 3.2, including the distinction between
   non-ANALYZE plan estimates and measured latency.
4. Test a normal SELECT, blank input, exact byte boundary and one byte over, SQL
   with non-ASCII characters expressed using escapes in test source, and comments
   containing misleading instructions or Markdown delimiters.
5. Test that decoding the embedded data reproduces the original accepted SQL.
   Rendering unapproved SQL must not claim it is executable or call any parser,
   database adapter, tool, or approval mechanism.

**Acceptance:** all payload budgets use bytes; instructions remain present around
adversarial input; errors exclude the submitted SQL; the workflow never proposes
automatic application of a fix or claims that a plan measured execution time.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_prompts.py -q
poetry run pytest tests/test_guarded_core.py -k core_dependency_boundaries -q
```

**Suggested commit:** `feat(mcp): add slow-query investigation prompt renderer`

**Evidence:** pytest tests/test_guidance_prompts.py -q: 21 passed in 0.14s. Tests cover exact/over byte limits, Unicode JSON escapes, hostile comments/delimiters and unapproved SQL preserved as data. The first renderer addition misplaced the schema return block; regression tests caught it and it was moved back. Core dependency boundary: 1 passed, 56 deselected in 0.24s. Commands used the baseline interpreter/cache overrides.

### T08: Expose the two MCP prompts

**Goal:** register both workflows with accurate argument metadata and error mapping.

**Files:** `src/mcp_server/adapters/mcp/prompts.py`,
`src/mcp_server/bootstrap.py`, `tests/test_mcp_prompts.py`.
Together with this plan: four files.

**Steps:**

1. Add `register_prompts(mcp, limits)` and register it in `create_server`.
2. Expose only optional `table` and required `sql`; inject limits through closures.
3. Map expected Core failures to sanitized `PromptError` messages. Leave unexpected
   failures masked by the existing server configuration.
4. Test list/get with an in-process legacy client and the same minimal fake-service
   approach as T05. Check names, descriptions, required flags, role, and text.
5. Test missing required SQL, invalid table input, oversized SQL, and unknown
   prompt names. Attach an elicitation handler that fails if called.
6. Extend server instructions briefly to mention available guidance while retaining
   the existing mutation-approval and uncertain-outcome instructions.

**Acceptance:** two prompts render through MCP; retrieval makes no tool call,
database request, audit write, or elicitation request. Tool and resource counts
remain nine and three. The host receives user-role text, not an execution result.

**Verify:**

```powershell
poetry run pytest tests/test_guidance_prompts.py tests/test_mcp_prompts.py tests/test_mcp_resources.py -q
```

**Suggested commit:** `feat(mcp): expose schema and query investigation prompts`

**Evidence:** pytest tests/test_guidance_prompts.py tests/test_mcp_prompts.py tests/test_mcp_resources.py -q: 30 passed in 1.63s. Required/optional arguments, user-role text, error sanitization, instance limits and no elicitation verified. FastMCP masks missing required arguments before rendering; a prompt-only argument middleware now reports missing SQL and rejects unsupported/nontext arguments safely. Unexpected errors remain masked. Commands used the baseline interpreter/cache overrides.

### T09: Verify authenticated HTTP behavior

**Goal:** prove the new interfaces use the existing real HTTP authentication path.

**Files:** `tests/test_mcp_http.py`. Together with this plan: two files.

**Steps:**

1. Extend the existing controlled Auth0/JWKS tests and `NoDatabaseServices` fixture.
2. Include successful requests for `resources/list`, `resources/templates/list`,
   `resources/read`, `prompts/list`, and `prompts/get`.
3. Check the legacy initialization response advertises resources/prompts and that
   each method returns the expected protocol result shape. Do not hardcode
   optional framework capability flags unrelated to this feature.
4. Parameterize invalid-authentication coverage across the new methods, including
   read/get rather than just discovery. Cover valid initialization followed by an
   expired/invalid token on a subsequent request.
5. Apply a second identity to the first identity's session for read/get and verify
   rejection. Assert no resource or prompt content is returned on failures.
6. Retain equal-access, host/origin, nine-tool, and inert-import regression checks.

**Acceptance:** HTTP tests pass with controlled keys and no PostgreSQL or external
Auth0 calls. Valid callers receive guidance; invalid callers cannot retrieve it.
The test does not rely solely on identity injection from in-process tests.

**Verify:**

```powershell
poetry run pytest tests/test_mcp_http.py tests/test_mcp_tools.py -q
```

**Suggested commit:** `test(mcp): cover authenticated resource and prompt requests`

**Evidence:** pytest tests/test_mcp_http.py tests/test_mcp_tools.py -q with baseline interpreter/cache overrides: 69 passed in 7.72s. All seven tool/guidance request variants reject eight invalid token cases both with and without a previously valid session; six guidance variants reject swapped identities. Two valid identities receive the same 3-resource/2-prompt inventory and legacy protocol result shapes. No real Auth0 or database used.

### T10: Document discovery and client usage

**Goal:** make the new interfaces and tool counting understandable to a learner.

**Files:** `docs/mcp-discovery.md`, `docs/guarded-server.md`, `docs/roadmap.md`.
Together with this plan: four files.

**Steps:**

1. Write a short guide explaining host, MCP client, model, and server responsibilities.
2. Show the handshake used by this repo, `tools/list`, `tools/call`, and the separate
   resource/prompt list and retrieval methods. Include a small Mermaid sequence.
3. Explain counting all pages using `nextCursor`, not assuming the first page is
   complete or that initialization returns a count. Distinguish the server's
   advertised tools from the subset a host may expose to its model.
4. Include a complete async FastMCP example using an already authenticated client
   to list/read resources and list/get prompts. Keep credentials out of examples.
   Use the locked SDK's actual return shapes, verified in T05/T08.
5. Document the nine/three/two inventories, argument examples, limits, curated
   content freshness, and the metadata-only audit boundary from section 3.3.
6. Link the guide from the runbook and update roadmap implementation status.
   Keep manual acceptance marked pending until T12 records it.

**Acceptance:** a reader can tell discovery from execution, count each interface,
and understand that prompt retrieval and resource listing do not automatically
execute tools or load content into the LLM.

Protocol references:
[tool listing/calling](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
and [legacy initialization](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

**Verify:** check local links and compare examples to adapter tests; run
`git diff --check`. Do not claim a real client walkthrough based on reading docs.

**Suggested commit:** `docs(mcp): explain discovery resources and prompts`

**Evidence:** The documented async SDK helper was executed against a legacy in-process client: {tools: 9, resources: 3, prompts: 2}. Local documentation links, ASCII and git diff --check passed. Primary 2025-11-25 MCP tools/resources/prompts/lifecycle references were reviewed. Manual acceptance remains separate.

### T11: Run the automated completion checks

**Goal:** verify the complete feature and current guard behavior together.

**Files:** this plan. If a regression needs changes, reopen the relevant small task
and fix it there before recording T11 as complete.

**Run:**

```powershell
poetry run pytest -m "not integration" -q
poetry run ruff check .
poetry run ruff format --check .
git diff --check
rg -n '[^\x00-\x7F]' src/mcp_server/core/guidance src/mcp_server/adapters/mcp docs/mcp-resources-prompts-plan.md docs/mcp-discovery.md tests/test_guidance_resources.py tests/test_guidance_prompts.py tests/test_mcp_resources.py tests/test_mcp_prompts.py
```

The final command should find no non-ASCII characters; `rg` exits 1 for no matches.
Review any pre-existing matches separately. Also inspect newly added lines in the
modified bootstrap, HTTP tests, runbook, and roadmap for ASCII compliance.

**Acceptance:** the default non-database suite, including approval, policy, and Core
dependency tests, passes; Ruff and diff checks pass; new guidance has the expected
inventory and no accidental runtime dependencies. Record real counts and any
warnings. Do not rerun seeding or mutating database integration tests merely to
verify a metadata-only feature.

If a fix changes database behavior, reconsider the scope and use the isolated test
workflow with the required authorization; do not treat this task as permission to
run mutation acceptance.

**Suggested commit:** include the verification record with the latest related
documentation commit, or `docs(mcp): record guidance verification`.

**Evidence:** Full command: .\.venv\Scripts\python.exe -m pytest -m "not integration" -q -o cache_dir=.scratch/pytest-cache with PYTEST_DEBUG_TEMPROOT=F:\repo\python-mcp-server\.scratch: 170 passed, 48 deselected in 45.82s, no warnings. Ruff check passed; 139 files already formatted. git diff --check passed; the specified ASCII rg returned no matches (exit 1). Three new files initially needed Ruff formatting and were formatted before the final checks. No database integration/mutation tests or seeding were run.

### T12: Perform and record manual acceptance

**Goal:** confirm how the user's actual client presents and uses the new interfaces.

**Files:** `docs/setup-guide.md`, `docs/roadmap.md`, `docs/guarded-server.md`,
`docs/mcp-discovery.md`. Together with this plan: five files.

**Preconditions:** use the existing Auth0/Inspector configuration and the isolated
server configuration on database port 55439. Check the existing server process
before starting another copy. Reuse the setup guide's working Inspector connection
and any required hook; do not assume a plain new Inspector process is equivalent.

If starting the server is needed, first inspect only the nonsecret database-port
setting and clear any migration-owner environment variable from that shell:

```powershell
Select-String -Path .env.mcp -Pattern '^SHOPMCP_POSTGRES_PORT='
Remove-Item Env:SHOPMCP_MIGRATION_URL -ErrorAction SilentlyContinue
# Continue only after confirming the configuration targets port 55439.
poetry run shopmcp serve
```

An absent port setting falls back to 5433; do not proceed in that case. Use the
existing isolated configuration or stop to resolve it. Starting or restarting
this server must be documented as an actual setup action with real output.

**Walkthrough:**

1. Authenticate in Inspector and inspect the nine tools, three resources, and two
   prompts. Record client version and negotiated protocol where available.
2. Read each resource; inspect the content, MIME type, and effective SQL limits.
3. Get `explore_schema` without arguments and with `table="orders"`.
4. Get `investigate_slow_query` with
   `SELECT product_id, name FROM shop.products LIMIT 3`.
5. Try a missing SQL argument and an invalid table name. Confirm useful errors.
6. Confirm fetching prompts returns instructions without running SQL or displaying
   a mutation approval. These metadata operations require no database mutations.
7. If the intended LLM host supports these features, select a prompt and explicitly
   attach/read a resource. Record whether the model received the content. This
   optional check is distinct from Inspector's protocol verification.
8. Record unsupported UI features or unavailable real authentication honestly.
   Leave unperformed acceptance pending; keep automated results recorded separately.

**Acceptance:** the setup-guide section records goals, alternatives, commands or
UI actions, actual output, files created, real failures/fixes, and primary links.
The roadmap distinguishes protocol success from host UI/model behavior. Nothing
in this walkthrough applies a mutation, schema change, or planted-problem fix.

**Suggested commit:** `docs(mcp): record resources and prompts acceptance`

**Evidence:** Setup-guide Step 18 records the verified isolated runtime restart,
actual commands, output and limitations. Original server PID 19016 was confirmed
as this repository's `mcp_server.cli serve`, with PostgreSQL connections on 55439;
it was restarted to load guidance (launcher PID 15460, server PID 77020).
Protected-resource discovery and existing Inspector returned HTTP 200; an
unauthenticated resources/list returned 401. No SQL tools were called.
Computer-use returned `apps: [], browsers: []`; opening Inspector returned
`Browser is not available: iab`. The user was asked asynchronously for a connected
browser or manual results. The user subsequently confirmed: "I checked, it worked".
T12 is complete on that user-reported manual acceptance. Per-method responses,
screenshots and a negotiated client protocol were not supplied; the assistant does
not claim independent observation of those UI checks. Detailed inventory, content,
argument and authentication behavior remains supported by the automated checks.
Optional LLM-host context inclusion is unverified and is not required for completion.

## 7. Risks and how the plan addresses them

| Risk | Mitigation and verification |
|---|---|
| Guides drift from schema or policy | Mark curated content; verify joins against DDL; derive numeric limits from `Limits`; use live tools for current facts. |
| Resource or prompt path misses identity checks | Shared middleware plus T09 authenticated HTTP read/get tests. |
| New code exposes secrets | Pass only `Limits`; package curated text; test with sentinel credentials; never serialize runtime settings. |
| Prompt retrieval performs work unexpectedly | Pure renderers and minimal service doubles; fail if elicitation or service access occurs. |
| SQL comments try to override instructions | Encode input as data, keep fixed guidance separate, and retain actual enforcement in tools; do not claim textual isolation guarantees safety. |
| Large input fills model context | Explicit serialized argument-byte and rendered output-byte budgets, with boundary tests. |
| Host supports tools but hides prompts/resources | Keep current tools usable and record actual client support in T12. |
| Framework examples use a newer protocol | Keep the lockfile and legacy mode; use public APIs verified by tests against the installed version. |

## 8. Later work, outside these twelve tasks

Consider these only after completing and using the first version:

- Live catalog resources or table templates routed through audited Core services.
- A procedure preparation prompt using `list_procedures` and the existing guarded
  `call_procedure` workflow.
- A mutation preparation prompt that still requires approval at execution time.
- Resource subscriptions when there is a real source of change notifications.
- Modern-protocol elicitation migration as a separately verified compatibility task.

None is required to discover or count the existing tools.
