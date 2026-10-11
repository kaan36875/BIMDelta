from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from bimdelta_core.matcher import match_elements
from bimdelta_core.parser import ParsedElement, ParsedModel, parse_ifc
from bimdelta_core.testing import add_door, add_wall, setup_project


def _write(tmp_path: Path, name: str, build) -> Path:
    ifc, body, storey = setup_project()
    build(ifc, body, storey)
    path = tmp_path / name
    ifc.write(str(path))
    return path


def _match(v1: Path, v2: Path, tol: float = 0.050):
    return match_elements(parse_ifc(str(v1), "v1"), parse_ifc(str(v2), "v2"), tol)


class TestTagMatching:
    def test_regenerated_global_ids_matched_by_tag(self, tmp_path: Path):
        v1 = _write(
            tmp_path, "v1.ifc", lambda *a: add_wall(*a, "A" * 22, "Wall", 0, 0, 0, tag="1001")
        )
        # Different name and placement too, so only the tag can pair them.
        v2 = _write(
            tmp_path, "v2.ifc", lambda *a: add_wall(*a, "B" * 22, "Wall-2", 3, 0, 0, tag="1001")
        )
        result = _match(v1, v2)
        [(e1, e2, method)] = result.matched
        assert method == "tag"
        assert (e1.global_id, e2.global_id) == ("A" * 22, "B" * 22)

    def test_same_tag_on_different_classes_is_not_a_match(self, tmp_path: Path):
        v1 = _write(tmp_path, "v1.ifc", lambda *a: add_wall(*a, "A" * 22, "X", 0, 0, 0, tag="1001"))
        v2 = _write(tmp_path, "v2.ifc", lambda *a: add_door(*a, "B" * 22, "X", 9, 0, 0, tag="1001"))
        result = _match(v1, v2)
        assert result.matched == []
        assert len(result.added) == len(result.removed) == 1

    def test_duplicate_tags_are_not_used(self, tmp_path: Path):
        def v1_build(*a):
            add_door(*a, "A" * 22, "Door", 0, 0, 0, tag="7")
            add_door(*a, "B" * 22, "Door", 4, 0, 0, tag="7")

        def v2_build(*a):
            add_door(*a, "C" * 22, "Door", 0, 0, 0, tag="7")
            add_door(*a, "D" * 22, "Door", 4, 0, 0, tag="7")

        result = _match(_write(tmp_path, "v1.ifc", v1_build), _write(tmp_path, "v2.ifc", v2_build))
        assert {m for _, _, m in result.matched} == {"fallback"}
        pairs = {(e1.global_id, e2.global_id) for e1, e2, _ in result.matched}
        assert pairs == {("A" * 22, "C" * 22), ("B" * 22, "D" * 22)}

    def test_redrawn_element_is_not_fallback_matched(self, tmp_path: Path):
        """Deleted and redrawn in place: new GlobalId and new authoring-tool id."""
        v1 = _write(
            tmp_path, "v1.ifc", lambda *a: add_wall(*a, "A" * 22, "Wall", 0, 0, 0, tag="1001")
        )
        v2 = _write(
            tmp_path, "v2.ifc", lambda *a: add_wall(*a, "B" * 22, "Wall", 0, 0, 0, tag="2002")
        )
        result = _match(v1, v2)
        assert result.matched == []
        assert len(result.added) == len(result.removed) == 1

    def test_fallback_still_used_when_a_tag_is_missing(self, tmp_path: Path):
        v1 = _write(
            tmp_path, "v1.ifc", lambda *a: add_wall(*a, "A" * 22, "Wall", 0, 0, 0, tag="1001")
        )
        v2 = _write(tmp_path, "v2.ifc", lambda *a: add_wall(*a, "B" * 22, "Wall", 0, 0, 0))
        [(_, _, method)] = _match(v1, v2).matched
        assert method == "fallback"


def _element(gid: str, x: float, y: float, tag: str | None = None) -> ParsedElement:
    placement = np.eye(4)
    placement[0, 3] = x
    placement[1, 3] = y
    return ParsedElement(
        global_id=gid,
        ifc_class="IfcFurnishingElement",
        name="Chair",
        storey="Level 1",
        storey_elevation=0.0,
        world_placement=placement,
        storey_relative_placement=None,
        properties=[],
        type_name=None,
        geometry_signature=None,
        tag=tag,
    )


def _model(elements: list[ParsedElement]) -> ParsedModel:
    return ParsedModel(
        filename="m",
        ifc_schema="IFC4",
        elements={e.global_id: e for e in elements},
        storeys={},
        unit_scale=1.0,
    )


class TestFallbackScaling:
    def test_many_identical_elements_match_nearest_quickly(self):
        """Thousands of same-class, same-name elements with regenerated GlobalIds."""
        n = 4000
        rng = np.random.default_rng(0)
        xs = rng.uniform(0, 200, n)
        ys = rng.uniform(0, 200, n)
        v1 = _model([_element(f"a{i}", xs[i], ys[i]) for i in range(n)])
        v2 = _model([_element(f"b{i}", xs[i] + 0.01, ys[i]) for i in range(n)])

        start = time.perf_counter()
        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)
        elapsed = time.perf_counter() - start

        assert len(result.matched) == n
        assert all(e1.global_id[1:] == e2.global_id[1:] for e1, e2, _ in result.matched)
        assert elapsed < 5.0

    def test_elements_beyond_tolerance_are_not_matched(self):
        v1 = _model([_element("a", 0.0, 0.0)])
        v2 = _model([_element("b", 0.051, 0.0)])
        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)
        assert result.matched == []

    def test_pair_across_cell_boundary(self):
        v1 = _model([_element("a", 0.049, 0.0)])
        v2 = _model([_element("b", 0.051, 0.0)])
        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)
        assert len(result.matched) == 1
