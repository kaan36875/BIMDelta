"""Command-line interface and Git integration for BIMDelta."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bimdelta")
except PackageNotFoundError:
    __version__ = "0.0.0"
