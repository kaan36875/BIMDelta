"""Elements changed on two branches since they diverged.

Both branches are compared with their merge base. An element modified on both sides is a
**conflict** when the two changed the same field (a property, the placement, the geometry,
...) to different results, and a **warning** when they changed different fields, which
usually combine but deserve a look. Deleting an element on one side while modifying it on
the other is a conflict. Nothing is merged: this is a report, like ``git merge-tree``.

Whether an overlapping field ended up the same on both sides is decided by a third
comparison, of the two branch versions with each other, so identical edits are not flagged.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from bimdelta_core import ChangeType, DiffResult, ElementDiff, Settings, run_diff

from .gitutil import git, git_text
from .render import describe_changes, format_value, md_code, md_escape
from .review import PATHSPEC, materialise

Level = Literal["conflict", "warning"]


@dataclass
class ElementConflict:
    global_id: str  # in the merge base
    ifc_class: str
    name: str | None
    storey: str | None
    level: Level
    fields: list[str]  # the fields both sides changed differently; empty for warnings
    ours: list[str]  # what each side changed
    theirs: list[str]


@dataclass
class FileConflict:
    path: str
    elements: list[ElementConflict] = field(default_factory=list)
    note: str | None = None  # a file-level clash, e.g. deleted on one side
    error: str | None = None

    @property
    def conflicts(self) -> int:
        return sum(1 for e in self.elements if e.level == "conflict") + bool(self.note)

    @property
    def warnings(self) -> int:
        return sum(1 for e in self.elements if e.level == "warning")


@dataclass
class ConflictReport:
    base: str
    ours: str
    theirs: str
    ours_name: str
    theirs_name: str
    files: list[FileConflict] = field(default_factory=list)

    @property
    def conflicts(self) -> int:
        return sum(f.conflicts for f in self.files)

    @property
    def warnings(self) -> int:
        return sum(f.warnings for f in self.files)


def find_conflicts(
    root: Path, ours: str, theirs: str, cfg: Settings, paths: list[str] | None = None
) -> ConflictReport:
    ours_sha = git_text("rev-parse", "--verify", f"{ours}^{{commit}}", cwd=root)
    theirs_sha = git_text("rev-parse", "--verify", f"{theirs}^{{commit}}", cwd=root)
    base = git_text("merge-base", ours_sha, theirs_sha, cwd=root)
    report = ConflictReport(base, ours_sha, theirs_sha, ours, theirs)

    spec = paths or [PATHSPEC]
    ours_changes = _changed(root, base, ours_sha, spec)
    theirs_changes = _changed(root, base, theirs_sha, spec)
    for path in sorted(set(ours_changes) & set(theirs_changes)):
        a, b = ours_changes[path], theirs_changes[path]
        fc = FileConflict(path)
        if a == "A" and b == "A":
            fc.note = "added on both branches"
        elif "D" in (a, b) and a != b:
            fc.note = f"deleted on {ours if a == 'D' else theirs}, modified on the other"
        elif a == "M" and b == "M":
            try:
                fc.elements = _file_conflicts(root, path, base, ours_sha, theirs_sha, cfg)
            except Exception as exc:
                fc.error = str(exc)
        if fc.note or fc.error or fc.elements:
            report.files.append(fc)
    return report


def _changed(root: Path, base: str, rev: str, spec: list[str]) -> dict[str, str]:
    """Path → status (A, D or M) of the files that differ between ``base`` and ``rev``.
    Renames count as a delete and an add, since the paths no longer line up."""
    out = git("diff", "--name-status", "-z", "--no-renames", base, rev, "--", *spec, cwd=root)
    fields = out.decode("utf-8").split("\0")
    return {fields[i + 1]: fields[i][0] for i in range(0, len(fields) - 1, 2) if fields[i]}


def _file_conflicts(
    root: Path, path: str, base: str, ours: str, theirs: str, cfg: Settings
) -> list[ElementConflict]:
    name = Path(path).name
    with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
        scratch = Path(tmp)
        b, _ = materialise(root, base, path, scratch, "base")
        a, _ = materialise(root, ours, path, scratch, "ours")
        t, _ = materialise(root, theirs, path, scratch, "theirs")
        to_ours = run_diff(str(b), name, str(a), name, cfg)
        to_theirs = run_diff(str(b), name, str(t), name, cfg)
        between = run_diff(str(a), name, str(t), name, cfg)
    return compare_sides(to_ours, to_theirs, between)


def compare_sides(
    to_ours: DiffResult, to_theirs: DiffResult, between: DiffResult
) -> list[ElementConflict]:
    """Element conflicts from the base→ours, base→theirs and ours→theirs comparisons."""
    ours = _by_base_id(to_ours)
    theirs = _by_base_id(to_theirs)
    # ours→theirs, keyed by the element's id on our side.
    across = _by_base_id(between)

    found = []
    for gid in sorted(set(ours) & set(theirs)):
        a, t = ours[gid], theirs[gid]
        a_removed = a.change_type == ChangeType.REMOVED
        t_removed = t.change_type == ChangeType.REMOVED
        if a_removed and t_removed:
            continue
        if a_removed or t_removed:
            level: Level = "conflict"
            clash = ["deleted"]
        else:
            fa, ft = changed_fields(a), changed_fields(t)
            overlap = fa.keys() & ft.keys()
            other = across.get(a.global_id)
            still_different = changed_fields(other) if other is not None else {}
            clash = sorted(overlap & still_different.keys())
            if clash:
                level = "conflict"
            elif fa.keys() - overlap and ft.keys() - overlap:
                level = "warning"
            else:
                continue  # the same edit on both sides, or one side's edit contains the other's
        el = t if a_removed else a
        found.append(
            ElementConflict(
                global_id=gid,
                ifc_class=el.ifc_class,
                name=el.name,
                storey=el.storey,
                level=level,
                fields=clash if level == "conflict" else [],
                ours=_describe(a),
                theirs=_describe(t),
            )
        )
    return found


def _by_base_id(result: DiffResult) -> dict[str, ElementDiff]:
    """Changed elements keyed by their GlobalId in the older version of ``result``."""
    out = {}
    for el in result.elements:
        if el.change_type in (ChangeType.MODIFIED, ChangeType.REMOVED):
            out[el.matched_global_id or el.global_id] = el
    return out


def changed_fields(el: ElementDiff) -> dict[str, str]:
    """Field name → new value (as text) for everything ``el`` changed."""
    fields = {
        f"{p.pset_name}.{p.property_name}": format_value(p.new_value) for p in el.property_changes
    }
    if el.change_type == ChangeType.REMOVED:
        fields["deleted"] = ""
    if el.type_changed:
        fields["type"] = el.new_type_name or ""
    if el.name_changed:
        fields["name"] = el.name or ""
    if el.storey_changed:
        fields["storey"] = el.storey or ""
    if el.material_changed:
        fields["material"] = el.new_material or ""
    if el.placement_changed:
        fields["placement"] = ""
    if el.geometry_changed:
        fields["geometry"] = ""
    return fields


def _describe(el: ElementDiff) -> list[str]:
    if el.change_type == ChangeType.REMOVED:
        return ["deleted"]
    return [d for d in describe_changes(el) if d != "geometry not evaluated"]


# --- Markdown -------------------------------------------------------------------------


def to_markdown(report: ConflictReport) -> str:
    ours, theirs = md_escape(report.ours_name), md_escape(report.theirs_name)
    lines = [
        f"## BIMDelta: {ours} and {theirs}",
        "",
        f"Merge base `{report.base[:7]}`. "
        + (
            f"**{report.conflicts}** conflict(s), **{report.warnings}** warning(s)."
            if report.files
            else "No element was changed on both branches."
        ),
    ]
    for fc in report.files:
        lines += ["", f"### {md_escape(fc.path)}", ""]
        if fc.error:
            lines.append(f"Could not compare this file: {md_escape(fc.error)}")
            continue
        if fc.note:
            lines.append(f"**Conflict:** {md_escape(fc.note)}.")
            continue
        lines += [
            f"| | Element | Fields | {ours} | {theirs} |",
            "|---|---|---|---|---|",
        ]
        for e in sorted(fc.elements, key=lambda e: (e.level != "conflict", e.ifc_class)):
            name = md_escape(e.name or "(unnamed)")
            label = f"{md_escape(e.ifc_class)} {name} {md_code(e.global_id)}"
            mark = "**conflict**" if e.level == "conflict" else "warning"
            fields = ", ".join(md_escape(f) for f in e.fields) or "different fields"
            lines.append(f"| {mark} | {label} | {fields} | {_cell(e.ours)} | {_cell(e.theirs)} |")
    return "\n".join(lines) + "\n"


def _cell(changes: list[str]) -> str:
    return "<br>".join(md_escape(c) for c in changes) or "—"
