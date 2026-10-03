"""Compatibility imports; CLI wiring lives in bootstrap."""

from .bootstrap import run_verify  # noqa: F401
from .core.verification.domain import Check, expected_counts  # noqa: F401
