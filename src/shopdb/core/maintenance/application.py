import time
from collections.abc import Callable, Sequence


def apply_post_load(
    scripts: Sequence[tuple[str, str]],
    execute: Callable[[str], None],
    log: Callable[[str], None] = print,
) -> int:
    if not scripts:
        raise RuntimeError("No post-load file matches the selected prefix")
    for name, sql in scripts:
        started = time.perf_counter()
        execute(sql)
        log(f"applied {name} ({time.perf_counter() - started:.1f}s)")
    return len(scripts)
