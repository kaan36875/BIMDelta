"""Text renderings of a DiffResult: a Rich terminal table and Markdown."""

from __future__ import annotations

import re

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from bimdelta_core import ChangeType, DiffResult, ElementDiff, QuantityDeltaRow, QuantityReport
from bimdelta_core.quantities import NO_MATERIAL

CHANGE_ORDER = (ChangeType.MODIFIED, ChangeType.ADDED, ChangeType.REMOVED)
CHANGE_STYLE = {
    ChangeType.ADDED: "green",
    ChangeType.REMOVED: "red",
    ChangeType.MODIFIED: "yellow",
    ChangeType.UNCHANGED: "dim",
}
COLUMNS = ("added", "removed", "modified", "unchanged")


def format_value(value) -> str:
    if value is None:
        return "∅"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def describe_changes(el: ElementDiff) -> list[str]:
    """What changed on a modified element, one short phrase per change."""
    parts = [
        f"{p.pset_name}.{p.property_name}: {format_value(p.old_value)} → "
        f"{format_value(p.new_value)}"
        for p in el.property_changes
    ]
    if el.type_changed:
        parts.append(f"type: {el.old_type_name} → {el.new_type_name}")
    if el.name_changed:
        parts.append(f"name: {el.old_name} → {el.name}")
    if el.storey_changed:
        parts.append(f"storey: {el.old_storey} → {el.storey}")
    if el.material_changed:
        parts.append(f"material: {el.old_material or '∅'} → {el.new_material or '∅'}")
    if el.placement_changed:
        parts.append("moved")
    if el.geometry_changed:
        parts.append("geometry changed")
    if el.geometry_unknown:
        parts.append("geometry not evaluated")
    return parts


def identity_note(el: ElementDiff) -> str | None:
    if el.matched_global_id and el.match_method is not None:
        return f"matched by {el.match_method.value.replace('_', ' ')}, was {el.matched_global_id}"
    return None


def changed_elements(result: DiffResult, change: ChangeType) -> list[ElementDiff]:
    els = [el for el in result.elements if el.change_type == change]
    return sorted(els, key=lambda el: (el.ifc_class, el.storey or "", el.name or "", el.global_id))


def has_changes(result: DiffResult) -> bool:
    s = result.summary
    return bool(s.added or s.removed or s.modified)


# --- Markdown -------------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>|#~])")


def md_escape(text: str) -> str:
    """Escape text from a model (names, values) so it cannot inject Markdown or HTML."""
    return _MD_SPECIAL.sub(r"\\\1", text.replace("\r", " ").replace("\n", " "))


def md_code(text: str) -> str:
    """Inline code for identifiers from a model; falls back to escaped text if the value
    contains a backtick and could close the code span."""
    if any(ch in text for ch in "`\r\n"):
        return md_escape(text)
    return f"`{text}`"


def to_markdown(
    result: DiffResult,
    *,
    summary_only: bool = False,
    limit: int = 100,
    title: str | None = None,
) -> str:
    title = title or f"{result.v1_filename} → {result.v2_filename}"
    lines = [f"### BIMDelta: {md_escape(title)}", ""]
    lines += class_table(result)
    headline = quantity_headline(result.quantities)
    if headline:
        lines += ["", f"**Quantities:** {headline}"]
    lines += _markdown_notes(result)
    if not summary_only:
        for heading, items in element_sections(result, limit):
            lines += ["", f"#### {heading}", "", *items]
    return "\n".join(lines) + "\n"


def _row(label: str, counts: dict[str, int], cols: tuple[str, ...]) -> str:
    return f"| {label} | " + " | ".join(str(counts.get(c, 0)) for c in cols) + " |"


def class_table(result: DiffResult, *, unchanged: bool = True) -> list[str]:
    """Per-class counts as a Markdown table, changed classes only, with a total row."""
    s = result.summary
    if not has_changes(result):
        return [f"No element changes ({s.unchanged} unchanged)."]
    cols = COLUMNS if unchanged else COLUMNS[:3]
    lines = [
        "| Class | " + " | ".join(c.capitalize() for c in cols) + " |",
        "|---|" + "---:|" * len(cols),
        _row("**Total**", {c: getattr(s, c) for c in cols}, cols),
    ]
    for cls, counts in sorted(s.by_class.items()):
        if any(counts.get(c, 0) for c in COLUMNS[:3]):
            lines.append(_row(md_escape(cls), counts, cols))
    return lines


def storey_table(result: DiffResult) -> list[str]:
    """Per-storey counts of changed elements; empty when nothing changed."""
    rows = [
        (storey, counts)
        for storey, counts in sorted(result.summary.by_storey.items())
        if any(counts.get(c, 0) for c in COLUMNS[:3])
    ]
    if not rows:
        return []
    lines = ["| Storey | Added | Removed | Modified |", "|---|---:|---:|---:|"]
    for storey, counts in rows:
        lines.append(_row(md_escape(storey), counts, COLUMNS[:3]))
    return lines


