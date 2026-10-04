"""Documentation is discoverable and readable without database services."""

import asyncio

import pytest
from fakes import principal
from fastmcp import Client
from fastmcp.exceptions import McpError
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from support import server_settings

from mcp_server.bootstrap import create_server


class NoDatabaseServices:
    async def close(self):
        pass


def guidance_server(**overrides):
    return create_server(
        server_settings(**overrides),
        auth=StaticTokenVerifier(tokens={}),
        services=NoDatabaseServices(),
        identity=principal,
    )


def test_client_discovers_and_reads_three_markdown_resources(monkeypatch, tmp_path):
    server = guidance_server(reader_password="SENTINEL-reader", audit_password="SENTINEL-audit")
    monkeypatch.chdir(tmp_path)

    async def run():
        async with Client(server, mode="2026-07-28") as client:
            resources = [
                r for r in await client.list_resources() if str(r.uri).startswith("shop://")
            ]
            assert {str(r.uri): r.name for r in resources} == {
                "shop://guide/schema": "schema_guide",
                "shop://guide/relationships": "relationships_guide",
                "shop://policy/sql": "sql_policy",
            }
            templates = await client.list_resource_templates()
            assert [t.uri_template for t in templates] == ["shop://tables/{table}"]
            assert len(await client.list_tools()) == 9
            for resource in resources:
                assert resource.description
                assert resource.mime_type == "text/markdown"
                contents = await client.read_resource(str(resource.uri))
                assert len(contents) == 1
                assert contents[0].mime_type == "text/markdown"
                text = contents[0].text
                assert 0 < len(text.encode("utf-8")) <= 16384
                assert "SENTINEL" not in text

    asyncio.run(run())


def test_resource_policy_is_per_instance_and_arbitrary_uris_are_rejected(tmp_path):
    private_file = tmp_path / "private.txt"
    private_file.write_text("SENTINEL-private-file", encoding="utf-8")

    async def run():
        for rows in (7, 19):
            async with Client(guidance_server(result_rows=rows), mode="2026-07-28") as client:
                policy = (await client.read_resource("shop://policy/sql"))[0].text
                assert f"| result_rows | {rows} |" in policy
                for uri in ("shop://guide/unknown", private_file.as_uri()):
                    with pytest.raises(McpError) as error:
                        await client.read_resource(uri)
                    assert "SENTINEL-private-file" not in str(error.value)

    asyncio.run(run())
