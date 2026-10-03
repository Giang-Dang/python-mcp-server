import time
from collections import Counter
from collections.abc import Callable

from shopdb.core.dataset.application import STAGES, build_context, tasks
from shopdb.core.dataset.scales import Scale

from .ports import SeedStore, WorkerPool

Log = Callable[[str], None]


def run_seed(
    scale: Scale,
    seed: int,
    workers: int,
    force: bool = False,
    *,
    store: SeedStore,
    executor: WorkerPool,
    log: Log = print,
) -> dict[str, int]:
    """Load a complete dataset. Returns rows loaded per table."""
    started = time.perf_counter()
    loaded: Counter[str] = Counter()

    with store.session() as session:
        if session.has_triggers():
            raise RuntimeError(
                "Triggers exist in schema shop (db/post_load was applied). Loading would fire them for every row and "
                "corrupt the data. To re-seed, recreate the database volume (docker compose down -v; docker compose "
                "up -d --wait), then seed, then run `shopdb post-load`."
            )
        existing = session.has_data()
        if existing and not force:
            raise RuntimeError(
                "The database already has data. Use --force to truncate it first, or run `shopdb reset`."
            )
        if existing:
            log("Truncating existing data ...")
            session.truncate()

        t = time.perf_counter()
        log(f"Planning orders for scale {scale.name} (seed {seed}) ...")
        ctx = build_context(scale, seed)
        log(
            f"  planned {scale.orders:,} orders -> {ctx.totals['items']:,} lines, {ctx.totals['payments']:,} payments "
            f"({time.perf_counter() - t:.1f}s)"
        )

        t = time.perf_counter()
        loaded.update(session.load_static(ctx))
        log(
            f"Loaded lookups, tenants, categories, suppliers, warehouses ({time.perf_counter() - t:.1f}s)"
        )

    with executor.open(ctx, workers) as pool:
        for stage_name, kinds in STAGES:
            stage_tasks = [task for kind in kinds for task in tasks(ctx, kind)]
            log(f"Stage {stage_name}: {len(stage_tasks)} chunks on {workers} workers")
            stage_started = time.perf_counter()
            for done, (kind, idx, counts, secs) in enumerate(pool.run(stage_tasks), start=1):
                loaded.update(counts)
                log(
                    f"  [{done}/{len(stage_tasks)}] {kind} chunk {idx}: {sum(counts.values()):,} rows in {secs:.1f}s"
                )
            log(f"  stage finished in {time.perf_counter() - stage_started:.1f}s")

    with store.session() as session:
        n = session.reset_sequences()
        log(f"Reset {n} identity sequences")

    log(f"Done: {sum(loaded.values()):,} rows in {time.perf_counter() - started:.1f}s")
    return dict(loaded)
