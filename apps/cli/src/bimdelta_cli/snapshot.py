"""A line-oriented text form of one IFC model, for Git's textconv protocol.

Git runs textconv on each version separately and line-diffs the outputs, so the text has
to be stable: one header line per element, sorted, followed by indented lines for its
type, placement, geometry and properties. A changed property then shows up as one
``-``/``+`` pair under the element's header (which ``diff.ifc.xfuncname`` puts in the
hunk header). For a matched, noise-filtered comparison use ``bimdelta diff``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from bimdelta_core import Settings
from bimdelta_core.engine import IFC_LOCK
from bimdelta_core.geometry import representation_fingerprint
from bimdelta_core.noise import PropertyFilter
from bimdelta_core.parser import ParsedElement, parse_ifc

from .render import format_value

# Matches the element header lines below; used as the Git hunk header pattern.
XFUNCNAME = "^Ifc[A-Za-z]+ .*$"


def snapshot(path: str, filename: str, cfg: Settings) -> str:
    return "\n".join(snapshot_lines(path, filename, cfg)) + "\n"


def snapshot_lines(path: str, filename: str, cfg: Settings) -> Iterator[str]:
    with IFC_LOCK:
        model = parse_ifc(path, filename, cfg.include_openings)
        memo: dict[int, str] = {}
        ifc = model._ifc_file
        fingerprints = {
            gid: representation_fingerprint(ifc.by_id(el._ifc_entity_id), memo)
            for gid, el in model.elements.items()
            if el.has_representation and el._ifc_entity_id is not None
        }

    prop_filter = (
        PropertyFilter()
        if cfg.strict
        else PropertyFilter(ignore_patterns=tuple(cfg.ignore_properties))
    )

    classes = Counter(el.ifc_class for el in model.elements.values())
    yield f"# {filename}  {model.ifc_schema}  {len(model.elements)} elements"
    yield ""
    yield "## Storeys"
    for name, elevation in sorted(model.storeys.items(), key=lambda kv: (kv[1], kv[0])):
        yield f"  {name}  {elevation:+.3f} m"
    yield ""
    yield "## Classes"
    for cls, n in sorted(classes.items()):
        yield f"  {cls}  {n}"
    yield ""
    yield "## Elements"

    for el in sorted(model.elements.values(), key=_sort_key):
        yield _header(el)
        if el.tag:
            yield f"    tag: {el.tag}"
        if el.type_name:
            yield f"    type: {el.type_name}"
        x, y, z = (float(v) for v in el.world_placement[:3, 3])
        yield f"    placement: {x:.3f}, {y:.3f}, {z:.3f}"
        fp = fingerprints.get(el.global_id)
        yield f"    geometry: {fp[:12] if fp else 'none'}"
        for prop in sorted(el.properties, key=lambda p: (p.source, p.pset_name, p.property_name)):
            if prop_filter.is_ignored(prop.pset_name, prop.property_name):
                continue
            prefix = "type " if prop.source == "type" else ""
            yield (
                f"    {prefix}{prop.pset_name}.{prop.property_name} = "
                f"{_one_line(format_value(prop.value))}"
            )


def _sort_key(el: ParsedElement) -> tuple:
    return (el.ifc_class, el.storey or "", el.name or "", el.tag or "", el.global_id)


def _header(el: ParsedElement) -> str:
    name = _one_line(el.name or "(unnamed)")
    storey = f"  @ {_one_line(el.storey)}" if el.storey else ""
    return f"{el.ifc_class} {el.global_id}  {name}{storey}"


def _one_line(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ")
