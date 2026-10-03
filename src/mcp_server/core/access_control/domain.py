import math
from dataclasses import dataclass

from mcp_server.core.errors import Category, GuardError


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    expires_at: float

    @property
    def identity(self) -> tuple[str, str]:
        return self.issuer, self.subject

    def require_valid(self, now: float) -> None:
        if (
            not self.issuer
            or not self.subject
            or not math.isfinite(self.expires_at)
            or self.expires_at <= now
        ):
            raise GuardError(
                Category.AUTHENTICATION, "A valid, unexpired caller identity is required."
            )


@dataclass(frozen=True)
class Approval:
    operation_id: str
    identity: tuple[str, str]
    fingerprint: str
    expires_at: float
    decision: str
