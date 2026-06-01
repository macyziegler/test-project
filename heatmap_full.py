"""
heatmap_full.py — Full festival heatmap capturing every step.
Highlights congestion pain points and compares transition vs calm periods.
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
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc = latlon_to_grid(stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# combine path cells
all_path_cells_heatmap = set()
for p in grid_paths:
    all_path_cells_heatmap.update(p["cells"])

# --------------------------------------------------------------------------- #
# BUILD SET TRANSITION LOOKUP
# --------------------------------------------------------------------------- #
transition_steps = {}
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        s = slot["start"]
        if s not in transition_steps:
            transition_steps[s] = []
        transition_steps[s].append(f"{slot['artist']} starts @ {cfg['name']}")
        e = slot["end"]
        if e not in transition_steps:
            transition_steps[e] = []
        transition_steps[e].append(f"{slot['artist']} ends @ {cfg['name']}")

# --------------------------------------------------------------------------- #
# RUN SIMULATION — CAPTURE EVERY STEP
# --------------------------------------------------------------------------- #
print("Running full simulation (capturing all 44 steps)...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
    path_cells=all_path_cells
)

snapshots = {}
agent_counts_moving = {}  # how many agents are in transit each step

for step in range(1, 45):
    model.step()

    # count agents in transit
    moving = sum(1 for a in model.agents if isinstance(a, Attendee) and not a.arrived)
    agent_counts_moving[step] = moving

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

    if step % 5 == 0:
        print(f"  Step {step}/44 complete...")

print("Simulation complete.\n")

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
# CONGESTION ANALYSIS — find pain points per step
# --------------------------------------------------------------------------- #
stage_cells = set()
for s in grid_stages:
    for dx in range(-20, 21):
        for dy in range(-20, 21):
            nx, ny = s["x"] + dx, s["y"] + dy
            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                if np.sqrt(dx**2 + dy**2) <= 20:
                    stage_cells.add((nx, ny))

# use locally parsed path cells
all_path_cells_local = all_path_cells_heatmap

print("=" * 90)
print("FULL FESTIVAL CONGESTION REPORT — EDC Orlando 2025 Day 3")
print("Analyzing WALKWAY congestion only (stage areas excluded)")
print("=" * 90)

pain_points = []

for step in range(1, 45):
    grid = snapshots[step].copy()

    # zero out stage areas (large radius)
    for (sx, sy) in stage_cells:
        grid[sy][sx] = 0

    # find peak congestion ON PATH CORRIDORS specifically
    path_peak_val = 0
    path_peak_x, path_peak_y = 0, 0
    for (px, py) in all_path_cells_local:
        if grid[py][px] > path_peak_val:
            path_peak_val = grid[py][px]
            path_peak_x, path_peak_y = px, py

    # also find overall peak (non-stage, non-path) for comparison
    overall_peak_val = grid.max() * SCALE
    path_peak_scaled = path_peak_val * SCALE

    # find nearest stage to path peak
    nearest = min(stage_pos.items(), key=lambda s: np.sqrt((s[1][0]-path_peak_x)**2 + (s[1][1]-path_peak_y)**2))
    dist_m = np.sqrt((nearest[1][0]-path_peak_x)**2 + (nearest[1][1]-path_peak_y)**2) * mpc

    # find which path this is on
    on_path = "open area"
    for p in grid_paths:
        if (path_peak_x, path_peak_y) in p["cells"]:
            on_path = p["name"]
            break

    moving_pct = agent_counts_moving[step] / max(model.spawned, 1) * 100

    severity = ""
    if path_peak_scaled > 300 and moving_pct > 30:
        severity = "** CRITICAL **"
    elif path_peak_scaled > 200 and moving_pct > 20:
        severity = "* HIGH *"
    elif path_peak_scaled > 100 and moving_pct > 15:
        severity = "MODERATE"

    transitions_now = transition_steps.get(step, [])
    trans_str = " | ".join(transitions_now) if transitions_now else "--"

    pain_points.append({
        "step": step,
        "time": step_to_time(step),
        "path_congestion": int(path_peak_scaled),
        "peak_location": f"({path_peak_x},{path_peak_y})",
        "on_path": on_path,
        "near_stage": nearest[0],
        "dist_m": int(dist_m),
        "moving_pct": moving_pct,
        "severity": severity,
        "transitions": trans_str,
    })

# print report
print(f"\n{'Time':<10} {'Severity':<16} {'Path Density':<14} {'On Path':<28} {'Near':<18} {'Moving%':<10} {'Transitions'}")
print("-" * 140)
for p in pain_points:
    print(f"{p['time']:<10} {p['severity']:<16} {p['path_congestion']:<14} {p['on_path']:<28} {p['near_stage']:<18} {p['moving_pct']:<10.1f} {p['transitions'][:50]}")

# --------------------------------------------------------------------------- #
# SUMMARY — worst moments
# --------------------------------------------------------------------------- #
critical = [p for p in pain_points if "CRITICAL" in p["severity"]]
high = [p for p in pain_points if "HIGH" in p["severity"]]

print("\n" + "=" * 90)
print("TOP WALKWAY PAIN POINTS")
print("=" * 90)

if critical:
    print("\n** CRITICAL congestion moments: **")
    for p in critical:
        print(f"  {p['time']} -- Density {p['path_congestion']} on [{p['on_path']}] near {p['near_stage']}")
        print(f"    {p['moving_pct']:.0f}% of crowd in transit | {p['transitions']}")

if high:
    print("\n* HIGH congestion moments: *")
    for p in high:
        print(f"  {p['time']} -- Density {p['path_congestion']} on [{p['on_path']}] near {p['near_stage']}")
        print(f"    {p['moving_pct']:.0f}% of crowd in transit | {p['transitions']}")

if not critical and not high:
    print("\nNo critical or high congestion detected on walkway corridors.")
    print("Top 5 busiest walkway moments:")
    top5 = sorted(pain_points, key=lambda p: p["path_congestion"], reverse=True)[:5]
    for p in top5:
        print(f"  {p['time']} -- Density {p['path_congestion']} on [{p['on_path']}] near {p['near_stage']}")
        print(f"    {p['moving_pct']:.0f}% in transit | {p['transitions']}")

# --------------------------------------------------------------------------- #
# PLOT — 8 worst congestion moments as heatmaps
# --------------------------------------------------------------------------- #
worst = sorted(pain_points, key=lambda p: p["path_congestion"], reverse=True)[:8]
worst.sort(key=lambda p: p["step"])

fig, axes = plt.subplots(2, 4, figsize=(24, 12))
axes = axes.flatten()

all_max = max(snapshots[w["step"]].max() for w in worst) * SCALE

for idx, w in enumerate(worst):
    ax = axes[idx]
    grid = snapshots[w["step"]] * SCALE

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
        ax.plot(sx, sy, "w*", markersize=10, markeredgecolor="black")
        ax.annotate(name, (sx, sy), color="white", fontsize=5,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.7))

    # mark peak congestion point
    peak_grid = snapshots[w["step"]].copy()
    for (sx, sy) in stage_cells:
        peak_grid[sy][sx] = 0
    pi = np.argmax(peak_grid)
    py, px = divmod(pi, GRID_SIZE)
    ax.plot(px, py, "x", color="cyan", markersize=15, markeredgewidth=3)

    title = f"{w['time']} {w['severity']}\n{w['on_path'][:30]}"
    ax.set_title(title, fontsize=8, fontweight="bold")
    ax.set_xlim(0, GRID_SIZE)
    ax.set_ylim(0, GRID_SIZE)

fig.suptitle("EDC Orlando 2025 Day 3 — Top 8 Congestion Pain Points", fontsize=14, fontweight="bold")
fig.colorbar(im, ax=axes, label="Estimated Crowd Density", shrink=0.6)
plt.tight_layout()
plt.savefig("data/edc_pain_points.png", dpi=150)
plt.show()
print("\nSaved edc_pain_points.png to data/")
