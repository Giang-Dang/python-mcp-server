from typing import Protocol


class DiagnosticsDatabase(Protocol):
    async def diagnostics(self, kind: str) -> dict: ...
