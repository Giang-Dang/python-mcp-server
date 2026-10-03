from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    request_bytes: int = 65536
    result_rows: int = 1000
    result_bytes: int = 1048576
    read_seconds: int = 15
    write_seconds: int = 30
    procedure_seconds: int = 60
    affected_rows: int = 1000
    approval_seconds: int = 300
    plan_cost: float = 1000000


@dataclass(frozen=True)
class Analysis:
    kind: str
    normalized_sql: str
    node_types: frozenset[str]
    functions: frozenset[str]
    tables: tuple[tuple[str, str], ...]
    has_where: bool
    violations: tuple[str, ...]
