from pathlib import Path

from app.diff.matcher import match_elements
from app.diff.parser import parse_ifc


class TestMatcher:
    def test_global_id_matching(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        v1 = parse_ifc(str(v1_path), "v1.ifc")
        v2 = parse_ifc(str(v2_path), "v2.ifc")

        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)

        matched_ids = {(m[0].global_id, m[1].global_id) for m in result.matched}
        for gid in ["0" * 22, "1" * 22, "2" * 22, "4" * 22, "5" * 22]:
            assert (gid, gid) in matched_ids

        assert all(m[2] == "global_id" for m in result.matched)

    def test_added_detected(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        v1 = parse_ifc(str(v1_path), "v1.ifc")
        v2 = parse_ifc(str(v2_path), "v2.ifc")

        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)

        added_ids = {el.global_id for el in result.added}
        assert "6" * 22 in added_ids

    def test_removed_detected(self, basic_diff_files: tuple[Path, Path]):
        v1_path, v2_path = basic_diff_files
        v1 = parse_ifc(str(v1_path), "v1.ifc")
        v2 = parse_ifc(str(v2_path), "v2.ifc")

        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)

        removed_ids = {el.global_id for el in result.removed}
        assert "3" * 22 in removed_ids

    def test_fallback_one_to_one(self, fallback_match_files: tuple[Path, Path]):
        v1_path, v2_path = fallback_match_files
        v1 = parse_ifc(str(v1_path), "v1.ifc")
        v2 = parse_ifc(str(v2_path), "v2.ifc")

        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)

        assert len(result.matched) == 3
        assert len(result.added) == 0
        assert len(result.removed) == 0

        # Each match should be "fallback" method
        assert all(m[2] == "fallback" for m in result.matched)

        # Verify one-to-one: no v1 or v2 element appears twice
        v1_ids = [m[0].global_id for m in result.matched]
        v2_ids = [m[1].global_id for m in result.matched]
        assert len(set(v1_ids)) == 3
        assert len(set(v2_ids)) == 3

    def test_fallback_matches_nearest(self, fallback_match_files: tuple[Path, Path]):
        """Each door should match to the door at the same position."""
        v1_path, v2_path = fallback_match_files
        v1 = parse_ifc(str(v1_path), "v1.ifc")
        v2 = parse_ifc(str(v2_path), "v2.ifc")

        result = match_elements(v1, v2, fallback_placement_tolerance=0.050)

        # Doors at x=1 should match, x=3 should match, x=5 should match
        for v1_el, v2_el, _ in result.matched:
            v1_x = v1_el.world_placement[0, 3]
            v2_x = v2_el.world_placement[0, 3]
            assert abs(v1_x - v2_x) < 0.001