def element_sections(result: DiffResult, limit: int = 100) -> list[tuple[str, list[str]]]:
    """(heading, bullet lines) for modified, added and removed elements; ``limit`` caps each
    section, 0 means no cap."""
    sections = []
    for change in CHANGE_ORDER:
        els = changed_elements(result, change)
        if not els:
            continue
        shown = els if limit <= 0 else els[:limit]
        items = [markdown_element(el) for el in shown]
        if len(els) > len(shown):
            items.append(f"- … and {len(els) - len(shown)} more")
        sections.append((f"{change.value.capitalize()} ({len(els)})", items))
    return sections


def markdown_element(el: ElementDiff) -> str:
    head = f"- {md_code(el.ifc_class)} **{md_escape(el.name or '(unnamed)')}**"
    if el.storey:
        head += f" ({md_escape(el.storey)})"
    head += f" {md_code(el.global_id)}"
    details = describe_changes(el) if el.change_type == ChangeType.MODIFIED else []
    note = identity_note(el)
    if note:
        details.append(note)
    if details:
        head += " — " + "; ".join(md_escape(d) for d in details)
    return head


def notes(result: DiffResult, esc=str, strong=str) -> list[str]:
    """Model-level remarks: storey moves, unevaluated geometry, what the noise filter hid.

    ``esc`` escapes text taken from the models; ``strong`` emphasises it.
    """
    s = result.summary
    out: list[str] = []
    for ch in s.storey_elevation_changes:
        out.append(
            f"Storey {strong(esc(ch.storey_name))} elevation: "
            f"{ch.old_elevation:.3f} → {ch.new_elevation:.3f} m"
        )
    if s.geometry_unknown:
        out.append(f"Geometry could not be evaluated for {s.geometry_unknown} element(s).")
    if s.noise is not None and not s.noise.strict:
        hidden = []
        if s.noise.ignored_property_changes:
            hidden.append(f"{s.noise.ignored_property_changes} property difference(s) ignored")
        one_sided = s.noise.one_sided_psets
        if one_sided:
            names = ", ".join(esc(p.pset_name) for p in one_sided[:5])
            if len(one_sided) > 5:
                names += f" and {len(one_sided) - 5} more"
            hidden.append(f"property sets in one version only: {names}")
        if hidden:
            out.append("Noise filter: " + "; ".join(hidden) + " (--strict shows them).")
    return out


def _markdown_notes(result: DiffResult) -> list[str]:
    found = notes(result, esc=md_escape, strong=lambda t: f"**{t}**")
    return ["", *(f"> {n}" for n in found)] if found else []


# --- Quantities -----------------------------------------------------------------------

QTY_COLUMNS = (
    ("count", "Count"),
    ("length", "Length m"),
    ("area", "Area m²"),
    ("volume", "Volume m³"),
    ("weight", "Weight kg"),
)
# Smallest change worth a mention in the headline.
HEADLINE_MIN = {"volume": 0.005, "weight": 0.5}
HEADLINE_ITEMS = 4


def quantity_columns(rows: list[QuantityDeltaRow]) -> list[str]:
    """Count, plus each measure that is non-zero somewhere in either version."""
    return ["count"] + [
        attr
        for attr, _ in QTY_COLUMNS[1:]
        if any(getattr(r.v1, attr) or getattr(r.v2, attr) for r in rows)
    ]


def quantity_cell(row: QuantityDeltaRow, attr: str) -> str:
    """The new value and the change, e.g. ``12.40 (+1.20)``."""
    new, delta = getattr(row.v2, attr), getattr(row.delta, attr)
    if attr == "count":
        return f"{new} ({delta:+d})"
    digits = 0 if attr == "weight" else 2
    return f"{new:,.{digits}f} ({delta:+,.{digits}f})"


def quantity_changed(row: QuantityDeltaRow) -> bool:
    d = row.delta
    return bool(d.count) or any(
        abs(getattr(d, attr)) >= HEADLINE_MIN.get(attr, 0.005) for attr, _ in QTY_COLUMNS[1:]
    )


def quantity_table(
    rows: list[QuantityDeltaRow], total: QuantityDeltaRow, label: str, esc=md_escape
) -> list[str]:
    """A Markdown table of v2 values and changes, with the total first."""
    cols = quantity_columns([*rows, total])
    heads = dict(QTY_COLUMNS)
    lines = [
        f"| {label} | " + " | ".join(heads[c] for c in cols) + " |",
        "|---|" + "---:|" * len(cols),
        "| **Total** | " + " | ".join(quantity_cell(total, c) for c in cols) + " |",
    ]
    for row in rows:
        cells = " | ".join(quantity_cell(row, c) for c in cols)
        lines.append(f"| {esc(row.group)} | {cells} |")
    return lines


