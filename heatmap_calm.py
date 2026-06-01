"""
heatmap_calm.py — Heatmap during calm mid-set periods (no transitions).
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE, all_path_cells
from model_edc import FestivalModel, Attendee
from parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# --------------------------------------------------------------------------- #
# PARSE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, paths_geo, bounds = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc = latlon_to_grid(
    stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE
)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# --------------------------------------------------------------------------- #
# MID-SET CALM MOMENTS — middle of long sets, no transitions
# --------------------------------------------------------------------------- #
capture_steps = [
    time_to_step(14, 0),   # 2:00 PM — early day
    time_to_step(16, 0),   # 4:00 PM — mid-afternoon
    time_to_step(18, 0),   # 6:00 PM — Green Velvet + Seven Lions mid-set
    time_to_step(19, 30),  # 7:30 PM — Sofi Tukker mid-set
    time_to_step(21, 30),  # 9:30 PM — Subtronics mid-set
    time_to_step(23, 0),   # 11:00 PM — Dom Dolla + Knock2 mid-set, peak
]
capture_labels = [
    "2:00 PM\nEarly day",
    "4:00 PM\nMid-afternoon",
    "6:00 PM\nGreen Velvet + Seven Lions",
    "7:30 PM\nSofi Tukker mid-set",
    "9:30 PM\nSubtronics mid-set",
    "11:00 PM\nDom Dolla + Knock2 (peak)",
]

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
print("Running simulation for mid-set heatmaps...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
    path_cells=all_path_cells
)

snapshots = {}
for step in range(1, 45):
    model.step()
    if step in capture_steps:
        grid = np.zeros((GRID_SIZE, GRID_SIZE))
        for a in model.agents:
            if isinstance(a, Attendee):
                cx, cy = a.pos
                for dx in range(-15, 16):
                    for dy in range(-15, 16):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                            dist = np.sqrt(dx**2 + dy**2)
                            if dist <= 15:
                                grid[ny][nx] += max(0, (1 - dist / 16)) ** 2
        snapshots[step] = grid
        print(f"  Captured step {step}")

# --------------------------------------------------------------------------- #
# PLOT
# --------------------------------------------------------------------------- #
fig, axes = plt.subplots(2, 3, figsize=(20, 13))
axes = axes.flatten()

all_max = max(g.max() for g in snapshots.values()) * SCALE

for idx, (step, label) in enumerate(zip(capture_steps, capture_labels)):
    ax = axes[idx]
    grid = snapshots[step] * SCALE

    im = ax.imshow(
        grid, cmap="YlOrRd", origin="lower",
        norm=mcolors.PowerNorm(gamma=0.3, vmin=0, vmax=all_max * 0.6),
        aspect="equal"
    )

    # obstacles
    obs_overlay = np.zeros((GRID_SIZE, GRID_SIZE, 4))
    for obs in grid_obstacles:
        for (x, y) in obs["cells"]:
            if "Water" in obs["name"]:
                obs_overlay[y][x] = [0.2, 0.5, 0.9, 0.6]
            else:
                obs_overlay[y][x] = [0.4, 0.3, 0.2, 0.6]
    ax.imshow(obs_overlay, origin="lower", aspect="equal")

    # stages
    for name, (sx, sy) in stage_pos.items():
        ax.plot(sx, sy, "w*", markersize=12, markeredgecolor="black")
        ax.annotate(name, (sx, sy), color="white", fontsize=6,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.7))

    # draw path corridors faintly
    for p in grid_paths:
        for (px, py) in p["cells"]:
            if 0 <= px < GRID_SIZE and 0 <= py < GRID_SIZE:
                pass  # paths show up naturally in the heat

    ax.set_title(label, fontsize=11, fontweight="bold")
    ax.set_xlim(0, GRID_SIZE)
    ax.set_ylim(0, GRID_SIZE)

fig.suptitle("EDC Orlando 2025 Day 3 — Mid-Set Crowd Distribution (Calm Periods)",
             fontsize=14, fontweight="bold")
fig.colorbar(im, ax=axes, label="Estimated Crowd Density", shrink=0.6)
plt.tight_layout()
plt.savefig("data/edc_midset_heatmap.png", dpi=150)
plt.show()
print("Saved edc_midset_heatmap.png to data/")
