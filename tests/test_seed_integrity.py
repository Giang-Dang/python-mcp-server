"""Integration test: the seeded database must satisfy every check in shopdb.verify.

Skipped automatically when the database is not reachable or has not been seeded.
"""

import psycopg
import pytest

from shopdb.config import get_scale, get_settings
from shopdb.db import connect
from shopdb.verify import run_verify


@pytest.fixture(scope="module")
def seeded_scale():
    settings = get_settings()
    scale = get_scale(settings.shop_scale)
    try:
        with connect("loader") as conn:
            rows = conn.execute("SELECT count(*) FROM shop.orders").fetchone()[0]
    except psycopg.OperationalError:
        pytest.skip("database is not running (docker compose up -d --wait)")
    if rows == 0:
        pytest.skip("database is empty (poetry run shopdb seed)")
    return scale


def test_every_verify_check_passes(seeded_scale):
    failures = [c for c in run_verify(seeded_scale, get_settings().shop_seed) if not c.ok]
    assert not failures, "\n".join(f"{c.name}: {c.detail}" for c in failures)


def test_row_level_security_isolates_tenants(seeded_scale):
    with connect("mcp_reader") as conn:
        tenant_1 = conn.execute("SELECT count(*) FROM shop.orders").fetchone()[0]
        conn.execute("SET app.tenant_id = ''")
        none = conn.execute("SELECT count(*) FROM shop.orders").fetchone()[0]
    with connect("loader") as conn:
        total = conn.execute("SELECT count(*) FROM shop.orders").fetchone()[0]
    assert 0 < tenant_1 < total
    assert none == 0


def test_reader_cannot_write(seeded_scale):
    with connect("mcp_reader") as conn, pytest.raises(psycopg.Error):
        conn.execute("DELETE FROM shop.refunds WHERE false")
