import json
from pathlib import Path

from characterization import snapshot
from typer.testing import CliRunner

from shopdb.cli import app


def test_original_generation_snapshot():
    assert snapshot() == json.loads(
        (Path(__file__).parent / "fixtures/generation-original.json").read_text()
    )


def test_cli_compatibility(monkeypatch):
    from support import seed_settings

    monkeypatch.setattr("shopdb.cli.get_settings", seed_settings)
    runner = CliRunner()
    help_text = runner.invoke(app, ["--help"])
    assert help_text.exit_code == 0
    for command in ("seed", "verify", "post-load", "reset", "docs", "version"):
        assert command in help_text.stdout
    assert runner.invoke(app, ["seed", "--scale", "M"]).exit_code == 2


def test_verification_rules_evaluate_measurements_in_core():
    from shopdb.core.dataset.application import build_context
    from shopdb.core.dataset.scales import get_scale
    from shopdb.core.verification.application import run_verify
    from shopdb.core.verification.domain import INTEGRITY_RULES, Measurements, expected_counts

    scale = get_scale("S")
    counts = expected_counts(build_context(scale, 42))
    values = {rule.name: float(rule.low) for rule in INTEGRITY_RULES}

    class Store:
        def measure(self, tables):
            return Measurements(counts, values, [("orders", 10, 10)])

    assert all(check.ok for check in run_verify(scale, 42, Store()))
    values[INTEGRITY_RULES[0].name] = 1
    counts["orders"] -= 1
    failed = [c.name for c in run_verify(scale, 42, Store()) if not c.ok]
    assert failed == ["rows in orders", INTEGRITY_RULES[0].name]
