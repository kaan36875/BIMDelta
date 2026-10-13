import json
from urllib.parse import parse_qs, urlparse

from typer.testing import CliRunner

from bimdelta_cli.main import app

from .conftest import make_model

runner = CliRunner()


def _commit(repo, message):
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", message)


def _pr(repo):
    """Base commit with two models; head modifies one, renames the other and adds a file
    that is not a model."""
    make_model().write(str(repo.path / "a.ifc"))
    (repo.path / "models").mkdir()
    make_model().write(str(repo.path / "models" / "old name.ifc"))
    _commit(repo, "base")

    make_model("2HR", with_column=True).write(str(repo.path / "a.ifc"))
    repo.git("mv", "models/old name.ifc", "models/new name.ifc")
    (repo.path / "notes.txt").write_text("not a model")
    _commit(repo, "head")
    return repo


def test_markdown_lists_every_changed_model(repo):
    _pr(repo)
    result = runner.invoke(app, ["review", "HEAD~1"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert out.startswith("## BIMDelta review")
    assert "2 IFC files changed" in out
    assert "### a.ifc" in out
    assert "**1** added · **0** removed · **1** modified" in out
    assert "### models/new name.ifc (renamed from models/old name.ifc)" in out
    assert "No element changes (3 unchanged)." in out
    assert "notes.txt" not in out
    assert "<summary>By storey</summary>" in out
    assert "FireRating: 1HR → 2HR" in out


def test_added_and_deleted_files(repo):
    make_model().write(str(repo.path / "a.ifc"))
    _commit(repo, "one")
    make_model().write(str(repo.path / "b.ifc"))
    _commit(repo, "add b")
    (repo.path / "a.ifc").unlink()
    _commit(repo, "delete a")

    added = runner.invoke(app, ["review", "HEAD~2", "HEAD~1"]).stdout
    assert "### b.ifc\n\nNew file with 3 elements." in added
    deleted = runner.invoke(app, ["review", "HEAD~1", "HEAD"]).stdout
    assert "### a.ifc\n\nDeleted file with 3 elements." in deleted
    links = runner.invoke(
        app, ["review", "HEAD~2", "HEAD~1", "--viewer-url", "https://v", "--github-repo", "o/r"]
    ).stdout
    assert "View 3D diff" not in links


def test_viewer_links(repo):
    _pr(repo)
    base = repo.git("rev-parse", "HEAD~1").strip()
    head = repo.git("rev-parse", "HEAD").strip()
    out = runner.invoke(
        app,
        [
            "review",
            "HEAD~1",
            "--viewer-url",
            "https://viewer.example/",
            "--github-repo",
            "acme/models",
            "--head-repo",
            "fork/models",
        ],
    ).stdout
    links = [
        line[len("[View 3D diff](") : -1]
        for line in out.splitlines()
        if line.startswith("[View 3D")
    ]
    assert len(links) == 2
    query = parse_qs(urlparse(links[1]).query)
    assert query["v1_url"] == [
        f"https://raw.githubusercontent.com/acme/models/{base}/models/old%20name.ifc"
    ]
    assert query["v2_url"] == [
        f"https://raw.githubusercontent.com/fork/models/{head}/models/new%20name.ifc"
    ]
    assert links[0].startswith("https://viewer.example/?")


def test_viewer_url_needs_repository(repo):
    _pr(repo)
    result = runner.invoke(app, ["review", "HEAD~1", "--viewer-url", "https://x"])
    assert result.exit_code == 2


def test_max_chars_drops_detail_first(repo):
    _pr(repo)
    full = runner.invoke(app, ["review", "HEAD~1"]).stdout
    short = runner.invoke(app, ["review", "HEAD~1", "--max-chars", str(len(full) - 1)]).stdout
    assert len(short) < len(full)
    assert "Changed elements" not in short
    assert "| **Total** |" in short


def test_json_and_output_file(repo, tmp_path):
    _pr(repo)
    target = tmp_path / "review.json"
    result = runner.invoke(app, ["review", "HEAD~1", "HEAD", "-f", "json", "-o", str(target)])
    assert result.exit_code == 0, result.output
    data = json.loads(target.read_text(encoding="utf-8"))
    by_path = {f["path"]: f for f in data["files"]}
    assert by_path["a.ifc"]["status"] == "M"
    assert by_path["a.ifc"]["result"]["summary"]["modified"] == 1
    assert by_path["models/new name.ifc"]["status"] == "R"
    assert by_path["models/new name.ifc"]["old_path"] == "models/old name.ifc"


def test_exit_code(repo):
    _pr(repo)
    assert runner.invoke(app, ["review", "HEAD~1", "--exit-code"]).exit_code == 1
    repo.git("commit", "-q", "--allow-empty", "-m", "nothing")
    result = runner.invoke(app, ["review", "HEAD~1", "--exit-code"])
    assert result.exit_code == 0
    assert "no IFC files changed" in result.stdout


def test_file_names_are_escaped(repo):
    make_model().write(str(repo.path / "base.ifc"))
    _commit(repo, "base")
    # Characters Windows allows in file names that mean something in Markdown.
    make_model().write(str(repo.path / "x [z](http---e) _b_ #1.ifc"))
    _commit(repo, "head")

    out = runner.invoke(app, ["review", "HEAD~1"]).stdout
    assert r"### x \[z\](http---e) \_b\_ \#1.ifc" in out


def test_unreadable_model_is_reported(repo):
    (repo.path / "m.ifc").write_text("not a model")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "base")
    (repo.path / "m.ifc").write_text("still not a model")
    repo.git("commit", "-q", "-am", "head")

    result = runner.invoke(app, ["review", "HEAD~1"])
    assert result.exit_code == 0
    assert "Could not compare this file:" in result.stdout
