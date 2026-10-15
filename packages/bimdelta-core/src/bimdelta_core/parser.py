from __future__ import annotations

import logging
from dataclasses import dataclass, field

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

from .geometry import GeometrySignature

logger = logging.getLogger(__name__)

EXCLUDED_CLASSES = frozenset(["IfcVirtualElement", "IfcFeatureElement"])
OPENING_CLASS = "IfcOpeningElement"

LENGTH_MEASURES = frozenset(
    ["IfcLengthMeasure", "IfcPositiveLengthMeasure", "IfcNonNegativeLengthMeasure"]
)
AREA_MEASURES = frozenset(["IfcAreaMeasure"])
VOLUME_MEASURES = frozenset(["IfcVolumeMeasure"])


@dataclass(frozen=True)
class PropertyValue:
    pset_name: str
    property_name: str
    source: str  # "occurrence" or "type"
    value: str | float | int | bool | None


@dataclass
class ParsedElement:
    global_id: str
    ifc_class: str
    name: str | None
    storey: str | None
    storey_elevation: float | None
    world_placement: np.ndarray
    storey_relative_placement: np.ndarray | None
    properties: list[PropertyValue]
    type_name: str | None
    geometry_signature: GeometrySignature | None
    _ifc_entity_id: int | None = None
    tag: str | None = None
    has_representation: bool = True
    geometry_failed: bool = False
    geometry_fingerprint: str | None = None
    # Readable material assignment, e.g. "Clay brick 102 mm | Mineral wool 100 mm".
    material: str | None = None
    # Names of the plain IfcGroups the element belongs to; Revit model groups export as
    # these, e.g. "Model Group:Apartment A:310442".
    groups: tuple[str, ...] = ()


@dataclass
class ParsedModel:
    filename: str
    ifc_schema: str
    elements: dict[str, ParsedElement]
    storeys: dict[str, float]
    unit_scale: float
    _ifc_file: object | None = None
    _fingerprint_memo: dict[int, str] = field(default_factory=dict)


def parse_ifc(filepath: str, filename: str, include_openings: bool = False) -> ParsedModel:
    ifc_file = ifcopenshell.open(filepath)
    schema = ifc_file.schema
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc_file)

    storeys, storey_placements = _parse_storeys(ifc_file, unit_scale)
    containment = _build_containment_map(ifc_file)
    groups = _build_group_map(ifc_file)

    elements: dict[str, ParsedElement] = {}
    for element in ifc_file.by_type("IfcElement"):
        if _is_excluded(element, include_openings):
            continue

        global_id = element.GlobalId
        ifc_class = element.is_a()
        name = element.Name

        storey_name = containment.get(element.id())
        storey_elevation = storeys.get(storey_name) if storey_name else None

        world_placement = _get_world_placement(element, unit_scale)
        storey_rel = _get_storey_relative_placement(world_placement, storey_name, storey_placements)

        properties = _extract_occurrence_properties(element, unit_scale)

        type_obj = ifcopenshell.util.element.get_type(element)
        type_name = None
        if type_obj:
            type_name = type_obj.Name
            properties.extend(_extract_type_properties(type_obj, unit_scale))

        elements[global_id] = ParsedElement(
            global_id=global_id,
            ifc_class=ifc_class,
            name=name,
            storey=storey_name,
            storey_elevation=storey_elevation,
            world_placement=world_placement,
            storey_relative_placement=storey_rel,
            properties=properties,
            type_name=type_name,
            _ifc_entity_id=element.id(),
            geometry_signature=None,
            tag=(element.Tag or "").strip() or None,
            has_representation=element.Representation is not None,
            material=material_description(element, unit_scale),
            groups=groups.get(element.id(), ()),
        )

    return ParsedModel(
        filename=filename,
        ifc_schema=schema,
        elements=elements,
        storeys=storeys,
        unit_scale=unit_scale,
        _ifc_file=ifc_file,
    )


