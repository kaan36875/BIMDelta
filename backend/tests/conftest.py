"""Synthetic IFC file generation for testing.

Creates small IFC4 models with known elements, properties, and geometry
so test expectations are deterministic.
"""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import pytest

run = ifcopenshell.api.run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_project(schema: str = "IFC4", length_unit: str = "METRE") -> tuple:
    """Create a minimal IFC project with one storey. Returns (ifc, body_context, storey)."""
    ifc = ifcopenshell.file(schema=schema)

    project = run("root.create_entity", ifc, ifc_class="IfcProject", name="TestProject")

    run("unit.assign_unit", ifc, length={"is_metric": True, "raw": length_unit})

    ctx = run("context.add_context", ifc, context_type="Model")
    body = run("context.add_context", ifc, context_type="Model",
               context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)

    site = run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")
    building = run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
    storey = run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 1")
    storey.Elevation = 0.0

    run("aggregate.assign_object", ifc, relating_object=project, products=[site])
    run("aggregate.assign_object", ifc, relating_object=site, products=[building])
    run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

    return ifc, body, storey


def _add_wall(
    ifc,
    body,
    storey,
    global_id: str,
    name: str,
    x: float,
    y: float,
    z: float,
    length: float = 5.0,
    thickness: float = 0.2,
    height: float = 3.0,
    fire_rating: str | None = None,
    is_external: bool | None = None,
) -> None:
    """Add a wall with simple extruded geometry and optional properties."""
    wall = run("root.create_entity", ifc, ifc_class="IfcWall", name=name)
    wall.GlobalId = global_id

    _set_placement(ifc, wall, storey, x, y, z)
    _add_box_geometry(ifc, body, wall, length, thickness, height)
    run("spatial.assign_container", ifc, relating_structure=storey, products=[wall])

    props = {}
    if fire_rating is not None:
        props["FireRating"] = fire_rating
    if is_external is not None:
        props["IsExternal"] = is_external
    if props:
        pset = run("pset.add_pset", ifc, product=wall, name="Pset_WallCommon")
        run("pset.edit_pset", ifc, pset=pset, properties=props)


def _add_door(
    ifc,
    body,
    storey,
    global_id: str,
    name: str,
    x: float,
    y: float,
    z: float,
    width: float = 0.9,
    depth: float = 0.1,
    height: float = 2.1,
) -> None:
    """Add a door with box geometry."""
    door = run("root.create_entity", ifc, ifc_class="IfcDoor", name=name)
    door.GlobalId = global_id

    _set_placement(ifc, door, storey, x, y, z)
    _add_box_geometry(ifc, body, door, width, depth, height)
    run("spatial.assign_container", ifc, relating_structure=storey, products=[door])


def _add_column(
    ifc,
    body,
    storey,
    global_id: str,
    name: str,
    x: float,
    y: float,
    z: float,
    side: float = 0.3,
    height: float = 3.0,
) -> None:
    """Add a column with box geometry."""
    col = run("root.create_entity", ifc, ifc_class="IfcColumn", name=name)
    col.GlobalId = global_id

    _set_placement(ifc, col, storey, x, y, z)
    _add_box_geometry(ifc, body, col, side, side, height)
    run("spatial.assign_container", ifc, relating_structure=storey, products=[col])


def _set_placement(ifc, element, storey, x: float, y: float, z: float) -> None:
    storey_placement = storey.ObjectPlacement
    if storey_placement is None:
        storey_placement = ifc.createIfcLocalPlacement(
            RelativePlacement=ifc.createIfcAxis2Placement3D(
                Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0])
            )
        )
        storey.ObjectPlacement = storey_placement

    element.ObjectPlacement = ifc.createIfcLocalPlacement(
        PlacementRelTo=storey_placement,
        RelativePlacement=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([x, y, z])
        ),
    )


