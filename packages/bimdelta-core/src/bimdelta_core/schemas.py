from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.3.0"


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class MatchMethod(str, Enum):
    GLOBAL_ID = "global_id"
    TAG = "tag"
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


class GeometrySummary(BaseModel):
    bbox_dims: tuple[float, float, float]  # m
    volume: float  # m³


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
    # Geometry could not be evaluated for at least one side, so it was not compared.
    geometry_unknown: bool = False
    placement_changed: bool = False
    type_changed: bool = False
    name_changed: bool = False
    storey_changed: bool = False
    material_changed: bool = False
    # Property differences hidden by the noise filter.
    ignored_property_changes: int = 0

    old_name: str | None = None
    old_storey: str | None = None
    old_type_name: str | None = None
    new_type_name: str | None = None
    old_material: str | None = None
    new_material: str | None = None
    # Bounding box and volume of both versions, when the geometry changed.
    old_geometry: GeometrySummary | None = None
    new_geometry: GeometrySummary | None = None


class StoreyElevationChange(BaseModel):
    storey_name: str
    old_elevation: float
    new_elevation: float


class OneSidedPset(BaseModel):
    pset_name: str
    only_in: Literal["v1", "v2"]
    element_count: int


class NoiseReport(BaseModel):
    strict: bool
    ignore_properties: list[str] = Field(default_factory=list)
    ignored_property_changes: int = 0
    # Property sets present in only one model, typically caused by different export settings.
    # Excluded from per-element comparison unless strict.
    one_sided_psets: list[OneSidedPset] = Field(default_factory=list)


class PropertyChangeCount(BaseModel):
    pset_name: str
    property_name: str
    element_count: int


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
    geometry_unknown: int = 0
    top_changed_properties: list[PropertyChangeCount] = Field(default_factory=list)
    noise: NoiseReport | None = None


class QuantityTotals(BaseModel):
    count: int = 0
    length: float = 0.0  # m
    area: float = 0.0  # m²
    volume: float = 0.0  # m³
    weight: float = 0.0  # kg


class QuantityDeltaRow(BaseModel):
    group: str
    v1: QuantityTotals
    v2: QuantityTotals
    delta: QuantityTotals


class QuantityReport(BaseModel):
    """Quantity take-off of both versions, grouped three ways.

    Totals come from the quantity sets in the files (e.g. Qto_WallBaseQuantities); nothing
    is measured from geometry. By material, the volume and weight of a layered or composite
    element are split by layer thickness (or constituent fraction), while its count, length
    and area count in full for each of its materials, so those columns do not add up to the
    total. ``*_without_quantities`` counts elements that carry no usable quantity, which
    usually means base quantities were not exported.
    """

    by_class: list[QuantityDeltaRow]
    by_material: list[QuantityDeltaRow]
    by_storey: list[QuantityDeltaRow]
    total: QuantityDeltaRow
    v1_without_quantities: int = 0
    v2_without_quantities: int = 0


class DiffResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    v1_filename: str
    v2_filename: str
    v1_ifc_schema: str
    v2_ifc_schema: str
    timestamp: datetime
    summary: DiffSummary
    elements: list[ElementDiff]
    # None when the take-off could not be read; the element diff is still complete.
    quantities: QuantityReport | None = None


class QuantityDelta(BaseModel):
    """One grouping of a :class:`QuantityReport`, as ``bimdelta quantities`` prints it."""

    schema_version: str = SCHEMA_VERSION
    v1_filename: str
    v2_filename: str
    group_by: Literal["class", "material", "storey"]
    rows: list[QuantityDeltaRow]
    total: QuantityDeltaRow
    v1_without_quantities: int = 0
    v2_without_quantities: int = 0
