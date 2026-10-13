"""Element-level diff engine for IFC building models."""

from importlib.metadata import PackageNotFoundError, version

from .config import CONFIG_FILENAME, Settings, load_settings
from .engine import filter_result, run_diff
from .quantities import quantity_delta
from .schemas import (
    SCHEMA_VERSION,
    ChangeType,
    DiffResult,
    DiffSummary,
    ElementDiff,
    MatchMethod,
    PropertyChange,
    QuantityDelta,
    QuantityDeltaRow,
    QuantityTotals,
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
    "QuantityDelta",
    "QuantityDeltaRow",
    "QuantityTotals",
    "Settings",
    "__version__",
    "filter_result",
    "load_settings",
    "quantity_delta",
    "run_diff",
]
