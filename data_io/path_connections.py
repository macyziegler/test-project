"""
data_io/path_connections.py — Automatic path-to-stage connection derivation.

This module replaces the hardcoded ``path_stage_map`` dict that previously
lived in ``app.py``.  Given the grid-space representation of paths and stages
produced by ``data_io.parse_kml.latlon_to_grid``, it determines which stages
each path connects by geometric proximity — no manual configuration required.

Public API
----------
derive_path_connections(grid_paths, grid_stages, meters_per_cell,
                        proximity_threshold_cells=30)
    → list[dict]   # path flow config dicts ready for PathFlowModel

Private helpers
---------------
_euclidean(p1, p2)              → float
_stages_near_point(point, grid_stages, threshold) → list[str]
"""

import math


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _euclidean(p1: tuple[int, int], p2: tuple[int, int]) -> float:
    """Return the straight-line (Euclidean) distance between two grid points.

    Parameters
    ----------
    p1, p2 : tuple[int, int]
        Grid coordinates as ``(x, y)`` pairs.

    Returns
    -------
    float
        Distance in grid cells.

    Examples
    --------
    >>> _euclidean((0, 0), (3, 4))
    5.0
    >>> _euclidean((1, 1), (1, 1))
    0.0
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


def _stages_near_point(
    point: tuple[int, int],
    grid_stages: list[dict],
    threshold: int,
) -> list[str]:
    """Return the names of all stages within *threshold* cells of *point*.

    Parameters
    ----------
    point : tuple[int, int]
        A grid coordinate ``(x, y)`` — typically a path waypoint.
    grid_stages : list[dict]
        Stage records as produced by ``latlon_to_grid``.  Each dict must
        contain at least ``{"name": str, "x": int, "y": int}``.
    threshold : int
        Maximum distance in grid cells for a stage to be considered "near"
        the point.  A stage exactly *threshold* cells away is included
        (i.e., the comparison is ``<=``).

    Returns
    -------
    list[str]
        Stage names whose grid position satisfies
        ``_euclidean(point, (stage["x"], stage["y"])) <= threshold``.
        The order matches the order of *grid_stages*.

    Examples
    --------
    >>> stages = [{"name": "Main", "x": 5, "y": 5},
    ...           {"name": "Far",  "x": 100, "y": 100}]
    >>> _stages_near_point((0, 0), stages, threshold=10)
    ['Main']
    """
    nearby: list[str] = []
    for stage in grid_stages:
        stage_pos = (stage["x"], stage["y"])
        if _euclidean(point, stage_pos) <= threshold:
            nearby.append(stage["name"])
    return nearby


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def derive_path_connections(
    grid_paths: list[dict],
    grid_stages: list[dict],
    meters_per_cell: float,
    proximity_threshold_cells: int = 30,
) -> list[dict]:
    """Derive path-to-stage connections from grid geometry.

    For each path in *grid_paths*, this function collects all stages within
    *proximity_threshold_cells* of **any** waypoint on the path, then builds
    the ``connects`` list as all ordered pairs of those stages (both directions).

    Parameters
    ----------
    grid_paths : list[dict]
        Path records as produced by ``latlon_to_grid``.  Each dict must
        contain::

            {
                "name":      str,
                "waypoints": list[tuple[int, int]],
                "cells":     set[tuple[int, int]],
                "width_m":   float,
            }

    grid_stages : list[dict]
        Stage records as produced by ``latlon_to_grid``.  Each dict must
        contain ``{"name": str, "x": int, "y": int}``.

    meters_per_cell : float
        Scale factor returned by ``latlon_to_grid``.  Used to convert
        waypoint-to-waypoint distances (in cells) to metres.

    proximity_threshold_cells : int, optional
        Maximum grid-cell distance from a waypoint to a stage for the stage
        to be considered connected to the path.  Defaults to 30.

    Returns
    -------
    list[dict]
        One dict per path, ready for use as a ``PathFlowModel`` config::

            {
                "name":     str,
                "length_m": float,   # sum of waypoint-to-waypoint distances
                                     # × meters_per_cell, minimum 150 m
                "width_m":  float,   # from grid_path["width_m"]
                "connects": list[tuple[str, str]],
                "warnings": list[str],
            }

        Paths with fewer than 2 connected stages receive an empty
        ``connects`` list and a warning string.

    Notes
    -----
    * Stage inclusion is based on proximity to **any** waypoint, not just
      the endpoints.
    * The ``connects`` list contains **both** ``(A, B)`` and ``(B, A)`` for
      every pair of connected stages.
    * ``length_m`` is clamped to a minimum of 150 m so that very short or
      single-waypoint paths still have a physically meaningful length.
    """
    results: list[dict] = []

    for grid_path in grid_paths:
        name: str = grid_path["name"]
        waypoints: list[tuple[int, int]] = grid_path.get("waypoints", [])
        width_m: float = grid_path.get("width_m", 8.0)
        warnings: list[str] = []

        # ------------------------------------------------------------------
        # 1. Collect all stages near any waypoint (deduplicated, order-stable)
        # ------------------------------------------------------------------
        seen: set[str] = set()
        connected_stages: list[str] = []
        for wp in waypoints:
            for stage_name in _stages_near_point(wp, grid_stages, proximity_threshold_cells):
                if stage_name not in seen:
                    seen.add(stage_name)
                    connected_stages.append(stage_name)

        # ------------------------------------------------------------------
        # 2. Build connects list — both (A, B) and (B, A) for every pair
        # ------------------------------------------------------------------
        if len(connected_stages) < 2:
            warnings.append(
                f"Path '{name}' has fewer than 2 connected stages "
                f"(found {len(connected_stages)}); connects list is empty."
            )
            connects: list[tuple[str, str]] = []
        else:
            connects = []
            for i in range(len(connected_stages)):
                for j in range(len(connected_stages)):
                    if i != j:
                        connects.append((connected_stages[i], connected_stages[j]))

        # ------------------------------------------------------------------
        # 3. Calculate length_m from waypoint-to-waypoint distances
        # ------------------------------------------------------------------
        if len(waypoints) >= 2:
            total_cells = sum(
                _euclidean(waypoints[k], waypoints[k + 1])
                for k in range(len(waypoints) - 1)
            )
        else:
            total_cells = 0.0

        length_m = max(total_cells * meters_per_cell, 150.0)

        results.append(
            {
                "name": name,
                "length_m": length_m,
                "width_m": width_m,
                "connects": connects,
                "warnings": warnings,
            }
        )

    return results
