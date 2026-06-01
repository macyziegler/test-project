"""
show_map.py — Visualize the EDC Orlando venue map from KML data.
Shows stages, obstacles (water, sound barriers), and venue boundary.
"""
from parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# parse the KML
stages, obstacles, bounds = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, obstacle_mask, mpc = latlon_to_grid(stages, obstacles, bounds, grid_size=200)

fig, ax = plt.subplots(figsize=(12, 12))

# plot obstacle mask: walkable = white, blocked = dark gray, obstacles = colored
display = np.ones((200, 200, 3))  # white background

# outside venue = light gray
for y in range(200):
    for x in range(200):
        if obstacle_mask[y][x]:
            display[y][x] = [0.85, 0.85, 0.85]

# color specific obstacles
colors_map = {
    "Water": [0.2, 0.5, 0.9],
    "Conex Sound Barriers": [0.6, 0.4, 0.2],
    "Conex Sounds Barriers": [0.6, 0.4, 0.2],
}
for obs in grid_obstacles:
    color = colors_map.get(obs["name"], [0.5, 0.5, 0.5])
    for (x, y) in obs["cells"]:
        display[y][x] = color

ax.imshow(display, origin="lower", aspect="equal")

# plot stages as large markers
stage_colors = {
    "Kinetic Field": "#FF4444",
    "Circuit Grounds": "#44AAFF",
    "Neon Garden": "#AA44FF",
    "Stereo Bloom": "#44DD44",
    "Casa Bacardi": "#FFAA00",
}

for s in grid_stages:
    color = stage_colors.get(s["name"], "white")
    ax.plot(s["x"], s["y"], "*", markersize=25, color=color,
            markeredgecolor="black", markeredgewidth=1.5)
    ax.annotate(s["name"], (s["x"], s["y"]),
                fontsize=10, fontweight="bold", ha="center", va="bottom",
                xytext=(0, 12), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", fc=color, alpha=0.8, ec="black"),
                color="white" if s["name"] != "Casa Bacardi" else "black")

# legend
legend_items = [
    mpatches.Patch(color=[0.2, 0.5, 0.9], label="Water"),
    mpatches.Patch(color=[0.6, 0.4, 0.2], label="Sound Barriers"),
    mpatches.Patch(color=[0.85, 0.85, 0.85], label="Out of Bounds"),
    mpatches.Patch(color="white", ec="black", label="Walkable Area"),
]
ax.legend(handles=legend_items, loc="lower right", fontsize=10)

# distances between stages
print("Stage positions and distances:")
print("-" * 50)
for s in grid_stages:
    print(f"  {s['name']:20s} → grid ({s['x']:3d}, {s['y']:3d})")
print()
for i, s1 in enumerate(grid_stages):
    for s2 in grid_stages[i+1:]:
        dx = (s1["x"] - s2["x"]) * mpc
        dy = (s1["y"] - s2["y"]) * mpc
        dist = np.sqrt(dx**2 + dy**2)
        walk_min = dist / 80
        print(f"  {s1['name']:20s} → {s2['name']:20s}: {dist:.0f}m (~{walk_min:.1f} min)")

ax.set_title("EDC Orlando — Venue Map", fontsize=14, fontweight="bold")
ax.set_xlabel(f"Grid cells (~{mpc:.1f}m each)", fontsize=11)
ax.set_ylabel(f"Grid cells (~{mpc:.1f}m each)", fontsize=11)

plt.tight_layout()
plt.savefig("data/edc_venue_map.png", dpi=150)
plt.show()
print("\nSaved edc_venue_map.png to data/")
