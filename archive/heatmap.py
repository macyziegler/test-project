"""
heatmap.py — Generate congestion heatmaps during set transitions.

Captures agent positions at key moments (when sets end and crowds move)
and plots density heatmaps showing bottleneck areas.
"""
from run_festival import stage_configs, time_to_step, WIDTH, HEIGHT, NUM_ATTENDEES, SCALE
from model import FestivalModel, Attendee
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# --------------------------------------------------------------------------- #
# IDENTIFY SET TRANSITION MOMENTS (when a set ends = crowd movement)
# --------------------------------------------------------------------------- #
transitions = []
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        step = slot["end"]
        label = f"{slot['artist']} ends @ {cfg['name']}"
        transitions.append({"step": step, "label": label})

# deduplicate by step, combine labels
from collections import defaultdict
step_labels = defaultdict(list)
for t in transitions:
    step_labels[t["step"]].append(t["label"])

# --------------------------------------------------------------------------- #
# CAPTURE AT SET TRANSITION TIMES (on the hour when sets start/end)
# --------------------------------------------------------------------------- #
# Steps that land on the hour or at :45/:55 (when sets actually change)
transition_steps = set()
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        transition_steps.add(slot["start"])
        transition_steps.add(slot["end"])
        # also capture 1 step after end (crowd in motion)
        transition_steps.add(slot["end"] + 1)

capture_steps = sorted([s for s in transition_steps if 1 <= s <= 32])

# --------------------------------------------------------------------------- #
# RUN SIMULATION, CAPTURE GRID SNAPSHOTS
# --------------------------------------------------------------------------- #
print("Running simulation for heatmap capture...")
model = FestivalModel(WIDTH, HEIGHT, NUM_ATTENDEES, stage_configs, listen_radius=4)

snapshots = {}
for step in range(1, 33):
    model.step()
    if step in capture_steps:
        grid = np.zeros((HEIGHT, WIDTH))
        for a in model.agents:
            if isinstance(a, Attendee):
                grid[a.pos[1]][a.pos[0]] += 1
        snapshots[step] = grid

# --------------------------------------------------------------------------- #
# HELPER: convert step to clock time
# --------------------------------------------------------------------------- #
def step_to_time(step):
    total_min = (step - 1) * 15
    hour = 15 + total_min // 60
    minute = total_min % 60
    period = "PM"
    display_hour = hour if hour <= 12 else hour - 12
    return f"{display_hour}:{minute:02d} {period}"

# --------------------------------------------------------------------------- #
# PLOT: 8 panels at the biggest set transitions
# --------------------------------------------------------------------------- #
# Rank transitions by artist popularity (bigger artist ending = more movement)
transition_importance = []
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        if slot["end"] in snapshots:
            transition_importance.append((slot["end"], slot["popularity"], slot["artist"], cfg["name"]))

# sort by popularity descending, take top 8
transition_importance.sort(key=lambda x: x[1], reverse=True)
plot_steps = [t[0] for t in transition_importance[:8]]
plot_steps.sort()  # chronological order

fig, axes = plt.subplots(2, 4, figsize=(20, 10))
axes = axes.flatten()

# stage positions for annotation
stage_positions = {cfg["name"]: (cfg["x"], cfg["y"]) for cfg in stage_configs}

for idx, step in enumerate(plot_steps):
    if idx >= len(axes):
        break
    ax = axes[idx]
    grid = snapshots[step] * SCALE  # scale to real attendance

    im = ax.imshow(
        grid, cmap="YlOrRd", origin="lower",
        norm=mcolors.PowerNorm(gamma=0.5, vmin=0, vmax=grid.max() or 1),
        aspect="equal"
    )

    # mark stages
    for name, (sx, sy) in stage_positions.items():
        ax.plot(sx, sy, "w*", markersize=12, markeredgecolor="black")
        ax.annotate(name, (sx, sy), color="white", fontsize=6,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.7))

    title = f"Step {step} ({step_to_time(step)})"
    if step in step_labels:
        title += f"\n{step_labels[step][0][:30]}"
    ax.set_title(title, fontsize=9)
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, HEIGHT)

# hide unused axes
for idx in range(len(plot_steps), len(axes)):
    axes[idx].set_visible(False)

fig.suptitle("Festival Congestion Heatmap — Set Transitions", fontsize=14, fontweight="bold")
fig.colorbar(im, ax=axes, label="Estimated People per Cell", shrink=0.6)
plt.tight_layout()
plt.savefig("data/congestion_heatmap.png", dpi=150)
plt.show()
print("Saved congestion_heatmap.png to data/")

# --------------------------------------------------------------------------- #
# BOTTLENECK REPORT — find hottest non-stage cells
# --------------------------------------------------------------------------- #
print("\n" + "="*70)
print("BOTTLENECK REPORT — Highest congestion areas (excluding stages)")
print("="*70)

stage_cells = {(cfg["x"], cfg["y"]) for cfg in stage_configs}

for step in plot_steps:
    grid = snapshots[step]
    # zero out stage cells
    for sx, sy in stage_cells:
        grid[sy][sx] = 0
    # find top 3 hotspots
    top_indices = np.argsort(grid.ravel())[-3:][::-1]
    print(f"\n{step_to_time(step)} (Step {step}):")
    for rank, flat_idx in enumerate(top_indices, 1):
        y, x = divmod(flat_idx, WIDTH)
        count = grid[y][x] * SCALE
        if count > 0:
            print(f"  #{rank}: Cell ({x},{y}) — ~{int(count)} people")
