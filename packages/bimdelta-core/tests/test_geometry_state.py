from __future__ import annotations

from pathlib import Path

import numpy as np

import bimdelta_core.comparator as comparator
from bimdelta_core import Settings, run_diff
from bimdelta_core.comparator import pair_qto_volumes
from bimdelta_core.parser import ParsedElement, PropertyValue
from bimdelta_core.testing import add_column, add_element, setup_project


def _two_columns(tmp_path: Path) -> tuple[Path, Path]:
    """Column-A gets a slightly different section in v2, so its geometry has to be evaluated."""
    paths = []
    for name, side in (("v1.ifc", 0.30), ("v2.ifc", 0.35)):
        ifc, body, storey = setup_project()
        add_column(ifc, body, storey, "A" * 22, "Column-A", 0, 0, 0, side=side)
        add_column(ifc, body, storey, "B" * 22, "Column-B", 4, 0, 0)
        ifc.write(str(tmp_path / name))
        paths.append(tmp_path / name)
    return paths[0], paths[1]


class TestGeometryUnknown:
    def test_failed_geometry_is_reported_not_hidden(self, tmp_path: Path, monkeypatch):
        v1, v2 = _two_columns(tmp_path)
        real = comparator.compute_geometry_signature

        def fail_for_a(entity, unit_scale, qto_volume=None, placement=None):
            if entity.GlobalId == "A" * 22:
                return None
            return real(entity, unit_scale, qto_volume, placement)

        monkeypatch.setattr(comparator, "compute_geometry_signature", fail_for_a)
        result = run_diff(str(v1), "v1", str(v2), "v2", Settings())

        by_id = {el.global_id: el for el in result.elements}
        assert by_id["A" * 22].geometry_unknown
        assert not by_id["A" * 22].geometry_changed
        assert by_id["A" * 22].change_type.value == "unchanged"
        assert not by_id["B" * 22].geometry_unknown
        assert result.summary.geometry_unknown == 1

    def test_element_without_representation_is_not_unknown(self, tmp_path: Path):
        ifc, _, storey = setup_project()
        assembly = ifc.createIfcElementAssembly(GlobalId="E" * 22, Name="Assembly")
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId="R" * 22, RelatedElements=[assembly], RelatingStructure=storey
        )
        v1 = tmp_path / "v1.ifc"
        ifc.write(str(v1))

        result = run_diff(str(v1), "v1", str(v1), "v1", Settings())
        [el] = result.elements
        assert el.change_type.value == "unchanged"
        assert not el.geometry_unknown


class TestQuantityVolume:
    def test_base_quantities_toggled_between_exports(self, tmp_path: Path):
        """Exported NetVolume on one side only must not be compared to a mesh volume."""
        ifc, body, storey = setup_project()
        col = add_element(
            ifc, body, storey, "IfcColumn", "A" * 22, "Column", 0, 0, 0, (0.3, 0.3, 3.0)
        )
        v1 = tmp_path / "v1.ifc"
        ifc.write(str(v1))

        qto = ifc.createIfcElementQuantity(
            GlobalId="Q" * 22,
            Name="Qto_ColumnBaseQuantities",
            Quantities=[ifc.createIfcQuantityVolume(Name="NetVolume", VolumeValue=0.2)],
        )
        ifc.createIfcRelDefinesByProperties(
            GlobalId="R" * 22, RelatedObjects=[col], RelatingPropertyDefinition=qto
        )
        v2 = tmp_path / "v2.ifc"
        ifc.write(str(v2))

        result = run_diff(str(v1), "v1", str(v2), "v2", Settings())
        [el] = result.elements
        assert el.change_type.value == "unchanged"
        assert not el.geometry_changed


def _with_props(*props: tuple[str, float]) -> ParsedElement:
    return ParsedElement(
        global_id="A" * 22,
        ifc_class="IfcColumn",
        name=None,
        storey=None,
        storey_elevation=None,
        world_placement=np.eye(4),
        storey_relative_placement=None,
        properties=[PropertyValue("Qto", name, "occurrence", value) for name, value in props],
        type_name=None,
        geometry_signature=None,
    )


class TestPairQtoVolumes:
    def test_same_quantity_on_both_sides(self):
        v1 = _with_props(("NetVolume", 0.27))
        v2 = _with_props(("NetVolume", 0.30))
        assert pair_qto_volumes(v1, v2) == (0.27, 0.30)

    def test_quantity_on_one_side_only(self):
        assert pair_qto_volumes(_with_props(("NetVolume", 0.27)), _with_props()) == (None, None)

    def test_falls_back_to_common_gross_volume(self):
        v1 = _with_props(("NetVolume", 0.27), ("GrossVolume", 0.30))
        v2 = _with_props(("GrossVolume", 0.31))
        assert pair_qto_volumes(v1, v2) == (0.30, 0.31)
