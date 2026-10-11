from __future__ import annotations

from pathlib import Path

import pytest

from bimdelta_core import load_settings, run_diff
from bimdelta_core.config import DEFAULT_IGNORE_PROPERTIES, Settings
from bimdelta_core.noise import PropertyFilter
from bimdelta_core.testing import add_pset, add_wall, set_property, setup_project


def _diff(v1: Path, v2: Path, **settings):
    return run_diff(str(v1), "v1.ifc", str(v2), "v2.ifc", Settings(**settings))


@pytest.fixture
def edited_by_files(tmp_path: Path) -> tuple[Path, Path]:
    """Only the Revit worksharing 'Edited by' value differs."""
    ifc, body, storey = setup_project()
    wall = add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0)
    add_pset(ifc, wall, "Identity Data", {"Edited by": "alice", "Mark": "W1"})
    v1 = tmp_path / "v1.ifc"
    ifc.write(str(v1))

    set_property(wall, "Identity Data", "Edited by", ifc.createIfcLabel("bob"))
    v2 = tmp_path / "v2.ifc"
    ifc.write(str(v2))
    return v1, v2


@pytest.fixture
def export_setting_files(tmp_path: Path) -> tuple[Path, Path]:
    """v2 was exported with Revit property sets switched on; the model itself is unchanged."""
    ifc, body, storey = setup_project()
    walls = [
        add_wall(ifc, body, storey, str(i) * 22, f"Wall-{i}", i * 6, 0, 0, fire_rating="1HR")
        for i in range(3)
    ]
    v1 = tmp_path / "v1.ifc"
    ifc.write(str(v1))

    for wall in walls:
        add_pset(ifc, wall, "PSet_Revit_Phasing", {"Phase Created": "New Construction"})
    v2 = tmp_path / "v2.ifc"
    ifc.write(str(v2))
    return v1, v2


class TestPropertyFilter:
    def test_glob_on_pset_and_property(self):
        f = PropertyFilter(ignore_patterns=("*.Edited by", "Pset_Revit_*.Volume"))
        assert f.is_ignored("Identity Data", "Edited by")
        assert f.is_ignored("Pset_Revit_Dimensions", "Volume")
        assert not f.is_ignored("Pset_Revit_Dimensions", "Area")
        assert not f.is_ignored("Identity Data", "Mark")

    def test_matching_is_case_sensitive(self):
        f = PropertyFilter(ignore_patterns=("*.Edited by",))
        assert not f.is_ignored("Identity Data", "edited by")

    def test_excluded_pset(self):
        f = PropertyFilter(excluded_psets=frozenset({"PSet_Revit_Phasing"}))
        assert f.is_ignored("PSet_Revit_Phasing", "Phase Created")
        assert not f.is_ignored("Pset_WallCommon", "FireRating")


class TestIgnorePatterns:
    def test_ignored_change_is_hidden_and_counted(self, edited_by_files):
        result = _diff(*edited_by_files)
        assert result.summary.modified == 0
        wall = result.elements[0]
        assert wall.ignored_property_changes == 1
        assert result.summary.noise.ignored_property_changes == 1
        assert result.summary.noise.ignore_properties == list(DEFAULT_IGNORE_PROPERTIES)

    def test_strict_reports_it(self, edited_by_files):
        result = _diff(*edited_by_files, strict=True)
        assert result.summary.modified == 1
        assert result.elements[0].property_changes[0].property_name == "Edited by"
        assert result.summary.noise.strict
        assert result.summary.noise.ignore_properties == []

    def test_custom_patterns_replace_defaults(self, edited_by_files):
        result = _diff(*edited_by_files, ignore_properties=["Identity Data.Mark"])
        assert result.summary.modified == 1


