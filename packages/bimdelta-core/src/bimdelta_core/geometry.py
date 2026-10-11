from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import ifcopenshell
import numpy as np

logger = logging.getLogger(__name__)

_BODY_IDENTIFIERS = ("Body", "Facetation")


@dataclass(frozen=True)
class GeometrySignature:
    bbox_dims: tuple[float, float, float]  # width, height, depth in metres
    volume: float  # cubic metres


_cached_geom_settings = None


def _get_geom_settings():
    global _cached_geom_settings
    if _cached_geom_settings is not None:
        return _cached_geom_settings
    import ifcopenshell.geom

    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    try:
        s.set(s.MESHER_LINEAR_DEFLECTION, 0.01)
    except Exception:
        pass
    _cached_geom_settings = s
    return s


def body_representation(element):
    """The 3D body representation of a product.

    Elements commonly carry an 'Axis' or 'FootPrint' representation next to 'Body'; left to
    choose, IfcOpenShell may pick the 2D one and fail.
    """
    shape = element.Representation
    if shape is None:
        return None
    reps = shape.Representations or ()
    for identifier in _BODY_IDENTIFIERS:
        for rep in reps:
            if rep.RepresentationIdentifier == identifier:
                return rep
    return reps[0] if len(reps) == 1 else None


def compute_geometry_signature(
    element, unit_scale: float, qto_volume: float | None = None
) -> GeometrySignature | None:
    """Compute bbox dims + volume. ifcopenshell.geom already normalises vertices
    to metres, so we do NOT re-apply unit_scale to geometry output."""
    try:
        import ifcopenshell.geom

        shape = ifcopenshell.geom.create_shape(
            _get_geom_settings(), element, body_representation(element)
        )
        verts = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)

        bbox_min = verts.min(axis=0)
        bbox_max = verts.max(axis=0)
        dims = bbox_max - bbox_min
        bbox_dims = (float(dims[0]), float(dims[1]), float(dims[2]))

        if qto_volume is not None:
            volume = qto_volume
        else:
            faces = shape.geometry.faces
            volume = _compute_mesh_volume(verts, faces)

        return GeometrySignature(bbox_dims=bbox_dims, volume=volume)
    except Exception:
        logger.debug("Geometry computation failed for %s", element.GlobalId, exc_info=True)
        return None


def representation_fingerprint(element, memo: dict[int, str]) -> str:
    """Content hash of everything that determines an element's body shape in its own
    coordinate system: the body representation and its openings and projections.

    Equal fingerprints (with equal file units) mean equal geometry, so tessellation can be
    skipped. STEP ids are not part of the hash; ``memo`` caches digests per entity id and
    must not be shared between files.
    """
    parts = [_digest(body_representation(element), memo)]
    features = [
        "void:" + _feature_digest(rel.RelatedOpeningElement, memo)
        for rel in getattr(element, "HasOpenings", None) or ()
    ]
    features += [
        "projection:" + _feature_digest(rel.RelatedFeatureElement, memo)
        for rel in getattr(element, "HasProjections", None) or ()
    ]
    parts.extend(sorted(features))
    return _hash("|".join(parts))


def _feature_digest(feature, memo: dict[int, str]) -> str:
    placement = feature.ObjectPlacement
    if placement is not None and placement.is_a("IfcLocalPlacement"):
        placement = placement.RelativePlacement
    return _digest(body_representation(feature), memo) + "@" + _digest(placement, memo)


def _digest(value, memo: dict[int, str]) -> str:
    if isinstance(value, ifcopenshell.entity_instance):
        eid = value.id()
        if eid and eid in memo:
            return memo[eid]
        attrs = ",".join(_digest(value[i], memo) for i in range(len(value)))
        digest = _hash(f"{value.is_a()}({attrs})")
        if eid:
            memo[eid] = digest
        return digest
    if isinstance(value, (tuple, list)):
        return "(" + ",".join(_digest(v, memo) for v in value) + ")"
    return repr(value)


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _compute_mesh_volume(verts: np.ndarray, faces: list[int] | tuple[int, ...]) -> float:
    """Signed volume via divergence theorem on a triangulated closed mesh."""
    faces_arr = np.array(faces, dtype=np.int32).reshape(-1, 3)
    v0 = verts[faces_arr[:, 0]]
    v1 = verts[faces_arr[:, 1]]
    v2 = verts[faces_arr[:, 2]]
    cross = np.cross(v1, v2)
    signed = np.sum(v0 * cross, axis=1)
    return float(abs(signed.sum()) / 6.0)


def signatures_equal(
    a: GeometrySignature | None,
    b: GeometrySignature | None,
    bbox_tol: float,
    volume_tol: float,
) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    for da, db in zip(a.bbox_dims, b.bbox_dims):
        if abs(da - db) > bbox_tol:
            return False
    if abs(a.volume - b.volume) > volume_tol:
        return False
    return True
