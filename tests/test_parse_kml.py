"""
tests/test_parse_kml.py — Property-based tests for data_io/parse_kml.py

Properties tested:
- Property 1: KML Point and Line Placemarks Round-Trip (Validates: Requirements 1.1, 1.2)
- Property 2: KML Polygon Classification by Name (Validates: Requirements 1.3)
- Property 3: Grid Coordinate Bounds and Ordering (Validates: Requirements 1.4)
"""

import tempfile
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from data_io.parse_kml import parse_kml, latlon_to_grid


# ---------------------------------------------------------------------------
# Helpers: KML generation
# ---------------------------------------------------------------------------

KML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>\n'
KML_FOOTER = "</Document></kml>\n"


def _point_placemark(name: str, lat: float, lon: float) -> str:
    """Generate a KML point placemark string."""
    return (
        f"<Placemark><name>{name}</name>"
        f"<Point><coordinates>{lon},{lat},0</coordinates></Point>"
        f"</Placemark>\n"
    )


def _line_placemark(name: str, coords: list[tuple[float, float]]) -> str:
    """Generate a KML line placemark string. coords is [(lat, lon), ...]."""
    coord_str = " ".join(f"{lon},{lat},0" for lat, lon in coords)
    return (
        f"<Placemark><name>{name}</name>"
        f"<LineString><coordinates>{coord_str}</coordinates></LineString>"
        f"</Placemark>\n"
    )


def _polygon_placemark(name: str, coords: list[tuple[float, float]]) -> str:
    """Generate a KML polygon placemark string. coords is [(lat, lon), ...]."""
    coord_str = " ".join(f"{lon},{lat},0" for lat, lon in coords)
    return (
        f"<Placemark><name>{name}</name>"
        f"<Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coord_str}</coordinates>"
        f"</LinearRing></outerBoundaryIs></Polygon>"
        f"</Placemark>\n"
    )


