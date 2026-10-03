import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from shopdb.adapters.generation import REGISTRY
from shopdb.adapters.postgres.connection import connect
from shopdb.adapters.postgres.seeding import copy_rows
from shopdb.core.dataset.context import SeedContext
from shopdb.settings import Settings

_CTX: SeedContext | None = None
_SETTINGS: Settings | None = None


def _init_worker(ctx: SeedContext, settings: Settings) -> None:
    global _CTX, _SETTINGS
    _CTX, _SETTINGS = ctx, settings


def _run_task(task: tuple[str, int, int, int]) -> tuple[str, int, dict[str, int], float]:
    """Runs inside a worker process: generate one chunk and load it in a single transaction."""
    kind, idx, lo, hi = task
    started = time.perf_counter()
    assert _CTX is not None and _SETTINGS is not None
    batches = REGISTRY[kind](_CTX, idx, lo, hi)
    counts: dict[str, int] = {}
    with connect("loader", _SETTINGS) as conn:
        # Do not wait for the WAL flush at commit: a crash during a seed just means we seed again.
        conn.execute("SET synchronous_commit = off")
        with conn.cursor() as cur:
            for table, columns, rows in batches:
                counts[table] = copy_rows(cur, table, columns, rows)
        conn.commit()
    return kind, idx, counts, time.perf_counter() - started


class Workers:
    def __init__(self, settings):
        self.settings = settings

    def open(self, ctx, workers):
        self.pool = ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(ctx, self.settings),
            mp_context=multiprocessing.get_context("spawn"),
        )
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.pool.shutdown(wait=True, cancel_futures=True)

    def run(self, tasks):
        futures = [self.pool.submit(_run_task, task) for task in tasks]
        for future in as_completed(futures):
            yield future.result()
