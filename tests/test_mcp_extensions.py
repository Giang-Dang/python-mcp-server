"""Completion, fixed skill files, capability opt-in and packaged UI acceptance."""

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from fakes import MemoryAudit, principal
from fastmcp import Client
from fastmcp.exceptions import McpError
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp.client.extension import ClientExtension
from mcp_types import PaginatedRequestParams, Request, Result
from sqlalchemy.dialects import postgresql
from support import server_settings
from test_mcp_resources import guidance_server

from mcp_server.adapters.mcp.skills import (
    EXTENSION,
    SKILL_URI,
    GetSkillParams,
    GetSkillResult,
    ListSkillsResult,
)
from mcp_server.adapters.mcp.viewer import VIEWER_URI
from mcp_server.adapters.postgres.queries import table_names_query
from mcp_server.bootstrap import create_server
from mcp_server.core.auditing.application import Audit
from mcp_server.core.catalog.application import Catalog
from mcp_server.core.sql_access.domain import Limits


class SkillsClient(ClientExtension):
    identifier = EXTENSION


def test_skills_wire_manifest_fixed_resources_and_opt_in():
    async def run():
        server = guidance_server(list_page_size=1)
        async with Client(server, mode="2026-07-28", extensions=[SkillsClient()]) as client:
            assert len(await client.list_resources()) == 6
            listing = await client.session.send_request(
                Request(method="skills/list", params=PaginatedRequestParams()), ListSkillsResult
            )
            payload = listing.model_dump(by_alias=True)
            assert payload["ttlMs"] == 0 and payload["cacheScope"] == "private"
            skill = payload["skills"][0]
            fetched = await client.session.send_request(
                Request(method="skills/get", params=GetSkillParams(uri=SKILL_URI)), GetSkillResult
            )
            assert fetched.model_dump(by_alias=True)["skill"] == skill
            assert len(skill["resources"]) == 2
            for entry in skill["resources"]:
                data = (await client.read_resource(entry["uri"]))[0].text.encode("ascii")
                assert entry["size"] == len(data)
                assert entry["digest"] == "sha256:" + hashlib.sha256(data).hexdigest()
            for uri in (
                "skill://investigate-slow-query/../private",
                "skill://investigate-slow-query/%2e%2e/private",
                "file:///private",
            ):
                with pytest.raises(McpError):
                    await client.read_resource(uri)
            with pytest.raises(McpError):
                await client.session.send_request(
                    Request(
                        method="skills/get", params=GetSkillParams(uri="skill://unknown/SKILL.md")
                    ),
                    Result,
                )
            with pytest.raises(McpError):
                await client.session.send_request(
                    Request(method="skills/list", params=PaginatedRequestParams(cursor="invalid")),
                    Result,
                )
        async with Client(server, mode="2026-07-28") as client:
            with pytest.raises(McpError):
                await client.session.send_request(
                    Request(method="skills/list", params=PaginatedRequestParams()), Result
                )
            # A generic resource read is transport, not skill activation.
            assert (await client.read_resource(SKILL_URI))[0].text.startswith("---")

    asyncio.run(run())


def test_completion_prefix_cap_and_sanitized_errors():
    async def run():
        class DB:
            async def complete_tables(self, prefix):
                assert prefix == "order"
                return {"rows": [[f"order_{i:03d}"] for i in range(101)], "truncated": False}

        store = MemoryAudit()

        async def close():
            pass

        server = create_server(
            server_settings(),
            auth=StaticTokenVerifier(tokens={}),
            services=SimpleNamespace(catalog=Catalog(DB(), Audit(store, Limits())), close=close),
            identity=principal,
        )
        async with Client(server, mode="2026-07-28") as client:
            for ref in (
                {"type": "ref/resource", "uri": "shop://tables/{table}"},
                {"type": "ref/prompt", "name": "explore_schema"},
            ):
                result = await client.complete(ref, {"name": "table", "value": "order"})
                assert len(result.values) == 100 and result.has_more is True
            assert len(store.operations) == 2
            result = await client.complete(
                {"type": "ref/prompt", "name": "unknown"}, {"name": "table", "value": "order"}
            )
            assert result.values == [] and len(store.operations) == 2
            with pytest.raises(McpError):
                await client.complete(
                    {"type": "ref/prompt", "name": "explore_schema"},
                    {"name": "table", "value": "shop.orders"},
                )

    asyncio.run(run())


def test_prefix_sql_is_bound_and_underscore_is_literal():
    compiled = table_names_query("order_").compile(dialect=postgresql.dialect())
    assert "order_" not in str(compiled)
    assert any(value == "order/_" for value in compiled.params.values())
    assert "pg_catalog.pg_class" in str(compiled) and "LIMIT" in str(compiled)


def test_app_metadata_asset_and_non_app_tool_discovery():
    async def run():
        async with Client(guidance_server(), mode="2026-07-28") as client:
            tool = next(t for t in await client.list_tools() if t.name == "explain")
            assert tool.meta["ui"]["resourceUri"] == VIEWER_URI
            result = await client.read_resource(VIEWER_URI)
            assert result[0].mime_type.startswith("text/html")
            assert "ESTIMATES ONLY" in result[0].text
            assert "<script src=" not in result[0].text
            resource = next(r for r in await client.list_resources() if str(r.uri) == VIEWER_URI)
            assert resource.meta["ui"]["csp"]["connectDomains"] == []
            assert resource.meta["ui"]["permissions"] == {}

    asyncio.run(run())
