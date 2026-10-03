from collections.abc import Awaitable, Callable
from typing import Protocol

from .domain import Analysis

BeforeCommit = Callable[[], Awaitable[None]]


class SQLParser(Protocol):
    def analyze(self, sql: str) -> Analysis: ...


class SQLDatabase(Protocol):
    async def preview(self, sql: str, role: str) -> dict: ...
    async def query(self, sql: str) -> dict: ...
    async def mutate(self, sql: str, before_commit: BeforeCommit) -> dict: ...
