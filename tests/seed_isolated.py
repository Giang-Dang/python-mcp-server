"""Run only against the separately provisioned shopmcp-test instance."""

from support import seed_settings

from shopdb.bootstrap import apply_post_load, run_seed, run_verify
from shopdb.core.dataset.scales import get_scale

if __name__ == "__main__":
    settings = seed_settings()
    loaded = run_seed(get_scale("S"), 42, 8, settings=settings)
    print(f"ISOLATED SEED: {sum(loaded.values()):,} rows")
    checks = run_verify(get_scale("S"), 42, settings=settings)
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}")
    assert all(c.ok for c in checks)
    apply_post_load(settings=settings)
