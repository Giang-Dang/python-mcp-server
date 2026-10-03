"""Apply the SQL files in db/post_load (indexes, functions, triggers, procedures, statistics, grants).

Each file runs as shop_owner in its own transaction, so a failing file leaves nothing half-applied. The files
are written to be re-runnable (IF NOT EXISTS, CREATE OR REPLACE, DROP TRIGGER IF EXISTS).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .config import ROOT, Settings, get_settings
from .db import connect

POST_LOAD_DIR = ROOT / "db" / "post_load"

Log = Callable[[str], None]


def post_load_files(only: str | None = None) -> list[Path]:
    files = sorted(POST_LOAD_DIR.glob("*.sql"))
    if only:
        files = [f for f in files if f.name.startswith(only)]
    return files


def apply_post_load(
    only: str | None = None, settings: Settings | None = None, log: Log = print
) -> int:
    """Run the selected files in name order. Returns how many were applied."""
    files = post_load_files(only)
    if not files:
        raise RuntimeError(f"No post-load file matches {only!r} in {POST_LOAD_DIR}")
    with connect("shop_owner", settings or get_settings()) as conn:
        for path in files:
            started = time.perf_counter()
            conn.execute(path.read_text(encoding="utf-8"))
            conn.commit()
            log(f"applied {path.name} ({time.perf_counter() - started:.1f}s)")
    return len(files)


def has_post_load_triggers(conn) -> bool:
    """True when user triggers exist in schema shop (foreign-key triggers are internal and ignored)."""
    row = conn.execute(
        """
        SELECT count(*) FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'shop' AND NOT t.tgisinternal
        """
    ).fetchone()
    return row[0] > 0
