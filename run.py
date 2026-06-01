"""
run.py — Configure and run a sample festival simulation.

Each time step = ~15 minutes of real time.
A 10-hour festival day = 40 steps.
"""
from model import FestivalModel
import matplotlib.pyplot as plt
import pandas as pd

# --------------------------------------------------------------------------- #
# SAMPLE FESTIVAL CONFIGURATION
# --------------------------------------------------------------------------- #
# Grid: 50x50 (think of each cell as ~10 meters → 500m x 500m venue)
WIDTH, HEIGHT = 50, 50
NUM_ATTENDEES = 500

# 3 stages with staggered artist schedules
# popularity: 0.0 (unknown opener) → 1.0 (headliner)
stage_configs = [
    {
        "name": "Main Stage",
        "x": 25, "y": 45,
        "schedule": [
            {"artist": "Opener A",      "popularity": 0.3, "start": 1,  "end": 10},
            {"artist": "Mid-Tier Band",  "popularity": 0.6, "start": 12, "end": 22},
            {"artist": "Headliner",      "popularity": 1.0, "start": 25, "end": 40},
        ],
    },
    {
        "name": "Second Stage",
        "x": 10, "y": 20,
        "schedule": [
            {"artist": "DJ Warm-Up",     "popularity": 0.4, "start": 1,  "end": 12},
            {"artist": "Fan Favorite",   "popularity": 0.8, "start": 14, "end": 26},
            {"artist": "Closer B",       "popularity": 0.5, "start": 28, "end": 40},
        ],
    },
    {
        "name": "Indie Tent",
        "x": 40, "y": 10,
        "schedule": [
            {"artist": "Local Act 1",    "popularity": 0.2, "start": 1,  "end": 15},
            {"artist": "Buzz Artist",    "popularity": 0.7, "start": 17, "end": 30},
            {"artist": "Local Act 2",    "popularity": 0.2, "start": 32, "end": 40},
        ],
    },
]

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
print("Running festival simulation...")
model = FestivalModel(WIDTH, HEIGHT, NUM_ATTENDEES, stage_configs, listen_radius=4)

TOTAL_STEPS = 40
for _ in range(TOTAL_STEPS):
    model.step()

# --------------------------------------------------------------------------- #
# RESULTS
# --------------------------------------------------------------------------- #
df = model.datacollector.get_model_vars_dataframe()
df.index.name = "Step"
print("\nCrowd counts per stage over time:")
print(df.to_string())

# save to CSV
df.to_csv("data/crowd_density.csv")
print("\nSaved crowd_density.csv to data/")

# plot
fig, ax = plt.subplots(figsize=(12, 6))
for col in df.columns:
    ax.plot(df.index, df[col], label=col, linewidth=2)

ax.set_xlabel("Time Step (each = ~15 min)")
ax.set_ylabel("Crowd Count at Stage")
ax.set_title("Festival Crowd Distribution Over Time")
ax.legend()
ax.grid(True, alpha=0.3)

# annotate artist names at midpoints
for cfg in stage_configs:
    for slot in cfg["schedule"]:
        mid = (slot["start"] + slot["end"]) / 2
        ax.annotate(
            slot["artist"],
            xy=(mid, df[cfg["name"]].iloc[int(mid) - 1] if int(mid) - 1 < len(df) else 0),
            fontsize=7, alpha=0.7, ha="center",
        )

plt.tight_layout()
plt.savefig("data/crowd_density_plot.png", dpi=150)
plt.show()
print("Saved crowd_density_plot.png to data/")
