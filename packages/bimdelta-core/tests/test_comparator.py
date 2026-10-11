import numpy as np

from bimdelta_core.comparator import compare_matched
from bimdelta_core.config import Settings
from bimdelta_core.geometry import GeometrySignature
from bimdelta_core.parser import ParsedElement, PropertyValue


def _make_element(
    global_id: str = "test_id_00000000000",
    ifc_class: str = "IfcWall",
    name: str | None = "Wall-A",
    storey: str | None = "Level 1",
    x: float = 0.0,
    properties: list[PropertyValue] | None = None,
    type_name: str | None = None,
    geom: GeometrySignature | None = None,
) -> ParsedElement:
    mat = np.eye(4, dtype=np.float64)
    mat[0, 3] = x
    return ParsedElement(
        global_id=global_id,
        ifc_class=ifc_class,
        name=name,
        storey=storey,
        storey_elevation=0.0,
        world_placement=mat,
        storey_relative_placement=mat.copy(),
        properties=properties or [],
        type_name=type_name,
        geometry_signature=geom,
    )


class TestComparator:
    def test_identical_elements_unchanged(self):
        cfg = Settings()
        el = _make_element()
        result = compare_matched(el, el, "global_id", cfg)
        assert result.change_type.value == "unchanged"
        assert not result.property_changes
        assert not result.geometry_changed
        assert not result.placement_changed

    def test_property_change_detected(self):
        cfg = Settings()
        v1 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "FireRating", "occurrence", "1HR")]
        )
        v2 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "FireRating", "occurrence", "2HR")]
        )
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert len(result.property_changes) == 1
        assert result.property_changes[0].old_value == "1HR"
        assert result.property_changes[0].new_value == "2HR"

    def test_property_added(self):
        cfg = Settings()
        v1 = _make_element(properties=[])
        v2 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "IsExternal", "occurrence", True)]
        )
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert len(result.property_changes) == 1
        assert result.property_changes[0].old_value is None
        assert result.property_changes[0].new_value is True

    def test_property_removed(self):
        cfg = Settings()
        v1 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "IsExternal", "occurrence", True)]
        )
        v2 = _make_element(properties=[])
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.property_changes[0].old_value is True
        assert result.property_changes[0].new_value is None

    def test_float_tolerance(self):
        cfg = Settings()
        v1 = _make_element(properties=[PropertyValue("Qto", "Length", "occurrence", 5.0000001)])
        v2 = _make_element(properties=[PropertyValue("Qto", "Length", "occurrence", 5.0000002)])
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "unchanged"

    def test_name_change(self):
        cfg = Settings()
        v1 = _make_element(name="Wall-A")
        v2 = _make_element(name="Wall-A-Renamed")
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.name_changed
        assert result.old_name == "Wall-A"

    def test_storey_change(self):
        cfg = Settings()
        v1 = _make_element(storey="Level 1")
        v2 = _make_element(storey="Level 2")
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.storey_changed
        assert result.old_storey == "Level 1"

    def test_type_change(self):
        cfg = Settings()
        v1 = _make_element(type_name="Type A")
        v2 = _make_element(type_name="Type B")
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.type_changed
        assert result.old_type_name == "Type A"
        assert result.new_type_name == "Type B"

    def test_placement_change(self):
        cfg = Settings()
        v1 = _make_element(x=0.0)
        v2 = _make_element(x=1.0)
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.placement_changed

    def test_placement_within_tolerance(self):
        cfg = Settings()
        v1 = _make_element(x=0.0)
        v2 = _make_element(x=0.0005)  # 0.5 mm < 1 mm tolerance
        result = compare_matched(v1, v2, "global_id", cfg)
        assert not result.placement_changed

    def test_geometry_change(self):
        cfg = Settings()
        g1 = GeometrySignature(bbox_dims=(5.0, 0.2, 3.0), volume=3.0)
        g2 = GeometrySignature(bbox_dims=(5.0, 0.3, 3.0), volume=4.5)
        v1 = _make_element(geom=g1)
        v2 = _make_element(geom=g2)
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.change_type.value == "modified"
        assert result.geometry_changed

    def test_geometry_within_tolerance(self):
        cfg = Settings()
        g1 = GeometrySignature(bbox_dims=(5.0, 0.2, 3.0), volume=3.0)
        g2 = GeometrySignature(bbox_dims=(5.0005, 0.2, 3.0), volume=3.0)
        v1 = _make_element(geom=g1)
        v2 = _make_element(geom=g2)
        result = compare_matched(v1, v2, "global_id", cfg)
        assert not result.geometry_changed

    def test_type_property_source(self):
        cfg = Settings()
        v1 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "FireRating", "type", "1HR")]
        )
        v2 = _make_element(
            properties=[PropertyValue("Pset_WallCommon", "FireRating", "type", "2HR")]
        )
        result = compare_matched(v1, v2, "global_id", cfg)
        assert result.property_changes[0].source.value == "type"

    def test_fallback_match_records_method(self):
        cfg = Settings()
        v1 = _make_element(global_id="AAAAAAAAAAAAAAAAAAAAAA")
        v2 = _make_element(global_id="BBBBBBBBBBBBBBBBBBBBBB")
        result = compare_matched(v1, v2, "fallback", cfg)
        assert result.match_method.value == "fallback"
        assert result.matched_global_id == "AAAAAAAAAAAAAAAAAAAAAA"
