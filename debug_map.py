"""debug_map.py — Check if stages are reachable."""
from parse_kml import parse_kml, latlon_to_grid
import numpy as np

stages, obstacles, bounds = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, mask, mpc = latlon_to_grid(stages, obstacles, bounds, grid_size=200)

print("Stage positions and blocked status:")
for s in grid_stages:
    x, y = s["x"], s["y"]
    blocked = mask[y][x]
    # check how many walkable cells in a 10-cell radius
    walkable_nearby = 0
    for dx in range(-10, 11):
        for dy in range(-10, 11):
            nx, ny = x + dx, y + dy
            if 0 <= nx < 200 and 0 <= ny < 200 and not mask[ny][nx]:
                walkable_nearby += 1
    print(f"  {s['name']:20s} grid=({x:3d},{y:3d})  blocked={blocked}  walkable_nearby={walkable_nearby}/441")

# check venue boundary extents
all_lats = [c[0] for c in bounds]
all_lons = [c[1] for c in bounds]
print(f"\nVenue lat range: {min(all_lats):.7f} to {max(all_lats):.7f}")
print(f"Venue lon range: {min(all_lons):.7f} to {max(all_lons):.7f}")
print(f"\nCircuit Grounds raw: lat=28.5398631, lon=-81.4047035")
print(f"  Inside lat range: {min(all_lats) <= 28.5398631 <= max(all_lats)}")
print(f"  Inside lon range: {min(all_lons) <= -81.4047035 <= max(all_lons)}")
