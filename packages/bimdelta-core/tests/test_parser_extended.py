from __future__ import annotations

from pathlib import Path

import pytest

from bimdelta_core.parser import parse_ifc
from bimdelta_core.testing import add_opening, add_wall, setup_project


@pytest.fixture
def model_file(tmp_path: Path) -> Path:
    ifc, body, storey = setup_project()
    wall = add_wall(ifc, body, storey, "W" * 22, "Wall", 0, 0, 0, tag="  305112 ")
    add_wall(ifc, body, storey, "X" * 22, "Untagged", 6, 0, 0)
    add_opening(ifc, body, storey, wall, "O" * 22, 1, 0, 0)

    pset = ifc.createIfcPropertySet(
        GlobalId="P" * 22,
        Name="Custom",
        HasProperties=[
            ifc.createIfcPropertyEnumeratedValue(
                Name="Single", EnumerationValues=[ifc.createIfcLabel("A")]
            ),
            ifc.createIfcPropertyEnumeratedValue(
                Name="Many",
                EnumerationValues=[ifc.createIfcLabel("A"), ifc.createIfcLabel("B")],
            ),
            ifc.createIfcPropertyListValue(
                Name="Lengths",
                ListValues=[ifc.createIfcLengthMeasure(1.0), ifc.createIfcLengthMeasure(2.5)],
            ),
            ifc.createIfcPropertyListValue(Name="Empty", ListValues=None),
            ifc.createIfcPropertyBoundedValue(Name="Bounded"),
        ],
    )
    ifc.createIfcRelDefinesByProperties(
        GlobalId="R" * 22, RelatedObjects=[wall], RelatingPropertyDefinition=pset
    )

    path = tmp_path / "model.ifc"
    ifc.write(str(path))
    return path


def _props(model, gid: str) -> dict[str, object]:
    return {p.property_name: p.value for p in model.elements[gid].properties}


class TestTag:
    def test_tag_is_stripped(self, model_file: Path):
        model = parse_ifc(str(model_file), "m")
        assert model.elements["W" * 22].tag == "305112"

    def test_missing_tag_is_none(self, model_file: Path):
        model = parse_ifc(str(model_file), "m")
        assert model.elements["X" * 22].tag is None


class TestOpenings:
    def test_excluded_by_default(self, model_file: Path):
        model = parse_ifc(str(model_file), "m")
        assert "O" * 22 not in model.elements

    def test_included_on_request(self, model_file: Path):
        model = parse_ifc(str(model_file), "m", include_openings=True)
        assert model.elements["O" * 22].ifc_class == "IfcOpeningElement"


class TestMultiValuedProperties:
    def test_single_enumerated_value_keeps_its_type(self, model_file: Path):
        assert _props(parse_ifc(str(model_file), "m"), "W" * 22)["Single"] == "A"

    def test_multiple_values_are_joined(self, model_file: Path):
        props = _props(parse_ifc(str(model_file), "m"), "W" * 22)
        assert props["Many"] == "A, B"
        assert props["Lengths"] == "1.0, 2.5"

    def test_empty_list_is_none(self, model_file: Path):
        assert _props(parse_ifc(str(model_file), "m"), "W" * 22)["Empty"] is None

    def test_unsupported_property_kinds_are_skipped(self, model_file: Path):
        assert "Bounded" not in _props(parse_ifc(str(model_file), "m"), "W" * 22)
