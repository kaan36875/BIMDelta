"""Create a revision of an IFC model with a known set of edits, for benchmarks and checks.

    python scripts/make_revision.py model.ifc revised.ifc --fraction 0.02 --seed 1

Each edit type is applied to a disjoint random sample of elements it cannot spill over from
(e.g. only placements nothing else is placed relative to). The expected diff is printed as JSON:

* moved:      placement shifted 100 mm along X          -> modified
* property:   one occurrence property value changed     -> modified
* reshaped:   extrusion depth increased by 10 %         -> modified (geometry)
* deleted:    element removed                           -> removed
* re_ided:    GlobalId regenerated, Tag kept            -> unchanged (matched by tag)
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.unit

from bimdelta_core.geometry import body_representation

SKIP = ("IfcFeatureElement", "IfcVirtualElement")
_PRESENTATION = {"IfcPresentationLayerAssignment", "IfcPresentationLayerWithStyle", "IfcStyledItem"}


class Revision:
    def __init__(self, f: ifcopenshell.file):
        self.f = f

    def refs(self, entity) -> int:
        """References that could carry an edit to another element (layers and styles cannot)."""
        return sum(1 for r in self.f.get_inverse(entity) if r.is_a() not in _PRESENTATION)

    def can_move(self, e) -> bool:
        p = e.ObjectPlacement
        return (
            p is not None
            and p.is_a("IfcLocalPlacement")
            and not p.ReferencedByPlacements
            and len(p.PlacesObject) == 1
            and self.refs(p.RelativePlacement) == 1
            and p.RelativePlacement.Location is not None
            and self.refs(p.RelativePlacement.Location) == 1
        )

    def editable_property(self, e):
        for rel in e.IsDefinedBy or ():
            if not rel.is_a("IfcRelDefinesByProperties") or len(rel.RelatedObjects) != 1:
                continue
            pset = rel.RelatingPropertyDefinition
            if not pset.is_a("IfcPropertySet") or self.refs(pset) != 1:
                continue
            for prop in pset.HasProperties or ():
                if (
                    prop.is_a("IfcPropertySingleValue")
                    and prop.NominalValue is not None
                    and prop.NominalValue.is_a("IfcLabel")
                    and self.refs(prop) == 1
                ):
                    return prop
        return None

    def own_extrusion(self, e):
        rep = body_representation(e)
        if rep is None or self.refs(rep) != 1:
            return None
        for item in rep.Items or ():
            if item.is_a("IfcExtrudedAreaSolid") and self.refs(item) == 1:
                return item
        return None

    @staticmethod
    def can_delete(e) -> bool:
        # Deleting a host or an aggregate (e.g. a curtain wall) would orphan its parts.
        return not any(
            getattr(e, attr, None) for attr in ("HasOpenings", "FillsVoids", "IsDecomposedBy")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--fraction", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--manifest", type=Path, help="write the edited GlobalIds as JSON")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    f = ifcopenshell.open(str(args.source))
    rev = Revision(f)
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f)

    elements = [e for e in f.by_type("IfcElement") if not any(e.is_a(c) for c in SKIP)]
    rng.shuffle(elements)
    n = max(1, int(len(elements) * args.fraction))
    tag_counts = Counter((e.is_a(), e.Tag) for e in elements if e.Tag)
    used: set[int] = set()

    def take(pred):
        picked = []
        for e in elements:
            if len(picked) == n:
                break
            if e.id() not in used and pred(e):
                picked.append(e)
                used.add(e.id())
        return picked

    moved = take(rev.can_move)
    for e in moved:
        loc = e.ObjectPlacement.RelativePlacement.Location
        coords = list(loc.Coordinates)
        coords[0] += 0.1 / unit_scale
        loc.Coordinates = coords

    prop_changed = take(lambda e: rev.editable_property(e) is not None)
    for e in prop_changed:
        prop = rev.editable_property(e)
        prop.NominalValue = f.createIfcLabel(f"{prop.NominalValue.wrappedValue} (rev)")

    reshaped = take(lambda e: rev.own_extrusion(e) is not None)
    for e in reshaped:
        solid = rev.own_extrusion(e)
        solid.Depth = solid.Depth * 1.1

    deleted = take(rev.can_delete)
    deleted_ids = [e.GlobalId for e in deleted]
    for e in deleted:
        ifcopenshell.api.run("root.remove_product", f, product=e)

    re_ided = take(lambda e: e.Tag and tag_counts[(e.is_a(), e.Tag)] == 1)
    for e in re_ided:
        e.GlobalId = ifcopenshell.guid.new()

    f.write(str(args.target))
    edits = {
        "moved": [e.GlobalId for e in moved],
        "property": [e.GlobalId for e in prop_changed],
        "reshaped": [e.GlobalId for e in reshaped],
        "deleted": deleted_ids,
        "re_ided": [e.GlobalId for e in re_ided],
    }
    expected = {
        "added": 0,
        "removed": len(deleted),
        "modified": len(moved) + len(prop_changed) + len(reshaped),
    }
    if args.manifest:
        args.manifest.write_text(json.dumps({"edits": edits, "expected": expected}, indent=1))
    print(json.dumps({"edits": {k: len(v) for k, v in edits.items()}, "expected": expected}))


if __name__ == "__main__":
    main()
