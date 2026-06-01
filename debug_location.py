from parse_kml import parse_kml, latlon_to_grid
import numpy as np

stages, obstacles, bounds = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, mask, mpc = latlon_to_grid(stages, obstacles, bounds, grid_size=200)

# problem area
all_lats = [c[0] for c in bounds]
all_lons = [c[1] for c in bounds]
min_lat, max_lat = min(all_lats), max(all_lats)
min_lon, max_lon = min(all_lons), max(all_lons)
lat_pad = (max_lat - min_lat) * 0.05
lon_pad = (max_lon - min_lon) * 0.05
min_lat -= lat_pad
max_lat += lat_pad
min_lon -= lon_pad
max_lon += lon_pad

prob_lat, prob_lon = 28.539096, -81.401039
px = int((prob_lon - min_lon) / (max_lon - min_lon) * 199)
py = int((prob_lat - min_lat) / (max_lat - min_lat) * 199)
print(f"Problem area: grid ({px}, {py})")
print(f"Blocked: {mask[py][px]}")

# show nearby stages
for s in grid_stages:
    dist = np.sqrt((s["x"] - px)**2 + (s["y"] - py)**2)
    print(f"  {s['name']:20s} at ({s['x']:3d},{s['y']:3d}) — {dist:.0f} cells away")
