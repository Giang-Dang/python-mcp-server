"""Tests for the documentation generator (shopdb docs)."""

from __future__ import annotations

from shopdb.db import connect
from shopdb.docgen import generate, read_catalog


def test_every_column_of_every_table_has_a_description():
    # The data dictionary and the MCP server's model both depend on these comments.
    with connect("shop_owner", autocommit=True) as conn:
        cat = read_catalog(conn)
    base = [t["name"] for t in cat.tables if t["kind"] in ("r", "p")]
    missing = [
        f"{t}.{c['name']}" for t in base for c in cat.columns[t] if not (c["comment"] or "").strip()
    ]
    assert not missing, f"columns without COMMENT ON: {missing}"
    assert all(t["comment"] for t in cat.tables if t["kind"] in ("r", "p")), (
        "tables without comment"
    )


def test_the_dictionary_covers_all_tables_views_and_routines(tmp_path):
    generate(tmp_path)
    text = (tmp_path / "data-dictionary.md").read_text(encoding="utf-8")
    for table in ("orders", "audit_log", "order_items", "inventory_movements"):
        assert f"\n## {table}\n" in text
    assert "\n## v_order_summary\n" in text
    assert "| `create_order` | procedure |" in text
    assert "audit_log_2024_01" not in text, "partitions must be hidden behind their parent"
    assert "(no description)" not in text


def test_the_erd_has_one_line_per_foreign_key_and_is_a_mermaid_block(tmp_path):
    generate(tmp_path)
    erd = (tmp_path / "erd.md").read_text(encoding="utf-8")
    assert erd.count("```mermaid\nerDiagram\n") == 1
    with connect("shop_owner", autocommit=True) as conn:
        fk_count = conn.execute(
            """SELECT count(*) FROM pg_constraint con JOIN pg_class t ON t.oid = con.conrelid
               WHERE con.contype = 'f' AND con.connamespace = 'shop'::regnamespace
                 AND con.conparentid = 0 AND NOT t.relispartition"""
        ).fetchone()[0]
    relationship_lines = [ln for ln in erd.splitlines() if ln.startswith("    ") and "--o{" in ln]
    assert len(relationship_lines) == fk_count


def test_output_is_deterministic_and_ascii(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    generate(first)
    generate(second)
    for name in ("data-dictionary.md", "erd.md"):
        a = (first / name).read_bytes()
        assert a == (second / name).read_bytes()
        a.decode("ascii")  # project rule: ASCII only
