"""Composition root for the seeder. No connections at import time."""

from .adapters.filesystem.documents import DocumentWriter
from .adapters.filesystem.scripts import scripts
from .adapters.multiprocessing.workers import Workers
from .adapters.postgres.catalog import read_catalog
from .adapters.postgres.connection import connect
from .adapters.postgres.seeding import SeedStore
from .adapters.postgres.verification import Verifier
from .core.documentation.application import generate as docs_workflow
from .core.maintenance.application import apply_post_load as maintenance_workflow
from .core.seeding.application import run_seed as seed_workflow
from .core.verification.application import run_verify as verify_workflow
from .settings import get_settings


def run_seed(scale, seed, workers, force=False, settings=None, log=print):
    selected = settings or get_settings()
    return seed_workflow(
        scale, seed, workers, force, store=SeedStore(selected), executor=Workers(selected), log=log
    )


def run_verify(scale, seed, settings=None):
    return verify_workflow(scale, seed, Verifier(settings or get_settings()))


def apply_post_load(only=None, settings=None, log=print):
    with connect("shop_owner", settings or get_settings()) as conn:

        def execute(sql):
            conn.execute(sql)
            conn.commit()

        return maintenance_workflow(scripts(only), execute, log)


def generate(out_dir, settings=None):
    with connect("shop_owner", settings or get_settings(), autocommit=True) as conn:
        return docs_workflow(lambda: read_catalog(conn), DocumentWriter(out_dir))
