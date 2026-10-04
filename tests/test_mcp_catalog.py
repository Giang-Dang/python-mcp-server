"""Discovery pagination and bounded audited metadata without a live database."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fakes import MemoryAudit, principal
from fastmcp import Client
from fastmcp.exceptions import McpError
from test_mcp_resources import guidance_server

from mcp_server.core.auditing.application import Audit
from mcp_server.core.catalog.application import Catalog
from mcp_server.core.sql_access.domain import Limits


class CatalogDB:
    async def describe_table(self, name):
        return {
            "columns": ["name", "type", "not_null", "comment"],
            "rows": [["id", "bigint", True, "Primary key"]],
            "truncated": False,
        }


def test_template_read_and_sanitized_invalid_names():
    async def run():
        server = guidance_server()
        store = MemoryAudit()
        catalog = Catalog(CatalogDB(), Audit(store, Limits()))
        # The registered resource resolves services lazily at read time.
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
        from support import server_settings

        from mcp_server.bootstrap import create_server

        async def close():
            pass

        server = create_server(
            server_settings(),
            auth=StaticTokenVerifier(tokens={}),
            services=SimpleNamespace(catalog=catalog, close=close),
            identity=principal,
        )
        async with Client(server, mode="2026-07-28") as client:
            assert len(await client.list_resource_templates()) == 1
            assert not store.operations
            content = (await client.read_resource("shop://tables/orders"))[0]
            assert content.mime_type == "application/json"
            assert json.loads(content.text)["columns"][0]["name"] == "id"
            assert store.operations[0].tool == "read_table_resource"
            raw = await client.read_resource_mcp("shop://tables/orders")
            assert raw.meta["operation_id"] == store.operations[-1].id
            for name in ("shop.orders", "..", "%2e%2e", "A", "a" * 64):
                with pytest.raises(McpError):
                    await client.read_resource(f"shop://tables/{name}")

    asyncio.run(run())


@pytest.mark.parametrize("size", [1, 5])
def test_discovery_all_pages_and_invalid_cursor(size):
    async def run():
        async with Client(guidance_server(list_page_size=size), mode="2026-07-28") as client:
            names = []
            cursor = None
            while True:
                page = await client.list_tools_mcp(cursor=cursor)
                assert 0 < len(page.tools) <= size
                names.extend(t.name for t in page.tools)
                cursor = page.next_cursor
                if cursor is None:
                    break
            assert len(names) == len(set(names)) == 9
            assert len(await client.list_tools()) == 9
            with pytest.raises(McpError):
                await client.list_tools_mcp(cursor="invalid!")

    asyncio.run(run())


def test_resource_serialized_size_and_audit_failure():
    async def run():
        class BigDB(CatalogDB):
            async def describe_table(self, name):
                result = await super().describe_table(name)
                result["rows"][0][3] = "x" * 300
                return result

        for db, fail, category in (
            (BigDB(), None, "limits"),
            (CatalogDB(), "start", "audit_unavailability"),
        ):
            result = await Catalog(
                db, Audit(MemoryAudit(fail), Limits(result_bytes=256))
            ).read_table(principal(), "orders")
            assert result["error"]["category"] == category
            assert result["data"] is None

    asyncio.run(run())
