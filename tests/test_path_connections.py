"""
tests/test_path_connections.py — Unit tests for data_io/path_connections.py

Covers:
- _euclidean helper
- _stages_near_point helper
- derive_path_connections:
    - path with no nearby stages → empty connects + warning
    - path with exactly 2 nearby stages → one ordered pair (both directions)
    - path with 3+ nearby stages → all ordered pairs (both directions)
    - length_m calculated from waypoint distances × meters_per_cell
    - length_m clamped to minimum 150 m
    - width_m passed through from grid_path
    - stages near intermediate waypoints (not just endpoints) are included
- Property 6: Path-to-Stage Connection Correctness (hypothesis)
"""

import math
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data_io.path_connections import (
    _euclidean,
    _stages_near_point,
    derive_path_connections,
)


# ---------------------------------------------------------------------------
# _euclidean
# ---------------------------------------------------------------------------

class TestEuclidean:
    def test_3_4_5_triangle(self):
        assert _euclidean((0, 0), (3, 4)) == pytest.approx(5.0)

    def test_same_point_is_zero(self):
        assert _euclidean((7, 7), (7, 7)) == pytest.approx(0.0)

    def test_horizontal_distance(self):
        assert _euclidean((0, 0), (10, 0)) == pytest.approx(10.0)

    def test_vertical_distance(self):
        assert _euclidean((0, 0), (0, 5)) == pytest.approx(5.0)

    def test_negative_coordinates(self):
        # Works with any integer coords, including negative
        assert _euclidean((-3, 0), (0, 4)) == pytest.approx(5.0)

    def test_symmetry(self):
        assert _euclidean((1, 2), (4, 6)) == pytest.approx(_euclidean((4, 6), (1, 2)))


# ---------------------------------------------------------------------------
# _stages_near_point
# ---------------------------------------------------------------------------

class TestStagesNearPoint:
    def setup_method(self):
        self.stages = [
            {"name": "Main Stage", "x": 5, "y": 5},
            {"name": "Second Stage", "x": 50, "y": 50},
            {"name": "Far Stage", "x": 100, "y": 100},
        ]

    def test_returns_only_nearby_stages(self):
        result = _stages_near_point((0, 0), self.stages, threshold=10)
        assert result == ["Main Stage"]

    def test_stage_exactly_at_threshold_is_included(self):
        # Main Stage is at (5,5); distance from (0,0) = sqrt(50) ≈ 7.07
        # Place a stage exactly 10 cells away
        stages = [{"name": "Exact", "x": 10, "y": 0}]
        result = _stages_near_point((0, 0), stages, threshold=10)
        assert result == ["Exact"]

    def test_stage_just_beyond_threshold_excluded(self):
        stages = [{"name": "Just Outside", "x": 11, "y": 0}]
        result = _stages_near_point((0, 0), stages, threshold=10)
        assert result == []

    def test_returns_multiple_nearby_stages(self):
        stages = [
            {"name": "A", "x": 1, "y": 0},
            {"name": "B", "x": 2, "y": 0},
            {"name": "C", "x": 100, "y": 100},
        ]
        result = _stages_near_point((0, 0), stages, threshold=5)
        assert set(result) == {"A", "B"}

    def test_empty_stages_list(self):
        result = _stages_near_point((0, 0), [], threshold=30)
        assert result == []

    def test_preserves_order_of_grid_stages(self):
        stages = [
            {"name": "First", "x": 1, "y": 0},
            {"name": "Second", "x": 2, "y": 0},
        ]
        result = _stages_near_point((0, 0), stages, threshold=5)
        assert result == ["First", "Second"]


# ---------------------------------------------------------------------------
# derive_path_connections
# ---------------------------------------------------------------------------

