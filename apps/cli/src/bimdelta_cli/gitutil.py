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
