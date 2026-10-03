from dataclasses import dataclass

from mcp_server.core.access_control.domain import Principal


@dataclass(frozen=True)
class Operation:
    id: str
    principal: Principal
    tool: str
    inputs: dict
    limits: dict
