from __future__ import annotations

from pathlib import Path

import pytest

from bimdelta_core.testing import (
    add_column,
    add_door,
    add_wall,
    remove_element,
    set_property,
    setup_project,
)


@pytest.fixture
def basic_diff_files(tmp_path: Path) -> tuple[Path, Path]:
    """v1 and v2 with known add/remove/modify/unchanged elements.

    v1: Wall-A, Wall-B, Wall-C, Wall-D, Door-1, Door-2
    v2: Wall-A (modified: fire rating changed), Wall-B, Wall-C,
        Door-1, Door-2, Column-1 (added). Wall-D removed.
    """
    ifc, body, storey = setup_project()

    add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0, fire_rating="1HR")
    add_wall(ifc, body, storey, "1" * 22, "Wall-B", 6, 0, 0)
    add_wall(ifc, body, storey, "2" * 22, "Wall-C", 12, 0, 0)
    add_wall(ifc, body, storey, "3" * 22, "Wall-D", 18, 0, 0)
    add_door(ifc, body, storey, "4" * 22, "Door-1", 2, 0, 0)
    add_door(ifc, body, storey, "5" * 22, "Door-2", 8, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    ifc.write(str(v1_path))

    set_property(ifc.by_guid("0" * 22), "Pset_WallCommon", "FireRating", ifc.createIfcLabel("2HR"))
    remove_element(ifc, ifc.by_guid("3" * 22))
    add_column(ifc, body, storey, "6" * 22, "Column-1", 0, 5, 0)

    v2_path = tmp_path / "v2.ifc"
    ifc.write(str(v2_path))

    return v1_path, v2_path


@pytest.fixture
def same_file(tmp_path: Path) -> tuple[Path, Path]:
    """Same model written twice — should produce 0 changes."""
    ifc, body, storey = setup_project()
    add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    add_door(ifc, body, storey, "1" * 22, "Door-1", 2, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    v2_path = tmp_path / "v2.ifc"
    ifc.write(str(v1_path))
    ifc.write(str(v2_path))
    return v1_path, v2_path


@pytest.fixture
def fallback_match_files(tmp_path: Path) -> tuple[Path, Path]:
    """Three identical doors with regenerated GlobalIds — tests one-to-one fallback."""
    ifc1, body1, storey1 = setup_project()
    add_door(ifc1, body1, storey1, "A" * 22, "Fire Door", 1, 0, 0)
    add_door(ifc1, body1, storey1, "B" * 22, "Fire Door", 3, 0, 0)
    add_door(ifc1, body1, storey1, "C" * 22, "Fire Door", 5, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    ifc1.write(str(v1_path))

    ifc2, body2, storey2 = setup_project()
    add_door(ifc2, body2, storey2, "D" * 22, "Fire Door", 1, 0, 0)
    add_door(ifc2, body2, storey2, "E" * 22, "Fire Door", 3, 0, 0)
    add_door(ifc2, body2, storey2, "F" * 22, "Fire Door", 5, 0, 0)

    v2_path = tmp_path / "v2.ifc"
    ifc2.write(str(v2_path))

    return v1_path, v2_path


@pytest.fixture
def mm_vs_m_files(tmp_path: Path) -> tuple[Path, Path]:
    """Same wall, one file in metres, one in millimetres."""
    ifc_m, body_m, storey_m = setup_project(length_unit="METRE")
    add_wall(ifc_m, body_m, storey_m, "0" * 22, "Wall-A", 1.0, 0.0, 0.0, 5.0, 0.2, 3.0)

    v1_path = tmp_path / "v1_m.ifc"
    ifc_m.write(str(v1_path))

    ifc_mm, body_mm, storey_mm = setup_project(length_unit="MILLIMETRE")
    add_wall(
        ifc_mm, body_mm, storey_mm, "0" * 22, "Wall-A", 1000.0, 0.0, 0.0, 5000.0, 200.0, 3000.0
    )

    v2_path = tmp_path / "v2_mm.ifc"
    ifc_mm.write(str(v2_path))

    return v1_path, v2_path
