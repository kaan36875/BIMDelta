"""Quantity take-off totals per class, material or storey, and their change between two models.

Totals are read from the quantity sets an authoring tool exported (Revit: "Export base
quantities"), using the first quantity name found from each list below; nothing is
measured from geometry. Units follow the file's own unit assignment.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

from .parser import EXCLUDED_CLASSES
from .schemas import QuantityDelta, QuantityDeltaRow, QuantityReport, QuantityTotals

GroupBy = Literal["class", "material", "storey"]

LENGTH_NAMES = ("Length", "NetLength", "GrossLength")
AREA_NAMES = (
    "NetSideArea",
    "GrossSideArea",
    "NetArea",
    "GrossArea",
    "NetFootprintArea",
    "GrossFootprintArea",
    "NetSurfaceArea",
    "GrossSurfaceArea",
    "CrossSectionArea",
)
VOLUME_NAMES = ("NetVolume", "GrossVolume", "Volume")
WEIGHT_NAMES = ("NetWeight", "GrossWeight", "Weight")

NO_MATERIAL = "(no material)"
NO_STOREY = "(no storey)"


@dataclass
class Measured:
    """One element's quantities in metres, square metres, cubic metres and kilograms."""

    ifc_class: str
    storey: str
    # (material name, share of the element's volume), shares summing to 1.
    materials: list[tuple[str, float]] = field(default_factory=list)
    length: float = 0.0
    area: float = 0.0
    volume: float = 0.0
    weight: float = 0.0
    has_quantities: bool = False


def quantity_delta(
    v1_path: str,
    v1_filename: str,
    v2_path: str,
    v2_filename: str,
    group_by: GroupBy = "class",
) -> QuantityDelta:
    from .engine import IFC_LOCK  # engine imports this module

    with IFC_LOCK:
        report = quantity_report(ifcopenshell.open(v1_path), ifcopenshell.open(v2_path))
    return QuantityDelta(
        v1_filename=v1_filename,
        v2_filename=v2_filename,
        group_by=group_by,
        rows=getattr(report, f"by_{group_by}"),
        total=report.total,
        v1_without_quantities=report.v1_without_quantities,
        v2_without_quantities=report.v2_without_quantities,
    )


def quantity_report(v1: ifcopenshell.file, v2: ifcopenshell.file) -> QuantityReport:
    """Take-off of two open models. The caller holds :data:`IFC_LOCK`."""
    m1, m2 = measure(v1), measure(v2)
    return QuantityReport(
        by_class=_rows(take_off(m1, "class"), take_off(m2, "class")),
        by_material=_rows(take_off(m1, "material"), take_off(m2, "material")),
        by_storey=_rows(take_off(m1, "storey"), take_off(m2, "storey")),
        total=_row("Total", _total(m1), _total(m2)),
        v1_without_quantities=sum(1 for m in m1 if not m.has_quantities),
        v2_without_quantities=sum(1 for m in m2 if not m.has_quantities),
    )


def measure(ifc_file: ifcopenshell.file) -> list[Measured]:
    length_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc_file)
    assigned = _assigned_units(ifc_file)
    area_scale = _scale(ifc_file, assigned, "AREAUNIT", length_scale**2)
    volume_scale = _scale(ifc_file, assigned, "VOLUMEUNIT", length_scale**3)
    # calculate_unit_scale gives mass in grams; without a mass unit, assume kilograms.
    weight_scale = _scale(ifc_file, assigned, "MASSUNIT", 1000.0) / 1000.0

    out = []
    for element in ifc_file.by_type("IfcElement"):
        if any(element.is_a(cls) for cls in EXCLUDED_CLASSES):
            continue
        m = Measured(
            ifc_class=element.is_a(),
            storey=_storey_name(element),
            materials=material_shares(element),
        )
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        values = [_first(qtos, names) for names in (LENGTH_NAMES, AREA_NAMES, VOLUME_NAMES)]
        weight = _first(qtos, WEIGHT_NAMES)
        m.has_quantities = any(v is not None for v in (*values, weight))
        length, area, volume = (v or 0.0 for v in values)
        m.length = length * length_scale
        m.area = area * area_scale
        m.volume = volume * volume_scale
        m.weight = (weight or 0.0) * weight_scale
        out.append(m)
    return out


