from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


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


def compute_geometry_signature(
    element, unit_scale: float, qto_volume: float | None = None
) -> GeometrySignature | None:
    """Compute bbox dims + volume. ifcopenshell.geom already normalises vertices
    to metres, so we do NOT re-apply unit_scale to geometry output."""
    try:
        import ifcopenshell.geom

        shape = ifcopenshell.geom.create_shape(_get_geom_settings(), element)
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