class TestOneSidedPsets:
    def test_export_setting_change_is_not_an_element_change(self, export_setting_files):
        result = _diff(*export_setting_files)
        assert result.summary.modified == 0
        assert result.summary.unchanged == 3
        [pset] = result.summary.noise.one_sided_psets
        assert pset.pset_name == "PSet_Revit_Phasing"
        assert pset.only_in == "v2"
        assert pset.element_count == 3
        assert result.summary.noise.ignored_property_changes == 3

    def test_strict_reports_every_element(self, export_setting_files):
        result = _diff(*export_setting_files, strict=True)
        assert result.summary.modified == 3
        assert result.summary.noise.one_sided_psets == []

    def test_changes_in_shared_psets_still_reported(self, tmp_path: Path):
        ifc, body, storey = setup_project()
        wall = add_wall(ifc, body, storey, "0" * 22, "Wall-A", 0, 0, 0, fire_rating="1HR")
        v1 = tmp_path / "v1.ifc"
        ifc.write(str(v1))
        add_pset(ifc, wall, "PSet_Revit_Phasing", {"Phase Created": "New Construction"})
        set_property(wall, "Pset_WallCommon", "FireRating", ifc.createIfcLabel("2HR"))
        v2 = tmp_path / "v2.ifc"
        ifc.write(str(v2))

        result = _diff(v1, v2)
        assert result.summary.modified == 1
        [change] = result.elements[0].property_changes
        assert (change.pset_name, change.property_name) == ("Pset_WallCommon", "FireRating")


class TestTopChangedProperties:
    def test_counts_elements_per_property(self, tmp_path: Path):
        ifc, body, storey = setup_project()
        walls = [
            add_wall(ifc, body, storey, str(i) * 22, f"Wall-{i}", i * 6, 0, 0, fire_rating="1HR")
            for i in range(3)
        ]
        v1 = tmp_path / "v1.ifc"
        ifc.write(str(v1))
        for wall in walls[:2]:
            set_property(wall, "Pset_WallCommon", "FireRating", ifc.createIfcLabel("2HR"))
        v2 = tmp_path / "v2.ifc"
        ifc.write(str(v2))

        [top] = _diff(v1, v2).summary.top_changed_properties
        assert (top.pset_name, top.property_name, top.element_count) == (
            "Pset_WallCommon",
            "FireRating",
            2,
        )


class TestLoadSettings:
    def test_yaml_values(self, tmp_path: Path):
        cfg_file = tmp_path / ".bimdelta.yml"
        cfg_file.write_text(
            "include_openings: true\n"
            "ignore_properties:\n"
            "  - 'Identity Data.*'\n"
            "fallback_placement_tolerance: 0.1\n",
            encoding="utf-8",
        )
        cfg = load_settings(cfg_file)
        assert cfg.include_openings is True
        assert cfg.ignore_properties == ["Identity Data.*"]
        assert cfg.fallback_placement_tolerance == 0.1

    def test_overrides_win_over_file(self, tmp_path: Path):
        cfg_file = tmp_path / ".bimdelta.yml"
        cfg_file.write_text("strict: false\n", encoding="utf-8")
        assert load_settings(cfg_file, strict=True).strict is True

    def test_file_wins_over_environment(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BIMDELTA_INCLUDE_OPENINGS", "true")
        cfg_file = tmp_path / ".bimdelta.yml"
        cfg_file.write_text("include_openings: false\n", encoding="utf-8")
        assert load_settings().include_openings is True
        assert load_settings(cfg_file).include_openings is False

    def test_unknown_key_is_rejected(self, tmp_path: Path):
        cfg_file = tmp_path / ".bimdelta.yml"
        cfg_file.write_text("ignore_property: ['x']\n", encoding="utf-8")
        with pytest.raises(ValueError, match="ignore_property"):
            load_settings(cfg_file)

    def test_empty_file(self, tmp_path: Path):
        cfg_file = tmp_path / ".bimdelta.yml"
        cfg_file.write_text("", encoding="utf-8")
        assert load_settings(cfg_file).strict is False