def _write_kml(content: str) -> str:
    """Write KML content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".kml")
    with os.fdopen(fd, "w") as f:
        f.write(KML_HEADER + content + KML_FOOTER)
    return path


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Stage names must not start with "Point" (those are skipped by parse_kml)
stage_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
).filter(lambda s: not s.startswith("Point") and s.strip() != "")

# Path names: any non-empty text
path_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")

# Obstacle names: must not be "EDC OuterBounds" or "Entry/Exit"
obstacle_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "" and s != "EDC OuterBounds" and s != "Entry/Exit")

# Realistic lat/lon ranges (roughly continental US)
lat_strategy = st.floats(min_value=25.0, max_value=48.0, allow_nan=False, allow_infinity=False)
lon_strategy = st.floats(min_value=-125.0, max_value=-70.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property 1: KML Point and Line Placemarks Round-Trip
# Validates: Requirements 1.1, 1.2
# ---------------------------------------------------------------------------

class TestKMLPointAndLineRoundTrip:
    """
    **Validates: Requirements 1.1, 1.2**

    For any KML document containing N point placemarks and M line placemarks
    with arbitrary names and coordinates, parse_kml SHALL return exactly N stage
    entries and M path entries, each with a name matching the corresponding
    placemark name and coordinates matching the placemark coordinates.
    """

    @given(
        stage_data=st.lists(
            st.tuples(stage_name_strategy, lat_strategy, lon_strategy),
            min_size=0,
            max_size=5,
        ),
        path_data=st.lists(
            st.tuples(
                path_name_strategy,
                st.lists(
                    st.tuples(lat_strategy, lon_strategy),
                    min_size=2,
                    max_size=4,
                ),
            ),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_point_and_line_round_trip(self, stage_data, path_data):
        """parse_kml returns exactly N stages and M paths with matching names and coords."""
        # Build KML content
        kml_body = ""
        for name, lat, lon in stage_data:
            kml_body += _point_placemark(name, lat, lon)
        for name, coords in path_data:
            kml_body += _line_placemark(name, coords)

        path = _write_kml(kml_body)
        try:
            stages, obstacles, paths, venue_bounds, entry_exit = parse_kml(path)

            # Assert correct count
            assert len(stages) == len(stage_data), (
                f"Expected {len(stage_data)} stages, got {len(stages)}"
            )
            assert len(paths) == len(path_data), (
                f"Expected {len(path_data)} paths, got {len(paths)}"
            )

            # Assert names match in order
            for i, (expected_name, expected_lat, expected_lon) in enumerate(stage_data):
                assert stages[i]["name"] == expected_name
                assert stages[i]["lat"] == pytest.approx(expected_lat, rel=1e-6)
                assert stages[i]["lon"] == pytest.approx(expected_lon, rel=1e-6)

            # Assert path names and coordinates match
            for i, (expected_name, expected_coords) in enumerate(path_data):
                assert paths[i]["name"] == expected_name
                assert len(paths[i]["coords"]) == len(expected_coords)
                for j, (exp_lat, exp_lon) in enumerate(expected_coords):
                    assert paths[i]["coords"][j][0] == pytest.approx(exp_lat, rel=1e-6)
                    assert paths[i]["coords"][j][1] == pytest.approx(exp_lon, rel=1e-6)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Property 2: KML Polygon Classification by Name
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

class TestKMLPolygonClassification:
    """
    **Validates: Requirements 1.3**

    For any KML document containing polygon placemarks, parse_kml SHALL route
    the polygon named "EDC OuterBounds" to venue_bounds, the polygon named
    "Entry/Exit" to entry_exit, and all other polygon placemarks to the
    obstacles list.
    """

    @given(
        has_venue_bounds=st.booleans(),
        has_entry_exit=st.booleans(),
        obstacle_names=st.lists(obstacle_name_strategy, min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_polygon_classification_by_name(self, has_venue_bounds, has_entry_exit, obstacle_names):
        """Polygons are classified correctly based on their name."""
        # Use a simple square polygon for all polygons
        square_coords = [(28.0, -81.0), (28.0, -80.0), (29.0, -80.0), (29.0, -81.0), (28.0, -81.0)]

        kml_body = ""

        if has_venue_bounds:
            kml_body += _polygon_placemark("EDC OuterBounds", square_coords)

        if has_entry_exit:
            kml_body += _polygon_placemark("Entry/Exit", square_coords)

        for name in obstacle_names:
            kml_body += _polygon_placemark(name, square_coords)

        path = _write_kml(kml_body)
        try:
            stages, obstacles, paths, venue_bounds, entry_exit = parse_kml(path)

            # venue_bounds
            if has_venue_bounds:
                assert venue_bounds is not None, "Expected venue_bounds to be set"
            else:
                assert venue_bounds is None, "Expected venue_bounds to be None"

            # entry_exit
            if has_entry_exit:
                assert entry_exit is not None, "Expected entry_exit to be set"
            else:
                assert entry_exit is None, "Expected entry_exit to be None"

            # obstacles: all other polygons go here
            assert len(obstacles) == len(obstacle_names), (
                f"Expected {len(obstacle_names)} obstacles, got {len(obstacles)}"
            )
            for i, expected_name in enumerate(obstacle_names):
                assert obstacles[i]["name"] == expected_name
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Property 3: Grid Coordinate Bounds and Ordering
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

class TestGridCoordinateBoundsAndOrdering:
    """
    **Validates: Requirements 1.4**

    For any set of lat/lon points within a valid venue bounding box,
    latlon_to_grid SHALL produce grid coordinates where:
    (a) all x and y values are in [0, grid_size - 1], and
    (b) a point that is strictly north of another point SHALL have a strictly
        greater y-grid value, and a point strictly east of another SHALL have
        a strictly greater x-grid value.
    """

    @given(
        # Generate a bounding box as (min_lat, max_lat, min_lon, max_lon)
        min_lat=st.floats(min_value=25.0, max_value=40.0, allow_nan=False, allow_infinity=False),
        lat_span=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        min_lon=st.floats(min_value=-120.0, max_value=-75.0, allow_nan=False, allow_infinity=False),
        lon_span=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        # Two points within the bounding box (as fractions 0-1 of the span)
        frac_lat1=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
        frac_lon1=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
        frac_lat2=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
        frac_lon2=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
        grid_size=st.integers(min_value=10, max_value=500),
    )
    @settings(max_examples=100)
    def test_grid_bounds_and_ordering(
        self, min_lat, lat_span, min_lon, lon_span,
        frac_lat1, frac_lon1, frac_lat2, frac_lon2, grid_size
    ):
        """Grid coordinates are bounded and preserve geographic ordering."""
        max_lat = min_lat + lat_span
        max_lon = min_lon + lon_span

        # Create two points within the bounding box
        lat1 = min_lat + frac_lat1 * lat_span
        lon1 = min_lon + frac_lon1 * lon_span
        lat2 = min_lat + frac_lat2 * lat_span
        lon2 = min_lon + frac_lon2 * lon_span

        # Build venue bounds as a rectangle
        venue_bounds = [
            (min_lat, min_lon),
            (min_lat, max_lon),
            (max_lat, max_lon),
            (max_lat, min_lon),
            (min_lat, min_lon),  # close the polygon
        ]

        # Create two stages at the generated points
        stages = [
            {"name": "Stage1", "lat": lat1, "lon": lon1},
            {"name": "Stage2", "lat": lat2, "lon": lon2},
        ]

        grid_stages, _, _, _, _, _ = latlon_to_grid(
            stages=stages,
            obstacles=[],
            paths=[],
            venue_bounds=venue_bounds,
            grid_size=grid_size,
        )

        # (a) All grid coordinates are in [0, grid_size - 1]
        for gs in grid_stages:
            assert 0 <= gs["x"] <= grid_size - 1, (
                f"x={gs['x']} out of bounds [0, {grid_size - 1}]"
            )
            assert 0 <= gs["y"] <= grid_size - 1, (
                f"y={gs['y']} out of bounds [0, {grid_size - 1}]"
            )

        s1 = grid_stages[0]
        s2 = grid_stages[1]

        # (b) Strictly north → strictly greater y
        if lat1 < lat2:
            # Stage2 is strictly north of Stage1
            assert s2["y"] >= s1["y"], (
                f"Stage2 (lat={lat2}) should have y >= Stage1 (lat={lat1}), "
                f"but got y2={s2['y']} vs y1={s1['y']}"
            )
        elif lat2 < lat1:
            # Stage1 is strictly north of Stage2
            assert s1["y"] >= s2["y"], (
                f"Stage1 (lat={lat1}) should have y >= Stage2 (lat={lat2}), "
                f"but got y1={s1['y']} vs y2={s2['y']}"
            )

        # (b) Strictly east → strictly greater x
        if lon1 < lon2:
            # Stage2 is strictly east of Stage1
            assert s2["x"] >= s1["x"], (
                f"Stage2 (lon={lon2}) should have x >= Stage1 (lon={lon1}), "
                f"but got x2={s2['x']} vs x1={s1['x']}"
            )
        elif lon2 < lon1:
            # Stage1 is strictly east of Stage2
            assert s1["x"] >= s2["x"], (
                f"Stage1 (lon={lon1}) should have x >= Stage2 (lon={lon2}), "
                f"but got x1={s1['x']} vs x2={s2['x']}"
            )
