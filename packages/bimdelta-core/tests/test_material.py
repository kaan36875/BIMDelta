from pathlib import Path

import pytest

from bimdelta_core import ChangeType, Settings, run_diff
from bimdelta_core.parser import parse_ifc
from bimdelta_core.testing import add_column, add_wall, run, setup_project

WALL = "0" * 22
COLUMN = "1" * 22


def _layered_wall(ifc, wall, layers: list[tuple[str, float]]) -> None:
    layer_set = run(
        "material.add_material_set", ifc, name="Wall build-up", set_type="IfcMaterialLayerSet"
    )
    for name, thickness in layers:
        material = run("material.add_material", ifc, name=name)
        layer = run("material.add_layer", ifc, layer_set=layer_set, material=material)
        layer.LayerThickness = thickness
    run("material.assign_material", ifc, products=[wall], material=layer_set)


def _model(path: Path, column_material: str, insulation: float, length_unit: str = "METRE"):
    scale = 1000 if length_unit == "MILLIMETRE" else 1
    ifc, body, storey = setup_project(length_unit=length_unit)
    wall = add_wall(ifc, body, storey, WALL, "Wall", 0, 0, 0)
    _layered_wall(ifc, wall, [("Clay brick", 0.102 * scale), ("Mineral wool", insulation * scale)])
    column = add_column(ifc, body, storey, COLUMN, "Column", 3 * scale, 0, 0)
    material = run("material.add_material", ifc, name=column_material)
    run("material.assign_material", ifc, products=[column], material=material)
    ifc.write(str(path))
    return path


def test_material_description(tmp_path: Path):
    path = _model(tmp_path / "m.ifc", "Concrete C30/37", 0.1)
    model = parse_ifc(str(path), "m.ifc")
    assert model.elements[WALL].material == "Clay brick 102 mm | Mineral wool 100 mm"
    assert model.elements[COLUMN].material == "Concrete C30/37"


def test_layer_thickness_in_millimetre_files(tmp_path: Path):
    path = _model(tmp_path / "mm.ifc", "Concrete C30/37", 0.1, length_unit="MILLIMETRE")
    model = parse_ifc(str(path), "mm.ifc")
    assert model.elements[WALL].material == "Clay brick 102 mm | Mineral wool 100 mm"


def test_material_changes(tmp_path: Path):
    v1 = _model(tmp_path / "v1.ifc", "Concrete C30/37", 0.1)
    v2 = _model(tmp_path / "v2.ifc", "Concrete C35/45", 0.15)
    result = run_diff(str(v1), "v1", str(v2), "v2", Settings())
    by_id = {el.global_id: el for el in result.elements}

    column = by_id[COLUMN]
    assert column.change_type == ChangeType.MODIFIED
    assert column.material_changed
    assert (column.old_material, column.new_material) == ("Concrete C30/37", "Concrete C35/45")

    wall = by_id[WALL]
    assert wall.material_changed
    assert wall.new_material == "Clay brick 102 mm | Mineral wool 150 mm"


def test_same_material_is_unchanged(tmp_path: Path):
    v1 = _model(tmp_path / "v1.ifc", "Concrete C30/37", 0.1)
    v2 = _model(tmp_path / "v2.ifc", "Concrete C30/37", 0.1)
    result = run_diff(str(v1), "v1", str(v2), "v2", Settings())
    assert result.summary.modified == 0


def test_geometry_summary_with_property_change(tmp_path: Path):
    """Geometry is compared even when a property already makes the element modified."""
    ifc, body, storey = setup_project()
    add_wall(ifc, body, storey, WALL, "Wall", 0, 0, 0, thickness=0.2, fire_rating="1HR")
    ifc.write(str(tmp_path / "v1.ifc"))

    ifc, body, storey = setup_project()
    add_wall(ifc, body, storey, WALL, "Wall", 0, 0, 0, thickness=0.3, fire_rating="2HR")
    ifc.write(str(tmp_path / "v2.ifc"))

    result = run_diff(str(tmp_path / "v1.ifc"), "v1", str(tmp_path / "v2.ifc"), "v2", Settings())
    wall = result.elements[0]
    assert wall.property_changes
    assert wall.geometry_changed
    assert wall.old_geometry.bbox_dims[1] == pytest.approx(0.2)
    assert wall.new_geometry.bbox_dims[1] == pytest.approx(0.3)
    assert wall.new_geometry.volume > wall.old_geometry.volume
