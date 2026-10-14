"""A review of every IFC file changed between two revisions, e.g. the two ends of a pull
request. ``bimdelta review`` renders it; the GitHub Action posts it as a PR comment."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlencode

from bimdelta_core import DiffResult, Settings, run_diff
from bimdelta_core.engine import IFC_LOCK
from bimdelta_core.parser import parse_ifc

from . import __version__
from .gitutil import git, git_text, is_lfs_pointer, resolve_lfs
from .render import (
    class_table,
    element_sections,
    has_changes,
    md_escape,
    notes,
    quantity_changed,
    quantity_coverage_note,
    quantity_headline,
    quantity_table,
    storey_table,
)

PATHSPEC = ":(glob,icase)**/*.ifc"
STATUS_WORDS = {"A": "added", "D": "deleted", "M": "modified", "R": "renamed"}


@dataclass
class FileReview:
    path: str
    status: str  # A, D, M or R
    old_path: str | None = None
    result: DiffResult | None = None
    element_count: int | None = None  # for added and deleted files
    error: str | None = None
    old_lfs: bool = False
    new_lfs: bool = False

    @property
    def changed(self) -> bool:
        if self.status in ("A", "D"):
            return True
        return self.result is not None and has_changes(self.result)


@dataclass
class Review:
    base: str
    head: str
    files: list[FileReview] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(f.changed for f in self.files)


def changed_ifc_files(root: Path, base: str, head: str) -> list[tuple[str, str | None, str]]:
    """(status, old path, new path) for each IFC file that differs between two commits."""
    out = git("diff", "--name-status", "-z", "-M", base, head, "--", PATHSPEC, cwd=root)
    fields = out.decode("utf-8").split("\0")
    changes = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i][0]
        if status == "R":
            changes.append(("R", fields[i + 1], fields[i + 2]))
            i += 3
        else:
            path = fields[i + 1]
            changes.append((status if status in "ADM" else "M", path, path))
            i += 2
    return changes


def review(root: Path, base: str, head: str, cfg: Settings) -> Review:
    base_sha = git_text("rev-parse", "--verify", f"{base}^{{commit}}", cwd=root)
    head_sha = git_text("rev-parse", "--verify", f"{head}^{{commit}}", cwd=root)
    result = Review(base=base_sha, head=head_sha)

    for status, old_path, new_path in changed_ifc_files(root, base_sha, head_sha):
        fr = FileReview(path=new_path, status=status, old_path=old_path if status == "R" else None)
        with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
            scratch = Path(tmp)
            try:
                old = new = None
                if status != "A":
                    old, fr.old_lfs = materialise(root, base_sha, old_path, scratch, "old")
                if status != "D":
                    new, fr.new_lfs = materialise(root, head_sha, new_path, scratch, "new")
                if old is not None and new is not None:
                    name = Path(new_path).name
                    fr.result = run_diff(str(old), name, str(new), name, cfg)
                else:
                    present = old or new
                    with IFC_LOCK:
                        fr.element_count = len(parse_ifc(str(present), new_path).elements)
            except Exception as exc:
                fr.error = str(exc)
        result.files.append(fr)
    return result


def materialise(root: Path, rev: str, path: str, scratch: Path, stem: str) -> tuple[Path, bool]:
    data = git("cat-file", "blob", f"{rev}:{path}", cwd=root)
    file = scratch / f"{stem}.ifc"
    file.write_bytes(data)
    lfs = is_lfs_pointer(data[:2048])
    return resolve_lfs(file, scratch, cwd=root), lfs


# --- Links to the hosted viewer --------------------------------------------------------


@dataclass
class ViewerLinks:
    """Builds "View 3D diff" links for files in a public GitHub repository."""

    viewer_url: str
    repo: str  # owner/name holding the base commit
    head_repo: str | None = None  # owner/name holding the head commit, for forks

    def url(self, rv: Review, fr: FileReview) -> str | None:
        if fr.status in ("A", "D"):
            return None
        v1 = _raw_url(self.repo, rv.base, fr.old_path or fr.path, fr.old_lfs)
        v2 = _raw_url(self.head_repo or self.repo, rv.head, fr.path, fr.new_lfs)
        return f"{self.viewer_url.rstrip('/')}/?{urlencode({'v1_url': v1, 'v2_url': v2})}"


def _raw_url(repo: str, sha: str, path: str, lfs: bool) -> str:
    # raw.githubusercontent.com serves the LFS pointer; media.githubusercontent.com the content.
    host = (
        "https://media.githubusercontent.com/media" if lfs else "https://raw.githubusercontent.com"
    )
    return f"{host}/{repo}/{sha}/{quote(path)}"


# --- Markdown --------------------------------------------------------------------------


def to_markdown(
    rv: Review,
    links: ViewerLinks | None = None,
    *,
    limit: int = 50,
    max_chars: int | None = None,
) -> str:
    """The review as Markdown. With ``max_chars``, element lists are shortened (and finally
    left out) until the text fits, e.g. GitHub's 65,536 character comment limit."""
    caps = [limit] + [c for c in (20, 5) if limit <= 0 or c < limit]
    attempts = [(cap, True, True) for cap in caps] + [(0, False, True), (0, False, False)]
    for cap, elements, storeys in attempts:
        text = _render(rv, links, cap, elements=elements, storeys=storeys)
        if max_chars is None or len(text) <= max_chars:
            break
    return text


