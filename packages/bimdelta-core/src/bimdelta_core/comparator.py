from __future__ import annotations

import math

import numpy as np

from ..config import Settings
from ..schemas.diff import (
    ChangeType,
    ElementDiff,
    MatchMethod,
    PropertyChange,
    PropertySource,
)
from .geometry import compute_geometry_signature, signatures_equal
from .parser import ParsedElement, ParsedModel, PropertyValue


def compare_matched(
    v1_el: ParsedElement,
    v2_el: ParsedElement,
    method: str,
    cfg: Settings,
    v1_model: ParsedModel | None = None,
    v2_model: ParsedModel | None = None,
) -> ElementDiff:
    prop_changes = _compare_properties(v1_el.properties, v2_el.properties, cfg.float_tolerance)

    placement_changed = _placement_changed(v1_el, v2_el, cfg)
    type_changed = v1_el.type_name != v2_el.type_name
    name_changed = v1_el.name != v2_el.name
    storey_changed = v1_el.storey != v2_el.storey

    already_modified = (
        bool(prop_changes) or placement_changed or type_changed
        or name_changed or storey_changed
    )

    geom_changed = False
    if not already_modified:
        ensure_geometry(v1_el, v1_model)
        ensure_geometry(v2_el, v2_model)
        geom_changed = not signatures_equal(
            v1_el.geometry_signature,
            v2_el.geometry_signature,
            cfg.geometry_bbox_tolerance,
            cfg.geometry_volume_tolerance,
        )

    is_modified = already_modified or geom_changed

    return ElementDiff(
        global_id=v2_el.global_id,
        ifc_class=v2_el.ifc_class,
        name=v2_el.name,
        storey=v2_el.storey,
        change_type=ChangeType.MODIFIED if is_modified else ChangeType.UNCHANGED,
        match_method=MatchMethod(method),
        matched_global_id=v1_el.global_id if v1_el.global_id != v2_el.global_id else None,
        property_changes=prop_changes,
        geometry_changed=geom_changed,
        placement_changed=placement_changed,
        type_changed=type_changed,
        name_changed=name_changed,
        storey_changed=storey_changed,
        old_name=v1_el.name if name_changed else None,
        old_storey=v1_el.storey if storey_changed else None,
        old_type_name=v1_el.type_name if type_changed else None,
        new_type_name=v2_el.type_name if type_changed else None,
    )


def build_added(el: ParsedElement) -> ElementDiff:
    return ElementDiff(
        global_id=el.global_id,
        ifc_class=el.ifc_class,
        name=el.name,
        storey=el.storey,
        change_type=ChangeType.ADDED,
    )


def build_removed(el: ParsedElement) -> ElementDiff:
    return ElementDiff(
        global_id=el.global_id,
        ifc_class=el.ifc_class,
        name=el.name,
        storey=el.storey,
        change_type=ChangeType.REMOVED,
    )


def build_unchanged(el: ParsedElement) -> ElementDiff:
    return ElementDiff(
        global_id=el.global_id,
        ifc_class=el.ifc_class,
        name=el.name,
        storey=el.storey,
        change_type=ChangeType.UNCHANGED,
    )


def _compare_properties(
    v1_props: list[PropertyValue],
    v2_props: list[PropertyValue],
    float_tol: float,
) -> list[PropertyChange]:
    v1_map = {(p.pset_name, p.property_name, p.source): p.value for p in v1_props}
    v2_map = {(p.pset_name, p.property_name, p.source): p.value for p in v2_props}

    all_keys = set(v1_map.keys()) | set(v2_map.keys())
    changes: list[PropertyChange] = []

    for key in sorted(all_keys):
        pset, prop, source = key
        old = v1_map.get(key)
        new = v2_map.get(key)

        if _values_equal(old, new, float_tol):
            continue

        changes.append(
            PropertyChange(
                pset_name=pset,
                property_name=prop,
                source=PropertySource(source),
                old_value=old,
                new_value=new,
            )
        )

    return changes


def _values_equal(
    a: str | float | int | bool | None,
    b: str | float | int | bool | None,
    float_tol: float,
) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if type(a) is bool or type(b) is bool:
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), abs_tol=float_tol)
    return a == b


def _placement_changed(
    v1_el: ParsedElement, v2_el: ParsedElement, cfg: Settings
) -> bool:
    m1 = v1_el.storey_relative_placement
    m2 = v2_el.storey_relative_placement

    # Fall back to world placement if no storey context
    if m1 is None or m2 is None:
        m1 = v1_el.world_placement
        m2 = v2_el.world_placement

    return not _matrices_close(
        m1, m2, cfg.placement_translation_tolerance, cfg.placement_rotation_tolerance_deg
    )


def _matrices_close(
    m1: np.ndarray,
    m2: np.ndarray,
    trans_tol: float,
    rot_tol_deg: float,
) -> bool:
    t1 = m1[:3, 3]
    t2 = m2[:3, 3]
    if float(np.linalg.norm(t1 - t2)) > trans_tol:
        return False

    r1 = m1[:3, :3]
    r2 = m2[:3, :3]
    r_diff = r1.T @ r2
    trace = float(np.trace(r_diff))
    trace_clamped = max(-1.0, min(3.0, trace))
    angle_rad = math.acos(max(-1.0, min(1.0, (trace_clamped - 1.0) / 2.0)))
    angle_deg = math.degrees(angle_rad)
    return angle_deg <= rot_tol_deg


def ensure_geometry(el: ParsedElement, model: ParsedModel | None) -> None:
    """Lazily compute geometry signature only when needed."""
    if el.geometry_signature is not None:
        return
    if model is None or model._ifc_file is None or el._ifc_entity_id is None:
        return
    try:
        ifc_entity = model._ifc_file.by_id(el._ifc_entity_id)
        qto_vol = _get_qto_volume_from_props(el.properties)
        el.geometry_signature = compute_geometry_signature(
            ifc_entity, model.unit_scale, qto_vol
        )
    except Exception:
        pass


def _get_qto_volume_from_props(props: list[PropertyValue]) -> float | None:
    for p in props:
        if p.property_name in ("NetVolume", "GrossVolume") and isinstance(p.value, float):
            return p.value
    return None
