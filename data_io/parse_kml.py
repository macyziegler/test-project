"""
parse_kml.py — Parse EDC Orlando KML map into simulation grid coordinates.

Converts lat/lon to grid positions, extracts stages and obstacles.
"""
import xml.etree.ElementTree as ET
import numpy as np

KML_NS = "{http://www.opengis.net/kml/2.2}"


def parse_kml(filepath):
    """Parse a KML file and return stages, obstacles, paths, and venue bounds."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    stages = []
    obstacles = []
    paths = []
    venue_bounds = None
    entry_exit = None

    for placemark in root.iter(f"{KML_NS}Placemark"):
        name = placemark.find(f"{KML_NS}name").text

        # check for point (stage) — skip unnamed/accidental points
        point = placemark.find(f"{KML_NS}Point")
        if point is not None:
            coords_text = point.find(f"{KML_NS}coordinates").text.strip()
            lon, lat, _ = [float(x) for x in coords_text.split(",")]
            if name.startswith("Point"):
                continue  # skip accidental markers
            stages.append({"name": name, "lat": lat, "lon": lon})
            continue

        # check for linestring (path)
        linestring = placemark.find(f"{KML_NS}LineString")
        if linestring is not None:
            coords_text = linestring.find(f"{KML_NS}coordinates").text.strip()
            coords = []
            for c in coords_text.split():
                lon, lat, _ = [float(x) for x in c.split(",")]
                coords.append((lat, lon))
            paths.append({"name": name, "coords": coords})
            continue

        # check for polygon (obstacle or bounds)
        polygon = placemark.find(f"{KML_NS}Polygon")
        if polygon is not None:
            coords_text = polygon.find(
                f"{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"
            ).text.strip()
            coords = []
            for c in coords_text.split():
                lon, lat, _ = [float(x) for x in c.split(",")]
                coords.append((lat, lon))

            if name == "EDC OuterBounds":
                venue_bounds = coords
            elif name == "Entry/Exit":
                entry_exit = coords
            else:
                obstacles.append({"name": name, "coords": coords})

    return stages, obstacles, paths, venue_bounds, entry_exit


def latlon_to_grid(stages, obstacles, paths, venue_bounds, grid_size=200, entry_exit=None):
    """Convert lat/lon coordinates to grid positions.

    Returns:
        grid_stages: list of {"name", "x", "y"}
        grid_obstacles: list of {"name", "cells": [(x,y), ...]}
        grid_paths: list of {"name", "waypoints": [(x,y), ...], "cells": set((x,y), ...)}
        obstacle_mask: 2D numpy array, True = blocked cell
        meters_per_cell: float
        entry_cells: set of (x,y) tuples for entry/exit area
    """
    # find bounding box from venue bounds
    all_lats = [c[0] for c in venue_bounds]
    all_lons = [c[1] for c in venue_bounds]
    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    # add small padding
    lat_pad = (max_lat - min_lat) * 0.05
    lon_pad = (max_lon - min_lon) * 0.05
    min_lat -= lat_pad
    max_lat += lat_pad
    min_lon -= lon_pad
    max_lon += lon_pad

    def to_grid(lat, lon):
        x = int((lon - min_lon) / (max_lon - min_lon) * (grid_size - 1))
        y = int((lat - min_lat) / (max_lat - min_lat) * (grid_size - 1))
        return max(0, min(grid_size - 1, x)), max(0, min(grid_size - 1, y))

    # convert stages
    grid_stages = []
    for s in stages:
        x, y = to_grid(s["lat"], s["lon"])
        grid_stages.append({"name": s["name"], "x": x, "y": y})

    # convert obstacles to filled cell sets
    obstacle_mask = np.zeros((grid_size, grid_size), dtype=bool)
    grid_obstacles = []

    for obs in obstacles:
        cells = set()
        poly_points = [to_grid(lat, lon) for lat, lon in obs["coords"]]

        # fill polygon using scanline
        ys = [p[1] for p in poly_points]
        for y in range(min(ys), max(ys) + 1):
            xs_at_y = []
            n = len(poly_points)
            for i in range(n):
                x1, y1 = poly_points[i]
                x2, y2 = poly_points[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    if y2 != y1:
                        x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        xs_at_y.append(int(round(x_intersect)))
            xs_at_y.sort()
            for j in range(0, len(xs_at_y) - 1, 2):
                for x in range(xs_at_y[j], xs_at_y[j + 1] + 1):
                    if 0 <= x < grid_size and 0 <= y < grid_size:
                        obstacle_mask[y][x] = True
                        cells.add((x, y))

        grid_obstacles.append({"name": obs["name"], "cells": cells})

    # also mark cells outside venue bounds as blocked
    venue_poly = [to_grid(lat, lon) for lat, lon in venue_bounds]
    venue_interior = np.zeros((grid_size, grid_size), dtype=bool)
    ys = [p[1] for p in venue_poly]
    for y in range(min(ys), max(ys) + 1):
        xs_at_y = []
        n = len(venue_poly)
        for i in range(n):
            x1, y1 = venue_poly[i]
            x2, y2 = venue_poly[(i + 1) % n]
            if (y1 <= y < y2) or (y2 <= y < y1):
                if y2 != y1:
                    x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                    xs_at_y.append(int(round(x_intersect)))
        xs_at_y.sort()
        for j in range(0, len(xs_at_y) - 1, 2):
            for x in range(xs_at_y[j], xs_at_y[j + 1] + 1):
                if 0 <= x < grid_size and 0 <= y < grid_size:
                    venue_interior[y][x] = True

    # outside venue = blocked
    obstacle_mask = obstacle_mask | ~venue_interior

    # ensure stage positions and surrounding area are always walkable
    for s in stages:
        sx, sy = to_grid(s["lat"], s["lon"])
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = sx + dx, sy + dy
                if 0 <= nx < grid_size and 0 <= ny < grid_size:
                    obstacle_mask[ny][nx] = False

    # block off vendor/food court/carnival area (between Kinetic Field and Neon Garden)
    # scale coordinates to grid size
    block_x_start = int(100 * grid_size / 200)
    block_x_end = int(146 * grid_size / 200)
    block_y_start = int(120 * grid_size / 200)
    block_y_end = int(176 * grid_size / 200)
    for y in range(block_y_start, block_y_end):
        for x in range(block_x_start, block_x_end):
            if 0 <= x < grid_size and 0 <= y < grid_size:
                obstacle_mask[y][x] = True

    # re-clear stages in case the block overlapped
    for s in stages:
        sx, sy = to_grid(s["lat"], s["lon"])
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                nx, ny = sx + dx, sy + dy
                if 0 <= nx < grid_size and 0 <= ny < grid_size:
                    obstacle_mask[ny][nx] = False

    # convert paths to grid waypoints and create path corridors
    grid_paths = []
    # path widths in meters (from real measurements)
    path_widths = {
        "Kinetic to Circuit Path": 11.3,   # 37ft
        "Casa to Stereo": 9.8,             # 32ft
        "Casa to Stereo route 2": 6.1,     # 20ft
    }
    for p in paths:
        waypoints = [to_grid(lat, lon) for lat, lon in p["coords"]]
        path_cells = set()
        # calculate width in cells based on real width
        width_m = path_widths.get(p["name"], 8.0)  # default 8m if unknown
        # we need meters_per_cell but don't have it yet, estimate from bounds
        lat_dist = (max_lat - min_lat) * 111_320
        lon_dist = (max_lon - min_lon) * 111_320 * np.cos(np.radians((min_lat + max_lat) / 2))
        est_mpc = max(lat_dist, lon_dist) / grid_size
        PATH_WIDTH = max(2, int(round(width_m / est_mpc / 2)))  # half-width in cells
        # draw corridor between consecutive waypoints
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            # bresenham-style line with width
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for t in range(steps + 1):
                cx = int(x1 + (x2 - x1) * t / steps)
                cy = int(y1 + (y2 - y1) * t / steps)
                for dx in range(-PATH_WIDTH, PATH_WIDTH + 1):
                    for dy in range(-PATH_WIDTH, PATH_WIDTH + 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < grid_size and 0 <= ny < grid_size:
                            path_cells.add((nx, ny))
                            obstacle_mask[ny][nx] = False  # ensure paths are walkable
        grid_paths.append({"name": p["name"], "waypoints": waypoints, "cells": path_cells, "width_m": width_m})

    # convert entry/exit polygon to grid cells
    entry_cells = set()
    if entry_exit:
        entry_poly = [to_grid(lat, lon) for lat, lon in entry_exit]
        eys = [p[1] for p in entry_poly]
        for y in range(min(eys), max(eys) + 1):
            xs_at_y = []
            n = len(entry_poly)
            for i in range(n):
                x1, y1 = entry_poly[i]
                x2, y2 = entry_poly[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    if y2 != y1:
                        x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        xs_at_y.append(int(round(x_intersect)))
            xs_at_y.sort()
            for j in range(0, len(xs_at_y) - 1, 2):
                for x in range(xs_at_y[j], xs_at_y[j + 1] + 1):
                    if 0 <= x < grid_size and 0 <= y < grid_size:
                        entry_cells.add((x, y))
                        obstacle_mask[y][x] = False  # ensure entry is walkable

    # calculate real-world scale
    lat_dist_m = (max_lat - min_lat) * 111_320  # approx meters per degree lat
    lon_dist_m = (max_lon - min_lon) * 111_320 * np.cos(np.radians((min_lat + max_lat) / 2))
    meters_per_cell = max(lat_dist_m, lon_dist_m) / grid_size

    return grid_stages, grid_obstacles, grid_paths, obstacle_mask, meters_per_cell, entry_cells


def print_map_summary(kml_path):
    """Parse KML and print a summary of the venue."""
    stages, obstacles, paths, bounds, entry_exit = parse_kml(kml_path)
    grid_stages, grid_obstacles, grid_paths, mask, mpc, entry_cells = latlon_to_grid(stages, obstacles, paths, bounds, entry_exit=entry_exit)

    print("=" * 60)
    print("EDC ORLANDO — VENUE MAP SUMMARY")
    print("=" * 60)
    print(f"\nGrid: 200x200 (~{mpc:.1f}m per cell)")
    print(f"Blocked cells: {mask.sum()} / {mask.size} ({mask.sum()/mask.size*100:.1f}%)")

    print("\nStages:")
    for s in grid_stages:
        print(f"  {s['name']:20s} → grid ({s['x']}, {s['y']})")

    print("\nObstacles:")
    for o in grid_obstacles:
        print(f"  {o['name']:25s} → {len(o['cells'])} cells blocked")

    # distances between stages
    print("\nWalking distances (straight line):")
    for i, s1 in enumerate(grid_stages):
        for s2 in grid_stages[i + 1:]:
            dx = (s1["x"] - s2["x"]) * mpc
            dy = (s1["y"] - s2["y"]) * mpc
            dist = np.sqrt(dx**2 + dy**2)
            walk_min = dist / 80  # ~80m/min walking speed
            print(f"  {s1['name']:20s} → {s2['name']:20s}: {dist:.0f}m (~{walk_min:.1f} min)")

    return grid_stages, grid_obstacles, mask, mpc


if __name__ == "__main__":
    print_map_summary("EDC Orlando Map.kml")
