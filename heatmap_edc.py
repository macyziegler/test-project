"""
heatmap_edc.py — Congestion heatmaps for EDC Orlando late-night set transitions.
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE
from simulation.model import FestivalModel, Attendee
from data_io.parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from collections import defaultdict

# --------------------------------------------------------------------------- #
# PARSE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc, entry_cells = latlon_to_grid(stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# --------------------------------------------------------------------------- #
# FOCUS ON LATE-NIGHT TRANSITIONS (7 PM onward = step 25+)
# --------------------------------------------------------------------------- #
late_transitions = []
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        step = slot["end"]
        if step >= time_to_step(19, 0):  # 7 PM onward
            late_transitions.append({
                "step": step,
                "artist": slot["artist"],
                "stage": cfg["name"],
                "popularity": slot["popularity"]
            })

# also capture 1 step after each transition
capture_steps = set()
for t in late_transitions:
    capture_steps.update([t["step"], t["step"] + 1])
capture_steps = sorted([s for s in capture_steps if 1 <= s <= 44])

# build step → label lookup
step_labels = defaultdict(list)
for t in late_transitions:
    step_labels[t["step"]].append(f"{t['artist']} ends @ {t['stage']}")

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
print("Running EDC simulation for heatmap capture...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=8,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE
)

snapshots = {}
for step in range(1, 45):
    model.step()
    if step in capture_steps:
        grid = np.zeros((GRID_SIZE, GRID_SIZE))
        for a in model.agents:
            if isinstance(a, Attendee):
                # spread each agent over a 5-cell radius for density visualization
                cx, cy = a.pos
                for dx in range(-5, 6):
                    for dy in range(-5, 6):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                            dist = np.sqrt(dx**2 + dy**2)
                            if dist <= 5:
                                grid[ny][nx] += (1 - dist / 6)  # falloff with distance
        snapshots[step] = grid
    if step % 10 == 0:
        print(f"  Step {step}/44 complete...")

# --------------------------------------------------------------------------- #
# HELPER
# --------------------------------------------------------------------------- #
def step_to_time(step):
    total_min = (step - 1) * 15
    hour = 13 + total_min // 60
    minute = total_min % 60
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minute:02d} PM"

# --------------------------------------------------------------------------- #
# PICK 8 MOST IMPORTANT TRANSITIONS
# --------------------------------------------------------------------------- #
late_transitions.sort(key=lambda x: x["popularity"], reverse=True)
plot_steps = []
seen = set()
for t in late_transitions:
    if t["step"] in snapshots and t["step"] not in seen:
        plot_steps.append(t["step"])
        seen.add(t["step"])
    if len(plot_steps) >= 8:
        break
plot_steps.sort()

# --------------------------------------------------------------------------- #
# PLOT
# --------------------------------------------------------------------------- #
rows = 2
cols = 4
fig, axes = plt.subplots(rows, cols, figsize=(22, 11))
axes = axes.flatten()

for idx, step in enumerate(plot_steps):
    if idx >= len(axes):
        break
    ax = axes[idx]
    grid = snapshots[step] * SCALE  # scale to real attendance volume

    im = ax.imshow(
        grid, cmap="YlOrRd", origin="lower",
        norm=mcolors.PowerNorm(gamma=0.4, vmin=0, vmax=max(grid.max(), 1)),
        aspect="equal"
    )

    # draw obstacles
    obs_overlay = np.zeros((GRID_SIZE, GRID_SIZE, 4))
    for obs in grid_obstacles:
        for (x, y) in obs["cells"]:
            if "Water" in obs["name"]:
                obs_overlay[y][x] = [0.2, 0.5, 0.9, 0.5]
            else:
                obs_overlay[y][x] = [0.4, 0.3, 0.2, 0.5]
    ax.imshow(obs_overlay, origin="lower", aspect="equal")

    # mark stages
    for name, (sx, sy) in stage_pos.items():
        ax.plot(sx, sy, "w*", markersize=10, markeredgecolor="black")
        ax.annotate(name, (sx, sy), color="white", fontsize=5,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.7))

    title = f"{step_to_time(step)}"
    if step in step_labels:
        title += f"\n{step_labels[step][0][:40]}"
    ax.set_title(title, fontsize=9)
    ax.set_xlim(0, GRID_SIZE)
    ax.set_ylim(0, GRID_SIZE)

for idx in range(len(plot_steps), len(axes)):
    axes[idx].set_visible(False)

fig.suptitle("EDC Orlando 2025 Day 3 — Late Night Congestion Heatmap", fontsize=14, fontweight="bold")
fig.colorbar(im, ax=axes, label="Estimated People per Cell", shrink=0.6)
plt.tight_layout()
plt.savefig("data/edc_congestion_heatmap.png", dpi=150)
plt.show()
print("Saved edc_congestion_heatmap.png to data/")

# --------------------------------------------------------------------------- #
# BOTTLENECK REPORT
# --------------------------------------------------------------------------- #
stage_cells = {(s["x"], s["y"]) for s in grid_stages}

print("\n" + "=" * 70)
print("BOTTLENECK REPORT — Late Night Congestion Hotspots")
print("=" * 70)

for step in plot_steps:
    grid = snapshots[step].copy()
    # zero out stage cells and their immediate area
    for sx, sy in stage_cells:
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                nx, ny = sx + dx, sy + dy
                if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                    grid[ny][nx] = 0

    # find top 5 hotspots
    top_indices = np.argsort(grid.ravel())[-5:][::-1]
    label = step_labels.get(step, [""])[0]
    print(f"\n{step_to_time(step)} (Step {step}) — {label}")
    for rank, flat_idx in enumerate(top_indices, 1):
        y, x = divmod(flat_idx, GRID_SIZE)
        count = grid[y][x] * SCALE
        if count > 0:
            # find nearest stage
            nearest = min(stage_pos.items(), key=lambda s: np.sqrt((s[1][0]-x)**2 + (s[1][1]-y)**2))
            dist_m = np.sqrt((nearest[1][0]-x)**2 + (nearest[1][1]-y)**2) * mpc
            print(f"  #{rank}: Cell ({x},{y}) — ~{int(count)} people — {dist_m:.0f}m from {nearest[0]}")
