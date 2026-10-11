from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_FILENAME = ".bimdelta.yml"

# Matched against "<property set>.<property>" with fnmatch-style wildcards.
DEFAULT_IGNORE_PROPERTIES: tuple[str, ...] = (
    # Revit worksharing: the user currently holding the element, not a model property.
    "*.Edited by",
)


class Settings(BaseSettings):
    # All lengths in metres
    float_tolerance: float = 1e-5
    placement_translation_tolerance: float = 0.001
    placement_rotation_tolerance_deg: float = 0.01
    fallback_placement_tolerance: float = 0.050
    geometry_bbox_tolerance: float = 0.001
    geometry_volume_tolerance: float = 1e-6  # m³

    include_openings: bool = False

    # Disables every noise rule: ignore patterns and one-sided property set handling.
    strict: bool = False
    ignore_properties: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE_PROPERTIES))

    model_config = SettingsConfigDict(env_prefix="BIMDELTA_", env_file=".env", extra="ignore")


def load_settings(config_path: str | Path | None = None, **overrides: Any) -> Settings:
    """Build settings from defaults, BIMDELTA_* env vars, an optional YAML file and overrides.

    Precedence (highest first): overrides, YAML file, environment, defaults.
    """
    data: dict[str, Any] = {}
    if config_path is not None:
        data.update(_read_config_file(Path(config_path)))
    data.update(overrides)
    return Settings(**data)


def _read_config_file(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")

    known = set(Settings.model_fields)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(
            f"{path}: unknown setting(s) {', '.join(unknown)}. "
            f"Valid settings: {', '.join(sorted(known))}"
        )
    return raw
