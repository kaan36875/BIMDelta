from __future__ import annotations

from pathlib import Path

import pytest

from bimdelta_core.testing import add_column, add_wall, remove_element, setup_project


@pytest.fixture
def basic_diff_files(tmp_path: Path) -> tuple[Path, Path]:
    """v1: Wall-A, Wall-B. v2: Wall-B removed, Column-1 added."""
    ifc, body, storey = setup_project()
    add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    add_wall(ifc, body, storey, "1" * 22, "Wall-B", 6, 0, 0)

    v1_path = tmp_path / "v1.ifc"
    ifc.write(str(v1_path))

    remove_element(ifc, ifc.by_guid("1" * 22))
    add_column(ifc, body, storey, "2" * 22, "Column-1", 0, 5, 0)

    v2_path = tmp_path / "v2.ifc"
    ifc.write(str(v2_path))
    return v1_path, v2_path
