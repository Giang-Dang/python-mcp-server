"""Real Auth0 provider with controlled metadata/JWKS; no external Auth0 tenant required."""

import base64
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from starlette.testclient import TestClient
from support import server_settings

from mcp_server.adapters.identity.auth0 import make_auth
from mcp_server.bootstrap import create_server


class NoDatabaseServices:
    async def close(self):
        pass


GUIDANCE_REQUESTS = [
    ("resources/list", {}),
    ("resources/templates/list", {}),
    ("resources/read", {"uri": "shop://guide/schema"}),
    ("prompts/list", {}),
    ("prompts/get", {"name": "explore_schema", "arguments": {"table": "orders"}}),
    (
        "prompts/get",
        {"name": "investigate_slow_query", "arguments": {"sql": "SELECT 1"}},
    ),
]


def rpc(client, token, session, method, params):
    return client.post(
        "/mcp",
        headers=headers(token, session),
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
    )


def assert_no_guidance(response):
    for text in ("# Shop schema guide", "Explore the shop schema", "Investigate the supplied SQL"):
        assert text not in response.text


def controlled_auth(monkeypatch, settings):
    key = RSAKeyPair.generate()
    metadata = SimpleNamespace(
        issuer=settings.issuer, jwks_uri=settings.issuer + ".well-known/jwks.json"
    )
    monkeypatch.setattr(OIDCConfiguration, "get_oidc_configuration", lambda *a, **kw: metadata)
    provider = make_auth(settings)
    numbers = load_pem_public_key(key.public_key.encode()).public_numbers()

    def encoded(number):
        return (
            base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, "big"))
            .decode()
            .rstrip("=")
        )

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test",
                "alg": "RS256",
                "use": "sig",
                "n": encoded(numbers.n),
                "e": encoded(numbers.e),
            }
        ]
    }
    provider.token_verifier.delegate._fetch_jwks = AsyncMock(return_value=jwks)
    return provider, key


def headers(token=None, session=None):
    result = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
    if token:
        result["Authorization"] = "Bearer " + token
    if session:
        result["Mcp-Session-Id"] = session
    return result


def initialize(client, token):
    return client.post(
        "/mcp",
        headers=headers(token),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "acceptance-test", "version": "1"},
            },
        },
    )


@pytest.fixture
def http_server(monkeypatch):
    settings = server_settings()
    auth, key = controlled_auth(monkeypatch, settings)
    server = create_server(settings, auth=auth, services=NoDatabaseServices())
    app = server.http_app(path="/mcp", json_response=True, host_origin_protection=True)
    with TestClient(app, base_url=settings.base_url) as client:
        yield client, key, settings


@pytest.mark.parametrize(
    "case",
    ["missing", "forged", "expired", "issuer", "audience", "subject", "expiry", "not_yet_valid"],
)
@pytest.mark.parametrize("method, params", [("tools/list", {})] + GUIDANCE_REQUESTS)
def test_http_rejects_invalid_authentication(http_server, case, method, params):
    client, key, settings = http_server
    valid = key.create_token(issuer=settings.issuer, audience=settings.resource_url, kid="test")
    session = initialize(client, valid).headers["mcp-session-id"]
    kwargs = {"issuer": settings.issuer, "audience": settings.resource_url, "kid": "test"}
    if case == "forged":
        key = RSAKeyPair.generate()
    if case == "expired":
        kwargs["expires_in_seconds"] = -60
    if case == "issuer":
        kwargs["issuer"] = "https://different.auth0.com/"
    if case == "audience":
        kwargs["audience"] = "https://different-api/"
    if case == "subject":
        kwargs["subject"] = ""
    if case == "expiry":
        kwargs["additional_claims"] = {"exp": None}
    if case == "not_yet_valid":
        kwargs["additional_claims"] = {"nbf": time.time() + 3600}
    token = None if case == "missing" else key.create_token(**kwargs)
    response = initialize(client, token)
    assert response.status_code == 401, response.text
    for current_session in (None, session):
        denied = rpc(client, token, current_session, method, params)
        assert denied.status_code == 401, denied.text
        assert_no_guidance(denied)


