from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .parser import ParsedElement, ParsedModel


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

    # Pass 1: GlobalId matching
    common_ids = set(v1_unmatched.keys()) & set(v2_unmatched.keys())
    for gid in common_ids:
        matched.append((v1_unmatched.pop(gid), v2_unmatched.pop(gid), "global_id"))

    # Pass 2: fallback matching — one-to-one by nearest placement
    if v1_unmatched and v2_unmatched:
        fallback = _fallback_match(
            list(v1_unmatched.values()),
            list(v2_unmatched.values()),
            fallback_placement_tolerance,
        )
        for v1_el, v2_el in fallback:
            matched.append((v1_el, v2_el, "fallback"))
            v1_unmatched.pop(v1_el.global_id)
            v2_unmatched.pop(v2_el.global_id)

    return MatchResult(
        matched=matched,
        added=list(v2_unmatched.values()),
        removed=list(v1_unmatched.values()),
    )


def _fallback_match(
    v1_elements: list[ParsedElement],
    v2_elements: list[ParsedElement],
    tolerance: float,
) -> list[tuple[ParsedElement, ParsedElement]]:
    """One-to-one greedy nearest-pair matching by (class, name, storey, placement)."""
    candidates: list[tuple[float, int, int]] = []

    for i, e1 in enumerate(v1_elements):
        for j, e2 in enumerate(v2_elements):
            if e1.ifc_class != e2.ifc_class:
                continue
            if e1.name != e2.name:
                continue
            if e1.storey != e2.storey:
                continue

            dist = _placement_distance(e1.world_placement, e2.world_placement)
            if dist <= tolerance:
                candidates.append((dist, i, j))

    candidates.sort(key=lambda x: x[0])

    used_v1: set[int] = set()
    used_v2: set[int] = set()
    result: list[tuple[ParsedElement, ParsedElement]] = []

    for dist, i, j in candidates:
        if i in used_v1 or j in used_v2:
            continue
        used_v1.add(i)
        used_v2.add(j)
        result.append((v1_elements[i], v2_elements[j]))

    return result


def _placement_distance(m1: np.ndarray, m2: np.ndarray) -> float:
    """Euclidean distance between translation components of two 4x4 matrices."""
    t1 = m1[:3, 3]
    t2 = m2[:3, 3]
    return float(np.linalg.norm(t1 - t2))
