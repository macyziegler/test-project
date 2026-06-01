"""
heatmap_animated.py — Animated heatmap that plays through the full festival day.
Saves as GIF. Shows crowd movement, stage labels, and congestion alerts.
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE, all_path_cells
from model_edc import FestivalModel, Attendee
from parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.animation as animation
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
# BUILD TRANSITION LOOKUP
# --------------------------------------------------------------------------- #
transition_steps = {}
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        for s in [slot["start"], slot["end"]]:
            if s not in transition_steps:
                transition_steps[s] = []
        transition_steps[slot["start"]].append(f"{slot['artist']} starts @ {cfg['name']}")
        transition_steps[slot["end"]].append(f"{slot['artist']} ends @ {cfg['name']}")

# build "now playing" lookup
now_playing = {}
for step in range(1, 45):
    playing = {}
    for cfg in stage_configs:
        for slot in cfg["schedule"]:
            if slot["start"] <= step < slot["end"]:
                playing[cfg["name"]] = slot["artist"]
    now_playing[step] = playing

# --------------------------------------------------------------------------- #
# RUN SIMULATION — CAPTURE EVERY STEP
# --------------------------------------------------------------------------- #
print("Running full simulation for animation...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
    path_cells=all_path_cells
)

snapshots = {}
crowd_counts = {}

for step in range(1, 45):
    model.step()

    # capture density grid
    grid = np.zeros((GRID_SIZE, GRID_SIZE))
    for a in model.agents:
        if isinstance(a, Attendee):
            cx, cy = a.pos
            for dx in range(-12, 13):
                for dy in range(-12, 13):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                        dist = np.sqrt(dx**2 + dy**2)
                        if dist <= 12:
                            grid[ny][nx] += max(0, (1 - dist / 13)) ** 2
    snapshots[step] = grid

    # capture crowd counts
    counts = {}
    for s in model.stages:
        counts[s.name] = s.crowd_count
    crowd_counts[step] = counts

    if step % 10 == 0:
        print(f"  Step {step}/44 complete...")

print("Simulation complete. Building animation...\n")

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
# BUILD OBSTACLE OVERLAY (static, drawn once)
# --------------------------------------------------------------------------- #
obs_overlay = np.zeros((GRID_SIZE, GRID_SIZE, 4))
for obs in grid_obstacles:
    for (x, y) in obs["cells"]:
        if "Water" in obs["name"]:
            obs_overlay[y][x] = [0.2, 0.5, 0.9, 0.6]
        else:
            obs_overlay[y][x] = [0.4, 0.3, 0.2, 0.6]

# --------------------------------------------------------------------------- #
# ANIMATION
# --------------------------------------------------------------------------- #
all_max = max(g.max() for g in snapshots.values()) * SCALE

fig, ax = plt.subplots(figsize=(12, 12))

# initial frame
im = ax.imshow(
    snapshots[1] * SCALE, cmap="YlOrRd", origin="lower",
    norm=mcolors.PowerNorm(gamma=0.3, vmin=0, vmax=all_max * 0.5),
    aspect="equal"
)
obs_im = ax.imshow(obs_overlay, origin="lower", aspect="equal")

# stage markers (static)
for name, (sx, sy) in stage_pos.items():
    ax.plot(sx, sy, "w*", markersize=14, markeredgecolor="black", markeredgewidth=1)

# stage labels (will update with artist names)
stage_labels = {}
for name, (sx, sy) in stage_pos.items():
    label = ax.annotate(
        name, (sx, sy), color="white", fontsize=7, fontweight="bold",
        ha="center", va="bottom", xytext=(0, 8), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.8)
    )
    stage_labels[name] = label

# title and info text
title_text = ax.set_title("", fontsize=14, fontweight="bold", pad=15)
info_text = ax.text(
    0.02, 0.98, "", transform=ax.transAxes, fontsize=9,
    verticalalignment="top", fontfamily="monospace",
    bbox=dict(boxstyle="round", fc="black", alpha=0.8, ec="white"),
    color="white"
)
alert_text = ax.text(
    0.98, 0.02, "", transform=ax.transAxes, fontsize=10,
    verticalalignment="bottom", horizontalalignment="right",
    fontweight="bold", color="red",
    bbox=dict(boxstyle="round", fc="white", alpha=0.9, ec="red")
)

ax.set_xlim(0, GRID_SIZE)
ax.set_ylim(0, GRID_SIZE)
ax.set_xticks([])
ax.set_yticks([])

def update(frame):
    step = frame + 1

    # update heatmap
    grid = snapshots[step] * SCALE
    im.set_data(grid)

    # update title
    title_text.set_text(f"EDC Orlando 2025 Day 3 — {step_to_time(step)}")

    # update stage labels with current artist
    playing = now_playing.get(step, {})
    for name, label in stage_labels.items():
        artist = playing.get(name, "—")
        label.set_text(f"{name}\n{artist}")

    # update crowd counts
    counts = crowd_counts[step]
    info_lines = "Stage Crowds (est):\n"
    for name in ["Kinetic Field", "Circuit Grounds", "Neon Garden", "Stereo Bloom", "Casa Bacardi"]:
        est = int(counts.get(name, 0) * SCALE)
        bar = "#" * (est // 3000)
        info_lines += f"  {name:<18s} {est:>6,}  {bar}\n"
    info_text.set_text(info_lines)

    # congestion alert
    transitions = transition_steps.get(step, [])
    if transitions:
        alert_str = "SET CHANGE:\n" + "\n".join(t[:40] for t in transitions[:3])
        alert_text.set_text(alert_str)
        alert_text.set_visible(True)
    else:
        alert_text.set_visible(False)

    return [im, title_text, info_text, alert_text] + list(stage_labels.values())

print("Rendering animation (this may take a minute)...")
ani = animation.FuncAnimation(
    fig, update, frames=44, interval=800, blit=False, repeat=True
)

# save as GIF
ani.save("data/edc_festival_animation.gif", writer="pillow", fps=2, dpi=100)
print("Saved edc_festival_animation.gif to data/")

plt.show()
