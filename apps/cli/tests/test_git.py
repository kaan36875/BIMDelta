import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from bimdelta_cli import gitdriver
from bimdelta_cli.gitutil import is_lfs_pointer
from bimdelta_cli.main import app

from .conftest import COLUMN, WALL_A, WALL_A_REEXPORTED, WALL_B, WALL_C, make_model

runner = CliRunner()

# Run the driver with this interpreter, whatever is on PATH.
COMMAND = f'"{sys.executable}" -m bimdelta_cli'.replace("\\", "/")


def test_textconv_lists_elements_and_properties(pair):
    v1, _ = pair
    out = runner.invoke(app, ["textconv", str(v1)]).stdout
    assert out.startswith("# v1.ifc  IFC4  3 elements")
    assert f"IfcWall {WALL_A}  Wall-A  @ Level 1" in out
    assert "    Pset_WallCommon.FireRating = 1HR" in out
    assert "    tag: 100" in out


def test_textconv_is_stable(same):
    a, b = same
    out_a = runner.invoke(app, ["textconv", str(a)]).stdout
    out_b = runner.invoke(app, ["textconv", str(b)]).stdout
    assert out_a.replace("a.ifc", "x") == out_b.replace("b.ifc", "x")


def test_textconv_does_not_fail_on_bad_input(tmp_path):
    bad = tmp_path / "bad.ifc"
    bad.write_text("garbage")
    result = runner.invoke(app, ["textconv", str(bad)])
    assert result.exit_code == 0
    assert result.stdout.startswith("# bimdelta: could not read bad.ifc")


def test_install_writes_config_and_attributes(repo):
    result = runner.invoke(app, ["install-git-driver", "--command", COMMAND])
    assert result.exit_code == 0, result.output
    assert repo.git("config", "diff.ifc.command").strip() == f"{COMMAND} git-diff"
    assert repo.git("config", "diff.ifc.textconv").strip() == f"{COMMAND} textconv"
    assert (repo.path / ".gitattributes").read_text() == "*.ifc merge=binary diff=ifc\n"

    # Idempotent.
    runner.invoke(app, ["install-git-driver", "--command", COMMAND])
    assert (repo.path / ".gitattributes").read_text() == "*.ifc merge=binary diff=ifc\n"


def test_uninstall(repo):
    runner.invoke(app, ["install-git-driver", "--command", COMMAND])
    result = runner.invoke(app, ["install-git-driver", "--uninstall"])
    assert result.exit_code == 0, result.output
    assert subprocess.run(["git", "config", "diff.ifc.command"], cwd=repo.path).returncode == 1


