"""Generate a small two-storey building, and revisions of it, for demos and end-to-end tests.

    python scripts/make_sample_building.py house.ifc                 # revision A
    python scripts/make_sample_building.py house.ifc --revision B    # a design change

Everything in the model is generated here, so the files can be published under this
repository's licence. Revision B, against A:

* the east wall on Level 1 moves 300 mm outwards (modified: placement)
* the front door's fire rating goes from EI30 to EI60 (modified: property)
* a column is added on Level 2 (added)
* one Level 2 window is removed (removed)
* Level 2 slab gets thicker, 200 to 250 mm (modified: geometry and quantities)
"""

from __future__ import annotations

import argparse

from bimdelta_core.testing import add_element, add_pset, run, setup_project

STOREY_HEIGHT = 3.0
LENGTH, WIDTH = 12.0, 8.0  # footprint, m
WALL = 0.25


def build(revision: str = "A"):
    b = revision.upper() == "B"
    ifc, body, level1 = setup_project()
    ifc.by_type("IfcProject")[0].Name = "BIMDelta sample house"
    building = ifc.by_type("IfcBuilding")[0]
    building.Name = "Sample house"

    level2 = run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 2")
    level2.Elevation = STOREY_HEIGHT
    run("aggregate.assign_object", ifc, relating_object=building, products=[level2])
    # Storey placement, so contained elements sit 3 m up.
    level2.ObjectPlacement = ifc.createIfcLocalPlacement(
        RelativePlacement=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, STOREY_HEIGHT])
        )
    )

    concrete = run("material.add_material", ifc, name="Concrete C30/37")
    masonry = run("material.add_material", ifc, name="Clay brick")
    timber = run("material.add_material", ifc, name="Oak")
    glass = run("material.add_material", ifc, name="Glass")

    counter = iter(range(1, 1000))

    def gid() -> str:
        # Stable, readable GlobalIds: same element, same id in every revision.
        return f"{next(counter):022d}"

    def element(cls, storey, name, xyz, dims, material, tag, psets=None, qto=None):
        el = add_element(ifc, body, storey, cls, gid(), name, *xyz, dims, tag=tag)
        run("material.assign_material", ifc, products=[el], material=material)
        for pset, props in (psets or {}).items():
            add_pset(ifc, el, pset, props)
        if qto:
            q = run("pset.add_qto", ifc, product=el, name=qto[0])
            run("pset.edit_qto", ifc, qto=q, properties=qto[1])
        return el

    def walls(storey, level: int, east_offset: float = 0.0):
        h = STOREY_HEIGHT
        spec = [
            ("South", (0, 0, 0), (LENGTH, WALL, h)),
            ("North", (0, WIDTH - WALL, 0), (LENGTH, WALL, h)),
            ("West", (0, 0, 0), (WALL, WIDTH, h)),
            ("East", (LENGTH - WALL + east_offset, 0, 0), (WALL, WIDTH, h)),
        ]
        for side, xyz, dims in spec:
            length = max(dims[0], dims[1])
            element(
                "IfcWall",
                storey,
                f"Exterior wall {side} L{level}",
                xyz,
                dims,
                masonry,
                f"W{level}-{side[0]}",
                {
                    "Pset_WallCommon": {
                        "IsExternal": True,
                        "FireRating": "REI60",
                        "ThermalTransmittance": 0.28,
                    }
                },
                (
                    "Qto_WallBaseQuantities",
                    {
                        "Length": length,
                        "Height": h,
                        "Width": WALL,
                        "NetSideArea": length * h,
                        "NetVolume": length * h * WALL,
                    },
                ),
            )
        element(
            "IfcWall",
            storey,
            f"Interior wall L{level}",
            (6.0, WALL, 0),
            (0.12, WIDTH - 2 * WALL, h),
            masonry,
            f"W{level}-I",
            {"Pset_WallCommon": {"IsExternal": False, "FireRating": "EI30"}},
            (
                "Qto_WallBaseQuantities",
                {
                    "Length": WIDTH - 2 * WALL,
                    "Height": h,
                    "Width": 0.12,
                    "NetSideArea": (WIDTH - 2 * WALL) * h,
                    "NetVolume": (WIDTH - 2 * WALL) * h * 0.12,
                },
            ),
        )

    def slab(storey, level: int, thickness: float):
        element(
            "IfcSlab",
            storey,
            f"Floor slab L{level}",
            (0, 0, -thickness),
            (LENGTH, WIDTH, thickness),
            concrete,
            f"S{level}",
            {"Pset_SlabCommon": {"IsExternal": False, "LoadBearing": True}},
            (
                "Qto_SlabBaseQuantities",
                {
                    "Width": thickness,
                    "NetArea": LENGTH * WIDTH,
                    "NetVolume": LENGTH * WIDTH * thickness,
                },
            ),
        )

    def column(storey, level: int, x: float, y: float, n: int):
        element(
            "IfcColumn",
            storey,
            f"Column C{n} L{level}",
            (x, y, 0),
            (0.3, 0.3, STOREY_HEIGHT),
            concrete,
            f"C{level}-{n}",
            {"Pset_ColumnCommon": {"LoadBearing": True, "IsExternal": False}},
            (
                "Qto_ColumnBaseQuantities",
                {"Length": STOREY_HEIGHT, "NetVolume": 0.3 * 0.3 * STOREY_HEIGHT},
            ),
        )

    # Level 1
    slab(level1, 1, 0.2)
    walls(level1, 1, east_offset=0.3 if b else 0.0)
    for n, (x, y) in enumerate([(3.0, 4.0), (9.0, 4.0)], start=1):
        column(level1, 1, x, y, n)
    element(
        "IfcDoor",
        level1,
        "Front door",
        (2.0, -0.05, 0),
        (1.0, 0.1, 2.1),
        timber,
        "D1-1",
        {"Pset_DoorCommon": {"FireRating": "EI60" if b else "EI30", "IsExternal": True}},
    )
    element(
        "IfcDoor",
        level1,
        "Kitchen door",
        (6.0, 2.0, 0),
        (0.1, 0.9, 2.1),
        timber,
        "D1-2",
        {"Pset_DoorCommon": {"FireRating": "EI30", "IsExternal": False}},
    )
    for n, x in enumerate([5.0, 8.5], start=1):
        element(
            "IfcWindow",
            level1,
            f"Window L1-{n}",
            (x, -0.05, 0.9),
            (1.2, 0.1, 1.2),
            glass,
            f"N1-{n}",
            {"Pset_WindowCommon": {"IsExternal": True}},
        )

    # Level 2
    slab(level2, 2, 0.25 if b else 0.2)
    walls(level2, 2)
    for n, (x, y) in enumerate([(3.0, 4.0), (9.0, 4.0)], start=1):
        column(level2, 2, x, y, n)
    windows = [2.0, 5.0, 8.5]
    for n, x in enumerate(windows, start=1):
        if b and n == 3:
            next(counter)  # keep later ids stable
            continue
        element(
            "IfcWindow",
            level2,
            f"Window L2-{n}",
            (x, -0.05, 0.9),
            (1.2, 0.1, 1.2),
            glass,
            f"N2-{n}",
            {"Pset_WindowCommon": {"IsExternal": True}},
        )
    if b:
        column(level2, 2, 6.0, 6.0, 3)
    return ifc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output")
    parser.add_argument("--revision", choices=("A", "B"), default="A")
    args = parser.parse_args()
    build(args.revision).write(args.output)
