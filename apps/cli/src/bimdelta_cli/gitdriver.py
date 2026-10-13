"""Registering BIMDelta as Git's diff driver for ``*.ifc`` files.

Two hooks are installed under ``[diff "ifc"]``:

* ``command``: an external diff driver. ``git diff`` hands it both versions of the file,
  so it shows the real matched, noise-filtered element diff as Markdown.
* ``textconv``: turns one version into stable text (see ``snapshot``). Git uses it where no
  external driver runs: ``git log -p``, ``git show`` and ``git diff --no-ext-diff``.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .gitutil import git, git_text, repo_root
from .snapshot import XFUNCNAME

DRIVER = "ifc"
PATTERN = "*.ifc"


@dataclass
class InstallReport:
    scope: str
    command: str
    attributes_file: Path
    attributes_changed: bool


def default_command() -> str:
    """How Git should invoke this CLI.

    The ``bimdelta`` script is used when it is on PATH. Otherwise (e.g. installed in a
    virtual environment that is not activated) the current interpreter is called directly,
    so the driver keeps working from any shell.
    """
    if shutil.which("bimdelta"):
        return "bimdelta"
    python = Path(sys.executable).as_posix()
    return f'"{python}" -m bimdelta_cli'


def install(
    global_: bool = False, command: str | None = None, cwd: Path | str = "."
) -> InstallReport:
    command = command or default_command()
    scope = ["--global"] if global_ else []
    if not global_:
        cwd = repo_root(cwd)

    git("config", *scope, f"diff.{DRIVER}.command", f"{command} git-diff", cwd=cwd)
    git("config", *scope, f"diff.{DRIVER}.textconv", f"{command} textconv", cwd=cwd)
    git("config", *scope, f"diff.{DRIVER}.xfuncname", XFUNCNAME, cwd=cwd)

    attributes = global_attributes_file(cwd) if global_ else Path(cwd) / ".gitattributes"
    changed = ensure_attribute(attributes)
    return InstallReport(
        scope="global" if global_ else "repository",
        command=command,
        attributes_file=attributes,
        attributes_changed=changed,
    )


def uninstall(global_: bool = False, cwd: Path | str = ".") -> None:
    """Remove the ``[diff "ifc"]`` section. The ``.gitattributes`` line is left in place: it
    is committed and shared, and does nothing without the driver."""
    scope = ["--global"] if global_ else []
    if not global_:
        cwd = repo_root(cwd)
    git("config", *scope, "--remove-section", f"diff.{DRIVER}", cwd=cwd)


def global_attributes_file(cwd: Path | str = ".") -> Path:
    try:
        configured = git_text("config", "--global", "--path", "core.attributesFile", cwd=cwd)
    except Exception:
        configured = ""
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "git" / "attributes"


def ensure_attribute(path: Path) -> bool:
    """Make ``*.ifc`` use ``diff=ifc`` in an attributes file. Returns True if it changed.

    An existing ``*.ifc`` line keeps its other attributes; Git LFS writes ``diff=lfs`` there,
    which is replaced (LFS still works: content is resolved through ``git lfs smudge``).
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    wanted = f"diff={DRIVER}"
    for i, line in enumerate(lines):
        fields = line.split()
        if not fields or fields[0] != PATTERN:
            continue
        attrs = [a for a in fields[1:] if not _is_diff_attr(a)]
        new_line = " ".join([PATTERN, *attrs, wanted])
        if fields[1:].count(wanted) == 1 and not any(
            _is_diff_attr(a) and a != wanted for a in fields[1:]
        ):
            return False
        lines[i] = new_line
        break
    else:
        lines.append(f"{PATTERN} {wanted}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return True


def _is_diff_attr(attr: str) -> bool:
    return attr in ("diff", "-diff", "!diff") or attr.startswith("diff=")
