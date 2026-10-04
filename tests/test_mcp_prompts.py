"""Prompt retrieval returns messages without execution or human approval requests."""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import McpError
from test_mcp_resources import guidance_server


def test_client_discovers_and_renders_two_user_message_prompts():
    async def forbidden_elicitation(*args, **kwargs):
        raise AssertionError("Prompt retrieval attempted elicitation")

    async def run():
        async with Client(
            guidance_server(), mode="2026-07-28", elicitation_handler=forbidden_elicitation
        ) as client:
            prompts = {p.name: p for p in await client.list_prompts()}
            assert set(prompts) == {"explore_schema", "investigate_slow_query"}
            assert len(await client.list_tools()) == 9
            assert len(await client.list_resources()) == 6
            for name, argument, required in (
                ("explore_schema", "table", False),
                ("investigate_slow_query", "sql", True),
            ):
                assert prompts[name].description
                assert len(prompts[name].arguments) == 1
                arg = prompts[name].arguments[0]
                assert arg.name == argument
                assert arg.required is required
                assert arg.description
            for name, arguments, expected in (
                ("explore_schema", None, "short map"),
                ("explore_schema", {"table": "orders"}, 'table="orders"'),
                (
                    "investigate_slow_query",
                    {"sql": "SELECT product_id, name FROM shop.products LIMIT 3"},
                    "non-ANALYZE",
                ),
            ):
                result = await client.get_prompt(name, arguments)
                assert len(result.messages) == 1
                assert result.messages[0].role == "user"
                assert result.messages[0].content.type == "text"
                assert expected in result.messages[0].content.text

    asyncio.run(run())


@pytest.mark.parametrize(
    "name, arguments, message",
    [
        ("investigate_slow_query", {}, "sql"),
        ("explore_schema", {"table": "shop.orders"}, "unqualified ASCII"),
        ("investigate_slow_query", {"sql": "SENTINEL" * 1024}, "8192-byte"),
        ("investigate_slow_query", {"sql": " "}, "nonempty"),
        ("unknown_prompt", {}, "Unknown prompt"),
    ],
)
def test_client_get_prompt_rejects_invalid_input_without_echoing_sql(name, arguments, message):
    async def run():
        async with Client(guidance_server(), mode="2026-07-28") as client:
            with pytest.raises(McpError) as error:
                await client.get_prompt(name, arguments)
            assert message in str(error.value)
            assert "SENTINEL" not in str(error.value)

    asyncio.run(run())


def test_prompt_uses_instance_request_limit():
    async def run():
        async with Client(guidance_server(request_bytes=1024), mode="2026-07-28") as client:
            with pytest.raises(McpError, match="1024-byte"):
                await client.get_prompt("investigate_slow_query", {"sql": "s" * 1015})
            result = await client.get_prompt("investigate_slow_query", {"sql": "s" * 1014})
            assert result.messages[0].role == "user"

    asyncio.run(run())
