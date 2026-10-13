from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rich.console import Console

from bimdelta_cli import main
from bimdelta_core.testing import add_column, add_wall, remove_element, setup_project

WALL_A = "0" * 22
WALL_B = "1" * 22
WALL_C = "2" * 22
COLUMN = "3" * 22
WALL_A_REEXPORTED = "9" * 22


def make_model(
    fire_rating: str = "1HR",
    wall_a_id: str = WALL_A,
    with_column: bool = False,
    with_wall_c: bool = True,
):
    ifc, body, storey = setup_project()
    add_wall(ifc, body, storey, wall_a_id, "Wall-A", 0, 0, 0, fire_rating=fire_rating, tag="100")
    add_wall(ifc, body, storey, WALL_B, "Wall-B", 6, 0, 0, tag="101")
    wall_c = add_wall(ifc, body, storey, WALL_C, "Wall-C", 12, 0, 0, tag="102")
    if not with_wall_c:
        remove_element(ifc, wall_c)
    if with_column:
        add_column(ifc, body, storey, COLUMN, "Column-1", 0, 5, 0, tag="103")
    return ifc


@pytest.fixture(autouse=True)
def wide_console(monkeypatch) -> None:
    """Rich reads the terminal width once, at import; keep output independent of the
    terminal the tests run in."""
    monkeypatch.setattr(main, "console", Console(width=200))
    monkeypatch.setattr(main, "say", Console(width=200, soft_wrap=True))


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """v2: Wall-A fire rating 1HR → 2HR, Wall-C removed, Column-1 added."""
    v1, v2 = tmp_path / "v1.ifc", tmp_path / "v2.ifc"
    make_model().write(str(v1))
    make_model("2HR", with_column=True, with_wall_c=False).write(str(v2))
    return v1, v2


@pytest.fixture
def same(tmp_path: Path) -> tuple[Path, Path]:
    v1, v2 = tmp_path / "a.ifc", tmp_path / "b.ifc"
    make_model().write(str(v1))
    make_model().write(str(v2))
    return v1, v2


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=self.path, capture_output=True, check=True)
        return proc.stdout.decode("utf-8")

    def commit_model(self, ifc, message: str, name: str = "model.ifc") -> None:
        ifc.write(str(self.path / name))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)


@pytest.fixture
def git_env(tmp_path: Path, monkeypatch) -> None:
    """Isolate Git from the user's configuration and give commits a fixed identity."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Alice")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "alice@example.com")
    os.environ.pop("GIT_DIR", None)


@pytest.fixture
def repo(tmp_path: Path, git_env, monkeypatch) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    r = Repo(path)
    r.git("init", "-q")
    monkeypatch.chdir(path)
    return r


@pytest.fixture
def history(repo: Repo) -> Repo:
    """Three commits of model.ifc:

    1. "Initial model": Wall-A (1HR), Wall-B, Wall-C
    2. "Re-export with new ids": Wall-A gets a new GlobalId (same Tag) and 2HR
    3. "Add column, remove Wall-C"
    """
    repo.commit_model(make_model(), "Initial model")
    repo.commit_model(make_model("2HR", wall_a_id=WALL_A_REEXPORTED), "Re-export with new ids")
    repo.commit_model(
        make_model("2HR", wall_a_id=WALL_A_REEXPORTED, with_column=True, with_wall_c=False),
        "Add column, remove Wall-C",
    )
    return repo
