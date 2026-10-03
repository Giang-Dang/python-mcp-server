import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import pytest
from support import seed_settings

from shopdb.adapters.multiprocessing.workers import _init_worker, _run_task
from shopdb.bootstrap import run_seed
from shopdb.core.dataset.application import build_context
from shopdb.core.dataset.scales import get_scale


@pytest.mark.integration
def test_spawned_worker_uses_explicit_settings_when_defaults_are_unreachable(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "9")
    context = build_context(get_scale("S"), 42)
    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_init_worker,
        initargs=(context, seed_settings()),
    ) as pool:
        # Empty chunk still opens the real worker connection and transaction; inserts no rows.
        kind, idx, counts, _ = pool.submit(_run_task, ("employees", 0, 1, 0)).result(timeout=20)
    assert kind == "employees" and idx == 0 and sum(counts.values()) == 0


@pytest.mark.integration
def test_seed_refuses_after_post_load_even_with_force():
    with pytest.raises(RuntimeError, match="Triggers exist"):
        run_seed(get_scale("S"), 42, 1, force=True, settings=seed_settings())
