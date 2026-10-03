# Discovering tools, resources and prompts

The guarded server exposes **9 tools, 3 resources and 2 prompts** at
`http://127.0.0.1:8000/mcp`. All MCP requests require authentication. Examples use
the locked FastMCP 4.0.10 SDK; setup is in [guarded-server.md](guarded-server.md).

## How the LLM reaches MCP

The host application owns an MCP client connection. It lists tools and supplies
selected names, descriptions and input schemas to the model. When the model
requests a tool with arguments, the host sends `tools/call` and returns the result
to the model. The model does not open the HTTP connection itself. Discovery does
not execute the tools.
[MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

This repo uses `mode="legacy"` and the `2025-11-25` handshake for its existing
imperative mutation elicitation path. `initialize` negotiates protocol and
capabilities, followed by `notifications/initialized`; initialization does not
return an inventory count.
[MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

```mermaid
sequenceDiagram
    participant User
    participant Host as Host and MCP client
    participant Model as LLM
    participant Server as shopmcp
    Host->>Server: initialize (authenticated, 2025-11-25)
    Server-->>Host: protocol and capabilities
    Host->>Server: notifications/initialized
    Host->>Server: tools/list (all pages)
    Server-->>Host: names, descriptions, schemas
    Host->>Model: selected tool definitions and user request
    Model-->>Host: tool name and arguments
    Host->>Server: tools/call
    Server-->>Host: guarded result
    Host->>Model: tool result
    User->>Host: select prompt or resource
    Host->>Server: prompts/list or resources/list
    Server-->>Host: metadata
    Host->>Server: prompts/get or resources/read
    Server-->>Host: messages or content
    Host->>Model: content the host/user chooses to include
```

## Counting the inventory

Send `tools/list`, append the `tools` array, and follow each `nextCursor` by sending
it as `params.cursor`. Count after the final page. Resources and prompts have their
own paginated list methods. There is no need for a custom `list_tools` tool.
[MCP tool discovery](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

The locked SDK's `list_tools()`, `list_resources()` and `list_prompts()` return lists
and follow pages automatically, with a default maximum of 250 pages. For manual
tool pagination use `list_tools_mcp(cursor=...)`; its result has `.tools` and
`.next_cursor` (wire field `nextCursor`). Reject repeated cursors or unfinished
pagination rather than presenting a partial count as complete. These SDK shapes
were verified against the installed version.

A host may filter tools, discover them on demand or combine servers. Its model may
see fewer tools than this server advertises. To answer the count accurately, the
host must give the model the complete inventory or verified count, identifying the
server and any filtering. The model cannot infer tools hidden by its host.

## Interfaces and bounds

The nine tools remain:

```text
ping, list_tables, describe_table, query, execute, explain,
list_procedures, call_procedure, diagnostics
```

| Resource URI | Name | Content |
|---|---|---|
| `shop://guide/schema` | `schema_guide` | Domains and live catalog inspection instructions. |
| `shop://guide/relationships` | `relationships_guide` | Selected join keys, cardinality cautions and fixture gaps. |
| `shop://policy/sql` | `sql_policy` | Guarded workflows and effective SQL limits for this instance. |

These URIs identify MCP resources, not HTTP endpoints or file paths. Each returns
`text/markdown` with a separate 16,384-byte UTF-8 text budget. The two guides are
shipped revision `guidance-v1`, not database snapshots or a complete ERD. Use
`list_tables` and `describe_table` for current metadata; planner estimates are not
current row counts. The policy reports all nine `Limits` fields from this instance.

`resources/list` returns metadata; `resources/read` fetches content. Listing alone
does not put text into the model's context. The host chooses what to include. This
version has no resource templates or subscriptions; `resources/templates/list`
returns an empty list, with no application change-notification workflow.
[MCP resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources).

| Prompt | Public string arguments | Examples |
|---|---|---|
| `explore_schema` | Optional `table`, default `""` | `{}` or `{"table":"orders"}` |
| `investigate_slow_query` | Required `sql` | `{"sql":"SELECT product_id, name FROM shop.products LIMIT 3"}` |

`prompts/list` discovers templates; `prompts/get` returns one user-role text message.
The host/user chooses whether to use that message. Retrieval does not call the
tools suggested in it or approve a mutation.
[MCP prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts).

`table` must be exactly empty or match `[a-z_][a-z0-9_]{0,62}`. Qualified names,
whitespace and uppercase names are rejected without normalization. Valid syntax
does not establish existence. Exploration prefers metadata; sample rows are only
requested when relevant to the user's request.

`sql` must be nonblank. The original text is preserved in canonical JSON as
untrusted analysis data. Delimiting it is not a prompt-injection security boundary.
The workflow requests a non-ANALYZE plan only for suitable read SQL, passing the
original SQL without adding EXPLAIN. It does not execute the query to measure
latency. Planner cost is not elapsed time, and aggregate diagnostics do not measure
that particular query. Findings separate evidence, likely cause, suggested change
and further verification; proposed changes remain for review.

Each public argument object is limited to `min(limits.request_bytes, 8192)` UTF-8
bytes of canonical JSON, including keys, quotes and escapes. Each complete prompt
message is limited to 65,536 UTF-8 text bytes. Oversized inputs are rejected without
truncation or echoing SQL. Missing SQL, invalid names and unsupported arguments
return useful errors. SQL tools retain their own budgets and enforcement.

## Authenticated FastMCP example

This complete async helper accepts an **already connected, authenticated** client.
Call it inside your existing `async with client:` connection. Configure Auth0 using
the runbook or Inspector; credentials do not belong in this helper. Construct the
client with `mode="legacy"` for this repository.

```python
from fastmcp import Client


async def inspect_guidance(client: Client) -> dict[str, int]:
    tools = await client.list_tools()
    resources = await client.list_resources()
    prompts = await client.list_prompts()
    counts = {
        "tools": len(tools),
        "resources": len(resources),
        "prompts": len(prompts),
    }
    print(counts)
    for resource in resources:
        contents = await client.read_resource(str(resource.uri))
        for content in contents:
            print(content.mime_type, content.text)
    print("templates:", await client.list_resource_templates())

    requests = [
        ("explore_schema", {}),
        ("explore_schema", {"table": "orders"}),
        (
            "investigate_slow_query",
            {"sql": "SELECT product_id, name FROM shop.products LIMIT 3"},
        ),
    ]
    for name, arguments in requests:
        result = await client.get_prompt(name, arguments)
        for message in result.messages:
            print(message.role, message.content.text)
    return counts
```

Expected count: `{"tools": 9, "resources": 3, "prompts": 2}`. Templates are empty.
`read_resource()` returns a list of content objects; `get_prompt()` returns a result
with `.messages`. Printing content does not attach it to a model conversation.

## Authentication, audit and availability

Shared identity middleware protects every MCP request and binds sessions to their
verified caller. Invalid tokens and cross-user session reuse are rejected on
discovery, reads and prompt rendering as well as tools.

| Operation | Authentication | Database operation audit |
|---|---|---|
| List tools/resources/templates/prompts | Required | No database operation. |
| Read these documentation resources | Required | No database operation. |
| Render these prompts | Required | No database operation; SQL is not persisted by this feature. |
| Call database tools | Required | Existing intent/outcome audit is mandatory. |
| Call `ping` | Required | Existing database-independent behavior. |

Given a running authenticated server, guidance handlers need no healthy database.
Startup retains its configuration, registry and Auth0 requirements. A later live
resource must use an audited application service. Guidance cannot bypass policy or
mutation approval; uncertain mutations must never be retried automatically.
Configured tenant context is not a tenant-isolation guarantee. P01-P13 remain
intentional learning problems, not changes for prompts to repair.

## Acceptance evidence

Automated checks use pure renderers, in-process clients with close-only services,
and controlled-JWKS HTTP authentication. Actual commands/counts are in the
[implementation checklist](mcp-resources-prompts-plan.md).

The user confirmed manual resource/prompt acceptance: "I checked, it worked".
This is user-reported client success; per-method UI responses and a negotiated
protocol were not captured. Optional LLM-host resource/prompt context inclusion
remains unverified separately from the required client acceptance.

[Setup-guide Step 18](setup-guide.md#step-18-load-resources-and-prompts-client-acceptance-preflight-2026-10-03)
records the isolated runtime restart and successful HTTP preflight. Computer-use
had no enabled browser surface, so the user performed the manual check. The
updated server was started and the existing Inspector was preserved.
