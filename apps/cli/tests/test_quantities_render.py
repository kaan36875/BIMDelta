from typer.testing import CliRunner

from bimdelta_cli.main import app
from bimdelta_cli.render import md_escape
from bimdelta_core import QuantityDelta

runner = CliRunner()


def test_quantities_formats(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["quantities", str(v1), str(v2), "-f", "json"])
    assert result.exit_code == 0, result.output
    parsed = QuantityDelta.model_validate_json(result.stdout)
    assert parsed.total.v1.count == 3
    assert parsed.total.v2.count == 3  # one wall removed, one column added
    assert parsed.v1_without_quantities == 3  # test models carry no quantity sets

    out = runner.invoke(app, ["quantities", str(v1), str(v2), "-f", "markdown"]).stdout
    assert "| IfcColumn | 1 (+1) |" in out
    assert "have no quantities" in out

    result = runner.invoke(app, ["quantities", str(v1), str(v2), "--by", "material"])
    assert result.exit_code == 0, result.output
    assert "(no material)" in result.stdout


def test_md_escape_neutralises_markup():
    hostile = "<img src=x onerror=alert(1)> | **bold** [link](http://x) `code`\nnext"
    escaped = md_escape(hostile)
    # A backslash before punctuation makes CommonMark render it literally.
    assert r"\<img" in escaped
    assert r"\*\*bold" in escaped
    assert "\\|" in escaped
    assert "\\[link\\]" in escaped
    assert "\n" not in escaped
