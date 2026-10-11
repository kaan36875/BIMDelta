"""Element-level diff engine for IFC building models."""

from importlib.metadata import PackageNotFoundError, version

from .config import CONFIG_FILENAME, Settings, load_settings
from .engine import run_diff
from .schemas import (
    SCHEMA_VERSION,
    ChangeType,
    DiffResult,
    DiffSummary,
    ElementDiff,
    MatchMethod,
    PropertyChange,
)

try:
    __version__ = version("bimdelta-core")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "CONFIG_FILENAME",
    "SCHEMA_VERSION",
    "ChangeType",
    "DiffResult",
    "DiffSummary",
    "ElementDiff",
    "MatchMethod",
    "PropertyChange",
    "Settings",
    "__version__",
    "load_settings",
    "run_diff",
]
