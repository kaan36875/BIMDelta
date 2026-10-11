from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product

import numpy as np

from .parser import ParsedElement, ParsedModel

_NEIGHBOUR_OFFSETS = tuple(product((-1, 0, 1), repeat=3))


@dataclass
class MatchResult:
    matched: list[tuple[ParsedElement, ParsedElement, str]]  # (v1_el, v2_el, method)
    added: list[ParsedElement]  # in v2 only
    removed: list[ParsedElement]  # in v1 only


def match_elements(
    v1: ParsedModel,
    v2: ParsedModel,
    fallback_placement_tolerance: float,
) -> MatchResult:
    matched: list[tuple[ParsedElement, ParsedElement, str]] = []

    v1_unmatched: dict[str, ParsedElement] = dict(v1.elements)
    v2_unmatched: dict[str, ParsedElement] = dict(v2.elements)

    # Pass 1: GlobalId
    common_ids = set(v1_unmatched) & set(v2_unmatched)
    for gid in sorted(common_ids):
        matched.append((v1_unmatched.pop(gid), v2_unmatched.pop(gid), "global_id"))

    # Pass 2: authoring-tool element id stored in IfcElement.Tag (e.g. Revit ElementId)
    for v1_el, v2_el in _tag_match(v1, v2, v1_unmatched, v2_unmatched):
        matched.append((v1_el, v2_el, "tag"))
        del v1_unmatched[v1_el.global_id]
        del v2_unmatched[v2_el.global_id]

    # Pass 3: same class, name and storey at (nearly) the same placement
    if v1_unmatched and v2_unmatched:
        fallback = _fallback_match(
            list(v1_unmatched.values()),
            list(v2_unmatched.values()),
            fallback_placement_tolerance,
        )
        for v1_el, v2_el in fallback:
            matched.append((v1_el, v2_el, "fallback"))
            del v1_unmatched[v1_el.global_id]
            del v2_unmatched[v2_el.global_id]

    return MatchResult(
        matched=matched,
        added=list(v2_unmatched.values()),
        removed=list(v1_unmatched.values()),
    )


def _tag_match(
    v1: ParsedModel,
    v2: ParsedModel,
    v1_unmatched: dict[str, ParsedElement],
    v2_unmatched: dict[str, ParsedElement],
) -> list[tuple[ParsedElement, ParsedElement]]:
    # A (class, tag) key only identifies an element if it is unique in its whole model;
    # Revit, for example, writes the host's id onto openings and some sub-elements.
    v1_unique = _unique_tag_keys(v1.elements.values())
    v2_unique = _unique_tag_keys(v2.elements.values())

    v2_by_key = {
        (el.ifc_class, el.tag): el
        for el in v2_unmatched.values()
        if (el.ifc_class, el.tag) in v2_unique
    }
    pairs = []
    for el in v1_unmatched.values():
        key = (el.ifc_class, el.tag)
        if key in v1_unique and key in v2_by_key:
            pairs.append((el, v2_by_key[key]))
    return pairs


def _unique_tag_keys(elements) -> set[tuple[str, str]]:
    counts = Counter((el.ifc_class, el.tag) for el in elements if el.tag)
    return {key for key, n in counts.items() if n == 1}


def _fallback_match(
    v1_elements: list[ParsedElement],
    v2_elements: list[ParsedElement],
    tolerance: float,
) -> list[tuple[ParsedElement, ParsedElement]]:
    """One-to-one greedy nearest-pair matching by (class, name, storey, placement).

    v2 elements are bucketed on a grid whose cell size equals the tolerance, so any pair
    within tolerance lies in the same or an adjacent cell.
    """
    cell = max(tolerance, 1e-9)

    index: dict[tuple, list[int]] = defaultdict(list)
    for j, e2 in enumerate(v2_elements):
        index[(_group_key(e2), *_cell_of(e2, cell))].append(j)

    candidates: list[tuple[float, int, int]] = []
    for i, e1 in enumerate(v1_elements):
        group = _group_key(e1)
        cx, cy, cz = _cell_of(e1, cell)
        for dx, dy, dz in _NEIGHBOUR_OFFSETS:
            for j in index.get((group, cx + dx, cy + dy, cz + dz), ()):
                e2 = v2_elements[j]
                if e1.tag and e2.tag and e1.tag != e2.tag:
                    # Both carry an authoring-tool id and they differ: these are distinct
                    # elements (e.g. deleted and redrawn in place), not a re-exported one.
                    continue
                dist = _placement_distance(e1.world_placement, e2.world_placement)
                if dist <= tolerance:
                    candidates.append((dist, i, j))

    candidates.sort()

    used_v1: set[int] = set()
    used_v2: set[int] = set()
    result: list[tuple[ParsedElement, ParsedElement]] = []
    for _, i, j in candidates:
        if i in used_v1 or j in used_v2:
            continue
        used_v1.add(i)
        used_v2.add(j)
        result.append((v1_elements[i], v2_elements[j]))

    return result


def _group_key(el: ParsedElement) -> tuple[str, str | None, str | None]:
    return (el.ifc_class, el.name, el.storey)


def _cell_of(el: ParsedElement, cell: float) -> tuple[int, int, int]:
    t = el.world_placement[:3, 3]
    return (math.floor(t[0] / cell), math.floor(t[1] / cell), math.floor(t[2] / cell))


def _placement_distance(m1: np.ndarray, m2: np.ndarray) -> float:
    """Euclidean distance between translation components of two 4x4 matrices."""
    return float(np.linalg.norm(m1[:3, 3] - m2[:3, 3]))
