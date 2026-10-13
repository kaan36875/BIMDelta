"""Write one of two versions of a small model, for the action's self-test in CI.

    python make_fixture.py v1|v2 OUTPUT.ifc

v2 changes Wall-A's fire rating and adds a column.
"""

import sys

from bimdelta_core.testing import add_column, add_wall, setup_project


def build(version: str):
    ifc, body, storey = setup_project()
    rating = "2HR" if version == "v2" else "1HR"
    add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0, fire_rating=rating, tag="100")
    add_wall(ifc, body, storey, "1" * 22, "Wall-B", 6, 0, 0, tag="101")
    if version == "v2":
        add_column(ifc, body, storey, "3" * 22, "Column-1", 0, 5, 0, tag="103")
    return ifc


if __name__ == "__main__":
    build(sys.argv[1]).write(sys.argv[2])
