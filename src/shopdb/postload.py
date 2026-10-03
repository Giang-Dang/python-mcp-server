"""Compatibility imports; CLI wiring lives in bootstrap."""

from .adapters.filesystem.scripts import POST_LOAD_DIR, post_load_files  # noqa: F401
from .adapters.postgres.seeding import has_post_load_triggers  # noqa: F401
from .bootstrap import apply_post_load  # noqa: F401
