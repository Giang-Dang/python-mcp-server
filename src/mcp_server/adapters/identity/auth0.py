"""Auth0 validates JWTs; Core sees only a verified Principal."""

import math
import time

from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.providers.auth0 import Auth0MCPProvider
from fastmcp.server.dependencies import get_access_token

from mcp_server.core.access_control.domain import Principal
from mcp_server.core.errors import Category, GuardError


def principal_from_token(token) -> Principal:
    if token is None:
        raise GuardError(Category.AUTHENTICATION, "Authentication is required.")
    claims = token.claims
    issuer, subject, expiry = claims.get("iss"), claims.get("sub"), claims.get("exp")
    if (
        not isinstance(issuer, str)
        or not isinstance(subject, str)
        or not subject.strip()
        or type(expiry) not in (int, float)
        or not math.isfinite(expiry)
    ):
        raise GuardError(Category.AUTHENTICATION, "Token lacks required identity claims.")
    principal = Principal(issuer, subject, expiry)
    principal.require_valid(time.time())
    return principal


def current_principal() -> Principal:
    return principal_from_token(get_access_token())


class IdentityVerifier(TokenVerifier):
    def __init__(self, delegate):
        super().__init__()
        self.delegate = delegate

    async def verify_token(self, token):
        verified = await self.delegate.verify_token(token)
        try:
            principal_from_token(verified)
            nbf = verified.claims.get("nbf")
            if nbf is not None and (
                type(nbf) not in (int, float) or not math.isfinite(nbf) or nbf > time.time()
            ):
                return None
        except (GuardError, TypeError, AttributeError):
            return None
        return verified


def make_auth(settings):
    # OIDC discovery happens explicitly at startup, never on import.
    provider = Auth0MCPProvider(
        config_url=settings.issuer + ".well-known/openid-configuration",
        base_url=settings.base_url,
        required_scopes=[],
        resource_name="Guarded shop SQL",
    )
    if provider.issuer.rstrip("/") != settings.issuer.rstrip("/"):
        raise ValueError("Discovered issuer does not match the configured Auth0 domain.")
    provider.set_mcp_path("/mcp")
    provider.token_verifier = IdentityVerifier(provider.token_verifier)
    return provider
