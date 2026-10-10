from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class MatchMethod(str, Enum):
    GLOBAL_ID = "global_id"
    FALLBACK = "fallback"


class PropertySource(str, Enum):
    OCCURRENCE = "occurrence"
    TYPE = "type"


class PropertyChange(BaseModel):
    pset_name: str
    property_name: str
    source: PropertySource
    old_value: str | float | int | bool | None = None
    new_value: str | float | int | bool | None = None


class ElementDiff(BaseModel):
    global_id: str
    ifc_class: str
    name: str | None = None
    storey: str | None = None
    change_type: ChangeType

    match_method: MatchMethod | None = None
    matched_global_id: str | None = None

    property_changes: list[PropertyChange] = Field(default_factory=list)
    geometry_changed: bool = False
    placement_changed: bool = False
    type_changed: bool = False
    name_changed: bool = False
    storey_changed: bool = False

    old_name: str | None = None
    old_storey: str | None = None
    old_type_name: str | None = None
    new_type_name: str | None = None


class StoreyElevationChange(BaseModel):
    storey_name: str
    old_elevation: float
    new_elevation: float


class DiffSummary(BaseModel):
    total_v1: int
    total_v2: int
    added: int
    removed: int
    modified: int
    unchanged: int
    by_class: dict[str, dict[str, int]]
    by_storey: dict[str, dict[str, int]]
    storey_elevation_changes: list[StoreyElevationChange] = Field(default_factory=list)


class DiffResult(BaseModel):
    schema_version: str = "1.0.0"
    v1_filename: str
    v2_filename: str
    v1_ifc_schema: str
    v2_ifc_schema: str
    timestamp: datetime
    summary: DiffSummary
    elements: list[ElementDiff]
