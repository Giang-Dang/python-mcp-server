"""Mutations are restricted by conftest to the explicitly provisioned port 55439."""

import psycopg
import pytest
from fakes import Approver, principal
from support import seed_settings, server_settings

from mcp_server.bootstrap import build_services
from mcp_server.runtime import run_async

pytestmark = pytest.mark.integration


def with_services(test, **options):
    async def run():
        services = build_services(server_settings(**options))
        try:
            await test(services)
            for engine in services.database.engines.values():
                assert engine.pool.checkedout() == 0
            assert services.audit_engine.pool.checkedout() == 0
        finally:
            await services.close()

    run_async(run())


def test_catalog_streamed_reads_plans_and_diagnostics():
    async def run(s):
        tables = await s.catalog.list_tables(principal())
        assert len(tables["data"]) == 25, tables
        assert all(r["comment"] for r in tables["data"])
        description = await s.catalog.describe_table(principal(), "orders")
        assert description["data"]["rows"], description
        result = await s.sql.run(
            principal(), "query", "SELECT product_id, name FROM shop.products ORDER BY product_id"
        )
        assert result["data"]["returned_rows"] == 1000 and result["data"]["truncated"], result
        assert result["data"]["columns"] == ["product_id", "name"]
        plan = await s.sql.run(
            principal(), "explain", "SELECT * FROM shop.products WHERE product_id=1"
        )
        assert plan["data"]["estimates_only"], plan
        for kind in ("query_statistics", "locks", "table_sizes", "table_health"):
            report = await s.diagnostics.run(principal(), kind)
            assert "error" not in report, report

    with_services(run)


def test_byte_limit_and_request_policy():
    async def run(s):
        result = await s.sql.run(principal(), "query", "SELECT description FROM shop.products")
        assert result["data"]["truncation_reason"] == "bytes", result
        for sql in (
            "SELECT pg_sleep(1)",
            "SELECT 1; SELECT 2",
            "SELECT * FROM shop.orders FOR UPDATE",
        ):
            rejected = await s.sql.run(principal(), "query", sql)
            assert rejected["error"]["category"] == "policy_rejection", rejected

    with_services(run, result_bytes=256)


def test_pass_through_percent_and_colon_are_not_driver_parameters():
    async def run(s):
        result = await s.sql.run(
            principal(), "query", "SELECT '100%:name' AS marker, 5 % 2 AS remainder"
        )
        assert "error" not in result, result
        assert result["data"]["rows"] == [["100%:name", 1]], result
        write = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1 AND first_name LIKE '%'",
            Approver(),
        )
        assert write["outcome"] == "committed", write

    with_services(run)


def test_real_plan_cost_ceiling_prevents_approval():
    async def run(s):
        approver = Approver()
        result = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id > 0",
            approver,
        )
        assert result["error"]["category"] == "limits", result
        assert not approver.messages

    with_services(run, plan_cost=1)


def test_approved_declined_and_capped_writes():
    async def run(s):
        sql = "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1"
        declined = await s.sql.run(principal(), "execute", sql, Approver("declined"))
        assert declined["outcome"] == "declined"
        committed = await s.sql.run(principal(), "execute", sql, Approver())
        assert committed["outcome"] == "committed", committed
        capped = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name='cap-must-rollback' WHERE customer_id > 0",
            Approver(),
        )
        assert capped["outcome"] == "rolled_back", capped
        result = await s.sql.run(
            principal(),
            "query",
            "SELECT count(*) FROM shop.customers WHERE first_name='cap-must-rollback'",
        )
        assert result["data"]["rows"] == [[0]]

    with_services(run)


def test_procedure_hashes_arguments_inout_and_batch_shape():
    async def run(s):
        for entry in s.procedures.registry.values():
            entry.check_definition(await s.database.definition_hash(entry))
        # A very old cutoff exercises the internal-COMMIT call shape without archiving fixture rows.
        batch = await s.procedures.call(
            principal(),
            "archive_old_orders",
            {"p_before": "1900-01-01", "p_batch_size": 1, "p_max_batches": 1},
            Approver(),
        )
        assert batch["outcome"] == "committed", batch
        purge = await s.procedures.call(
            principal(), "purge_abandoned_carts", {"p_older_than_days": 36500}, Approver()
        )
        assert purge["outcome"] == "committed" and purge["data"]["output"] == [{"p_deleted": 0}], (
            purge
        )
        invalid = await s.procedures.call(principal(), "bulk_update_prices", {}, Approver())
        assert invalid["error"]["category"] == "invalid_arguments"

    with_services(run)


def test_audit_runtime_is_append_only_and_reader_cannot_write():
    with psycopg.connect(
        host="127.0.0.1",
        port=55439,
        dbname="mcp_audit",
        user="mcp_audit_runtime",
        password="test_audit",
    ) as conn:
        for statement in (
            "DELETE FROM audit.events",
            "UPDATE audit.operations SET tool='x'",
            "TRUNCATE audit.events",
            "SELECT * FROM audit.operations",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
            conn.rollback()
    from shopdb.db import connect

    with connect("mcp_reader", seed_settings(), autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only=off")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE shop.customers SET first_name=first_name WHERE customer_id=1")


def test_missing_audit_intent_prevents_database_work():
    async def run(s):
        result = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1",
            Approver(),
        )
        assert result["error"]["category"] == "audit_unavailability", result

    with_services(run, audit_password="deliberately-wrong")
