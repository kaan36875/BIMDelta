from __future__ import annotations

import math

import numpy as np

from .config import Settings
from .geometry import (
    GeometrySignature,
    compute_geometry_signature,
    representation_fingerprint,
    signatures_equal,
)
from .noise import NO_FILTER, PropertyFilter
from .parser import ParsedElement, ParsedModel, PropertyValue, name_without_id
from .schemas import (
    ChangeType,
    ElementDiff,
    GeometrySummary,
    MatchMethod,
    PropertyChange,
    PropertySource,
)


def compare_matched(
    v1_el: ParsedElement,
    v2_el: ParsedElement,
    method: str,
    cfg: Settings,
    v1_model: ParsedModel | None = None,
    v2_model: ParsedModel | None = None,
    prop_filter: PropertyFilter = NO_FILTER,
) -> ElementDiff:
    prop_changes, ignored = _compare_properties(
        v1_el.properties, v2_el.properties, cfg.float_tolerance, prop_filter
    )

    placement_changed = _placement_changed(v1_el, v2_el, cfg)
    type_changed = v1_el.type_name != v2_el.type_name
    # A new Revit element id in the name is a new id, not a rename.
    name_changed = name_without_id(v1_el) != name_without_id(v2_el)
    storey_changed = v1_el.storey != v2_el.storey
    material_changed = v1_el.material != v2_el.material

    # The fingerprint check is cheap; tessellation only runs where the IFC geometry differs.
    geom_changed, geom_unknown = pair_geometry_state(v1_el, v2_el, v1_model, v2_model, cfg)

    is_modified = (
        bool(prop_changes)
        or placement_changed
        or type_changed
        or name_changed
        or storey_changed
        or material_changed
        or geom_changed
    )

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
        geometry_unknown=geom_unknown,
        placement_changed=placement_changed,
        type_changed=type_changed,
        name_changed=name_changed,
        storey_changed=storey_changed,
        ignored_property_changes=ignored,
        old_name=v1_el.name if name_changed else None,
        old_storey=v1_el.storey if storey_changed else None,
        old_type_name=v1_el.type_name if type_changed else None,
        new_type_name=v2_el.type_name if type_changed else None,
        material_changed=material_changed,
        old_material=v1_el.material if material_changed else None,
        new_material=v2_el.material if material_changed else None,
        old_geometry=_summary(v1_el.geometry_signature) if geom_changed else None,
        new_geometry=_summary(v2_el.geometry_signature) if geom_changed else None,
    )


def _summary(sig: GeometrySignature | None) -> GeometrySummary | None:
    if sig is None:
        return None
    return GeometrySummary(bbox_dims=sig.bbox_dims, volume=sig.volume, offset=sig.offset)


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


def pair_geometry_state(
    v1_el: ParsedElement,
    v2_el: ParsedElement,
    v1_model: ParsedModel | None,
    v2_model: ParsedModel | None,
    cfg: Settings,
) -> tuple[bool, bool]:
    if v1_model is not None and v2_model is not None:
        if same_geometry_source(v1_el, v2_el, v1_model, v2_model):
            return False, False
    ensure_pair_geometry(v1_el, v2_el, v1_model, v2_model)
    return geometry_state(v1_el, v2_el, cfg)


def same_geometry_source(
    v1_el: ParsedElement, v2_el: ParsedElement, v1_model: ParsedModel, v2_model: ParsedModel
) -> bool:
    """True if both elements are defined by identical IFC geometry, without tessellating."""
    if not math.isclose(v1_model.unit_scale, v2_model.unit_scale):
        return False
    return _fingerprint(v1_el, v1_model) == _fingerprint(v2_el, v2_model)


def _fingerprint(el: ParsedElement, model: ParsedModel) -> str | None:
    if el.geometry_fingerprint is None and model._ifc_file is not None:
        if el._ifc_entity_id is not None:
            entity = model._ifc_file.by_id(el._ifc_entity_id)
            el.geometry_fingerprint = representation_fingerprint(entity, model._fingerprint_memo)
    return el.geometry_fingerprint


def geometry_state(v1_el: ParsedElement, v2_el: ParsedElement, cfg: Settings) -> tuple[bool, bool]:
    """Return (changed, unknown). A missing signature without a failure means no representation."""
    if v1_el.geometry_failed or v2_el.geometry_failed:
        return False, True
    changed = not signatures_equal(
        v1_el.geometry_signature,
        v2_el.geometry_signature,
        cfg.geometry_bbox_tolerance,
        cfg.geometry_volume_tolerance,
    )
    return changed, False


def _compare_properties(
    v1_props: list[PropertyValue],
    v2_props: list[PropertyValue],
    float_tol: float,
    prop_filter: PropertyFilter,
) -> tuple[list[PropertyChange], int]:
    v1_map = {(p.pset_name, p.property_name, p.source): p.value for p in v1_props}
    v2_map = {(p.pset_name, p.property_name, p.source): p.value for p in v2_props}

    changes: list[PropertyChange] = []
    ignored = 0

    for key in sorted(set(v1_map) | set(v2_map)):
        pset, prop, source = key
        old = v1_map.get(key)
        new = v2_map.get(key)

        if _values_equal(old, new, float_tol):
            continue
        if prop_filter.is_ignored(pset, prop):
            ignored += 1
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

    return changes, ignored


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


def _placement_changed(v1_el: ParsedElement, v2_el: ParsedElement, cfg: Settings) -> bool:
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


def ensure_pair_geometry(
    v1_el: ParsedElement,
    v2_el: ParsedElement,
    v1_model: ParsedModel | None,
    v2_model: ParsedModel | None,
) -> None:
    v1_qto, v2_qto = pair_qto_volumes(v1_el, v2_el)
    ensure_geometry(v1_el, v1_model, v1_qto)
    ensure_geometry(v2_el, v2_model, v2_qto)


def ensure_geometry(
    el: ParsedElement, model: ParsedModel | None, qto_volume: float | None = None
) -> None:
    """Lazily compute the geometry signature; record a failure instead of hiding it."""
    if el.geometry_signature is not None or el.geometry_failed or not el.has_representation:
        return
    if model is None or model._ifc_file is None or el._ifc_entity_id is None:
        return
    ifc_entity = model._ifc_file.by_id(el._ifc_entity_id)
    signature = compute_geometry_signature(
        ifc_entity, model.unit_scale, qto_volume, el.world_placement
    )
    if signature is None:
        el.geometry_failed = True
    else:
        el.geometry_signature = signature


_VOLUME_QUANTITIES = ("NetVolume", "GrossVolume")


def pair_qto_volumes(
    v1_el: ParsedElement, v2_el: ParsedElement
) -> tuple[float | None, float | None]:
    """Exported volume quantities, used only when both sides carry the same one.

    Mixing an exported quantity on one side with a mesh-derived volume on the other would
    report a geometry change whenever "export base quantities" differs between exports.
    """
    v1_vols = _volume_quantities(v1_el.properties)
    v2_vols = _volume_quantities(v2_el.properties)
    for name in _VOLUME_QUANTITIES:
        if name in v1_vols and name in v2_vols:
            return v1_vols[name], v2_vols[name]
    return None, None


def _volume_quantities(props: list[PropertyValue]) -> dict[str, float]:
    return {
        p.property_name: p.value
        for p in props
        if p.property_name in _VOLUME_QUANTITIES and isinstance(p.value, float)
    }
