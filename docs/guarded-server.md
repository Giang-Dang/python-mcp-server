# Authenticated guarded SQL server

`shopmcp serve` runs at `http://127.0.0.1:8000/mcp`. It requires Auth0
configuration and runtime database passwords. It replaced the earlier unauthenticated
stdio stub (history: setup guide Steps 8 and 10). Imports do not start the server.

## Configure Auth0 and Inspector

Real Auth0 login and authenticated read-only checks succeeded on 2026-10-03.
See [the local walkthrough](setup-guide.md#step-16-connect-auth0-and-mcp-inspector-2026-10-03)
for the working configuration and Inspector troubleshooting. The real Inspector
mutation-approval, rejection, decline and batch walkthrough was completed on the
test instance on 2026-10-03: see [Step 17](setup-guide.md#step-17-inspector-mutation-rejection-and-batch-acceptance-2026-10-03).

1. Create an Auth0 API with identifier `http://127.0.0.1:8000/mcp` and RS256
   signing. Keep the server URL and audience identical.
2. In tenant Settings > Advanced, enable Resource Parameter Compatibility Profile
   and Include Issuer in Authorization Responses. The resource parameter selects
   the API audience.
3. Statically register an MCP Inspector application for Authorization Code with
   PKCE. Auth0's current guide uses a Regular Web Application,
   `client_secret_post`, and callback `http://localhost:6274/oauth/callback`.
   Keep its client ID and secret in Inspector's local configuration.
4. Provision your developer account and disable open signup on its database
   connection. Do not enable open dynamic client registration.
5. No tool-specific scopes, roles, or permission tiers are required by this server.
   Tokens must have a valid signature, issuer, audience, expiry, and nonempty subject.
6. Authorize Inspector to request user-delegated tokens for this API. In
   Applications > APIs > Shop MCP Server > Settings > Application Access Policy,
   use Per-app authorization for User-Delegated Access. Then open Application
   Access, edit MCP Inspector, and authorize its User Access. This is distinct
   from machine-to-machine Client Access. A missing user grant can produce
   `Client ... is not authorized to access resource server ...` before login.
   No custom API permission scopes are required for this server.

Primary references:
[Auth0 resource compatibility](https://auth0.com/ai/docs/mcp/guides/resource-param-compatibility-profile),
[Auth0 Inspector registration](https://auth0.com/ai/docs/mcp/guides/test-your-mcp-server-with-mcp-inspector),
[Auth0 API access policies](https://auth0.com/blog/developers-guide-api-access-policies-auth0/).

## Provision monitoring and audit storage

Run once on the intended instance after reviewing the target. The existing shop
schema, data, grants, and planted problems are preserved. The script creates
three new roles and one separate database; it does not reset a volume.

Set `MCP_MONITOR_PASSWORD`, `MCP_AUDIT_OWNER_PASSWORD`, and `MCP_AUDIT_PASSWORD`
in the provisioning shell using your secret manager or masked prompt. For example,
PowerShell 7 supports `$env:MCP_MONITOR_PASSWORD = Read-Host -MaskInput`.
Do not put these values in chat or commit them.

For the ordinary local Compose instance, pass these variables to psql:

```powershell
Get-Content db/mcp/000_roles.sql -Raw | docker compose exec -T -e MCP_MONITOR_PASSWORD -e MCP_AUDIT_OWNER_PASSWORD -e MCP_AUDIT_PASSWORD db psql -U postgres -d shop -v ON_ERROR_STOP=1 -f -
```

For the isolated test instance the same step is:

```powershell
docker compose -f tests/compose.yml exec -T db psql -U postgres -d shop -v ON_ERROR_STOP=1 -f /db/mcp/000_roles.sql
```

Existing roles/databases cause an error. Inspect what exists instead of dropping
or automatically replacing it.

Set `SHOPMCP_MIGRATION_URL` to a SQLAlchemy psycopg URL for
`mcp_audit_owner` connecting to `mcp_audit`. For the disposable test instance:

```powershell
$env:SHOPMCP_MIGRATION_URL='postgresql+psycopg://mcp_audit_owner:test_audit_owner@127.0.0.1:55439/mcp_audit'
poetry run shopmcp audit status
poetry run shopmcp audit migrate
Remove-Item Env:SHOPMCP_MIGRATION_URL
```

The CLI applies pending files from `db/audit/migrations`, checks stored checksums,
and takes an advisory migration lock. It does not rewrite an applied migration.
There is no automatic downgrade. Serving refuses to start while the migration URL
is present in its environment; remove owner credentials from the runtime shell.

## Configure and start the runtime

```powershell
Copy-Item .env.mcp.example .env.mcp
# Edit .env.mcp locally, preserving any existing file.
poetry install
poetry run shopmcp serve
```

Use your Auth0 domain without a URL scheme. Runtime settings contain only reader,
writer, procedure, monitor, and audit-runtime passwords. Use port 55439 for the
test instance and its test passwords. Default port 5433 targets the existing local
shop database, so set the test port before interactive mutation acceptance.

`.env.mcp` is ignored by Git. The server does not read `.env` or shopdb settings.
The configured shop context is tenant 1. It is not a tenant-isolation guarantee:
some fixture tables/views expose multiple tenants and some registered procedures
explicitly maintain ALL tenants.

The server publishes OAuth protected-resource metadata without a token. Tool
discovery and calls require a token. Localhost Host/Origin protection stays enabled;
Inspector origins on localhost/127.0.0.1 port 6274 are explicitly trusted.

## Tools and results

| Tool | Input | Result |
| --- | --- | --- |
| ping | none | `pong`; works without either database |
| list_tables | none | Table array with `table`, `partitioned`, `approx_rows`, `comment` |
| describe_table | unqualified table name | Ordered column metadata in the shop schema |
| query | one permitted read statement | Ordered columns and row arrays |
| execute | one INSERT/UPDATE/DELETE | Approval followed by atomic bounded DML |
| explain | permitted read SQL | Non-ANALYZE JSON plan with labeled estimates |
| list_procedures | none | Reviewed signatures, arguments, effects, and limits |
| call_procedure | name, argument object | Approved registered procedure call |
| diagnostics | query_statistics / locks / table_sizes / table_health | Fixed report through monitoring role |

Every database-tool response wraps its payload in `data` and includes
`operation_id`, `outcome`, and `audit_status`. This preserves the table-list
item fields while adding the required operation envelope. Query payloads contain
`columns`, `rows`, `returned_rows`, `truncated`, `truncation_reason`, and
`result_bytes`. The byte budget measures serialized columns and row arrays;
the small operation/metadata envelope is additional. Decimal values are strings
and dates/timestamps use ISO text.

Mutations report `committed`, `declined`, `cancelled`, `rolled_back`,
`partially_completed`, or `uncertain`. A rejected request reports `rejected`.
For batches, `partially_completed` means earlier batches **may** have committed;
inspect state before deciding what to do. Cancellation can close the client
request before it receives a response; the audit trail remains the inspection path.

Error categories are `authentication`, `policy_rejection`, `invalid_arguments`,
`limits`, `registry_mismatch`, `audit_unavailability`, `database_failure`,
and `uncertain_completion`. HTTP authentication failures use HTTP 401.
Driver errors and credentials are withheld from tool responses.

## Resources, prompts and discovery

Three packaged Markdown resources and two read-oriented prompts share the tools'
identity/session protection. See [MCP discovery and client usage](mcp-discovery.md)
for inventories, argument limits, SDK examples and how the host connects an LLM.
Documentation reads and prompt renders start no database operation and create no
audit rows. Database tools retain mandatory intent/outcome auditing. Retrieving a
prompt does not execute SQL or approve mutations.

Automated guidance acceptance is in the [implementation plan](mcp-resources-prompts-plan.md).
The user confirmed manual acceptance of the new interfaces: "I checked, it worked".
This result is user-reported; per-method UI responses were not captured. Optional
LLM-host context inclusion remains unverified.
The isolated runtime was restarted with guidance installed; protected-resource
discovery returned 200 and unauthenticated resource discovery returned 401.
No browser surface was available to the assistant; the user completed the check. See
[setup-guide Step 18](setup-guide.md#step-18-load-resources-and-prompts-client-acceptance-preflight-2026-10-03).

## Limits and approval

| Limit | Default |
| --- | ---: |
| SQL/request arguments | 64 KiB |
| Returned rows | 1,000 |
| Columns and row JSON | 1 MiB |
| Read timeout | 15 seconds |
| Ordinary write timeout | 30 seconds |
| Procedure timeout | 60 seconds |
| Direct DML affected rows | 1,000 |
| Approval lifetime | 5 minutes, bounded by token expiry |
| Plan total-cost ceiling | 1,000,000 estimated planner cost units |

Runtime `SHOPMCP_*` settings can adjust these within Settings' validated bounds.
Reads use server-side cursors and a whole-read deadline. Writes/procedures use
PostgreSQL statement timeouts with a client deadline allowing five seconds for
transaction/audit cleanup. Planner costs are estimates, never runtime guarantees.

SQL must name shop tables explicitly. Only reviewed built-ins and expression forms
are accepted; arbitrary user-defined functions, modifying CTEs, SELECT INTO,
locking reads, DDL, session commands, raw CALL, and DML RETURNING are rejected.
Approval cannot override rejection.

The preview closes its database connection before asking the human. It shows exact
SQL/arguments, effects, estimates, limits, registry fingerprint, and transaction mode.
Approval is bound to the operation and caller. Unsupported elicitation, decline,
cancellation, changed inputs, expired approval, or expired identity stops execution.
The installed FastMCP imperative elicitation path requires a handshake-era MCP
client; automated clients use `mode="legacy"`. A client negotiating a modern
protocol without that back-channel receives a refusal, never silent execution.

The direct DML cap excludes trigger effects. Rollback undoes transactional effects
but does not restore consumed sequences:
[PostgreSQL sequence semantics](https://www.postgresql.org/docs/17/functions-sequence.html).

## Reviewed procedures

`config/procedures.yaml` contains the ten ordinary procedures from
`db/post_load/130_procedures.sql`. Each entry has a full signature, definition
hash, typed/defaulted/bounded parameters, effects, timeout, role, and transaction mode.
INOUT bookkeeping is controlled by the server. Adversarial routines and refcursor
procedures are not registered.

`archive_old_orders` uses `mcp_writer` on a dedicated autocommit connection;
each call is capped at 5,000 rows per batch and 10 batches. Other procedures run
atomically as `mcp_proc_exec` with their reviewed bounds and timeout. Full-table
owner procedures are explicitly described as such and do not inherit the ordinary
DML row cap.

```powershell
poetry run shopmcp inspect-registry
```

Inspection is read-only and prints live definitions/hashes. Compare with the reviewed
source before editing YAML; never paste live hashes over mismatches automatically.
Hashes are SHA-256 of PostgreSQL 17 `pg_get_functiondef` with LF line endings.
Restart after a reviewed registry change. Definitions are rechecked before preview,
after approval, and on the execution connection. Administrative DDL should not race
calls; referenced trigger/helper definitions are outside the procedure hash.

## Inspect audit and uncertain operations

Authenticated ping is independent of both databases. Database tools require a
persisted audit intent. SQL, arguments, caller, limits, approvals, definition hashes,
timestamps, execution intent, commit intent, and outcomes are append-only.
Tokens, infrastructure credentials, and result sets are excluded.

The two databases cannot commit atomically. A confirmed shop commit followed by an
audit outage returns `outcome: committed`, `audit_status: unavailable`. A lost
commit acknowledgement returns `uncertain`. Neither case triggers an automatic
retry. An interrupted archive may have earlier committed batches. No operation is
automatically resumed.

Use a separate administrative read session, for example on the test instance:

```powershell
docker compose -f tests/compose.yml exec db psql -U mcp_audit_owner -d mcp_audit
```

```sql
SELECT operation_id, issuer, subject, tool, inputs, created_at
FROM audit.operations ORDER BY created_at DESC LIMIT 20;
SELECT event_id, operation_id, kind, detail, created_at
FROM audit.events ORDER BY event_id DESC LIMIT 50;
SELECT o.operation_id, o.tool, o.created_at
FROM audit.operations o
WHERE NOT EXISTS (
    SELECT 1 FROM audit.events e
    WHERE e.operation_id = o.operation_id AND e.kind IN ('outcome', 'error', 'cancelled')
)
ORDER BY o.created_at;
```

An error/cancellation record can still indicate uncertainty; inspect its outcome and
commit-intent events. Absence of a final record never proves that nothing happened.

## Isolated tests

Database tests never use the project's `.env`. Start a new test instance once:

```powershell
docker compose -f tests/compose.yml up -d --wait
poetry run python tests/seed_isolated.py
$env:SHOP_TEST_DATABASE='isolated'
poetry run pytest tests/test_seed_integrity.py tests/test_planted.py tests/test_docgen.py
```

The seed runner selects S explicitly, validates the fresh dataset, then applies
post-load scripts. Run the baseline tests before mutation tests. Repeating the seed
against post-load triggers intentionally refuses; do not delete a volume merely
to make a test pass. Provision/migrate the test audit database as described above.

```powershell
poetry run pytest tests/test_guarded_integration.py tests/test_guarded_failures.py tests/test_http_integration.py tests/test_worker_configuration.py
Remove-Item Env:SHOP_TEST_DATABASE
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
```

The second phase deliberately changes the disposable fixture and advances sequences.
Fresh-seed integrity checks may fail afterward; use a separately approved fresh test
instance for another baseline cycle. No test automatically drops volumes.
The default pytest command runs database-independent tests and skips integrations.

## Inspector acceptance checklist

After configuring the real tenant, start `shopmcp serve` with the isolated database
settings and launch:

```powershell
npx.cmd --yes @modelcontextprotocol/inspector@2.9.0 --catalog .scratch/inspector-catalog.json
```

The catalog entry `shop-mcp` (setup guide Step 16) uses Streamable HTTP and `http://127.0.0.1:8000/mcp`. Enter the statically
registered client ID/secret locally, connect, log in as the provisioned developer,
and complete consent. Verify discovery and ping, then:

1. Run `query` with `SELECT product_id, name FROM shop.products LIMIT 3`.
2. Run `query` with `SELECT pg_sleep(1)`; verify policy rejection.
3. Run `execute` with a targeted no-op customer update; decline, then repeat and
   approve. Inspect the complete preview before approval.
4. Call `archive_old_orders` with an old cutoff such as `1900-01-01`, batch size 1,
   maximum batches 1. Confirm the partial-commit warning and approve.
5. Inspect the operation IDs and events in `mcp_audit`.

Results of the real walkthrough (test instance, 2026-10-03) are in setup guide Step 17:
items 3-5 passed, plus the rejection and decline paths. The approval prompt text and a
multi-batch partial commit were not captured by hand. The automated tests do not
claim a real Auth0/Inspector login; that was done separately by the user.
