from __future__ import annotations

from pathlib import Path

import pytest

import bimdelta_core.comparator as comparator
from bimdelta_core import Settings, run_diff
from bimdelta_core.testing import add_opening, add_wall, setup_project


def _build(path: Path, opening_x: float | None = None, length: float = 5.0, axis: bool = False):
    ifc, body, storey = setup_project()
    wall = add_wall(ifc, body, storey, "W" * 22, "Wall", 0, 0, 0, length=length)
    if axis:
        # Walls exported from authoring tools usually carry a 2D axis next to the body.
        axis_ctx = ifc.createIfcGeometricRepresentationSubContext(
            ContextIdentifier="Axis",
            ContextType="Model",
            ParentContext=body.ParentContext,
            TargetView="GRAPH_VIEW",
        )
        line = ifc.createIfcPolyline(
            [ifc.createIfcCartesianPoint([0.0, 0.0]), ifc.createIfcCartesianPoint([length, 0.0])]
        )
        axis_rep = ifc.createIfcShapeRepresentation(axis_ctx, "Axis", "Curve2D", [line])
        reps = wall.Representation.Representations
        wall.Representation.Representations = [axis_rep, *reps]
    if opening_x is not None:
        add_opening(ifc, body, storey, wall, "O" * 22, opening_x, -0.05, 0)
    ifc.write(str(path))
    return path


def _wall(v1: Path, v2: Path):
    [el] = run_diff(str(v1), "v1", str(v2), "v2", Settings()).elements
    return el


@pytest.fixture
def no_tessellation(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("geometry was tessellated")

    monkeypatch.setattr(comparator, "compute_geometry_signature", fail)


class TestFingerprintShortcut:
    def test_identical_geometry_is_not_tessellated(self, tmp_path: Path, no_tessellation):
        v1 = _build(tmp_path / "v1.ifc", opening_x=1.0, axis=True)
        v2 = _build(tmp_path / "v2.ifc", opening_x=1.0, axis=True)
        el = _wall(v1, v2)
        assert el.change_type.value == "unchanged"
        assert not el.geometry_unknown

    def test_moved_opening_changes_host_geometry(self, tmp_path: Path):
        """Same wall representation, but the opening that cuts it moved."""
        v1 = _build(tmp_path / "v1.ifc", opening_x=1.0)
        v2 = _build(tmp_path / "v2.ifc", opening_x=1.0)
        v3 = _build(tmp_path / "v3.ifc", opening_x=4.6)  # now partly outside the wall
        assert _wall(v1, v2).change_type.value == "unchanged"
        assert _wall(v1, v3).geometry_changed

    def test_different_units_are_never_shortcut(self, tmp_path: Path):
        """Identical numbers in different units are different geometry."""
        ifc_m, body_m, storey_m = setup_project(length_unit="METRE")
        add_wall(ifc_m, body_m, storey_m, "W" * 22, "Wall", 0, 0, 0, 5.0, 0.2, 3.0)
        ifc_m.write(str(tmp_path / "m.ifc"))
        ifc_mm, body_mm, storey_mm = setup_project(length_unit="MILLIMETRE")
        add_wall(ifc_mm, body_mm, storey_mm, "W" * 22, "Wall", 0, 0, 0, 5.0, 0.2, 3.0)
        ifc_mm.write(str(tmp_path / "mm.ifc"))
        assert _wall(tmp_path / "m.ifc", tmp_path / "mm.ifc").geometry_changed


class TestBodyRepresentation:
    def test_body_is_used_when_an_axis_is_present(self, tmp_path: Path):
        v1 = _build(tmp_path / "v1.ifc", axis=True)
        v2 = _build(tmp_path / "v2.ifc", axis=True, length=6.0)
        el = _wall(v1, v2)
        assert el.geometry_changed
        assert not el.geometry_unknown