def test_metadata_discovery_equal_access_and_ping(http_server):
    client, key, settings = http_server
    metadata = client.get("/.well-known/oauth-protected-resource/mcp")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["resource"] == settings.resource_url
    lists = []
    sessions = []
    tokens = []
    for subject in ("developer-a", "developer-b"):
        token = key.create_token(
            subject=subject, issuer=settings.issuer, audience=settings.resource_url, kid="test"
        )
        tokens.append(token)
        init = initialize(client, token)
        assert init.status_code == 200, init.text
        session = init.headers["mcp-session-id"]
        sessions.append(session)
        response = client.post(
            "/mcp",
            headers=headers(token, session),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert "error" not in response.json(), response.text
        lists.append({t["name"] for t in response.json()["result"]["tools"]})
        pong = client.post(
            "/mcp",
            headers=headers(token, session),
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ping", "arguments": {}},
            },
        )
        assert "pong" in pong.text, pong.text
    assert (
        lists[0]
        == lists[1]
        == {
            "ping",
            "list_tables",
            "describe_table",
            "query",
            "execute",
            "explain",
            "list_procedures",
            "call_procedure",
            "diagnostics",
        }
    )
    swapped = client.post(
        "/mcp",
        headers=headers(tokens[1], sessions[0]),
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
    )
    assert swapped.status_code in (400, 403, 404) or "error" in swapped.json(), swapped.text


@pytest.mark.parametrize("subject", ["developer-a", "developer-b"])
def test_http_guidance_discovery_and_retrieval(http_server, subject):
    client, key, settings = http_server
    token = key.create_token(
        subject=subject, issuer=settings.issuer, audience=settings.resource_url, kid="test"
    )
    init = initialize(client, token)
    assert init.json()["result"]["protocolVersion"] == "2025-11-25"
    capabilities = init.json()["result"]["capabilities"]
    assert {"tools", "resources", "prompts"} <= capabilities.keys()
    session = init.headers["mcp-session-id"]
    resources = rpc(client, token, session, "resources/list", {}).json()["result"]["resources"]
    assert {r["uri"]: r["name"] for r in resources} == {
        "shop://guide/schema": "schema_guide",
        "shop://guide/relationships": "relationships_guide",
        "shop://policy/sql": "sql_policy",
    }
    assert rpc(client, token, session, "resources/templates/list", {}).json()["result"] == {
        "resourceTemplates": []
    }
    for resource in resources:
        response = rpc(client, token, session, "resources/read", {"uri": resource["uri"]})
        assert "error" not in response.json(), response.text
        contents = response.json()["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["mimeType"] == "text/markdown"
        assert contents[0]["text"]
        assert "test_reader" not in response.text
        assert "test_audit" not in response.text
    prompts = rpc(client, token, session, "prompts/list", {}).json()["result"]["prompts"]
    assert {p["name"] for p in prompts} == {"explore_schema", "investigate_slow_query"}
    for name, arguments in (
        ("explore_schema", {}),
        ("explore_schema", {"table": "orders"}),
        ("investigate_slow_query", {"sql": "SELECT 1"}),
    ):
        response = rpc(
            client, token, session, "prompts/get", {"name": name, "arguments": arguments}
        )
        assert "error" not in response.json(), response.text
        messages = response.json()["result"]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"]["type"] == "text"


@pytest.mark.parametrize("method, params", GUIDANCE_REQUESTS)
def test_guidance_rejects_cross_user_session_reuse(http_server, method, params):
    client, key, settings = http_server
    tokens = [
        key.create_token(
            subject=subject, issuer=settings.issuer, audience=settings.resource_url, kid="test"
        )
        for subject in ("developer-a", "developer-b")
    ]
    session = initialize(client, tokens[0]).headers["mcp-session-id"]
    # Bind a guidance request to the first caller before attempting reuse.
    assert (
        "error"
        not in rpc(
            client, tokens[0], session, "resources/read", {"uri": "shop://guide/schema"}
        ).json()
    )
    denied = rpc(client, tokens[1], session, method, params)
    assert denied.status_code in (400, 403, 404) or "error" in denied.json(), denied.text
    assert_no_guidance(denied)


def test_host_and_origin_protection(http_server):
    client, key, settings = http_server
    token = key.create_token(issuer=settings.issuer, audience=settings.resource_url, kid="test")
    for extra in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"}):
        response = client.post(
            "/mcp",
            headers=headers(token) | extra,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert response.status_code in (400, 403, 421), response.text


def test_missing_configuration_fails_without_network(monkeypatch):
    from pydantic import ValidationError

    from mcp_server.settings import Settings

    for key in (
        "AUTH0_DOMAIN",
        "READER_PASSWORD",
        "WRITER_PASSWORD",
        "PROCEDURE_PASSWORD",
        "MONITOR_PASSWORD",
        "AUDIT_PASSWORD",
    ):
        monkeypatch.delenv("SHOPMCP_" + key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_module_import_is_inert(monkeypatch):
    import importlib

    import sqlalchemy.ext.asyncio

    def forbidden(*args, **kwargs):
        raise AssertionError("Import attempted startup work")

    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", forbidden)
    monkeypatch.setattr(OIDCConfiguration, "get_oidc_configuration", forbidden)
    import mcp_server.server

    importlib.reload(mcp_server.server)
