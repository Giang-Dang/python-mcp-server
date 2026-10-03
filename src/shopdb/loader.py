"""Compatibility imports; CLI wiring lives in bootstrap."""

from .adapters.postgres.seeding import truncate_all  # noqa: F401
from .bootstrap import run_seed  # noqa: F401
from .core.dataset.application import build_context  # noqa: F401
