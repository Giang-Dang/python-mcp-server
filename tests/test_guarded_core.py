import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import Approver, MemoryAudit, principal

from mcp_server.adapters.registry.yaml_registry import load_registry
from mcp_server.adapters.sql_parser.sqlglot import Parser
from mcp_server.core.access_control.application import obtain_approval, verify_approval
from mcp_server.core.auditing.application import Audit
from mcp_server.core.errors import Category, GuardError
from mcp_server.core.procedures.application import Procedures
from mcp_server.core.sql_access.application import SQLAccess
from mcp_server.core.sql_access.domain import Limits
from mcp_server.core.sql_access.policy import authorize


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DELETE FROM shop.orders WHERE true",
        "WITH x AS (DELETE FROM shop.orders RETURNING *) SELECT * FROM x",
        "SELECT * INTO shop.stolen FROM shop.customers",
        "SELECT * FROM shop.orders FOR UPDATE",
        "SELECT pg_sleep(10)",
        "SELECT nextval('shop.orders_order_id_seq')",
        "SELECT shop.get_next_invoice_number(1)",
        "SELECT set_config('role', 'postgres', false)",
        "SELECT * FROM public.pg_stat_statements",
        "SELECT * FROM customers",
        "SELECT 1::regclass",
        "SELECT lo_import('/tmp/a')",
        "SET ROLE postgres",
        "BEGIN",
        "COMMIT",
        "VACUUM shop.orders",
        "COPY shop.orders TO '/tmp/a'",
        "DO $$BEGIN END$$",
        "CALL shop.cancel_order(1)",
        "EXPLAIN ANALYZE SELECT 1",
        "SELECT * FROM shop.orders WHERE pg_try_advisory_lock(1)",
        "SELECT shop.warm_cache(3)",
        "SELECT * FROM shop.orders TABLESAMPLE BERNOULLI(10)",
        "SELECT * FROM shop.orders UNION SELECT * FROM pg_catalog.pg_authid",
        "SELECT * FROM shop.orders; -- hidden\n SELECT 1",
    ],
)
def test_unsafe_reads_rejected(sql):
    with pytest.raises(GuardError):
        authorize(Parser().analyze(sql), "query")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT product_id, lower(name) FROM shop.products WHERE product_id < 4 ORDER BY product_id",
        "SELECT count(*) FROM shop.orders",
        "SELECT status_id, sum(total_amount) FROM shop.orders GROUP BY status_id",
        "WITH x AS (SELECT product_id FROM shop.products) SELECT * FROM x",
        "SELECT 'semi;colon' AS value",
        "SELECT CAST(1 AS integer)",
        "SELECT 1 UNION SELECT 2",
    ],
)
def test_reviewed_reads_accepted(sql):
    authorize(Parser().analyze(sql), "query")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE shop.customers SET email='a'",
        "DELETE FROM shop.orders",
        "UPDATE shop.orders SET status_id=1 WHERE order_id=1 RETURNING *",
        "SELECT * FROM shop.orders",
        "INSERT INTO shop.customers (email) VALUES ('a') RETURNING customer_id",
    ],
)
def test_write_restrictions(sql):
    with pytest.raises(GuardError):
        authorize(Parser().analyze(sql), "execute")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE shop.orders SET status_id=1 WHERE order_id=2",
        "DELETE FROM shop.carts WHERE cart_id=3",
        "INSERT INTO shop.carts (customer_id) VALUES (3)",
    ],
)
def test_reviewed_dml_accepted(sql):
    authorize(Parser().analyze(sql), "execute")


class FakeDatabase:
    def __init__(self):
        self.calls = 0
        self.cost = 1
        self.hash = None
        self.failure = None

    async def preview(self, sql, role):
        return {"total_cost_estimate": self.cost}

    async def query(self, sql):
        self.calls += 1
        return {"rows": [[1]]}

    async def mutate(self, sql, before_commit):
        await before_commit()
        self.calls += 1
        if self.failure:
            raise self.failure
        return {"outcome": "committed", "affected_rows": 1}

    async def definition_hash(self, entry):
        return self.hash or entry.definition_hash

    async def call(self, entry, arguments, before_commit):
        return await self.mutate("", before_commit)


def run_flow(decision="approved", fail=None, limits=None, database=None):
    db = database or FakeDatabase()
    storage = MemoryAudit(fail)
    audit = Audit(storage, limits or Limits())
    service = SQLAccess(Parser(), db, audit, limits or Limits())
    result = asyncio.run(
        service.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET email=email WHERE customer_id=1",
            Approver(decision),
        )
    )
    return result, db, storage


