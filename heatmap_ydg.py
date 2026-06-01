"""
heatmap_ydg.py — Focused heatmap around YDG's set ending at Stereo Bloom (8:00 PM)
Shows congestion before, during, and after the set transition.
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE
from model_edc import FestivalModel, Attendee
from parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# --------------------------------------------------------------------------- #
# PARSE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, bounds = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, obstacle_mask, mpc = latlon_to_grid(stages_geo, obstacles_geo, bounds, grid_size=GRID_SIZE)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# --------------------------------------------------------------------------- #
# YDG plays 6:45-8:00 PM at Stereo Bloom
# time_to_step(18, 45) to time_to_step(20, 0)
# Capture: before, start, during, end, after
# --------------------------------------------------------------------------- #
ydg_start = time_to_step(18, 45)
ydg_end = time_to_step(20, 0)
capture_steps = [ydg_start - 1, ydg_start, ydg_start + 1, 
                 ydg_start + 3, ydg_end - 1, ydg_end]
capture_labels = [
    "6:30 PM\nCaspa finishing",
    "6:45 PM\nYDG starts (genre clash)",
    "7:00 PM\nCrowd swapping",
    "7:30 PM\nYDG mid-set",
    "7:45 PM\nYDG finishing",
    "8:00 PM\nYDG ends / ALLEYCVT starts",
]

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
print("Running simulation focused on YDG set transition...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE
)

snapshots = {}
for step in range(1, 45):
    model.step()
    if step in capture_steps:
        grid = np.zeros((GRID_SIZE, GRID_SIZE))
        for a in model.agents:
            if isinstance(a, Attendee):
                cx, cy = a.pos
                # larger spread radius — each person affects a 15-cell area
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
# PLOT — 6 panels: before, during, after YDG
# --------------------------------------------------------------------------- #
fig, axes = plt.subplots(2, 3, figsize=(20, 13))
axes = axes.flatten()

# find global max for consistent color scale
all_max = max(g.max() for g in snapshots.values()) * SCALE

for idx, (step, label) in enumerate(zip(capture_steps, capture_labels)):
    ax = axes[idx]
    grid = snapshots[step] * SCALE

    im = ax.imshow(
        grid, cmap="YlOrRd", origin="lower",
        norm=mcolors.PowerNorm(gamma=0.3, vmin=0, vmax=all_max * 0.6),
        aspect="equal"
    )

    # draw obstacles
    obs_overlay = np.zeros((GRID_SIZE, GRID_SIZE, 4))
    for obs in grid_obstacles:
        for (x, y) in obs["cells"]:
            if "Water" in obs["name"]:
                obs_overlay[y][x] = [0.2, 0.5, 0.9, 0.6]
            else:
                obs_overlay[y][x] = [0.4, 0.3, 0.2, 0.6]
    ax.imshow(obs_overlay, origin="lower", aspect="equal")

    # mark stages — highlight Stereo Bloom
    for name, (sx, sy) in stage_pos.items():
        color = "cyan" if name == "Stereo Bloom" else "white"
        size = 18 if name == "Stereo Bloom" else 10
        ax.plot(sx, sy, "*", markersize=size, color=color, markeredgecolor="black")
        ax.annotate(name, (sx, sy), color="white", fontsize=6,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.7))

    ax.set_title(label, fontsize=11, fontweight="bold")
    ax.set_xlim(0, GRID_SIZE)
    ax.set_ylim(0, GRID_SIZE)

fig.suptitle("EDC Orlando — YDG Set Transition Congestion (Stereo Bloom)", fontsize=14, fontweight="bold")
fig.colorbar(im, ax=axes, label="Estimated Crowd Density", shrink=0.6)
plt.tight_layout()
plt.savefig("data/edc_ydg_heatmap.png", dpi=150)
plt.show()

# --------------------------------------------------------------------------- #
# BOTTLENECK REPORT — focus area around Stereo Bloom
# --------------------------------------------------------------------------- #
sb_x, sb_y = stage_pos["Stereo Bloom"]
stage_cells = {(s["x"], s["y"]) for s in grid_stages}

print("\n" + "=" * 70)
print("BOTTLENECK REPORT — Stereo Bloom Area (YDG transition)")
print("=" * 70)

for step, label in zip(capture_steps, capture_labels):
    grid = snapshots[step].copy()
    # zero out stage centers
    for sx, sy in stage_cells:
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                nx, ny = sx + dx, sy + dy
                if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                    grid[ny][nx] = 0

    # find top 5 hotspots near Stereo Bloom (within 50 cells)
    hotspots = []
    for y in range(max(0, sb_y - 50), min(GRID_SIZE, sb_y + 50)):
        for x in range(max(0, sb_x - 50), min(GRID_SIZE, sb_x + 50)):
            if grid[y][x] > 0:
                hotspots.append((grid[y][x] * SCALE, x, y))
    hotspots.sort(reverse=True)

    print(f"\n{label.replace(chr(10), ' ')}  (Step {step}):")
    for rank, (count, x, y) in enumerate(hotspots[:5], 1):
        nearest = min(stage_pos.items(), key=lambda s: np.sqrt((s[1][0]-x)**2 + (s[1][1]-y)**2))
        dist_m = np.sqrt((nearest[1][0]-x)**2 + (nearest[1][1]-y)**2) * mpc
        print(f"  #{rank}: Cell ({x},{y}) — density ~{int(count)} — {dist_m:.0f}m from {nearest[0]}")

print("\nSaved edc_ydg_heatmap.png to data/")
