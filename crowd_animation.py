"""
crowd_animation.py — Animated crowd flow showing individual agents moving between stages.
Each dot = ~30 real people. Color = target stage.
Saves as GIF.
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE, all_path_cells
from simulation.model import FestivalModel, Attendee
from data_io.parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

# --------------------------------------------------------------------------- #
# PARSE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc, entry_cells = latlon_to_grid(
    stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE
)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# stage colors
STAGE_COLORS = {
    "Kinetic Field": "#FF4444",
    "Circuit Grounds": "#44AAFF",
    "Neon Garden": "#AA44FF",
    "Stereo Bloom": "#44DD44",
    "Casa Bacardi": "#FFAA00",
}

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
# RUN SIMULATION — CAPTURE AGENT POSITIONS EVERY STEP
# --------------------------------------------------------------------------- #
print("Running simulation and capturing agent positions...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
    path_cells=all_path_cells
)

# store positions and colors per frame
frames_data = []

for step in range(1, 45):
    model.step()

    xs = []
    ys = []
    colors = []
    for a in model.agents:
        if isinstance(a, Attendee):
            xs.append(a.pos[0])
            ys.append(a.pos[1])
            if a.target_stage:
                colors.append(STAGE_COLORS.get(a.target_stage.name, "#888888"))
            else:
                colors.append("#888888")

    counts = {}
    for s in model.stages:
        counts[s.name] = int(s.crowd_count * SCALE)

    frames_data.append({
        "xs": xs, "ys": ys, "colors": colors,
        "counts": counts, "step": step
    })

    if step % 10 == 0:
        print(f"  Step {step}/44 complete...")

print("Simulation complete. Building animation...\n")

# --------------------------------------------------------------------------- #
# BUILD STATIC MAP ELEMENTS
# --------------------------------------------------------------------------- #
# obstacle image
map_img = np.ones((GRID_SIZE, GRID_SIZE, 3)) * 0.15  # dark background

# walkable area = slightly lighter
for y in range(GRID_SIZE):
    for x in range(GRID_SIZE):
        if not obstacle_mask[y][x]:
            map_img[y][x] = [0.12, 0.12, 0.18]

# water = blue
for obs in grid_obstacles:
    for (x, y) in obs["cells"]:
        if "Water" in obs["name"]:
            map_img[y][x] = [0.1, 0.2, 0.4]
        elif "Conex" in obs["name"]:
            map_img[y][x] = [0.3, 0.25, 0.15]
        elif "Food" in obs["name"] or "Vendor" in obs["name"]:
            map_img[y][x] = [0.2, 0.15, 0.1]
        elif "Carnival" in obs["name"]:
            map_img[y][x] = [0.2, 0.15, 0.1]

# path corridors = faint lines
for p in grid_paths:
    for (x, y) in p["cells"]:
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            map_img[y][x] = [0.2, 0.2, 0.25]

# --------------------------------------------------------------------------- #
# ANIMATION
# --------------------------------------------------------------------------- #
fig, ax = plt.subplots(figsize=(12, 12), facecolor="black")
ax.set_facecolor("black")

# draw map
ax.imshow(map_img, origin="lower", aspect="equal")

# stage markers
for name, (sx, sy) in stage_pos.items():
    color = STAGE_COLORS[name]
    ax.plot(sx, sy, "s", markersize=12, color=color, markeredgecolor="white", markeredgewidth=1.5)

# stage labels (will update with artist)
stage_labels = {}
for name, (sx, sy) in stage_pos.items():
    label = ax.annotate(
        name, (sx, sy), color="white", fontsize=7, fontweight="bold",
        ha="center", va="bottom", xytext=(0, 10), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.3", fc=STAGE_COLORS[name], alpha=0.9, ec="white")
    )
    stage_labels[name] = label

# agent scatter (will update each frame)
scatter = ax.scatter([], [], s=3, alpha=0.6)

# text elements
title_text = ax.set_title("", fontsize=16, fontweight="bold", color="white", pad=15)

info_text = ax.text(
    0.02, 0.98, "", transform=ax.transAxes, fontsize=9,
    verticalalignment="top", fontfamily="monospace",
    bbox=dict(boxstyle="round", fc="black", alpha=0.85, ec="white"),
    color="white"
)

legend_text = ax.text(
    0.98, 0.98, "", transform=ax.transAxes, fontsize=8,
    verticalalignment="top", horizontalalignment="right",
    fontfamily="monospace",
    bbox=dict(boxstyle="round", fc="black", alpha=0.85, ec="white"),
    color="white"
)

# build legend
legend_lines = "Each dot = ~30 people\n"
for name in ["Kinetic Field", "Circuit Grounds", "Neon Garden", "Stereo Bloom", "Casa Bacardi"]:
    legend_lines += f"  {STAGE_COLORS[name]}  {name}\n"
legend_text.set_text(legend_lines)

ax.set_xlim(0, GRID_SIZE)
ax.set_ylim(0, GRID_SIZE)
ax.set_xticks([])
ax.set_yticks([])

def update(frame):
    data = frames_data[frame]
    step = data["step"]

    # update dots
    offsets = np.column_stack([data["xs"], data["ys"]]) if data["xs"] else np.empty((0, 2))
    scatter.set_offsets(offsets)
    scatter.set_facecolors(data["colors"])

    # update title
    title_text.set_text(f"EDC Orlando 2025 Day 3 — {step_to_time(step)}")

    # update stage labels with artist
    playing = now_playing.get(step, {})
    for name, label in stage_labels.items():
        artist = playing.get(name, "—")
        label.set_text(f"{name}\n{artist}")

    # update crowd info
    counts = data["counts"]
    info_lines = "Crowd Estimates:\n"
    for name in ["Kinetic Field", "Circuit Grounds", "Neon Garden", "Stereo Bloom", "Casa Bacardi"]:
        est = counts.get(name, 0)
        bar = "|" * (est // 2000)
        info_lines += f"  {name:<18s} {est:>6,}  {bar}\n"
    total = sum(counts.values())
    info_lines += f"\n  {'TOTAL':<18s} {total:>6,}"
    info_text.set_text(info_lines)

    return [scatter, title_text, info_text] + list(stage_labels.values())

print("Rendering crowd animation (this may take a few minutes)...")
ani = animation.FuncAnimation(
    fig, update, frames=44, interval=1000, blit=False, repeat=True
)

ani.save("data/edc_crowd_animation.gif", writer="pillow", fps=2, dpi=100)
print("Saved edc_crowd_animation.gif to data/")

plt.show()
