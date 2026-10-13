from __future__ import annotations

import threading
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

from .comparator import build_added, build_removed, compare_matched
from .config import Settings
from .matcher import match_elements
from .noise import build_property_filter, find_one_sided_psets
from .parser import ParsedModel, parse_ifc
from .schemas import (
    DiffResult,
    DiffSummary,
    ElementDiff,
    NoiseReport,
    OneSidedPset,
    PropertyChangeCount,
    StoreyElevationChange,
)

TOP_CHANGED_PROPERTIES = 20


# IfcOpenShell is not safe to use from several threads at once: parallel ifcopenshell.open()
# calls intermittently fail to parse the header or crash the process. Diffs run one at a time.
IFC_LOCK = threading.Lock()


def run_diff(
    v1_path: str,
    v1_filename: str,
    v2_path: str,
    v2_filename: str,
    cfg: Settings | None = None,
) -> DiffResult:
    cfg = cfg if cfg is not None else Settings()

    with IFC_LOCK:
        v1 = parse_ifc(v1_path, v1_filename, cfg.include_openings)
        v2 = parse_ifc(v2_path, v2_filename, cfg.include_openings)

        one_sided = [] if cfg.strict else find_one_sided_psets(v1, v2)
        prop_filter = build_property_filter(cfg, one_sided)

        match_result = match_elements(v1, v2, cfg.fallback_placement_tolerance)

        elements: list[ElementDiff] = [
            compare_matched(v1_el, v2_el, method, cfg, v1, v2, prop_filter=prop_filter)
            for v1_el, v2_el, method in match_result.matched
        ]

    for el in match_result.added:
        elements.append(build_added(el))

    for el in match_result.removed:
        elements.append(build_removed(el))

    storey_changes = _compute_storey_elevation_changes(v1, v2)
    summary = _build_summary(v1, v2, elements, storey_changes, cfg, one_sided)

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
    cfg: Settings,
    one_sided: list[OneSidedPset],
) -> DiffSummary:
    noise = NoiseReport(
        strict=cfg.strict,
        ignore_properties=[] if cfg.strict else list(cfg.ignore_properties),
        ignored_property_changes=0,
        one_sided_psets=one_sided,
    )
    summary = DiffSummary(
        total_v1=len(v1.elements),
        total_v2=len(v2.elements),
        added=0,
        removed=0,
        modified=0,
        unchanged=0,
        by_class={},
        by_storey={},
        storey_elevation_changes=storey_changes,
        noise=noise,
    )
    return _tally(summary, elements)


def filter_result(result: DiffResult, keep: Callable[[ElementDiff], bool]) -> DiffResult:
    """A copy of ``result`` with only the elements ``keep`` accepts, and the summary counts
    recomputed for them. Model totals, storey elevation changes and the noise settings are
    properties of the two models and stay as they are."""
    elements = [el for el in result.elements if keep(el)]
    summary = _tally(result.summary.model_copy(deep=True), elements)
    return result.model_copy(update={"summary": summary, "elements": elements})


def _tally(summary: DiffSummary, elements: list[ElementDiff]) -> DiffSummary:
    """Fill the per-element counts of ``summary`` from ``elements``."""
    counts: Counter[str] = Counter()
    by_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_storey: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    changed_props: Counter[tuple[str, str]] = Counter()

    for el in elements:
        ct = el.change_type.value
        counts[ct] += 1
        by_class[el.ifc_class][ct] += 1
        by_storey[el.storey or "(no storey)"][ct] += 1
        changed_props.update({(p.pset_name, p.property_name) for p in el.property_changes})

    summary.added = counts["added"]
    summary.removed = counts["removed"]
    summary.modified = counts["modified"]
    summary.unchanged = counts["unchanged"]
    summary.by_class = {k: dict(v) for k, v in by_class.items()}
    summary.by_storey = {k: dict(v) for k, v in by_storey.items()}
    summary.geometry_unknown = sum(1 for el in elements if el.geometry_unknown)
    summary.top_changed_properties = [
        PropertyChangeCount(pset_name=pset, property_name=prop, element_count=n)
        for (pset, prop), n in sorted(changed_props.items(), key=lambda kv: (-kv[1], kv[0]))[
            :TOP_CHANGED_PROPERTIES
        ]
    ]
    if summary.noise is not None:
        summary.noise.ignored_property_changes = sum(el.ignored_property_changes for el in elements)
    return summary


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
