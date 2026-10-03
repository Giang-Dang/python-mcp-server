"""Compatibility imports; CLI wiring lives in bootstrap."""

from .adapters.postgres.catalog import read_catalog  # noqa: F401
from .bootstrap import generate  # noqa: F401
from .core.documentation.application import render_dictionary, render_erd  # noqa: F401
from .core.documentation.domain import Catalog  # noqa: F401