@pytest.mark.parametrize(
    "decision,outcome",
    [
        ("approved", "committed"),
        ("declined", "declined"),
        ("cancelled", "cancelled"),
        ("expired", "cancelled"),
        ("unavailable", "cancelled"),
    ],
)
def test_approval_outcomes(decision, outcome):
    result, db, audit = run_flow(decision)
    assert result["outcome"] == outcome
    assert db.calls == (decision == "approved")
    assert audit.operations[0].principal.subject == "developer"


@pytest.mark.parametrize("failure", ["start", "approval", "execution_intent", "commit_intent"])
def test_audit_failure_prevents_mutation(failure):
    result, db, _ = run_flow(fail=failure)
    assert result["error"]["category"] == "audit_unavailability"
    assert db.calls == 0


def test_audit_failure_after_commit_is_distinct():
    result, db, _ = run_flow(fail="outcome")
    assert result["outcome"] == "committed"
    assert result["audit_status"] == "unavailable"
    assert result["retry_safe"] is False
    assert db.calls == 1


def test_uncertainty_never_retries():
    db = FakeDatabase()
    db.failure = GuardError(Category.UNCERTAIN, "Commit lost", "uncertain")
    result, db, _ = run_flow(database=db)
    assert result["outcome"] == "uncertain" and db.calls == 1
    assert result["retry_safe"] is False


def test_cost_and_payload_limits():
    db = FakeDatabase()
    db.cost = 1000001
    result, db, _ = run_flow(database=db)
    assert result["error"]["category"] == "limits" and db.calls == 0
    result, db, audit = run_flow(limits=Limits(request_bytes=10))
    assert result["error"]["category"] == "limits" and not audit.operations


def test_approval_binding_and_expiry():
    async def run():
        caller = principal()
        preview = {"sql": "exact"}
        approval = await obtain_approval(caller, "op", preview, Approver(), 300, clock=lambda: 10)
        verify_approval(approval, caller, "op", preview, clock=lambda: 11)
        for who, op, data, now in [
            (principal("other"), "op", preview, 11),
            (caller, "other", preview, 11),
            (caller, "op", {"sql": "changed"}, 11),
            (caller, "op", preview, 311),
            (replace(caller, expires_at=10), "op", preview, 11),
        ]:
            with pytest.raises(GuardError):
                verify_approval(approval, who, op, data, clock=lambda now=now: now)
        timed = await obtain_approval(caller, "op", preview, Approver(delay=0.03), 0.001)
        assert timed.decision == "expired"

    asyncio.run(run())


def test_registry_rejects_unknown_arguments_and_controls_inout():
    registry = load_registry(Path("config/procedures.yaml"))
    assert len(registry) == 10 and "bulk_update_prices" not in registry
    create = registry["create_order"]
    assert (
        create.bind({"p_customer_id": 1, "p_variant_ids": [1], "p_quantities": [1]})["p_order_id"]
        is None
    )
    with pytest.raises(GuardError):
        create.bind(
            {"p_customer_id": 1, "p_variant_ids": [1], "p_quantities": [1], "p_order_id": 99}
        )
    for args in (
        {"p_before": "2024-01-01", "p_batch_size": 5001},
        {"p_before": "2024-01-01", "p_max_batches": 11},
        {"p_before": "bad"},
    ):
        with pytest.raises(GuardError):
            registry["archive_old_orders"].bind(args)
    with pytest.raises(GuardError):
        registry["purge_abandoned_carts"].bind({"p_older_than_days": 6})


def test_definition_drift_during_approval():
    async def run():
        registry = load_registry(Path("config/procedures.yaml"))
        db, store = FakeDatabase(), MemoryAudit()
        service = Procedures(registry, db, Audit(store, Limits()), Limits())
        result = await service.call(
            principal(),
            "cancel_order",
            {"p_order_id": 1},
            Approver(callback=lambda: setattr(db, "hash", "changed")),
        )
        assert result["error"]["category"] == "registry_mismatch" and db.calls == 0

    asyncio.run(run())


def test_core_dependency_boundaries():
    import ast

    for package in ("mcp_server", "shopdb"):
        for path in Path("src", package, "core").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert not any(
                    "adapters" in m
                    or m.startswith(
                        ("fastmcp", "sqlalchemy", "psycopg", "faker", "pydantic", "yaml")
                    )
                    for m in modules
                ), path
