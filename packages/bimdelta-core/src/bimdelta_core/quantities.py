"""Quantity take-off totals per class or material, and their change between two models.

A skeleton: totals are read from the quantity sets an authoring tool exported, using the
first quantity name found from each list below. Measuring from geometry and per-material
splits of layered elements are left for later.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

from .engine import IFC_LOCK
from .parser import EXCLUDED_CLASSES
from .schemas import QuantityDelta, QuantityDeltaRow, QuantityTotals

GroupBy = Literal["class", "material"]

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

NO_MATERIAL = "(no material)"


def quantity_delta(
    v1_path: str,
    v1_filename: str,
    v2_path: str,
    v2_filename: str,
    group_by: GroupBy = "class",
) -> QuantityDelta:
    with IFC_LOCK:
        v1, v1_missing = take_off(ifcopenshell.open(v1_path), group_by)
        v2, v2_missing = take_off(ifcopenshell.open(v2_path), group_by)

    rows = [_row(group, v1.get(group), v2.get(group)) for group in sorted(set(v1) | set(v2))]
    total = _row("Total", _sum(v1.values()), _sum(v2.values()))
    return QuantityDelta(
        v1_filename=v1_filename,
        v2_filename=v2_filename,
        group_by=group_by,
        rows=rows,
        total=total,
        v1_without_quantities=v1_missing,
        v2_without_quantities=v2_missing,
    )


def take_off(
    ifc_file: ifcopenshell.file, group_by: GroupBy
) -> tuple[dict[str, QuantityTotals], int]:
    """Totals per group, and the number of elements without any usable quantity."""
    scale = ifcopenshell.util.unit.calculate_unit_scale(ifc_file)
    totals: dict[str, QuantityTotals] = defaultdict(QuantityTotals)
    missing = 0

    for element in ifc_file.by_type("IfcElement"):
        if any(element.is_a(cls) for cls in EXCLUDED_CLASSES):
            continue
        group = element.is_a() if group_by == "class" else _material_name(element)
        row = totals[group]
        row.count += 1

        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        length = _first(qtos, LENGTH_NAMES)
        area = _first(qtos, AREA_NAMES)
        volume = _first(qtos, VOLUME_NAMES)
        if length is None and area is None and volume is None:
            missing += 1
            continue
        row.length += (length or 0.0) * scale
        row.area += (area or 0.0) * scale**2
        row.volume += (volume or 0.0) * scale**3

    return dict(totals), missing


def _first(qtos: dict[str, dict], names: tuple[str, ...]) -> float | None:
    for name in names:
        for qto in qtos.values():
            value = qto.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _material_name(element) -> str:
    material = ifcopenshell.util.element.get_material(element, should_skip_usage=True)
    if material is None:
        return NO_MATERIAL
    for attr in ("Name", "LayerSetName"):
        name = getattr(material, attr, None)
        if name:
            return name
    return material.is_a()


def _sum(rows) -> QuantityTotals:
    total = QuantityTotals()
    for row in rows:
        total.count += row.count
        total.length += row.length
        total.area += row.area
        total.volume += row.volume
    return total


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
        ),
    )
