"""Rules that keep export artefacts from showing up as element changes.

Two rules, both disabled by ``Settings.strict``:

* ``ignore_properties``: glob patterns matched against ``"<pset>.<property>"``.
* One-sided property sets: a property set that exists in only one of the two models is
  almost always the result of different export settings (e.g. Revit's "Export Revit
  property sets" toggled), not of hundreds of elements being edited. Such sets are
  reported once in the summary instead of on every element.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase

from .config import Settings
from .parser import ParsedModel
from .schemas import OneSidedPset


@dataclass(frozen=True)
class PropertyFilter:
    ignore_patterns: tuple[str, ...] = ()
    excluded_psets: frozenset[str] = frozenset()

    def is_ignored(self, pset_name: str, property_name: str) -> bool:
        if pset_name in self.excluded_psets:
            return True
        key = f"{pset_name}.{property_name}"
        return any(fnmatchcase(key, pattern) for pattern in self.ignore_patterns)


NO_FILTER = PropertyFilter()


def find_one_sided_psets(v1: ParsedModel, v2: ParsedModel) -> list[OneSidedPset]:
    v1_counts = _pset_element_counts(v1)
    v2_counts = _pset_element_counts(v2)
    result = [
        OneSidedPset(pset_name=name, only_in="v1", element_count=count)
        for name, count in v1_counts.items()
        if name not in v2_counts
    ]
    result += [
        OneSidedPset(pset_name=name, only_in="v2", element_count=count)
        for name, count in v2_counts.items()
        if name not in v1_counts
    ]
    return sorted(result, key=lambda p: (-p.element_count, p.pset_name, p.only_in))


def build_property_filter(cfg: Settings, one_sided: list[OneSidedPset]) -> PropertyFilter:
    if cfg.strict:
        return NO_FILTER
    return PropertyFilter(
        ignore_patterns=tuple(cfg.ignore_properties),
        excluded_psets=frozenset(p.pset_name for p in one_sided),
    )


def _pset_element_counts(model: ParsedModel) -> Counter[str]:
    counts: Counter[str] = Counter()
    for el in model.elements.values():
        counts.update({p.pset_name for p in el.properties})
    return counts
