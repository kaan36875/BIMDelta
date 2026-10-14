"""Small helpers around the ``git`` executable."""

from __future__ import annotations

import subprocess
from pathlib import Path

LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"
# LFS pointer files are tiny; anything bigger is real content.
LFS_POINTER_MAX_BYTES = 1024


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path | str | None = None, input: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, input=input, capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise GitError("git was not found on PATH") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(msg or f"git {' '.join(args)} failed with exit code {proc.returncode}")
    return proc.stdout


def git_text(*args: str, cwd: Path | str | None = None) -> str:
    return git(*args, cwd=cwd).decode("utf-8", "replace").strip()


def repo_root(start: Path | str = ".") -> Path:
    return Path(git_text("rev-parse", "--show-toplevel", cwd=start))


def git_dir(start: Path | str = ".") -> Path:
    """The directory shared by all worktrees of the repository (normally ``.git``)."""
    path = Path(git_text("rev-parse", "--git-common-dir", cwd=start))
    return path if path.is_absolute() else (Path(start) / path).resolve()


def is_lfs_pointer(data: bytes) -> bool:
    return len(data) <= LFS_POINTER_MAX_BYTES and data.startswith(LFS_POINTER_HEADER)


def resolve_lfs(path: Path, scratch: Path, cwd: Path | str | None = None) -> Path:
    """If ``path`` holds a Git LFS pointer, write the real content into the ``scratch``
    directory and return that file; otherwise return ``path`` unchanged.

    Git hands diff drivers the stored blob, which for LFS-tracked files is the pointer, not
    the model. The object must already be in the local LFS store (``git lfs fetch``).
    """
    with open(path, "rb") as f:
        head = f.read(LFS_POINTER_MAX_BYTES + 1)
    if not is_lfs_pointer(head):
        return path
    try:
        content = git("lfs", "smudge", cwd=cwd, input=path.read_bytes())
    except GitError as exc:
        raise GitError(
            f"{path.name} is a Git LFS pointer and its content is not available locally "
            f"(run `git lfs fetch`): {exc}"
        ) from exc
    if is_lfs_pointer(content[: LFS_POINTER_MAX_BYTES + 1]):
        raise GitError(f"{path.name}: Git LFS object is not downloaded (run `git lfs fetch`)")
    resolved = scratch / f"lfs-{path.stem}.ifc"
    resolved.write_bytes(content)
    return resolved


def model_input(arg: str, scratch: Path, cwd: Path | str = ".") -> tuple[Path, str]:
    """A model named on the command line, as a local file and a display name.

    ``arg`` is a file path, or ``REV:PATH`` for a committed version (``HEAD~1:model.ifc``,
    ``main:./model.ifc``), which is written into ``scratch``. Git LFS content is resolved
    either way.
    """
    path = Path(cwd) / arg
    if path.is_file():
        return resolve_lfs(path, scratch, cwd=cwd), path.name
    rev, sep, rel = arg.partition(":")
    # "C:" is a drive, not a revision.
    if not sep or not rev or not rel or len(rev) == 1:
        raise GitError(f"{arg}: no such file (use REV:PATH for a committed version)")
    content = git("cat-file", "--filters", f"{rev}:{rel}", cwd=cwd)
    name = f"{Path(rel).name}@{rev}"
    out = scratch / f"rev-{len(list(scratch.iterdir()))}-{Path(rel).name}"
    out.write_bytes(content)
    if is_lfs_pointer(content[: LFS_POINTER_MAX_BYTES + 1]):
        raise GitError(f"{arg}: Git LFS object is not downloaded (run `git lfs fetch`)")
    return out, name
