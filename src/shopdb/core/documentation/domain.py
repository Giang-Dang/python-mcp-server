from collections import defaultdict
from dataclasses import dataclass, field

KIND_LABEL = {"r": "table", "p": "partitioned table", "v": "view", "m": "materialized view"}
VOLATILITY = {"i": "immutable", "s": "stable", "v": "volatile"}
CONSTRAINT_LABEL = {
    "p": "primary key",
    "f": "foreign key",
    "u": "unique",
    "c": "check",
    "x": "exclusion",
}


@dataclass
class Catalog:
    tables: list[dict]
    columns: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    constraints: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    indexes: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    triggers: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    policies: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    routines: list[dict] = field(default_factory=list)
