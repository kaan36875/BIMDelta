import json

from typer.testing import CliRunner

from bimdelta_cli.main import app
from bimdelta_core import DiffResult, DiffSummary

from .conftest import COLUMN, WALL_A, WALL_C

runner = CliRunner()


def test_table(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["diff", str(v1), str(v2)])
    assert result.exit_code == 0, result.output
    assert "Pset_WallCommon.FireRating: 1HR → 2HR" in result.output
    assert COLUMN in result.output


def test_json_is_a_diff_result(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["diff", str(v1), str(v2), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = DiffResult.model_validate_json(result.stdout)
    assert (parsed.summary.added, parsed.summary.removed, parsed.summary.modified) == (1, 1, 1)
    assert json.loads(result.stdout)["schema_version"] == parsed.schema_version


def test_json_summary_only(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "json", "--summary-only"])
    assert DiffSummary.model_validate_json(result.stdout).modified == 1


def test_markdown(pair):
    v1, v2 = pair
    out = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "markdown"]).stdout
    assert out.startswith("### BIMDelta: v1.ifc → v2.ifc")
    assert "| **Total** | 1 | 1 | 1 | 1 |" in out
    assert "#### Modified (1)" in out
    assert "#### Added (1)" in out
    assert "#### Removed (1)" in out
    assert "Pset\\_WallCommon.FireRating: 1HR → 2HR" in out


def test_markdown_summary_only(pair):
    v1, v2 = pair
    out = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "markdown", "--summary-only"]).stdout
    assert "| **Total** |" in out
    assert "####" not in out


def test_markdown_limit(pair):
    v1, v2 = pair
    out = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "markdown", "--limit", "1"]).stdout
    assert out.count("- `Ifc") == 3  # one per section
    assert "and" not in out.split("#### Added")[1]


def test_same_model_reports_no_changes(same):
    v1, v2 = same
    result = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "markdown", "--exit-code"])
    assert result.exit_code == 0
    assert "No element changes (3 unchanged)." in result.stdout


def test_exit_code_with_changes(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "json", "--exit-code"])
    assert result.exit_code == 1


def test_filter(pair):
    v1, v2 = pair
    result = runner.invoke(
        app, ["diff", str(v1), str(v2), "-f", "json", "--filter", "class=IfcWall,change=removed"]
    )
    parsed = DiffResult.model_validate_json(result.stdout)
    assert [el.global_id for el in parsed.elements] == [WALL_C]
    assert parsed.summary.removed == 1
    assert parsed.summary.added == 0


def test_filter_alternatives_and_wildcards(pair):
    v1, v2 = pair
    args = ["diff", str(v1), str(v2), "-f", "json", "--filter"]
    result = runner.invoke(app, [*args, "change=added,change=modified"])
    ids = {el.global_id for el in DiffResult.model_validate_json(result.stdout).elements}
    assert ids == {WALL_A, COLUMN}

    result = runner.invoke(app, [*args, "name=wall-*"])
    names = [el.name for el in DiffResult.model_validate_json(result.stdout).elements]
    assert names and all(n.startswith("Wall") for n in names)


def test_bad_filter(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["diff", str(v1), str(v2), "--filter", "colour=red"])
    assert result.exit_code == 2
    assert "unknown filter key" in result.output


def test_config_file_and_strict(pair, tmp_path):
    v1, v2 = pair
    config = tmp_path / "custom.yml"
    config.write_text("ignore_properties: ['Pset_WallCommon.*']\n")
    args = ["diff", str(v1), str(v2), "-f", "json", "--config", str(config)]

    parsed = DiffResult.model_validate_json(runner.invoke(app, args).stdout)
    assert parsed.summary.modified == 0
    assert parsed.summary.noise.ignored_property_changes == 1

    parsed = DiffResult.model_validate_json(runner.invoke(app, [*args, "--strict"]).stdout)
    assert parsed.summary.modified == 1


def test_config_discovered_from_parent_directory(pair, tmp_path, monkeypatch):
    v1, v2 = pair
    (tmp_path / ".bimdelta.yml").write_text("ignore_properties: ['*.FireRating']\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    result = runner.invoke(app, ["diff", str(v1), str(v2), "-f", "json"])
    assert DiffResult.model_validate_json(result.stdout).summary.modified == 0


def test_invalid_config(pair, tmp_path):
    v1, v2 = pair
    config = tmp_path / "bad.yml"
    config.write_text("no_such_setting: 1\n")
    result = runner.invoke(app, ["diff", str(v1), str(v2), "--config", str(config)])
    assert result.exit_code == 2
    assert "unknown setting" in result.output


def test_not_an_ifc(tmp_path):
    bad = tmp_path / "bad.ifc"
    bad.write_text("not a model")
    result = runner.invoke(app, ["diff", str(bad), str(bad)])
    assert result.exit_code == 2
    assert "could not compare" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.startswith("bimdelta ")