def material_description(element, unit_scale: float) -> str | None:
    """The element's material assignment (its own, else its type's) as one line of text.

    Layer sets list each layer with its thickness, profile sets each material with its
    profile, so a change of build-up or section reads as a material change.
    """
    try:
        material = ifcopenshell.util.element.get_material(element, should_skip_usage=True)
    except Exception:
        logger.debug("Material lookup failed for %s", element.GlobalId, exc_info=True)
        return None
    if material is None:
        return None

    def name(mat) -> str:
        return (getattr(mat, "Name", None) or "(unnamed)") if mat is not None else "(none)"

    if material.is_a("IfcMaterial"):
        return name(material)
    if material.is_a("IfcMaterialLayerSet"):
        layers = []
        for layer in material.MaterialLayers or ():
            thickness = (layer.LayerThickness or 0.0) * unit_scale * 1000
            layers.append(f"{name(layer.Material)} {thickness:g} mm")
        return " | ".join(layers) or name(material)
    if material.is_a("IfcMaterialProfileSet"):
        parts = []
        for mp in material.MaterialProfiles or ():
            profile = getattr(mp.Profile, "ProfileName", None) if mp.Profile else None
            parts.append(f"{name(mp.Material)} ({profile})" if profile else name(mp.Material))
        return " | ".join(parts) or name(material)
    if material.is_a("IfcMaterialConstituentSet"):
        return " | ".join(name(c.Material) for c in material.MaterialConstituents or ()) or None
    if material.is_a("IfcMaterialList"):
        return " | ".join(name(m) for m in material.Materials or ()) or None
    return name(material)


def _parse_storeys(
    ifc_file: ifcopenshell.file, unit_scale: float
) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    storeys: dict[str, float] = {}
    placements: dict[str, np.ndarray] = {}
    for storey in ifc_file.by_type("IfcBuildingStorey"):
        name = storey.Name or storey.GlobalId
        elevation = (storey.Elevation or 0.0) * unit_scale
        storeys[name] = elevation
        if storey.ObjectPlacement:
            mat = ifcopenshell.util.placement.get_local_placement(storey.ObjectPlacement)
            mat[:3, 3] *= unit_scale
            placements[name] = mat
    return storeys, placements


def name_without_id(el: ParsedElement) -> str | None:
    """The name without the element id Revit appends ("Floor:Slab 200:1327530" → "Floor:Slab
    200"), which changes whenever Revit recreates the element."""
    if el.name and el.tag and el.name.endswith(":" + el.tag):
        return el.name[: -len(el.tag) - 1]
    return el.name


def _build_group_map(ifc_file: ifcopenshell.file) -> dict[int, tuple[str, ...]]:
    # Only IfcGroup itself: systems, zones and other subclasses are not authoring groups.
    groups: dict[int, list[str]] = {}
    for rel in ifc_file.by_type("IfcRelAssignsToGroup"):
        group = rel.RelatingGroup
        if group is None or group.is_a() != "IfcGroup":
            continue
        name = group.Name or group.GlobalId
        for obj in rel.RelatedObjects or ():
            groups.setdefault(obj.id(), []).append(name)
    return {k: tuple(v) for k, v in groups.items()}


def _build_containment_map(ifc_file: ifcopenshell.file) -> dict[int, str]:
    containment: dict[int, str] = {}
    for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
        structure = rel.RelatingStructure
        if structure.is_a("IfcBuildingStorey"):
            storey_name = structure.Name or structure.GlobalId
            for el in rel.RelatedElements:
                containment[el.id()] = storey_name
                _assign_decomposed(ifc_file, el, storey_name, containment)
    return containment


def _assign_decomposed(
    ifc_file: ifcopenshell.file,
    parent,
    storey_name: str,
    containment: dict[int, str],
) -> None:
    for rel in getattr(parent, "IsDecomposedBy", []) or []:
        for child in rel.RelatedObjects:
            if child.id() not in containment:
                containment[child.id()] = storey_name
                _assign_decomposed(ifc_file, child, storey_name, containment)


def _is_excluded(element, include_openings: bool) -> bool:
    if include_openings and element.is_a(OPENING_CLASS):
        return False
    return any(element.is_a(cls) for cls in EXCLUDED_CLASSES)


def _get_world_placement(element, unit_scale: float) -> np.ndarray:
    if element.ObjectPlacement:
        mat = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
        mat = mat.astype(np.float64)
        mat[:3, 3] *= unit_scale
        return mat
    return np.eye(4, dtype=np.float64)


