"""The ``--filter`` expression: ``class=IfcWall*,storey=Level 1,change=modified``.

Terms are separated by commas. Terms with the same key are alternatives (OR), different
keys must all match (AND). Values are case-insensitive and may use ``*`` and ``?``.
"""

from __future__ import annotations

from collections.abc import Callable
from fnmatch import fnmatchcase

from bimdelta_core import ElementDiff

KEYS = ("class", "storey", "change", "name", "id")


class FilterError(ValueError):
    pass


def parse_filter(expression: str) -> Callable[[ElementDiff], bool]:
    terms: dict[str, list[str]] = {}
    for raw in expression.split(","):
        if not raw.strip():
            continue
        key, sep, value = raw.partition("=")
        key = key.strip().lower()
        if not sep or not value.strip():
            raise FilterError(f"expected key=value, got {raw.strip()!r}")
        if key not in KEYS:
            raise FilterError(f"unknown filter key {key!r}; valid keys: {', '.join(KEYS)}")
        terms.setdefault(key, []).append(value.strip().lower())

    def keep(el: ElementDiff) -> bool:
        fields = {
            "class": [el.ifc_class],
            "storey": [el.storey or "", el.old_storey or ""],
            "change": [el.change_type.value],
            "name": [el.name or "", el.old_name or ""],
            "id": [el.global_id, el.matched_global_id or ""],
        }
        return all(
            any(
                fnmatchcase(field.lower(), pattern) for field in fields[key] for pattern in patterns
            )
            for key, patterns in terms.items()
        )

    return keep