class TestDerivePathConnections:
    """Unit tests for derive_path_connections."""

    def _make_path(self, name, waypoints, width_m=10.0):
        return {"name": name, "waypoints": waypoints, "width_m": width_m}

    def _make_stage(self, name, x, y):
        return {"name": name, "x": x, "y": y}

    # ------------------------------------------------------------------
    # Basic structure
    # ------------------------------------------------------------------

    def test_returns_one_dict_per_path(self):
        paths = [
            self._make_path("Path A", [(0, 0), (100, 0)]),
            self._make_path("Path B", [(0, 50), (100, 50)]),
        ]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 100, 0)]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        assert len(result) == 2

    def test_result_dict_has_required_keys(self):
        paths = [self._make_path("P", [(0, 0), (10, 0)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 10, 0)]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        assert set(result[0].keys()) == {"name", "length_m", "width_m", "connects", "warnings"}

    def test_name_passed_through(self):
        paths = [self._make_path("My Path", [(0, 0), (10, 0)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 10, 0)]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        assert result[0]["name"] == "My Path"

    def test_width_m_passed_through(self):
        paths = [self._make_path("P", [(0, 0), (10, 0)], width_m=12.5)]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 10, 0)]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        assert result[0]["width_m"] == pytest.approx(12.5)

    # ------------------------------------------------------------------
    # Warning: fewer than 2 connected stages
    # ------------------------------------------------------------------

    def test_no_nearby_stages_returns_empty_connects_and_warning(self):
        paths = [self._make_path("Lonely Path", [(50, 50), (60, 50)])]
        stages = [self._make_stage("Far Stage", 0, 0)]  # 70+ cells away
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert result[0]["connects"] == []
        assert len(result[0]["warnings"]) == 1
        assert "fewer than 2" in result[0]["warnings"][0]

    def test_exactly_one_nearby_stage_returns_empty_connects_and_warning(self):
        paths = [self._make_path("One Stage Path", [(0, 0), (10, 0)])]
        stages = [
            self._make_stage("Near", 0, 0),
            self._make_stage("Far", 200, 200),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert result[0]["connects"] == []
        assert len(result[0]["warnings"]) == 1

    def test_warning_message_contains_path_name(self):
        paths = [self._make_path("Isolated Walkway", [(50, 50)])]
        stages = []
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert "Isolated Walkway" in result[0]["warnings"][0]

    # ------------------------------------------------------------------
    # Connects list: 2 stages → both directions
    # ------------------------------------------------------------------

    def test_two_nearby_stages_produces_both_directions(self):
        paths = [self._make_path("AB Path", [(0, 0), (100, 0)])]
        stages = [
            self._make_stage("Alpha", 0, 0),
            self._make_stage("Beta", 100, 0),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        connects = result[0]["connects"]
        assert ("Alpha", "Beta") in connects
        assert ("Beta", "Alpha") in connects
        assert len(connects) == 2

    def test_two_nearby_stages_no_warnings(self):
        paths = [self._make_path("AB Path", [(0, 0), (100, 0)])]
        stages = [
            self._make_stage("Alpha", 0, 0),
            self._make_stage("Beta", 100, 0),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert result[0]["warnings"] == []

    # ------------------------------------------------------------------
    # Connects list: 3 stages → all ordered pairs
    # ------------------------------------------------------------------

    def test_three_nearby_stages_produces_all_ordered_pairs(self):
        # Place three stages near the path waypoints
        paths = [self._make_path("ABC Path", [(0, 0), (50, 0), (100, 0)])]
        stages = [
            self._make_stage("A", 0, 0),
            self._make_stage("B", 50, 0),
            self._make_stage("C", 100, 0),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        connects = set(result[0]["connects"])
        expected = {
            ("A", "B"), ("B", "A"),
            ("A", "C"), ("C", "A"),
            ("B", "C"), ("C", "B"),
        }
        assert connects == expected

    # ------------------------------------------------------------------
    # Intermediate waypoints are checked (not just endpoints)
    # ------------------------------------------------------------------

    def test_stage_near_intermediate_waypoint_is_included(self):
        # Endpoints are far from all stages; middle waypoint is near "Mid Stage"
        paths = [self._make_path("Long Path", [(0, 0), (50, 50), (100, 100)])]
        stages = [
            self._make_stage("Start Stage", 0, 0),
            self._make_stage("Mid Stage", 50, 50),   # near middle waypoint
            self._make_stage("End Stage", 100, 100),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        stage_names_in_connects = {s for pair in result[0]["connects"] for s in pair}
        assert "Mid Stage" in stage_names_in_connects

    # ------------------------------------------------------------------
    # length_m calculation
    # ------------------------------------------------------------------

    def test_length_m_calculated_from_waypoint_distances(self):
        # Two waypoints 100 cells apart, meters_per_cell=2.0 → 200 m
        paths = [self._make_path("P", [(0, 0), (100, 0)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 100, 0)]
        result = derive_path_connections(
            paths, stages, meters_per_cell=2.0, proximity_threshold_cells=5
        )
        assert result[0]["length_m"] == pytest.approx(200.0)

    def test_length_m_sums_multiple_segments(self):
        # Three waypoints: (0,0)→(30,40)→(60,40)
        # Segment 1: sqrt(30²+40²) = 50 cells
        # Segment 2: 30 cells
        # Total: 80 cells × 1.0 m/cell = 80 m → clamped to 150 m
        paths = [self._make_path("P", [(0, 0), (30, 40), (60, 40)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 60, 40)]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        # 80 m < 150 m minimum, so clamped
        assert result[0]["length_m"] == pytest.approx(150.0)

    def test_length_m_minimum_clamp_applied(self):
        # Single waypoint → 0 cells → clamped to 150 m
        paths = [self._make_path("P", [(50, 50)])]
        stages = [self._make_stage("S1", 50, 50), self._make_stage("S2", 51, 50)]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert result[0]["length_m"] == pytest.approx(150.0)

    def test_length_m_not_clamped_when_long_enough(self):
        # 200 cells × 1.0 m/cell = 200 m > 150 m minimum
        paths = [self._make_path("P", [(0, 0), (200, 0)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 200, 0)]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        assert result[0]["length_m"] == pytest.approx(200.0)

    def test_length_m_respects_meters_per_cell_scale(self):
        # 10 cells × 5.0 m/cell = 50 m → clamped to 150 m
        paths = [self._make_path("P", [(0, 0), (10, 0)])]
        stages = [self._make_stage("S1", 0, 0), self._make_stage("S2", 10, 0)]
        result = derive_path_connections(
            paths, stages, meters_per_cell=5.0, proximity_threshold_cells=15
        )
        assert result[0]["length_m"] == pytest.approx(150.0)

    # ------------------------------------------------------------------
    # Empty inputs
    # ------------------------------------------------------------------

    def test_empty_paths_returns_empty_list(self):
        stages = [self._make_stage("S1", 0, 0)]
        result = derive_path_connections([], stages, meters_per_cell=1.0)
        assert result == []

    def test_empty_stages_all_paths_get_warnings(self):
        paths = [
            self._make_path("P1", [(0, 0), (10, 0)]),
            self._make_path("P2", [(20, 0), (30, 0)]),
        ]
        result = derive_path_connections(paths, [], meters_per_cell=1.0)
        for r in result:
            assert r["connects"] == []
            assert len(r["warnings"]) == 1

    # ------------------------------------------------------------------
    # Deduplication: same stage near multiple waypoints counted once
    # ------------------------------------------------------------------

    def test_stage_near_multiple_waypoints_counted_once(self):
        # Stage "S1" is near both waypoints of the path
        paths = [self._make_path("P", [(0, 0), (1, 0)])]
        stages = [
            self._make_stage("S1", 0, 0),   # near both waypoints
            self._make_stage("S2", 100, 0),  # far away
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=5
        )
        # Only S1 is near; fewer than 2 → empty connects
        assert result[0]["connects"] == []
        assert len(result[0]["warnings"]) == 1

    def test_no_duplicate_stages_in_connects(self):
        # Both waypoints are near both stages; each stage should appear once
        paths = [self._make_path("P", [(0, 0), (5, 0)])]
        stages = [
            self._make_stage("A", 0, 0),
            self._make_stage("B", 5, 0),
        ]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0, proximity_threshold_cells=10
        )
        connects = result[0]["connects"]
        # Should be exactly 2 pairs: (A,B) and (B,A)
        assert len(connects) == 2
        assert ("A", "B") in connects
        assert ("B", "A") in connects

    # ------------------------------------------------------------------
    # Default proximity threshold
    # ------------------------------------------------------------------

    def test_default_proximity_threshold_is_30(self):
        # Stage 29 cells away should be included with default threshold
        paths = [self._make_path("P", [(0, 0), (100, 0)])]
        stages = [
            self._make_stage("Near", 29, 0),   # 29 cells from first waypoint
            self._make_stage("Far", 100, 0),   # at second waypoint
        ]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        stage_names = {s for pair in result[0]["connects"] for s in pair}
        assert "Near" in stage_names

    def test_stage_31_cells_away_excluded_with_default_threshold(self):
        # Stage 31 cells away should NOT be included with default threshold of 30
        paths = [self._make_path("P", [(0, 0), (100, 0)])]
        stages = [
            self._make_stage("Just Outside", 31, 0),
            self._make_stage("At End", 100, 0),
        ]
        result = derive_path_connections(paths, stages, meters_per_cell=1.0)
        # Only 1 stage found → empty connects + warning
        assert result[0]["connects"] == []
        assert len(result[0]["warnings"]) == 1


# ---------------------------------------------------------------------------
# Property 6: Path-to-Stage Connection Correctness (Hypothesis)
# ---------------------------------------------------------------------------

# Hypothesis strategies for generating stage grids and path waypoints

# Generate a stage dict with a unique name and grid coordinates
def stage_strategy(name_prefix="Stage"):
    """Strategy for a single stage with grid coordinates in [0, 199]."""
    return st.builds(
        lambda x, y, idx: {"name": f"{name_prefix}_{idx}", "x": x, "y": y},
        x=st.integers(min_value=0, max_value=199),
        y=st.integers(min_value=0, max_value=199),
        idx=st.integers(min_value=0, max_value=9999),
    )


@st.composite
def stages_strategy(draw):
    """Strategy for a list of 1-6 stages with unique names."""
    count = draw(st.integers(min_value=1, max_value=6))
    stages = []
    for i in range(count):
        x = draw(st.integers(min_value=0, max_value=199))
        y = draw(st.integers(min_value=0, max_value=199))
        stages.append({"name": f"Stage_{i}", "x": x, "y": y})
    return stages


@st.composite
def path_strategy(draw):
    """Strategy for a single path with 1-5 waypoints in grid space."""
    num_waypoints = draw(st.integers(min_value=1, max_value=5))
    waypoints = [
        (draw(st.integers(min_value=0, max_value=199)),
         draw(st.integers(min_value=0, max_value=199)))
        for _ in range(num_waypoints)
    ]
    width_m = draw(st.floats(min_value=3.0, max_value=20.0))
    return {"name": "TestPath", "waypoints": waypoints, "width_m": width_m}


class TestPathConnectionCorrectnessProperty:
    """
    Property 6: Path-to-Stage Connection Correctness

    **Validates: Requirements 3.1, 3.2**

    For any set of stage grid positions and any path with known waypoints,
    derive_path_connections SHALL include a stage in the path's connection list
    if and only if that stage's grid position is within proximity_threshold_cells
    of at least one waypoint on the path. The resulting connects list SHALL
    contain both directions (A, B) and (B, A) for every connected stage pair.
    """

    @given(
        stages=stages_strategy(),
        path=path_strategy(),
        threshold=st.integers(min_value=5, max_value=60),
    )
    @settings(max_examples=100)
    def test_stage_included_iff_within_threshold_of_any_waypoint(
        self, stages, path, threshold
    ):
        """A stage appears in the connection list iff it is within
        proximity_threshold_cells of at least one waypoint."""
        paths = [path]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0,
            proximity_threshold_cells=threshold,
        )
        assert len(result) == 1
        conn = result[0]

        # Determine which stages SHOULD be connected based on distance
        expected_connected = set()
        for stage in stages:
            stage_pos = (stage["x"], stage["y"])
            for wp in path["waypoints"]:
                if _euclidean(wp, stage_pos) <= threshold:
                    expected_connected.add(stage["name"])
                    break

        # Extract actual connected stages from the connects list
        actual_connected = set()
        for pair in conn["connects"]:
            actual_connected.add(pair[0])
            actual_connected.add(pair[1])

        # If fewer than 2 stages are expected, connects should be empty
        if len(expected_connected) < 2:
            assert conn["connects"] == []
            assert len(conn["warnings"]) == 1
        else:
            # The set of stages in connects should match expected
            assert actual_connected == expected_connected
            assert conn["warnings"] == []

    @given(
        stages=stages_strategy(),
        path=path_strategy(),
        threshold=st.integers(min_value=5, max_value=60),
    )
    @settings(max_examples=100)
    def test_connects_contains_both_directions_for_every_pair(
        self, stages, path, threshold
    ):
        """Both (A, B) and (B, A) are present for every connected pair."""
        paths = [path]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0,
            proximity_threshold_cells=threshold,
        )
        conn = result[0]
        connects = conn["connects"]

        # For every pair (A, B) in connects, (B, A) must also be present
        connects_set = set(connects)
        for a, b in connects:
            assert (b, a) in connects_set, (
                f"Found ({a}, {b}) but not ({b}, {a}) in connects"
            )

    @given(
        stages=stages_strategy(),
        path=path_strategy(),
        threshold=st.integers(min_value=5, max_value=60),
    )
    @settings(max_examples=100)
    def test_connects_has_no_self_pairs(self, stages, path, threshold):
        """No pair (A, A) should ever appear in the connects list."""
        paths = [path]
        result = derive_path_connections(
            paths, stages, meters_per_cell=1.0,
            proximity_threshold_cells=threshold,
        )
        conn = result[0]
        for a, b in conn["connects"]:
            assert a != b, f"Self-pair ({a}, {a}) found in connects"
