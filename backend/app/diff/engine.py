from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from ..config import Settings
from ..schemas.diff import (
    ChangeType,
    DiffResult,
    DiffSummary,
    ElementDiff,
    StoreyElevationChange,
)
from .comparator import build_added, build_removed, compare_matched
from .matcher import match_elements
from .parser import ParsedModel, parse_ifc


def run_diff(
    v1_path: str,
    v1_filename: str,
    v2_path: str,
    v2_filename: str,
    cfg: Settings,
) -> DiffResult:
    v1 = parse_ifc(v1_path, v1_filename)
    v2 = parse_ifc(v2_path, v2_filename)

    match_result = match_elements(v1, v2, cfg.fallback_placement_tolerance)

    elements: list[ElementDiff] = []

    for v1_el, v2_el, method in match_result.matched:
        elements.append(compare_matched(v1_el, v2_el, method, cfg, v1, v2))

    for el in match_result.added:
        elements.append(build_added(el))

    for el in match_result.removed:
        elements.append(build_removed(el))

    storey_changes = _compute_storey_elevation_changes(v1, v2)
    summary = _build_summary(v1, v2, elements, storey_changes)

    return DiffResult(
        v1_filename=v1_filename,
        v2_filename=v2_filename,
        v1_ifc_schema=v1.ifc_schema,
        v2_ifc_schema=v2.ifc_schema,
        timestamp=datetime.now(timezone.utc),
        summary=summary,
        elements=elements,
    )


def _build_summary(
    v1: ParsedModel,
    v2: ParsedModel,
    elements: list[ElementDiff],
    storey_changes: list[StoreyElevationChange],
) -> DiffSummary:
    counts = defaultdict(int)
    by_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_storey: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for el in elements:
        ct = el.change_type.value
        counts[ct] += 1
        by_class[el.ifc_class][ct] += 1
        storey_key = el.storey or "(no storey)"
        by_storey[storey_key][ct] += 1

    return DiffSummary(
        total_v1=len(v1.elements),
        total_v2=len(v2.elements),
        added=counts.get("added", 0),
        removed=counts.get("removed", 0),
        modified=counts.get("modified", 0),
        unchanged=counts.get("unchanged", 0),
        by_class=dict(by_class),
        by_storey=dict(by_storey),
        storey_elevation_changes=storey_changes,
    )


def _compute_storey_elevation_changes(
    v1: ParsedModel, v2: ParsedModel
) -> list[StoreyElevationChange]:
    changes: list[StoreyElevationChange] = []
    common_storeys = set(v1.storeys.keys()) & set(v2.storeys.keys())
    for name in sorted(common_storeys):
        old_elev = v1.storeys[name]
        new_elev = v2.storeys[name]
        if abs(old_elev - new_elev) > 1e-6:
            changes.append(
                StoreyElevationChange(
                    storey_name=name,
                    old_elevation=old_elev,
                    new_elevation=new_elev,
                )
            )
    return changes
