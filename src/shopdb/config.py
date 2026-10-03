"""Compatibility imports; CLI wiring lives in bootstrap."""

from .core.dataset.scales import SCALES, Scale, get_scale  # noqa: F401
from .settings import ROOT, Settings, get_settings  # noqa: F401
