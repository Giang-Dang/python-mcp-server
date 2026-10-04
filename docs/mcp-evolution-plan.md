# MCP evolution implementation

## Objective and approved defaults

Implement discovery pagination and `shop://tables/{table}` first, then modern
MRTR approval, typed explain/diagnostics, a query-plan MCP App, completion and
one official Skills extension. Tasks remain disabled until a real long job
requires durable execution. The user approved this sequence on 2026-10-04.

Keep nine tools and the existing list_tables result. Discovery page size is 5
(configurable 1..100). Modern protocol is 2026-07-28 only. SQLAlchemy Core owns
fixed queries; Core imports no framework types. Source and docs use ASCII.

## Ordered tasks and acceptance

Each implementation chunk changes at most five files, including its tests/docs.

- [x] Catalog: shared bounded table-resource read with audited URI and operation id.
- [x] Discovery: native pagination, one table template, no DB work on discovery.
- [x] Verify initial milestone before changing protocol.
- [x] Audit: separate intent, waiting, and terminal completion for MRTR.
- [x] Mutation services: prepare and resume exact approved requests.
- [x] MRTR store: 128 operations / 16 MiB, caller/content/expiry binding, atomic
  single execution, cached replay, restart invalidation, no unsafe retries.
- [x] Modern transport: per-request identity, explicit legacy rejection,
  stateless HTTP and Inspector modern configuration.
- [x] DTOs: typed audit envelopes and explain; discriminated four diagnostics.
- [x] App: bundled HTML, tree selection, estimates, safe DOM, keyboard and fallback.
- [x] Completion: audited table-prefix lookup, 100 results and hasMore.
- [x] Skill: packaged SKILL.md and checklist; official skills/list and skills/get,
  opt-in, immutable manifest/digests, no arbitrary directory reads.
- [x] Verification/docs: default tests, Ruff, frontend tests/build, wheel assets;
  record manual/isolated checks as pending unless actually performed.

## Public contracts

Table resource JSON: schema, table, columns(name, type, not_null, comment).
Its metadata includes operation_id; failures become sanitized resource errors.
MRTR uses approval -> elicitation/create form with boolean approve. Only
accept + true executes. State is protected by SDK request-state security;
the application stores the immutable preview behind an opaque handle. TTL is
the minimum of original token expiry and approval_seconds, never renewed.
Waiting never holds a DB connection. Restart invalidates pending handles.

Explain keeps plan, total_cost_estimate, rows_estimate and estimates_only.
Diagnostics adds data.kind, preserves positional rows and truncation fields.
The viewer uses ui://shop/query-plan-viewer.html on explain, never executes SQL.
Skills use authenticated per-request extension opt-in and fixed file resources.

## Commands and verification

Run `poetry run pytest -q`, `poetry run ruff check .`, and
`poetry run ruff format --check .`. Use the existing .venv interpreter when the
Poetry launcher fails. Frontend: npm ci, npm test, npm run build; package:
poetry build. Tests cover pagination, URI validation and bounds, MRTR tamper,
caller/expiry/replay/concurrent resumes, failure outcomes, typed outputs, UI
safe rendering, completion and skill manifest integrity.

Isolated DB acceptance uses port 55439 and SHOP_TEST_DATABASE=isolated only.
No real DB mutations, volume reset, M seed, planted-problem fixes or secret commits.
Every setup/build invocation gets a numbered docs/setup-guide.md entry with
purpose, exact commands, actual outputs, failures/fixes and concept links.

## Deferred Tasks

Keep tasks=False. A later concrete job must specify durable ownership, input
fingerprint, idempotency, result storage separate from audit, restart/reconnect,
TTL/cleanup and cooperative cancellation. Report actual partial commits and
uncertain acknowledgements; never invent progress or automatically retry.

## References

- https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr
- https://gofastmcp.com/servers/pagination
- https://modelcontextprotocol.io/extensions/apps/overview
- https://skills.extensions.modelcontextprotocol.io/specification/stable/skills


## Implementation evidence

The initial pagination/table milestone passed 6 tests before protocol changes.
Modern wire/auth/schema tests and direct MRTR failure tests passed. The frontend
has four DOM acceptance tests and a reproducible locked build; wheel/sdist asset
checks cover the viewer and both skill files. Default and isolated results are
recorded in setup-guide Steps 19-20.

No audit schema migration or privilege change was needed: awaiting_approval is
an additional event kind in the existing append-only event table. The store's
16 MiB budget counts serialized inputs/previews/results and reserves in-flight
previews. Waiting entries are swept every five seconds and cancelled on shutdown.
The SDK's omitted cache hint configuration emits ttlMs=0/cacheScope=private;
passing cache_ttl=0 directly is invalid in the locked FastMCP API.

Manual modern Inspector rendering and host skill activation are pending: the
available computer-use inventory has no browsers. Deployment/restart of an
existing runtime was not part of these acceptance tests. Use a modern client when
starting this version; legacy initialization is explicitly rejected. Tasks are
intentionally deferred, not an unfinished implementation task.
