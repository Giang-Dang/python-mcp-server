from collections.abc import Iterable
from typing import Protocol

from shopdb.core.dataset.application import build_context
from shopdb.core.dataset.scales import Scale

from .domain import INTEGRITY_RULES, Check, Measurements, expected_counts


class VerificationStore(Protocol):
    def measure(self, tables: Iterable[str]) -> Measurements: ...


def run_verify(scale: Scale, seed: int, store: VerificationStore) -> list[Check]:
    expected = expected_counts(build_context(scale, seed))
    measured = store.measure(expected)
    checks = [
        Check(
            f"rows in {table}",
            measured.counts[table] == want,
            f"{measured.counts[table]:,} (expected {want:,})",
        )
        for table, want in expected.items()
    ]
    for rule in INTEGRITY_RULES:
        value = measured.values[rule.name]
        checks.append(
            Check(
                rule.name,
                rule.low <= value <= rule.high,
                f"{value:g} {rule.unit} (allowed {rule.low:g}..{rule.high:g})",
            )
        )
    behind = [
        table
        for table, last, maximum in measured.sequences
        if maximum is not None and (last is None or last < maximum)
    ]
    checks.append(
        Check(
            f"identity sequences are past max(id) ({len(measured.sequences)} tables)",
            not behind,
            ", ".join(behind) or "all ok",
        )
    )
    return checks
