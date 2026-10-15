"""Revit export round-trip battery (see docs/globalid-stability.md).

``TestSyntheticRoundtrip`` simulates each scenario with generated models and always runs.
``test_recorded_roundtrip`` runs the same checks against real exports placed in
``samples/roundtrip/<scenario>/`` (or ``$BIMDELTA_ROUNDTRIP_DIR``) and is skipped if none exist.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bimdelta_core import Settings, run_diff
from bimdelta_core.testing import (
    add_column,
    add_door,
    add_element,
    add_pset,
    add_wall,
    run,
    setup_project,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUNDTRIP_DIR = Path(os.environ.get("BIMDELTA_ROUNDTRIP_DIR", REPO_ROOT / "samples" / "roundtrip"))

# (GlobalId, Revit ElementId, x position)
WALLS = [("0" * 22, "305001", 0.0), ("1" * 22, "305002", 6.0), ("2" * 22, "305003", 12.0)]


def _export(
    path: Path,
    walls=WALLS,
    reverse: bool = False,
    revit_psets: bool = False,
    base_quantities: bool = False,
    extra=None,
) -> Path:
    """Write a small 'Revit export'. Element order, psets and quantities mimic export options."""
    ifc, body, storey = setup_project()
    for gid, tag, x in reversed(walls) if reverse else walls:
        # Same name for every wall, so only GlobalId and Tag can tell them apart.
        wall = add_wall(
            ifc,
            body,
            storey,
            gid,
            "Basic Wall:Generic 200mm",
            x,
            0,
            0,
            tag=tag,
            fire_rating="REI60",
        )
        if revit_psets:
            add_pset(ifc, wall, "PSet_Revit_Constraints", {"Base Offset": 0.0})
            add_pset(ifc, wall, "PSet_Revit_Phasing", {"Phase Created": "New Construction"})
        if base_quantities:
            qto = ifc.createIfcElementQuantity(
                GlobalId=gid[:-1] + "Q",
                Name="Qto_WallBaseQuantities",
                # Net of openings, so deliberately not equal to the mesh volume (3.0 m³).
                Quantities=[ifc.createIfcQuantityVolume(Name="NetVolume", VolumeValue=2.85)],
            )
            ifc.createIfcRelDefinesByProperties(
                GlobalId=gid[:-1] + "R", RelatedObjects=[wall], RelatingPropertyDefinition=qto
            )
    add_door(ifc, body, storey, "D" * 22, "Single-Flush:0915 x 2134mm", 2, 0, 0, tag="306001")
    add_column(ifc, body, storey, "C" * 22, "Concrete Column:300 x 300", 0, 5, 0, tag="307001")
    if extra:
        extra(ifc, body, storey)
    ifc.write(str(path))
    return path


def _diff(v1: Path, v2: Path, **settings):
    return run_diff(str(v1), v1.name, str(v2), v2.name, Settings(**settings)).summary


class TestSyntheticRoundtrip:
    def test_1_same_model_exported_twice(self, tmp_path: Path):
        """Element order and STEP ids differ between exports; nothing else."""
        s = _diff(_export(tmp_path / "a.ifc"), _export(tmp_path / "b.ifc", reverse=True))
        assert (s.added, s.removed, s.modified, s.unchanged) == (0, 0, 0, 5)

    def test_2_exporter_regenerated_global_ids(self, tmp_path: Path):
        """GlobalIds change but the Revit ElementIds in IfcElement.Tag do not."""
        regenerated = [("Z" * 21 + str(i), tag, x) for i, (_, tag, x) in enumerate(WALLS)]
        result = run_diff(
            str(_export(tmp_path / "a.ifc")),
            "a.ifc",
            str(_export(tmp_path / "b.ifc", walls=regenerated)),
            "b.ifc",
            Settings(),
        )
        s = result.summary
        assert (s.added, s.removed, s.modified, s.unchanged) == (0, 0, 0, 5)
        walls = [e for e in result.elements if e.ifc_class == "IfcWall"]
        assert {e.match_method.value for e in walls} == {"tag"}

    def test_3_copy_paste_in_place(self, tmp_path: Path):
        copied = WALLS + [("9" * 22, "305099", 0.0)]
        s = _diff(_export(tmp_path / "a.ifc"), _export(tmp_path / "b.ifc", walls=copied))
        assert (s.added, s.removed, s.modified) == (1, 0, 0)

    def test_4_deleted_and_redrawn_in_place(self, tmp_path: Path):
        redrawn = [("8" * 22, "305100", 0.0)] + WALLS[1:]
        s = _diff(_export(tmp_path / "a.ifc"), _export(tmp_path / "b.ifc", walls=redrawn))
        assert (s.added, s.removed, s.modified) == (1, 1, 0)

    def test_5_element_moved_100mm(self, tmp_path: Path):
        moved = [(WALLS[0][0], WALLS[0][1], 0.1)] + WALLS[1:]
        result = run_diff(
            str(_export(tmp_path / "a.ifc")),
            "a.ifc",
            str(_export(tmp_path / "b.ifc", walls=moved)),
            "b.ifc",
            Settings(),
        )
        [el] = [e for e in result.elements if e.change_type.value == "modified"]
        assert el.global_id == WALLS[0][0]
        assert el.placement_changed

    def test_6_revit_property_sets_toggled(self, tmp_path: Path):
        s = _diff(_export(tmp_path / "a.ifc"), _export(tmp_path / "b.ifc", revit_psets=True))
        assert (s.added, s.removed, s.modified) == (0, 0, 0)
        assert {p.pset_name for p in s.noise.one_sided_psets} == {
            "PSet_Revit_Constraints",
            "PSet_Revit_Phasing",
        }

    def test_7_base_quantities_toggled(self, tmp_path: Path):
        s = _diff(_export(tmp_path / "a.ifc"), _export(tmp_path / "b.ifc", base_quantities=True))
        assert (s.added, s.removed, s.modified) == (0, 0, 0)

    def test_8_model_group_edited(self, tmp_path: Path):
        """Finishing a group edit gives the group and its members new ElementIds, so new
        GlobalIds and names; the members are matched through the recreated group."""

        def grouped(ifc, body, storey, group_id: str, members: list[tuple[str, str, float]]):
            group = run("group.add_group", ifc, name=f"Model Group:Apartment A:{group_id}")
            slabs = []
            for gid, tag, z in members:
                slab = add_element(
                    ifc,
                    body,
                    storey,
                    "IfcSlab",
                    gid,
                    f"Floor:Slab 200:{tag}",
                    0,
                    0,
                    0,
                    (5, 5, 0.2),
                    tag,
                )
                # Revit writes a slab's height offset into the extrusion, not the placement.
                slab.Representation.Representations[0].Items[
                    0
                ].Position = ifc.createIfcAxis2Placement3D(
                    ifc.createIfcCartesianPoint([0.0, 0.0, z])
                )
                slabs.append(slab)
            run("group.assign_group", ifc, products=slabs, group=group)

        v1 = _export(
            tmp_path / "a.ifc",
            extra=lambda *a: grouped(
                *a, "400100", [("G" * 22, "400101", 3.3), ("H" * 22, "400102", 0.0)]
            ),
        )
        v2 = _export(
            tmp_path / "b.ifc",
            extra=lambda *a: grouped(
                *a, "400200", [("J" * 22, "400201", 3.4), ("K" * 22, "400202", 0.0)]
            ),
        )
        result = run_diff(str(v1), "a.ifc", str(v2), "b.ifc", Settings())
        s = result.summary
        assert (s.added, s.removed, s.modified, s.unchanged) == (0, 0, 1, 6)
        slabs = {e.global_id: e for e in result.elements if e.ifc_class == "IfcSlab"}
        assert {e.match_method.value for e in slabs.values()} == {"group"}
        moved = slabs["J" * 22]
        assert moved.matched_global_id == "G" * 22
        assert moved.geometry_changed and not moved.placement_changed and not moved.name_changed
        assert round((moved.new_geometry.offset[2] - moved.old_geometry.offset[2]) * 1000) == 100

    def test_8b_group_type_must_match(self, tmp_path: Path):
        """Members of a different group type are not the same elements."""

        def grouped(ifc, body, storey, name, gid, tag):
            group = run("group.add_group", ifc, name=name)
            slab = add_element(
                ifc, body, storey, "IfcSlab", gid, "Floor:Slab 200", 0, 0, 0, (5, 5, 0.2), tag
            )
            run("group.assign_group", ifc, products=[slab], group=group)

        v1 = _export(
            tmp_path / "a.ifc", extra=lambda *a: grouped(*a, "Model Group:A:1", "G" * 22, "11")
        )
        v2 = _export(
            tmp_path / "b.ifc", extra=lambda *a: grouped(*a, "Model Group:B:2", "J" * 22, "22")
        )
        s = _diff(v1, v2)
        assert (s.added, s.removed) == (1, 1)


def _recorded_cases() -> list[Path]:
    if not ROUNDTRIP_DIR.is_dir():
        return []
    return sorted(
        d
        for d in ROUNDTRIP_DIR.iterdir()
        if (d / "v1.ifc").is_file() and (d / "v2.ifc").is_file() and (d / "expected.json").is_file()
    )


@pytest.mark.parametrize("case", _recorded_cases() or [None], ids=lambda c: c.name if c else "none")
def test_recorded_roundtrip(case: Path | None):
    if case is None:
        pytest.skip(f"no recorded exports in {ROUNDTRIP_DIR}")
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    summary = _diff(case / "v1.ifc", case / "v2.ifc", **expected.get("settings", {}))
    for key in ("added", "removed", "modified"):
        if key in expected:
            assert getattr(summary, key) == expected[key], (
                f"{case.name}: expected {key}={expected[key]}, got {getattr(summary, key)}. "
                f"Most changed properties: {summary.top_changed_properties[:5]}"
            )
