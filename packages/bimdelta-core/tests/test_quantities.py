from pathlib import Path

import pytest

from bimdelta_core import quantity_delta
from bimdelta_core.testing import add_pset, add_wall, run, setup_project


def _add_qto(ifc, element, name: str, quantities: dict[str, float]) -> None:
    qto = run("pset.add_qto", ifc, product=element, name=name)
    run("pset.edit_qto", ifc, qto=qto, properties=quantities)


@pytest.fixture
def qto_files(tmp_path: Path) -> tuple[Path, Path]:
    """v1: two 5 m walls with quantities. v2: one wall lengthened to 7 m, and a wall
    without quantities added."""
    ifc, body, storey = setup_project()
    a = add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    b = add_wall(ifc, body, storey, "1" * 22, "Wall-B", 6, 0, 0)
    base = {"Length": 5.0, "NetSideArea": 15.0, "NetVolume": 3.0}
    _add_qto(ifc, a, "Qto_WallBaseQuantities", base)
    _add_qto(ifc, b, "Qto_WallBaseQuantities", base)
    material = run("material.add_material", ifc, name="Concrete")
    run("material.assign_material", ifc, products=[a, b], material=material)
    v1 = tmp_path / "v1.ifc"
    ifc.write(str(v1))

    for qto_rel in a.IsDefinedBy:
        qto = qto_rel.RelatingPropertyDefinition
        if qto.is_a("IfcElementQuantity"):
            run("pset.edit_qto", ifc, qto=qto, properties={"Length": 7.0, "NetVolume": 4.2})
    c = add_wall(ifc, body, storey, "2" * 22, "Wall-C", 12, 0, 0)
    add_pset(ifc, c, "Pset_WallCommon", {"IsExternal": True})
    v2 = tmp_path / "v2.ifc"
    ifc.write(str(v2))
    return v1, v2


def test_by_class(qto_files):
    v1, v2 = qto_files
    result = quantity_delta(str(v1), "v1.ifc", str(v2), "v2.ifc", "class")

    assert [row.group for row in result.rows] == ["IfcWall"]
    row = result.rows[0]
    assert row.v1.count == 2 and row.v2.count == 3
    assert row.delta.count == 1
    assert row.delta.length == pytest.approx(2.0)
    assert row.delta.area == pytest.approx(0.0)
    assert row.delta.volume == pytest.approx(1.2)
    assert result.v1_without_quantities == 0
    assert result.v2_without_quantities == 1
    assert result.total.delta.volume == pytest.approx(1.2)


def test_by_material(qto_files):
    v1, v2 = qto_files
    result = quantity_delta(str(v1), "v1.ifc", str(v2), "v2.ifc", "material")

    groups = {row.group: row for row in result.rows}
    assert set(groups) == {"Concrete", "(no material)"}
    assert groups["Concrete"].delta.volume == pytest.approx(1.2)
    assert groups["(no material)"].v1.count == 0
    assert groups["(no material)"].v2.count == 1


def test_unit_scale(tmp_path: Path):
    ifc, body, storey = setup_project(length_unit="MILLIMETRE")
    wall = add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    _add_qto(ifc, wall, "Qto_WallBaseQuantities", {"Length": 5000.0, "NetVolume": 3e9})
    path = tmp_path / "mm.ifc"
    ifc.write(str(path))

    result = quantity_delta(str(path), "a", str(path), "b")
    assert result.rows[0].v1.length == pytest.approx(5.0)
    assert result.rows[0].v1.volume == pytest.approx(3.0)
