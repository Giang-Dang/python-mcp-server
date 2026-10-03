# Guarded SQL implementation status

The feature-first release is implemented. The source of the agreed plan remains
the conversation; this file records the resulting architecture and verification
status. Operational setup is in [guarded-server.md](guarded-server.md).

## 1. Delivered interfaces

The authenticated Streamable HTTP endpoint is `http://127.0.0.1:8000/mcp`.
Tools: `ping`, `list_tables`, `describe_table`, `query`, `execute`,
`explain`, `list_procedures`, `call_procedure`, and `diagnostics`.

All verified callers have the same access. Identity is used for sessions,
approvals, and auditing. The configured tenant is initially 1; the fixture still
exposes cross-tenant data through some tables, views, and owner procedures.
There is no user-to-tenant membership model or tenant-isolation guarantee.

## 2. Package boundaries

Both `shopdb` and `mcp_server` own their Core, adapters, configuration, and
composition root. Neither package imports the other.

| Package | Core features | Adapters |
| --- | --- | --- |
| shopdb | dataset, seeding, verification, maintenance, documentation | generation, multiprocessing, postgres, filesystem |
| mcp_server | access_control, catalog, sql_access, procedures, diagnostics, auditing | mcp, identity, postgres, sql_parser, registry |

Core imports no FastMCP, SQLAlchemy, psycopg, Faker, YAML, or Pydantic types.
Feature ports describe only the dependencies required by their workflows.
The original shopdb commands/options and compatibility imports remain available.
Worker initializers receive the parent's selected Settings object explicitly.

## 3. Policy and approvals

SQLGlot's PostgreSQL parser supplies analysis facts. Core enforces positive
allowlists of statements, expressions, functions, and schema references. Unknown
syntax is rejected. UPDATE/DELETE need WHERE, all ordinary DML has an affected-row
cap, and modifying CTEs/RETURNING/raw CALL/locking reads/utility commands are refused.

Each read and ordinary mutation receives a non-ANALYZE plan estimate. Preview work
is closed before elicitation. Approval binds identity, operation ID, exact inputs,
limits, and procedure registry fingerprint. Expired or unavailable approval refuses
execution. The token and procedure definition are rechecked afterward.

## 4. Data access and lifecycle

Async SQLAlchemy Core with psycopg owns role-specific pools. Catalog, settings,
diagnostics, and definition lookups are Core expressions. Validated SQL uses
`exec_driver_sql`; reviewed CALL uses a Core utility construct with typed bound
parameters. Server-side cursors stop at result row/byte limits.

Transactional settings are local and rolled back on connection return. Archive
uses a dedicated NullPool autocommit connection, closed after the call.
The explicit Windows runtime selects a psycopg-compatible Selector event loop.
Imports create no engines and contact neither PostgreSQL nor Auth0.

## 5. Registry and audit

Ten ordinary procedures are registered in reviewed YAML; adversarial routines and
refcursors are excluded. Hashes cover PostgreSQL 17's full `pg_get_functiondef`
output with LF endings. Inspection never edits the registry. Registry changes
require review and restart.

The separate `mcp_audit` database uses versioned owner migrations and an insert-only
runtime role. Requests and events exclude tokens, infrastructure credentials, and
result sets. Missing audit intent stops database tools while authenticated ping
remains available. Commit intent precedes shop commit. A confirmed commit with a
failed final audit event is distinguished from a lost commit acknowledgement.

No uncertain operation is retried or resumed automatically. Archive failures
report possible partial completion, with no invented per-batch progress count.

## 6. Verification and remaining acceptance

Completed against a separate PostgreSQL 17 instance on port 55439:

- Original generation snapshot equality and CLI compatibility.
- Full S seed: 4,630,316 rows, all fresh integrity checks, and P01-P13.
- SQL policy, row/byte/time/cost limits, approval binding, and registry bounds.
- Auth0 provider tests with controlled OIDC metadata and signing keys: invalid
  signatures, expiry, issuer/audience, missing identity, discovery, session binding,
  equal access, and localhost protections.
- Transaction rollback, audit outages, lost commit acknowledgement, procedure
  drift, INOUT handling, internal commits, cancellation, and connection cleanup.
- A real loopback HTTP MCP client exercising discovery, reads, rejected unsafe SQL,
  declined/approved mutation, batch execution, and persisted audit records.

Pending: provision the user's Auth0 tenant, API, developer account, and static
Inspector client; perform the real browser login/consent walkthrough. The user
confirmed Auth0 is not configured yet. Automated provider tests do not substitute
for that final external integration check.

The initial release does not include an audit UI, background jobs, arbitrary
routine execution, unreviewed SQL extensions, or automatic recovery of incomplete
operations. These remain outside the agreed scope.
