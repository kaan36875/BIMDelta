"""Text renderings of a DiffResult: a Rich terminal table and Markdown."""

from __future__ import annotations

import re

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from bimdelta_core import ChangeType, DiffResult, ElementDiff

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