def take_off(measured: Iterable[Measured], group_by: GroupBy) -> dict[str, QuantityTotals]:
    totals: dict[str, QuantityTotals] = defaultdict(QuantityTotals)
    for m in measured:
        if group_by == "material":
            for name, share in m.materials:
                _add(totals[name], m, share)
        else:
            _add(totals[m.ifc_class if group_by == "class" else m.storey], m, 1.0)
    return dict(totals)


def material_shares(element) -> list[tuple[str, float]]:
    """Each material of an element with its share of the volume: layers by thickness,
    constituents by their fraction, otherwise equal shares."""
    try:
        material = ifcopenshell.util.element.get_material(element, should_skip_usage=True)
    except Exception:
        material = None
    if material is None:
        return [(NO_MATERIAL, 1.0)]

    if material.is_a("IfcMaterialLayerSet"):
        parts = [(layer.Material, layer.LayerThickness) for layer in material.MaterialLayers or ()]
    elif material.is_a("IfcMaterialConstituentSet"):
        parts = [(c.Material, c.Fraction) for c in material.MaterialConstituents or ()]
    elif material.is_a("IfcMaterialProfileSet"):
        parts = [(p.Material, None) for p in material.MaterialProfiles or ()]
    elif material.is_a("IfcMaterialList"):
        parts = [(m, None) for m in material.Materials or ()]
    else:
        parts = [(material, None)]
    if not parts:
        return [(NO_MATERIAL, 1.0)]

    weights = [w for _, w in parts]
    if any(w is None or w < 0 for w in weights) or sum(weights) <= 0:
        weights = [1.0] * len(parts)
    total = sum(weights)
    shares: dict[str, float] = defaultdict(float)
    for (mat, _), w in zip(parts, weights):
        shares[_material_name(mat)] += w / total
    return list(shares.items())


def _material_name(material) -> str:
    if material is None:
        return NO_MATERIAL
    return getattr(material, "Name", None) or "(unnamed material)"


def _storey_name(element) -> str:
    try:
        container = ifcopenshell.util.element.get_container(element)
        # An element in a space belongs to the space's storey.
        for _ in range(8):
            if container is None or container.is_a("IfcBuildingStorey"):
                break
            container = ifcopenshell.util.element.get_container(container)
    except Exception:
        container = None
    if container is None:
        return NO_STOREY
    return container.Name or container.GlobalId


def _assigned_units(ifc_file: ifcopenshell.file) -> set[str]:
    projects = ifc_file.by_type("IfcProject")
    units = projects[0].UnitsInContext if projects else None
    return {getattr(u, "UnitType", None) for u in (units.Units if units else ())} - {None}


def _scale(ifc_file, assigned: set[str], unit_type: str, fallback: float) -> float:
    if unit_type not in assigned:
        return fallback
    return ifcopenshell.util.unit.calculate_unit_scale(ifc_file, unit_type)


def _first(qtos: dict[str, dict], names: tuple[str, ...]) -> float | None:
    for name in names:
        for qto in qtos.values():
            value = qto.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _add(row: QuantityTotals, m: Measured, share: float) -> None:
    row.count += 1
    row.length += m.length
    row.area += m.area
    row.volume += m.volume * share
    row.weight += m.weight * share


def _total(measured: list[Measured]) -> QuantityTotals:
    total = QuantityTotals()
    for m in measured:
        _add(total, m, 1.0)
    return total


def _rows(v1: dict[str, QuantityTotals], v2: dict[str, QuantityTotals]) -> list[QuantityDeltaRow]:
    return [_row(group, v1.get(group), v2.get(group)) for group in sorted(set(v1) | set(v2))]


def _row(group: str, v1: QuantityTotals | None, v2: QuantityTotals | None) -> QuantityDeltaRow:
    v1 = v1 or QuantityTotals()
    v2 = v2 or QuantityTotals()
    return QuantityDeltaRow(
        group=group,
        v1=v1,
        v2=v2,
        delta=QuantityTotals(
            count=v2.count - v1.count,
            length=v2.length - v1.length,
            area=v2.area - v1.area,
            volume=v2.volume - v1.volume,
            weight=v2.weight - v1.weight,
        ),
    )
