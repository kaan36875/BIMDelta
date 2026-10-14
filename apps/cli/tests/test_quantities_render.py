from typer.testing import CliRunner

from bimdelta_cli.main import app
from bimdelta_cli.render import md_escape, quantity_headline
from bimdelta_core import (
    DiffResult,
    QuantityDelta,
    QuantityDeltaRow,
    QuantityReport,
    QuantityTotals,
)

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


def test_quantities_by_storey_and_changed_only(pair):
    v1, v2 = pair
    result = runner.invoke(app, ["quantities", str(v1), str(v2), "--by", "storey", "-f", "json"])
    assert result.exit_code == 0, result.output
    assert QuantityDelta.model_validate_json(result.stdout).group_by == "storey"

    out = runner.invoke(
        app, ["quantities", str(v1), str(v2), "--changed-only", "-f", "markdown"]
    ).stdout
    assert "| IfcColumn |" in out
    assert "| IfcWall |" in out  # one wall removed


def test_revision_arguments(history):
    out = runner.invoke(app, ["quantities", "HEAD~2:model.ifc", "HEAD:model.ifc", "-f", "markdown"])
    assert out.exit_code == 0, out.output
    assert r"model.ifc@HEAD\~2 → model.ifc@HEAD" in out.stdout

    out = runner.invoke(app, ["diff", "HEAD~1:model.ifc", "model.ifc", "-f", "json"])
    assert out.exit_code == 0, out.output
    summary = DiffResult.model_validate_json(out.stdout).summary
    assert (summary.added, summary.removed) == (1, 1)  # the last commit's column and wall

    out = runner.invoke(app, ["diff", "HEAD~9:model.ifc", "model.ifc"])
    assert out.exit_code == 2
    out = runner.invoke(app, ["diff", "missing.ifc", "model.ifc"])
    assert out.exit_code == 2
    assert "no such file" in out.output


def test_quantity_headline():
    def row(group, volume=0.0, weight=0.0):
        totals = QuantityTotals(volume=volume, weight=weight)
        return QuantityDeltaRow(group=group, v1=QuantityTotals(), v2=totals, delta=totals)

    report = QuantityReport(
        by_class=[row("IfcWall", 3.5)],
        by_material=[row("Concrete", 12.0), row("Steel", weight=-400.0), row("Paint", 0.001)],
        by_storey=[],
        total=row("Total", 12.0, -400.0),
    )
    assert quantity_headline(report) == "Concrete +12.00 m³ · Steel -400 kg"

    no_materials = report.model_copy(update={"by_material": [row("(no material)", 3.5)]})
    assert quantity_headline(no_materials) == "IfcWall +3.50 m³"
    assert quantity_headline(None) is None
