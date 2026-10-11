from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ..config import Settings
from ..schemas.diff import (
    ChangeType,
    DiffResult,
    DiffSummary,
    ElementDiff,
    StoreyElevationChange,
)
from .comparator import build_added, build_removed, compare_matched, ensure_geometry
from .geometry import signatures_equal
from .matcher import match_elements
from .parser import ParsedElement, ParsedModel, parse_ifc


def run_diff(
    v1_path: str,
    v1_filename: str,
    v2_path: str,
    v2_filename: str,
    cfg: Settings,
) -> DiffResult:
    with ThreadPoolExecutor(max_workers=2) as pool:
        v1_future = pool.submit(parse_ifc, v1_path, v1_filename)
        v2_future = pool.submit(parse_ifc, v2_path, v2_filename)
        v1 = v1_future.result()
        v2 = v2_future.result()

    match_result = match_elements(v1, v2, cfg.fallback_placement_tolerance)

    elements: list[ElementDiff] = []
    pending_geom: list[tuple[int, ParsedElement, ParsedElement, str]] = []

    for v1_el, v2_el, method in match_result.matched:
        diff = compare_matched(v1_el, v2_el, method, cfg)
        elements.append(diff)
        if diff.change_type == ChangeType.UNCHANGED:
            pending_geom.append((len(elements) - 1, v1_el, v2_el, method))

    if pending_geom:
        _resolve_geometry_batch(pending_geom, v1, v2, cfg, elements)

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


def _resolve_geometry_batch(
    pending: list[tuple[int, ParsedElement, ParsedElement, str]],
    v1: ParsedModel,
    v2: ParsedModel,
    cfg: Settings,
    elements: list[ElementDiff],
) -> None:
    v1_els = [v1_el for _, v1_el, _, _ in pending]
    v2_els = [v2_el for _, _, v2_el, _ in pending]

    def compute_batch(els: list[ParsedElement], model: ParsedModel) -> None:
        for el in els:
            ensure_geometry(el, model)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(compute_batch, v1_els, v1)
        f2 = pool.submit(compute_batch, v2_els, v2)
        f1.result()
        f2.result()

    for idx, v1_el, v2_el, method in pending:
        geom_changed = not signatures_equal(
            v1_el.geometry_signature,
            v2_el.geometry_signature,
            cfg.geometry_bbox_tolerance,
            cfg.geometry_volume_tolerance,
        )
        if geom_changed:
            elements[idx] = compare_matched(v1_el, v2_el, method, cfg, v1, v2)


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