def test_install_outside_a_repository(tmp_path, git_env, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install-git-driver"])
    assert result.exit_code == 2


def test_install_global(git_env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install-git-driver", "--global", "--command", COMMAND])
    assert result.exit_code == 0, result.output
    attributes = tmp_path / "home" / ".config" / "git" / "attributes"
    assert attributes.read_text() == "*.ifc merge=binary diff=ifc\n"


def test_attribute_replaces_lfs_diff(tmp_path):
    path = tmp_path / ".gitattributes"
    path.write_text("*.png binary\n*.ifc filter=lfs diff=lfs merge=lfs -text\n")
    assert gitdriver.ensure_attribute(path)
    assert path.read_text() == "*.png binary\n*.ifc filter=lfs merge=lfs -text diff=ifc\n"
    assert not gitdriver.ensure_attribute(path)


def test_git_diff_shows_element_changes(repo):
    repo.commit_model(make_model(), "v1")
    repo.commit_model(make_model("2HR", with_column=True, with_wall_c=False), "v2")
    runner.invoke(app, ["install-git-driver", "--command", COMMAND])

    out = repo.git("diff", "HEAD~1", "HEAD", "--", "model.ifc")
    assert out.startswith("diff --bimdelta a/model.ifc b/model.ifc")
    assert "### BIMDelta: model.ifc" in out
    assert "| **Total** | 1 | 1 | 1 | 1 |" in out
    assert "FireRating: 1HR → 2HR" in out


def test_git_diff_working_tree_and_new_file(repo):
    repo.commit_model(make_model(), "v1")
    runner.invoke(app, ["install-git-driver", "--command", COMMAND])

    make_model("2HR").write(str(repo.path / "model.ifc"))
    assert "FireRating: 1HR → 2HR" in repo.git("diff", "--", "model.ifc")

    make_model().write(str(repo.path / "other.ifc"))
    repo.git("add", "other.ifc")
    out = repo.git("diff", "--cached", "--", "other.ifc")
    assert "(new file, 3 elements)" in out


def test_git_log_uses_textconv(repo):
    repo.commit_model(make_model(), "v1")
    repo.commit_model(make_model("2HR"), "v2")
    runner.invoke(app, ["install-git-driver", "--command", COMMAND])

    out = repo.git("log", "-p", "-1", "--", "model.ifc")
    assert "-    Pset_WallCommon.FireRating = 1HR" in out
    assert "+    Pset_WallCommon.FireRating = 2HR" in out


def test_blame_follows_reexported_element(history):
    result = runner.invoke(app, ["blame", WALL_A_REEXPORTED, "-f", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    events = [(e["change"], e["subject"]) for e in data["events"]]
    assert events == [("modified", "Re-export with new ids"), ("added", "Initial model")]
    modified = data["events"][0]
    assert "Pset_WallCommon.FireRating: 1HR → 2HR" in modified["details"]
    assert modified["author"] == "Alice"
    assert data["events"][1]["global_id"] == WALL_A


def test_blame_added_and_removed(history):
    data = json.loads(runner.invoke(app, ["blame", COLUMN, "-f", "json"]).stdout)
    assert [(e["change"], e["subject"]) for e in data["events"]] == [
        ("added", "Add column, remove Wall-C")
    ]

    data = json.loads(runner.invoke(app, ["blame", WALL_C, "-f", "json"]).stdout)
    assert [(e["change"], e["subject"]) for e in data["events"]] == [
        ("removed", "Add column, remove Wall-C"),
        ("added", "Initial model"),
    ]


def test_blame_unchanged_element(history):
    data = json.loads(runner.invoke(app, ["blame", WALL_B, "model.ifc", "-f", "json"]).stdout)
    assert [e["change"] for e in data["events"]] == ["added"]


def test_blame_max_commits(history):
    data = json.loads(
        runner.invoke(app, ["blame", WALL_B, "--max-commits", "2", "-f", "json"]).stdout
    )
    assert data["truncated"] is True
    assert data["events"] == []
    assert data["present_before"] is True
    assert data["commits_scanned"] == 2


def test_blame_text_output_and_cache(history):
    first = runner.invoke(app, ["blame", WALL_A_REEXPORTED])
    assert first.exit_code == 0, first.output
    assert "modified" in first.stdout and '"Re-export with new ids"' in first.stdout
    cache = history.path / ".git" / "bimdelta-cache"
    assert any(p.name.startswith("pair-") for p in cache.iterdir())

    second = runner.invoke(app, ["blame", WALL_A_REEXPORTED])
    assert second.stdout == first.stdout


def test_blame_unknown_element(history):
    result = runner.invoke(app, ["blame", "x" * 22])
    assert result.exit_code == 2
    assert "no element with GlobalId" in result.output


def test_blame_needs_a_path_when_several_models(history):
    history.commit_model(make_model(), "Second model", name="other.ifc")
    result = runner.invoke(app, ["blame", WALL_B])
    assert result.exit_code == 2
    assert "several .ifc files" in result.output


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 12\n", True),
        (b"ISO-10303-21;\nHEADER;", False),
    ],
)
def test_lfs_pointer_detection(data, expected):
    assert is_lfs_pointer(data) is expected