def _get_storey_relative_placement(
    world_placement: np.ndarray,
    storey_name: str | None,
    storey_placements: dict[str, np.ndarray],
) -> np.ndarray | None:
    if storey_name and storey_name in storey_placements:
        storey_world = storey_placements[storey_name]
        storey_inv = np.linalg.inv(storey_world)
        return storey_inv @ world_placement
    return None


def _extract_occurrence_properties(element, unit_scale: float) -> list[PropertyValue]:
    return _extract_properties_from_entity(element, "occurrence", unit_scale)


def _extract_type_properties(type_obj, unit_scale: float) -> list[PropertyValue]:
    props: list[PropertyValue] = []
    for pset in getattr(type_obj, "HasPropertySets", None) or []:
        if pset.is_a("IfcPropertySet"):
            props.extend(_extract_pset_properties(pset, "type", unit_scale))
        elif pset.is_a("IfcElementQuantity"):
            props.extend(_extract_quantities(pset, "type", unit_scale))
    return props


def _extract_properties_from_entity(entity, source: str, unit_scale: float) -> list[PropertyValue]:
    props: list[PropertyValue] = []
    for rel in getattr(entity, "IsDefinedBy", None) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if pset.is_a("IfcPropertySet"):
            props.extend(_extract_pset_properties(pset, source, unit_scale))
        elif pset.is_a("IfcElementQuantity"):
            props.extend(_extract_quantities(pset, source, unit_scale))
    return props


def _extract_pset_properties(pset, source: str, unit_scale: float) -> list[PropertyValue]:
    props: list[PropertyValue] = []
    pset_name = pset.Name or ""
    for prop in pset.HasProperties or []:
        if prop.is_a("IfcPropertySingleValue"):
            value = _extract_ifc_value(prop.NominalValue, unit_scale)
        elif prop.is_a("IfcPropertyEnumeratedValue"):
            value = _extract_ifc_values(prop.EnumerationValues, unit_scale)
        elif prop.is_a("IfcPropertyListValue"):
            value = _extract_ifc_values(prop.ListValues, unit_scale)
        else:
            continue
        props.append(PropertyValue(pset_name, prop.Name or "", source, value))
    return props


def _extract_ifc_values(ifc_values, unit_scale: float) -> str | float | int | bool | None:
    """Collapse a multi-valued property to one comparable value; a single item keeps its type."""
    values = [_extract_ifc_value(v, unit_scale) for v in ifc_values or []]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return ", ".join(str(v) for v in values)


def _extract_quantities(qset, source: str, unit_scale: float) -> list[PropertyValue]:
    props: list[PropertyValue] = []
    qset_name = qset.Name or ""
    for qty in qset.Quantities or []:
        value = _extract_quantity_value(qty, unit_scale)
        if value is not None:
            props.append(PropertyValue(qset_name, qty.Name or "", source, value))
    return props


def _extract_ifc_value(ifc_value, unit_scale: float) -> str | float | int | bool | None:
    if ifc_value is None:
        return None
    raw = ifc_value.wrappedValue
    type_name = ifc_value.is_a()

    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if type_name in LENGTH_MEASURES:
            return float(raw) * unit_scale
        if type_name in AREA_MEASURES:
            return float(raw) * unit_scale * unit_scale
        if type_name in VOLUME_MEASURES:
            return float(raw) * unit_scale * unit_scale * unit_scale
        return raw
    if isinstance(raw, str):
        return raw
    return str(raw)


def _extract_quantity_value(qty, unit_scale: float) -> float | None:
    if qty.is_a("IfcQuantityLength"):
        val = getattr(qty, "LengthValue", None)
        return float(val) * unit_scale if val is not None else None
    if qty.is_a("IfcQuantityArea"):
        val = getattr(qty, "AreaValue", None)
        return float(val) * unit_scale * unit_scale if val is not None else None
    if qty.is_a("IfcQuantityVolume"):
        val = getattr(qty, "VolumeValue", None)
        return float(val) * unit_scale * unit_scale * unit_scale if val is not None else None
    if qty.is_a("IfcQuantityCount"):
        val = getattr(qty, "CountValue", None)
        return float(val) if val is not None else None
    if qty.is_a("IfcQuantityWeight"):
        val = getattr(qty, "WeightValue", None)
        return float(val) if val is not None else None
    return None
