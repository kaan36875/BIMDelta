from pathlib import Path

from app.diff.parser import parse_ifc


class TestParseIfc:
    def test_parses_elements(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")

        assert model.filename == "v1.ifc"
        assert model.ifc_schema == "IFC4"
        assert len(model.elements) == 6  # 4 walls + 2 doors

    def test_element_classes(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")

        classes = {el.ifc_class for el in model.elements.values()}
        assert "IfcWall" in classes
        assert "IfcDoor" in classes

    def test_storey_containment(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")

        for el in model.elements.values():
            assert el.storey == "Level 1"

    def test_storeys_parsed(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")

        assert "Level 1" in model.storeys
        assert model.storeys["Level 1"] == 0.0

    def test_properties_extracted(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")

        wall_a = model.elements["0" * 22]
        prop_names = {p.property_name for p in wall_a.properties}
        assert "FireRating" in prop_names

        fire_prop = next(p for p in wall_a.properties if p.property_name == "FireRating")
        assert fire_prop.value == "1HR"
        assert fire_prop.source == "occurrence"
        assert fire_prop.pset_name == "Pset_WallCommon"

    def test_unit_scale_metres(self, basic_diff_files: tuple[Path, Path]):
        v1_path, _ = basic_diff_files
        model = parse_ifc(str(v1_path), "v1.ifc")
        assert abs(model.unit_scale - 1.0) < 1e-9

    def test_unit_scale_millimetres(self, mm_vs_m_files: tuple[Path, Path]):
        _, v2_path = mm_vs_m_files
        model = parse_ifc(str(v2_path), "v2_mm.ifc")
        assert abs(model.unit_scale - 0.001) < 1e-9

    def test_placement_normalized_to_metres(self, mm_vs_m_files: tuple[Path, Path]):
        v1_path, v2_path = mm_vs_m_files

        model_m = parse_ifc(str(v1_path), "v1_m.ifc")
        model_mm = parse_ifc(str(v2_path), "v2_mm.ifc")

        wall_m = model_m.elements["0" * 22]
        wall_mm = model_mm.elements["0" * 22]

        # Both should have x=1.0 metre after normalization
        assert abs(wall_m.world_placement[0, 3] - 1.0) < 1e-6
        assert abs(wall_mm.world_placement[0, 3] - 1.0) < 1e-6
