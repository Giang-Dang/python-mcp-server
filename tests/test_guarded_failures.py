"""Transaction failure injection and real timeout/cancellation tests."""

import asyncio
import time
from dataclasses import replace

import pytest
from fakes import Approver, principal
from sqlalchemy.ext.asyncio import AsyncTransaction
from support import seed_settings, server_settings

from mcp_server.bootstrap import build_services
from mcp_server.core.errors import Category, GuardError
from mcp_server.runtime import run_async
from shopdb.db import connect

pytestmark = pytest.mark.integration


def isolated(test, **options):
    async def run():
        services = build_services(server_settings(**options))
        try:
            await test(services)
        finally:
            for engine in services.database.engines.values():
                assert engine.pool.checkedout() == 0
            await services.close()

    run_async(run())


def test_commit_acknowledgement_loss_is_uncertain_without_retry(monkeypatch):
    async def run(s):
        real_commit = AsyncTransaction.commit
        commits = 0

        async def commit_then_disconnect(transaction):
            nonlocal commits
            if transaction.connection.engine is s.database.engines["mcp_writer"]:
                commits += 1
                await real_commit(transaction)
                raise ConnectionError("lost acknowledgement")
            return await real_commit(transaction)

        monkeypatch.setattr(AsyncTransaction, "commit", commit_then_disconnect)
        result = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1",
            Approver(),
        )
        assert result["outcome"] == "uncertain" and result["retry_safe"] is False, result
        assert commits == 1

    isolated(run)


def test_audit_failure_during_write_rolls_back(monkeypatch):
    async def run(s):
        store = s.sql.audit.store
        original = store.event

        async def fail_commit_intent(operation_id, kind, detail):
            if kind == "commit_intent":
                raise ConnectionError("audit disconnected")
            return await original(operation_id, kind, detail)

        monkeypatch.setattr(store, "event", fail_commit_intent)
        result = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name='audit-must-rollback' WHERE customer_id > 0 AND customer_id < 20",
            Approver(),
        )
        assert result["error"]["category"] == "audit_unavailability", result
        read = await s.sql.run(
            principal(),
            "query",
            "SELECT count(*) FROM shop.customers WHERE first_name='audit-must-rollback'",
        )
        assert read["data"]["rows"] == [[0]]

    isolated(run)


def test_audit_final_failure_preserves_confirmed_commit(monkeypatch):
    async def run(s):
        store = s.sql.audit.store
        original = store.event

        async def fail_outcome(operation_id, kind, detail):
            if kind == "outcome":
                raise ConnectionError("audit disconnected")
            return await original(operation_id, kind, detail)

        monkeypatch.setattr(store, "event", fail_outcome)
        result = await s.sql.run(
            principal(),
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1",
            Approver(),
        )
        assert result["outcome"] == "committed" and result["audit_status"] == "unavailable", result

    isolated(run)


def test_read_deadline_closes_stream():
    async def run(s):
        # Adapter-only probe: pg_sleep is intentionally unavailable through the SQL policy.
        with pytest.raises(GuardError) as caught:
            await s.database.query("SELECT pg_sleep(3)")
        assert caught.value.category == Category.LIMIT

    isolated(run, read_seconds=1)


def test_write_timeout_rolls_back():
    with connect("shop_owner", seed_settings()) as blocker:
        customer_id = blocker.execute(
            "SELECT customer_id FROM shop.customers WHERE tenant_id=1 LIMIT 1"
        ).fetchone()[0]
        blocker.execute(
            "SELECT 1 FROM shop.customers WHERE customer_id=%s FOR UPDATE", (customer_id,)
        )

        async def run(s):
            result = await s.sql.run(
                principal(),
                "execute",
                f"UPDATE shop.customers SET first_name=first_name WHERE customer_id={customer_id}",
                Approver(),
            )
            assert result["outcome"] == "rolled_back" and result["error"]["category"] == "limits", (
                result
            )

        isolated(run, write_seconds=1)
        blocker.rollback()


