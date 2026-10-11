"""Builders for small synthetic IFC4 models with known content, for tests in this repo."""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

run = ifcopenshell.api.run


def setup_project(schema: str = "IFC4", length_unit: str = "METRE") -> tuple:
    """Create a minimal IFC project with one storey. Returns (ifc, body_context, storey)."""
    ifc = ifcopenshell.file(schema=schema)

    project = run("root.create_entity", ifc, ifc_class="IfcProject", name="TestProject")

    run("unit.assign_unit", ifc, length={"is_metric": True, "raw": length_unit})

    ctx = run("context.add_context", ifc, context_type="Model")
    body = run(
        "context.add_context",
        ifc,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    site = run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")
    building = run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
    storey = run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 1")
    storey.Elevation = 0.0

    run("aggregate.assign_object", ifc, relating_object=project, products=[site])
    run("aggregate.assign_object", ifc, relating_object=site, products=[building])
    run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

    return ifc, body, storey


def add_element(
    ifc,
    body,
    storey,
    ifc_class: str,
    global_id: str,
    name: str,
    x: float,
    y: float,
    z: float,
    dims: tuple[float, float, float],
    tag: str | None = None,
):
    """Add an element with box geometry, contained in the storey."""
    el = run("root.create_entity", ifc, ifc_class=ifc_class, name=name)
    el.GlobalId = global_id
    if tag is not None:
        el.Tag = tag
    set_placement(ifc, el, storey, x, y, z)
    add_box_geometry(ifc, body, el, *dims)
    run("spatial.assign_container", ifc, relating_structure=storey, products=[el])
    return el


def add_wall(
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
    tag: str | None = None,
):
    """Add a wall with simple extruded geometry and optional properties."""
    wall = add_element(
        ifc, body, storey, "IfcWall", global_id, name, x, y, z, (length, thickness, height), tag
    )
    props = {}
    if fire_rating is not None:
        props["FireRating"] = fire_rating
    if is_external is not None:
        props["IsExternal"] = is_external
    if props:
        add_pset(ifc, wall, "Pset_WallCommon", props)
    return wall


def add_door(
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
    tag: str | None = None,
):
    return add_element(
        ifc, body, storey, "IfcDoor", global_id, name, x, y, z, (width, depth, height), tag
    )


def add_column(
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
    tag: str | None = None,
):
    return add_element(
        ifc, body, storey, "IfcColumn", global_id, name, x, y, z, (side, side, height), tag
    )


def add_opening(
    ifc,
    body,
    storey,
    host,
    global_id: str,
    x: float,
    y: float,
    z: float,
    dims: tuple[float, float, float] = (0.9, 0.3, 2.1),
):
    """Add an opening voiding ``host``."""
    opening = run("root.create_entity", ifc, ifc_class="IfcOpeningElement", name="Opening")
    opening.GlobalId = global_id
    set_placement(ifc, opening, storey, x, y, z)
    add_box_geometry(ifc, body, opening, *dims)
    run("feature.add_feature", ifc, feature=opening, element=host)
    return opening


def add_pset(ifc, element, name: str, properties: dict):
    pset = run("pset.add_pset", ifc, product=element, name=name)
    run("pset.edit_pset", ifc, pset=pset, properties=properties)
    return pset


def set_property(element, pset_name: str, prop_name: str, ifc_value) -> None:
    """Overwrite the nominal value of an existing single-value property."""
    for rel in element.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties"):
            pset = rel.RelatingPropertyDefinition
            if pset.Name == pset_name:
                for prop in pset.HasProperties:
                    if prop.Name == prop_name:
                        prop.NominalValue = ifc_value
                        return
    raise KeyError(f"{pset_name}.{prop_name}")


def set_placement(ifc, element, storey, x: float, y: float, z: float) -> None:
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


def add_box_geometry(ifc, body, element, dx: float, dy: float, dz: float) -> None:
    profile = ifc.createIfcRectangleProfileDef(ProfileType="AREA", XDim=dx, YDim=dy)
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
    element.Representation = ifc.createIfcProductDefinitionShape(Representations=[shape_rep])


def remove_element(ifc, element) -> None:
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
