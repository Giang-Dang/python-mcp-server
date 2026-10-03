from typing import Protocol

from mcp_server.core.sql_access.ports import BeforeCommit

from .domain import Procedure


class ProcedureDatabase(Protocol):
    async def definition_hash(self, entry: Procedure) -> str | None: ...
    async def call(
        self, entry: Procedure, arguments: dict, before_commit: BeforeCommit
    ) -> dict: ...