def quantity_headline(report: QuantityReport | None, esc=md_escape) -> str | None:
    """The largest volume and weight changes per material, e.g.
    ``Concrete +1.20 m³ · Steel -400 kg``; falls back to classes when no element has a
    material. None when no quantity changed."""
    if report is None:
        return None
    rows = report.by_material
    if all(r.group == NO_MATERIAL for r in rows):
        rows = report.by_class
    items = []
    # Volumes first, then weights; each by the size of the change.
    for attr, unit, digits in (("volume", "m³", 2), ("weight", "kg", 0)):
        changed = [r for r in rows if abs(getattr(r.delta, attr)) >= HEADLINE_MIN[attr]]
        changed.sort(key=lambda r: -abs(getattr(r.delta, attr)))
        items += [f"{esc(r.group)} {getattr(r.delta, attr):+,.{digits}f} {unit}" for r in changed]
    if not items:
        return None
    text = " · ".join(items[:HEADLINE_ITEMS])
    if len(items) > HEADLINE_ITEMS:
        text += f" · {len(items) - HEADLINE_ITEMS} more"
    return text


def missing_quantities(report, v1_name: str, v2_name: str) -> list[str]:
    """Notes about elements without quantity sets (``report`` is a QuantityReport or a
    QuantityDelta)."""
    return [
        f"{n} element(s) in {name} have no quantities (export base quantities to include them)."
        for n, name in (
            (report.v1_without_quantities, v1_name),
            (report.v2_without_quantities, v2_name),
        )
        if n
    ]


def quantity_coverage_note(report: QuantityReport) -> str | None:
    """A warning when only one version has quantity sets at all, e.g. base quantities were
    exported for one of them only: the delta is then the whole take-off, not a change."""
    t = report.total
    none_before = t.v1.count > 0 and report.v1_without_quantities == t.v1.count
    none_after = t.v2.count > 0 and report.v2_without_quantities == t.v2.count
    if none_before == none_after:
        return None
    side = "base" if none_before else "head"
    return (
        f"The {side} version has no quantity sets, so the quantity change is its whole "
        "take-off. Export base quantities for both versions."
    )


# --- Terminal -------------------------------------------------------------------------


def print_table(
    console: Console, result: DiffResult, *, summary_only: bool = False, limit: int = 100
) -> None:
    s = result.summary
    console.print(
        Text.assemble(
            ("BIMDelta  ", "bold"),
            (result.v1_filename, "cyan"),
            " → ",
            (result.v2_filename, "cyan"),
            (f"   ({result.v1_ifc_schema} → {result.v2_ifc_schema})", "dim"),
        )
    )

    summary = Table(box=box.SIMPLE_HEAD, show_edge=False)
    summary.add_column("Class")
    for col in COLUMNS:
        summary.add_column(col.capitalize(), justify="right", style=CHANGE_STYLE[ChangeType(col)])
    summary.add_row(
        "[bold]Total[/]", str(s.added), str(s.removed), str(s.modified), str(s.unchanged)
    )
    summary.add_section()
    for cls, counts in sorted(s.by_class.items()):
        summary.add_row(escape(cls), *(str(counts.get(c, 0)) for c in COLUMNS))
    console.print(summary)

    for note in notes(result):
        console.print(Text(note, "dim"))

    if summary_only or not has_changes(result):
        return

    elements = Table(box=box.SIMPLE_HEAD, show_edge=False, expand=False)
    elements.add_column("Change")
    elements.add_column("Class")
    elements.add_column("Name", overflow="fold")
    elements.add_column("Storey")
    elements.add_column("GlobalId", style="dim", no_wrap=True)
    elements.add_column("What changed", overflow="fold")

    rows = [el for change in CHANGE_ORDER for el in changed_elements(result, change)]
    shown = rows if limit <= 0 else rows[:limit]
    for el in shown:
        details = describe_changes(el) if el.change_type == ChangeType.MODIFIED else []
        note = identity_note(el)
        if note:
            details.append(note)
        elements.add_row(
            Text(el.change_type.value, CHANGE_STYLE[el.change_type]),
            Text(el.ifc_class),
            Text(el.name or ""),
            Text(el.storey or ""),
            Text(el.global_id),
            Group(*(Text(d) for d in details)) if details else Text(""),
        )
    console.print(elements)
    if len(rows) > len(shown):
        console.print(
            Text(f"… and {len(rows) - len(shown)} more (use --limit 0 to list all)", "dim")
        )