def test_cancelled_read_releases_connection():
    async def run(s):
        task = asyncio.create_task(s.database.query("SELECT pg_sleep(10)"))
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    isolated(run)


def test_expired_identity_after_approval_never_executes():
    async def run(s):
        caller = replace(principal(), expires_at=time.time() + 0.1)
        result = await s.sql.run(
            caller,
            "execute",
            "UPDATE shop.customers SET first_name=first_name WHERE customer_id=1",
            Approver(delay=0.2),
        )
        assert result["outcome"] != "committed", result

    isolated(run)


@pytest.mark.parametrize("mode", ["failure", "cancel"])
def test_real_archive_partial_commit_failure_is_reported(mode):
    # Test-only extra trigger fails the second one-row batch. Source definitions are untouched.
    with connect("shop_owner", seed_settings(), autocommit=True) as conn:
        ids = [
            r[0]
            for r in conn.execute("""
            SELECT order_id FROM shop.orders WHERE tenant_id=1 AND placed_at<'2025-01-01'
            AND deleted_at IS NULL AND status_id IN (5,6,7) ORDER BY order_id LIMIT 2
        """)
        ]
        assert len(ids) == 2
        interruption = (
            "RAISE EXCEPTION 'test second batch failure'"
            if mode == "failure"
            else "PERFORM pg_sleep(30)"
        )
        conn.execute(
            f"""
            CREATE FUNCTION shop.test_archive_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.order_id = {ids[1]} AND NEW.deleted_at IS NOT NULL THEN
                    {interruption};
                END IF;
                RETURN NEW;
            END $$;
        """
        )
        conn.execute(
            "CREATE TRIGGER zz_test_archive_failure BEFORE UPDATE ON shop.orders FOR EACH ROW EXECUTE FUNCTION shop.test_archive_failure()"
        )
        try:

            async def run(s):
                task = asyncio.create_task(
                    s.procedures.call(
                        principal(),
                        "archive_old_orders",
                        {"p_before": "2025-01-01", "p_batch_size": 1, "p_max_batches": 2},
                        Approver(),
                    )
                )
                if mode == "cancel":
                    with connect("postgres", seed_settings(), autocommit=True) as observer:
                        for _ in range(200):
                            sleeping = observer.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE usename='mcp_writer' AND wait_event='PgSleep'"
                            ).fetchone()[0]
                            if sleeping or task.done():
                                break
                            await asyncio.sleep(0.01)
                    if task.done():
                        assert False, await task
                    assert sleeping, "Test procedure never reached its second batch"
                    task.cancel()
                result = await task
                assert (
                    result["outcome"] == "partially_completed" and result["retry_safe"] is False
                ), result

            isolated(run)
            rows = conn.execute(
                "SELECT order_id, deleted_at IS NOT NULL FROM shop.orders WHERE order_id=ANY(%s) ORDER BY order_id",
                (ids,),
            ).fetchall()
            assert rows == [(ids[0], True), (ids[1], False)]
        finally:
            conn.execute("DROP TRIGGER zz_test_archive_failure ON shop.orders")
            conn.execute("DROP FUNCTION shop.test_archive_failure()")
            conn.execute("UPDATE shop.orders SET deleted_at=NULL WHERE order_id=ANY(%s)", (ids,))


def test_registry_live_drift_rejected_and_restored():
    with connect("shop_owner", seed_settings(), autocommit=True) as conn:
        signature = "shop.cancel_order(bigint)"
        original = conn.execute(
            "SELECT pg_get_functiondef(%s::regprocedure)", (signature,)
        ).fetchone()[0]
        conn.execute(
            "CREATE OR REPLACE PROCEDURE shop.cancel_order(p_order_id bigint) LANGUAGE plpgsql AS $$BEGIN NULL; END$$"
        )
        try:

            async def run(s):
                result = await s.procedures.call(
                    principal(), "cancel_order", {"p_order_id": 1}, Approver()
                )
                assert result["error"]["category"] == "registry_mismatch", result

            isolated(run)
        finally:
            conn.execute(original)
