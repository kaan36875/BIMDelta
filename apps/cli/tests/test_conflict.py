import json

from typer.testing import CliRunner

from bimdelta_cli.main import app
from bimdelta_core.testing import add_wall, remove_element, set_property, setup_project

runner = CliRunner()

FIRE = "0" * 22  # fire rating changed differently on both branches: conflict
SPLIT = "1" * 22  # fire rating on one branch, name on the other: warning
GONE = "2" * 22  # deleted on one branch, changed on the other: conflict
SAME = "3" * 22  # the same edit on both branches: nothing to report
ONE_SIDE = "4" * 22  # changed on one branch only


def build(*edits):
    ifc, body, storey = setup_project()
    for i, gid in enumerate((FIRE, SPLIT, GONE, SAME, ONE_SIDE)):
        add_wall(ifc, body, storey, gid, f"Wall-{i}", i * 6, 0, 0, fire_rating="1HR")
    for edit in edits:
        edit(ifc)
    return ifc


def fire(gid, rating):
    def edit(ifc):
        set_property(ifc.by_guid(gid), "Pset_WallCommon", "FireRating", ifc.createIfcLabel(rating))

    return edit


def rename(gid, name):
    def edit(ifc):
        ifc.by_guid(gid).Name = name

    return edit


def delete(gid):
    return lambda ifc: remove_element(ifc, ifc.by_guid(gid))


def _branches(repo):
    repo.commit_model(build(), "base")
    repo.git("branch", "-M", "main")
    repo.git("checkout", "-q", "-b", "ours")
    repo.commit_model(
        build(fire(FIRE, "2HR"), fire(SPLIT, "2HR"), delete(GONE), fire(SAME, "2HR")), "ours"
    )
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "theirs")
    repo.commit_model(
        build(
            fire(FIRE, "3HR"),
            rename(SPLIT, "Wall-1 renamed"),
            fire(GONE, "2HR"),
            fire(SAME, "2HR"),
            fire(ONE_SIDE, "2HR"),
        ),
        "theirs",
    )


def test_conflicts_and_warnings(repo):
    _branches(repo)
    result = runner.invoke(app, ["conflict", "ours", "theirs", "-f", "json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert (report["conflicts"], report["warnings"]) == (2, 1)

    (file,) = report["files"]
    assert file["path"] == "model.ifc"
    found = {e["global_id"]: e for e in file["elements"]}
    assert set(found) == {FIRE, SPLIT, GONE}

    assert found[FIRE]["level"] == "conflict"
    assert found[FIRE]["fields"] == ["Pset_WallCommon.FireRating"]
    assert found[FIRE]["ours"] == ["Pset_WallCommon.FireRating: 1HR → 2HR"]
    assert found[FIRE]["theirs"] == ["Pset_WallCommon.FireRating: 1HR → 3HR"]

    assert found[SPLIT]["level"] == "warning"
    assert found[SPLIT]["fields"] == []

    assert found[GONE]["level"] == "conflict"
    assert found[GONE]["ours"] == ["deleted"]


def test_markdown_and_exit_code(repo):
    _branches(repo)
    result = runner.invoke(app, ["conflict", "ours", "theirs", "-f", "markdown", "--exit-code"])
    assert result.exit_code == 1
    out = result.stdout
    assert "**2** conflict(s), **1** warning(s)." in out
    assert "| **conflict** | IfcWall Wall-0 `" + FIRE + "` | Pset\\_WallCommon.FireRating |" in out
    assert "| warning | IfcWall Wall-1 `" + SPLIT + "` | different fields |" in out

    table = runner.invoke(app, ["conflict", "ours", "theirs"])
    assert table.exit_code == 0, table.output
    assert "2 conflict(s), 1 warning(s)" in table.stdout


def test_no_overlap(repo):
    repo.commit_model(build(), "base")
    repo.git("branch", "-M", "main")
    repo.git("checkout", "-q", "-b", "ours")
    repo.commit_model(build(fire(FIRE, "2HR")), "ours")
    repo.git("checkout", "-q", "main")
    repo.commit_model(build(fire(SPLIT, "2HR")), "main edit")

    result = runner.invoke(app, ["conflict", "ours", "main", "--exit-code", "-f", "markdown"])
    assert result.exit_code == 0, result.output
    assert "No element was changed on both branches." in result.stdout


def test_file_deleted_on_one_branch(repo):
    repo.commit_model(build(), "base")
    repo.git("branch", "-M", "main")
    repo.git("checkout", "-q", "-b", "ours")
    repo.git("rm", "-q", "model.ifc")
    repo.git("commit", "-q", "-m", "drop the model")
    repo.git("checkout", "-q", "main")
    repo.commit_model(build(fire(FIRE, "2HR")), "edit")

    report = json.loads(runner.invoke(app, ["conflict", "ours", "main", "-f", "json"]).stdout)
    assert report["conflicts"] == 1
    assert report["files"][0]["note"] == "deleted on ours, modified on the other"


def test_unknown_branch(repo):
    repo.commit_model(build(), "base")
    result = runner.invoke(app, ["conflict", "nope"])
    assert result.exit_code == 2
