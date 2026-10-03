"""Compatibility imports; CLI wiring lives in bootstrap."""

from .adapters.postgres.connection import connect  # noqa: F401
