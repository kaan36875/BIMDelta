from pathlib import Path

from app.config import Settings
from app.diff.engine import run_diff


class TestEngine:
    def test_basic_diff(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        assert result.schema_version == "1.0.0"
        assert result.v1_filename == "v1.ifc"
        assert result.v2_filename == "v2.ifc"
        assert result.v1_ifc_schema == "IFC4"

        assert result.summary.total_v1 == 6
        assert result.summary.total_v2 == 6  # -1 removed +1 added
        assert result.summary.added == 1
        assert result.summary.removed == 1
        assert result.summary.modified == 1
        assert result.summary.unchanged == 4

    def test_basic_diff_elements(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        by_type = {}
        for el in result.elements:
            by_type.setdefault(el.change_type.value, []).append(el)

        assert len(by_type["added"]) == 1
        assert by_type["added"][0].ifc_class == "IfcColumn"

        assert len(by_type["removed"]) == 1
        assert by_type["removed"][0].global_id == "3" * 22

        modified = by_type["modified"]
        assert len(modified) == 1
        assert modified[0].global_id == "0" * 22
        fire_change = next(
            p for p in modified[0].property_changes if p.property_name == "FireRating"
        )
        assert fire_change.old_value == "1HR"
        assert fire_change.new_value == "2HR"

    def test_same_file_zero_changes(self, same_file: tuple[Path, Path]):
        v1_path, v2_path = same_file
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        assert result.summary.added == 0
        assert result.summary.removed == 0
        assert result.summary.modified == 0
        assert result.summary.unchanged == 2

    def test_mm_vs_m_zero_changes(self, mm_vs_m_files: tuple[Path, Path]):
        v1_path, v2_path = mm_vs_m_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1_m.ifc", str(v2_path), "v2_mm.ifc", cfg)

        assert result.summary.added == 0
        assert result.summary.removed == 0
        assert result.summary.modified == 0
        assert result.summary.unchanged == 1

    def test_fallback_matching(self, fallback_match_files: tuple[Path, Path]):
        v1_path, v2_path = fallback_match_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        assert result.summary.added == 0
        assert result.summary.removed == 0
        # All matched by fallback — may show as modified (different GlobalId recorded)
        # or unchanged depending on geometry
        assert result.summary.added + result.summary.removed == 0

    def test_by_class_summary(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        assert "IfcWall" in result.summary.by_class
        assert "IfcColumn" in result.summary.by_class
        assert result.summary.by_class["IfcColumn"].get("added", 0) == 1

    def test_by_storey_summary(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        cfg = Settings()
        result = run_diff(str(v1_path), "v1.ifc", str(v2_path), "v2.ifc", cfg)

        assert "Level 1" in result.summary.by_storey