def _add_box_geometry(
    ifc, body, element, dx: float, dy: float, dz: float
) -> None:
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=dx, YDim=dy
    )
    extrusion = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Depth=dz,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
    )
    shape_rep = ifc.createIfcShapeRepresentation(
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    prod_rep = ifc.createIfcProductDefinitionShape(Representations=[shape_rep])
    element.Representation = prod_rep


def _remove_element(ifc, element) -> None:
    """Remove an element and its relationships from the model."""
    for rel in list(getattr(element, "ContainedInStructure", []) or []):
        elements = list(rel.RelatedElements)
        elements.remove(element)
        if elements:
            rel.RelatedElements = elements
        else:
            ifc.remove(rel)

    for rel in list(getattr(element, "IsDefinedBy", []) or []):
        ifc.remove(rel)

    if element.Representation:
        for rep in element.Representation.Representations or []:
            for item in rep.Items or []:
                ifc.remove(item)
            ifc.remove(rep)
        ifc.remove(element.Representation)

    if element.ObjectPlacement:
        ifc.remove(element.ObjectPlacement.RelativePlacement.Location)
        ifc.remove(element.ObjectPlacement.RelativePlacement)
        ifc.remove(element.ObjectPlacement)

    ifc.remove(element)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_diff_files(tmp_path: Path) -> tuple[Path, Path]:
    """v1 and v2 with known add/remove/modify/unchanged elements.

    v1: Wall-A, Wall-B, Wall-C, Wall-D, Door-1, Door-2
    v2: Wall-A (modified: fire rating changed), Wall-B, Wall-C,
        Door-1, Door-2, Column-1 (added). Wall-D removed.
    """
    ifc, body, storey = _setup_project()

    _add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0, fire_rating="1HR")
    _add_wall(ifc, body, storey, "1" * 22, "Wall-B", 6, 0, 0)
    _add_wall(ifc, body, storey, "2" * 22, "Wall-C", 12, 0, 0)
    _add_wall(ifc, body, storey, "3" * 22, "Wall-D", 18, 0, 0)
    _add_door(ifc, body, storey, "4" * 22, "Door-1", 2, 0, 0)
    _add_door(ifc, body, storey, "5" * 22, "Door-2", 8, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    ifc.write(str(v1_path))

    # Modify Wall-A: change fire rating
    wall_a = ifc.by_guid("0" * 22)
    for rel in wall_a.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties"):
            pset = rel.RelatingPropertyDefinition
            if pset.Name == "Pset_WallCommon":
                for prop in pset.HasProperties:
                    if prop.Name == "FireRating":
                        prop.NominalValue = ifc.createIfcLabel("2HR")

    # Remove Wall-D
    wall_d = ifc.by_guid("3" * 22)
    _remove_element(ifc, wall_d)

    # Add Column-1
    _add_column(ifc, body, storey, "6" * 22, "Column-1", 0, 5, 0)

    v2_path = tmp_path / "v2.ifc"
    ifc.write(str(v2_path))

    return v1_path, v2_path


@pytest.fixture
def same_file(tmp_path: Path) -> tuple[Path, Path]:
    """Same model written twice — should produce 0 changes."""
    ifc, body, storey = _setup_project()
    _add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    _add_door(ifc, body, storey, "1" * 22, "Door-1", 2, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    v2_path = tmp_path / "v2.ifc"
    ifc.write(str(v1_path))
    ifc.write(str(v2_path))
    return v1_path, v2_path


@pytest.fixture
def fallback_match_files(tmp_path: Path) -> tuple[Path, Path]:
    """Three identical doors with regenerated GlobalIds — tests one-to-one fallback."""
    ifc1, body1, storey1 = _setup_project()
    _add_door(ifc1, body1, storey1, "A" * 22, "Fire Door", 1, 0, 0)
    _add_door(ifc1, body1, storey1, "B" * 22, "Fire Door", 3, 0, 0)
    _add_door(ifc1, body1, storey1, "C" * 22, "Fire Door", 5, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    ifc1.write(str(v1_path))

    ifc2, body2, storey2 = _setup_project()
    _add_door(ifc2, body2, storey2, "D" * 22, "Fire Door", 1, 0, 0)
    _add_door(ifc2, body2, storey2, "E" * 22, "Fire Door", 3, 0, 0)
    _add_door(ifc2, body2, storey2, "F" * 22, "Fire Door", 5, 0, 0)

    v2_path = tmp_path / "v2.ifc"
    ifc2.write(str(v2_path))

    return v1_path, v2_path


@pytest.fixture
def mm_vs_m_files(tmp_path: Path) -> tuple[Path, Path]:
    """Same wall, one file in metres, one in millimetres."""
    # Model in metres
    ifc_m, body_m, storey_m = _setup_project(length_unit="METRE")
    _add_wall(ifc_m, body_m, storey_m, "0" * 22, "Wall-A", 1.0, 0.0, 0.0,
              length=5.0, thickness=0.2, height=3.0)

    v1_path = tmp_path / "v1_m.ifc"
    ifc_m.write(str(v1_path))

    # Model in millimetres
    ifc_mm, body_mm, storey_mm = _setup_project(length_unit="MILLIMETRE")
    _add_wall(ifc_mm, body_mm, storey_mm, "0" * 22, "Wall-A", 1000.0, 0.0, 0.0,
              length=5000.0, thickness=200.0, height=3000.0)

    v2_path = tmp_path / "v2_mm.ifc"
    ifc_mm.write(str(v2_path))

    return v1_path, v2_path
