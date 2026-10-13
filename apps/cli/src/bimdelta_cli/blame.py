"""History of one element through the commits that touched an IFC file.

Consecutive versions of the file are compared with the diff engine, so an element is
followed the same way ``bimdelta diff`` matches it: by GlobalId, then Tag, then placement.
A re-export that changes an element's GlobalId therefore does not break its history.

Each comparison is cached in ``<git dir>/bimdelta-cache`` keyed by the two blob ids and the
diff settings; a later blame of any element in the same file reuses it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bimdelta_core import ChangeType, Settings, __version__, run_diff
from bimdelta_core.engine import IFC_LOCK
from bimdelta_core.parser import parse_ifc

from .gitutil import GitError, git, git_dir, git_text, repo_root, resolve_lfs
from .render import describe_changes

CACHE_DIRNAME = "bimdelta-cache"
CACHE_FORMAT = 1
_SEP = "\x1f"


@dataclass
class Commit:
    sha: str
    author: str
    date: str
    subject: str
    blob: str | None  # None where the file does not exist in this commit


@dataclass
class BlameEvent:
    change: str  # added | modified | removed | reidentified
    sha: str
    author: str
    date: str
    subject: str
    global_id: str
    ifc_class: str | None = None
    name: str | None = None
    details: list[str] = field(default_factory=list)


@dataclass
class BlameResult:
    global_id: str
    path: str
    commits_scanned: int
    truncated: bool
    events: list[BlameEvent]  # newest first
    # The element already existed before the oldest commit scanned (--max-commits).
    present_before: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class BlameError(RuntimeError):
    pass


def blame(
    global_id: str,
    path: str | None,
    cfg: Settings,
    repo: Path | str = ".",
    rev: str = "HEAD",
    max_commits: int | None = None,
) -> BlameResult:
    root = repo_root(repo)
    rel_path = _resolve_path(root, path, rev)
    # One commit more than asked for: the version just before the window is what the
    # oldest commit in it is compared with.
    commits = _history(root, rel_path, rev, None if max_commits is None else max_commits + 1)
    if not commits:
        raise BlameError(f"{rel_path} has no history at {rev}")
    truncated = max_commits is not None and len(commits) > max_commits
    window = commits[:max_commits] if truncated else commits

    cache = _Cache(git_dir(root) / CACHE_DIRNAME, cfg)

    events: list[BlameEvent] = []
    tracked = global_id
    newest = commits[0].blob
    found = newest is not None and tracked in cache.element_ids(root, newest)
    present_before = False

    # Walk from newest to oldest; each step compares a commit with its predecessor.
    for i, newer in enumerate(window):
        older = commits[i + 1] if i + 1 < len(commits) else None
        if newer.blob is None:
            continue
        older_blob = older.blob if older is not None else None
        if older_blob is None:
            # File created (or re-created) here: everything in it was added.
            info = cache.element_ids(root, newer.blob).get(tracked)
            if info is not None:
                events.append(_event("added", newer, tracked, info))
                found = True
                break
            continue
        if older_blob == newer.blob:
            continue

        rec = cache.pair(root, older_blob, newer.blob).get(tracked)
        if rec is None:
            continue
        found = True
        change = rec["change"]
        if change == ChangeType.ADDED.value:
            events.append(_event("added", newer, tracked, rec))
            break
        if change == ChangeType.REMOVED.value:
            events.append(_event("removed", newer, tracked, rec))
            continue
        previous_id = rec.get("matched_global_id") or tracked
        if change == ChangeType.MODIFIED.value:
            events.append(_event("modified", newer, tracked, rec))
        elif previous_id != tracked:
            events.append(_event("reidentified", newer, tracked, rec))
        tracked = previous_id
    else:
        if truncated and commits[-1].blob is not None:
            present_before = tracked in cache.element_ids(root, commits[-1].blob)
            found = found or present_before

    if not found:
        raise BlameError(f"no element with GlobalId {global_id} in the history of {rel_path}")

    return BlameResult(
        global_id=global_id,
        path=rel_path,
        commits_scanned=len(window),
        truncated=truncated,
        events=events,
        present_before=present_before,
    )


def _event(change: str, commit: Commit, global_id: str, rec: dict | None) -> BlameEvent:
    rec = rec or {}
    return BlameEvent(
        change=change,
        sha=commit.sha,
        author=commit.author,
        date=commit.date,
        subject=commit.subject,
        global_id=global_id,
        ifc_class=rec.get("ifc_class"),
        name=rec.get("name"),
        details=list(rec.get("details", [])),
    )


def _resolve_path(root: Path, path: str | None, rev: str) -> str:
    if path is not None:
        full = Path(path)
        if not full.is_absolute():
            full = (Path.cwd() / full).resolve()
        try:
            return full.relative_to(root.resolve()).as_posix()
        except ValueError:
            raise BlameError(f"{path} is not inside the repository at {root}") from None
    tracked = [
        p
        for p in git_text("ls-tree", "-r", "--name-only", rev, cwd=root).splitlines()
        if p.lower().endswith(".ifc")
    ]
    if len(tracked) == 1:
        return tracked[0]
    if not tracked:
        raise BlameError(f"no .ifc file is tracked at {rev}")
    raise BlameError("several .ifc files are tracked; name one: " + ", ".join(tracked))


def _history(root: Path, rel_path: str, rev: str, max_commits: int | None) -> list[Commit]:
    args = ["log", f"--format=%H{_SEP}%an{_SEP}%aI{_SEP}%s"]
    if max_commits is not None:
        args.append(f"--max-count={max_commits}")
    out = git_text(*args, rev, "--", rel_path, cwd=root)
    commits = []
    for line in out.splitlines():
        sha, author, date, subject = line.split(_SEP, 3)
        commits.append(Commit(sha, author, date, subject, _blob(root, sha, rel_path)))
    return commits


def _blob(root: Path, sha: str, rel_path: str) -> str | None:
    try:
        return git_text("rev-parse", "--verify", "--quiet", f"{sha}:{rel_path}", cwd=root)
    except GitError:
        return None


class _Cache:
    def __init__(self, directory: Path, cfg: Settings):
        self.dir = directory
        self.cfg = cfg
        key = f"{CACHE_FORMAT}|{__version__}|{cfg.model_dump_json()}"
        self.settings_key = hashlib.blake2b(key.encode(), digest_size=8).hexdigest()

    def pair(self, root: Path, old_blob: str, new_blob: str) -> dict[str, dict]:
        """Every element of the newer version that differs from the older one, keyed by
        its GlobalId; removed elements are keyed by their GlobalId in the older version."""
        path = self.dir / f"pair-{old_blob}-{new_blob}-{self.settings_key}.json"
        cached = self._read(path)
        if cached is not None:
            return cached

        with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
            old = _materialise(root, old_blob, Path(tmp), "old")
            new = _materialise(root, new_blob, Path(tmp), "new")
            result = run_diff(str(old), "old.ifc", str(new), "new.ifc", self.cfg)

        records: dict[str, dict] = {}
        for el in result.elements:
            if el.change_type == ChangeType.UNCHANGED and not el.matched_global_id:
                continue
            records[el.global_id] = {
                "change": el.change_type.value,
                "ifc_class": el.ifc_class,
                "name": el.name,
                "matched_global_id": el.matched_global_id,
                "details": describe_changes(el) if el.change_type == ChangeType.MODIFIED else [],
            }
        self._write(path, records)
        return records

    def element_ids(self, root: Path, blob: str) -> dict[str, dict]:
        """Class and name of every element in one version, keyed by GlobalId."""
        path = self.dir / f"elements-{blob}.json"
        cached = self._read(path)
        if cached is not None:
            return cached

        with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
            file = _materialise(root, blob, Path(tmp), "model")
            with IFC_LOCK:
                model = parse_ifc(str(file), "model.ifc", self.cfg.include_openings)
                elements = {
                    gid: {"ifc_class": el.ifc_class, "name": el.name}
                    for gid, el in model.elements.items()
                }
        self._write(path, elements)
        return elements

    def _read(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, path: Path, data) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # The cache is an optimisation only.


def _materialise(root: Path, blob: str, directory: Path, stem: str) -> Path:
    path = directory / f"{stem}.ifc"
    path.write_bytes(git("cat-file", "blob", blob, cwd=root))
    return resolve_lfs(path, directory, cwd=root)