def _render(
    rv: Review,
    links: ViewerLinks | None,
    limit: int,
    *,
    elements: bool = True,
    storeys: bool = True,
) -> str:
    n = len(rv.files)
    lines = [
        "## BIMDelta review",
        "",
        f"`{rv.base[:7]}` → `{rv.head[:7]}` · "
        + (f"{n} IFC file{'s' if n != 1 else ''} changed" if n else "no IFC files changed"),
    ]
    for fr in rv.files:
        lines += ["", *_file_section(rv, fr, links, limit, elements, storeys)]
    lines += ["", "---", f"<sub>bimdelta {__version__}</sub>"]
    return "\n".join(lines) + "\n"


def _file_section(
    rv: Review,
    fr: FileReview,
    links: ViewerLinks | None,
    limit: int,
    elements: bool,
    storeys: bool,
) -> list[str]:
    title = f"### {md_escape(fr.path)}"
    if fr.status == "R" and fr.old_path:
        title += f" (renamed from {md_escape(fr.old_path)})"
    if fr.error:
        return [title, "", f"Could not compare this file: {md_escape(fr.error)}"]
    if fr.result is None:
        state = "New file" if fr.status == "A" else "Deleted file"
        return [title, "", f"{state} with {fr.element_count} elements."]

    r = fr.result
    s = r.summary
    lines = [title, ""]
    if has_changes(r):
        lines.append(f"**{s.added}** added · **{s.removed}** removed · **{s.modified}** modified")
    url = links.url(rv, fr) if links else None
    if url:
        lines += ["", f"[View 3D diff]({url})"]
    lines += ["", *class_table(r, unchanged=False)]

    q = r.quantities
    headline = quantity_headline(q)
    if headline:
        lines += ["", f"**Quantities:** {headline}"]

    found = notes(r, esc=md_escape, strong=lambda t: f"**{t}**")
    coverage = quantity_coverage_note(q) if q is not None and headline else None
    if coverage:
        found.append(coverage)
    if found:
        lines += ["", *(f"> {n}" for n in found)]

    if storeys:
        table = storey_table(r)
        if table:
            lines += ["", "<details><summary>By storey</summary>", "", *table, "", "</details>"]
        if q is not None and headline:
            for label, rows in (("material", q.by_material), ("class", q.by_class)):
                changed = [row for row in rows if quantity_changed(row)]
                if changed:
                    table = quantity_table(changed, q.total, label.capitalize())
                    summary = f"Quantities by {label}"
                    lines += ["", f"<details><summary>{summary}</summary>", "", *table]
                    lines += ["", "</details>"]

    if elements and has_changes(r):
        total = s.added + s.removed + s.modified
        lines += ["", f"<details><summary>Changed elements ({total})</summary>"]
        for heading, items in element_sections(r, limit):
            lines += ["", f"**{heading}**", "", *items]
        lines += ["", "</details>"]
    return lines
