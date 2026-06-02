"""
run_festival.py — Real festival simulation based on user's festival data.

Layout (triangle):
         Forbidden Realm (Main Stage) — top
              /          \
            /              \
          /                  \
        /    Crystal Spire     \
      /      (midpoint right)    \
    /                              \
Dragons Lair --------5-7 min------- Mystic Garden

Grid: 100x100 (~10m per cell = 1km x 1km venue)
5-7 min walk between bottom stages ≈ 50-70 cells apart
Time: 3:00 PM - 11:00 PM = 8 hours = 32 steps (each step = 15 min)
Step 1 = 3:00 PM, Step 32 = 11:00 PM
"""
from model import FestivalModel
import matplotlib.pyplot as plt
import pandas as pd

# --------------------------------------------------------------------------- #
# HELPER: convert clock time to step number (3:00 PM = step 1)
# --------------------------------------------------------------------------- #
def time_to_step(hour, minute=0):
    """Convert clock time to step. 3:00 PM = step 1."""
    total_min = (hour - 15) * 60 + minute  # minutes since 3:00 PM
    return max(1, int(total_min / 15) + 1)

# --------------------------------------------------------------------------- #
# VENUE CONFIG
# --------------------------------------------------------------------------- #
WIDTH, HEIGHT = 100, 100
NUM_ATTENDEES = 2000  # scaled down from 35k for performance (ratio preserved)

# --------------------------------------------------------------------------- #
# ARTIST POPULARITY SCORES (0.0 - 1.0)
# Based on billing, headliner status, and EDM scene prominence
#
# Forbidden Realm (Main Stage) — biggest acts, headliners
# Dragons Lair — strong undercard, SVDDEN DEATH is a massive draw
# Mystic Garden — mid-tier with some standouts (Reaper)
# Crystal Spire — smallest stage, up-and-coming acts
# --------------------------------------------------------------------------- #

stage_configs = [
    # FORBIDDEN REALM (Main Stage) — top of triangle
    {
        "name": "Forbidden Realm",
        "x": 50, "y": 90,
        "schedule": [
            {"artist": "Bella Renee",                "popularity": 0.15, "start": time_to_step(15, 0),  "end": time_to_step(15, 55)},
            {"artist": "Dream Takers",               "popularity": 0.20, "start": time_to_step(15, 55), "end": time_to_step(16, 55)},
            {"artist": "Mary Droppinz",              "popularity": 0.35, "start": time_to_step(16, 55), "end": time_to_step(17, 55)},
            {"artist": "Cyclops",                    "popularity": 0.40, "start": time_to_step(17, 55), "end": time_to_step(18, 55)},
            {"artist": "Kompany",                    "popularity": 0.55, "start": time_to_step(18, 55), "end": time_to_step(19, 55)},
            {"artist": "Whethan",                    "popularity": 0.60, "start": time_to_step(19, 55), "end": time_to_step(20, 55)},
            {"artist": "Liquid Stranger B2B Mersiv", "popularity": 0.90, "start": time_to_step(20, 55), "end": time_to_step(21, 55)},
            {"artist": "Zeds Dead",                  "popularity": 1.00, "start": time_to_step(21, 55), "end": time_to_step(23, 0)},
        ],
    },
    # DRAGONS LAIR — bottom left of triangle
    {
        "name": "Dragons Lair",
        "x": 15, "y": 15,
        "schedule": [
            {"artist": "Gardella",                   "popularity": 0.15, "start": time_to_step(15, 0),  "end": time_to_step(15, 45)},
            {"artist": "A Hundred Drums",            "popularity": 0.30, "start": time_to_step(15, 45), "end": time_to_step(16, 30)},
            {"artist": "HVDES",                      "popularity": 0.35, "start": time_to_step(16, 30), "end": time_to_step(17, 15)},
            {"artist": "Automhate B2B Mad Dubz",     "popularity": 0.35, "start": time_to_step(17, 15), "end": time_to_step(18, 0)},
            {"artist": "Phaseone",                   "popularity": 0.50, "start": time_to_step(18, 0),  "end": time_to_step(19, 0)},
            {"artist": "Ghengar",                    "popularity": 0.45, "start": time_to_step(19, 0),  "end": time_to_step(20, 0)},
            {"artist": "Boogie T",                   "popularity": 0.65, "start": time_to_step(20, 0),  "end": time_to_step(21, 0)},
            {"artist": "SVDDEN DEATH",               "popularity": 0.95, "start": time_to_step(21, 0),  "end": time_to_step(22, 0)},
            {"artist": "Virtual Riot",               "popularity": 0.85, "start": time_to_step(22, 0),  "end": time_to_step(23, 0)},
        ],
    },
    # MYSTIC GARDEN — bottom right of triangle
    {
        "name": "Mystic Garden",
        "x": 85, "y": 15,
        "schedule": [
            {"artist": "Crumb Pit",                  "popularity": 0.10, "start": time_to_step(15, 0),  "end": time_to_step(15, 45)},
            {"artist": "Natty Lou",                  "popularity": 0.10, "start": time_to_step(15, 45), "end": time_to_step(16, 30)},
            {"artist": "[IVY]",                      "popularity": 0.15, "start": time_to_step(16, 30), "end": time_to_step(17, 15)},
            {"artist": "PHRVA",                      "popularity": 0.20, "start": time_to_step(17, 15), "end": time_to_step(18, 0)},
            {"artist": "Basstripper",                "popularity": 0.30, "start": time_to_step(18, 0),  "end": time_to_step(19, 0)},
            {"artist": "Ivy Lab",                    "popularity": 0.45, "start": time_to_step(19, 0),  "end": time_to_step(20, 0)},
            {"artist": "Reaper",                     "popularity": 0.60, "start": time_to_step(20, 0),  "end": time_to_step(21, 0)},
            {"artist": "Subsonic",                   "popularity": 0.25, "start": time_to_step(21, 0),  "end": time_to_step(22, 0)},
            {"artist": "Andromedik",                 "popularity": 0.20, "start": time_to_step(22, 0),  "end": time_to_step(23, 0)},
        ],
    },
    # CRYSTAL SPIRE — midpoint between Dragons Lair and Mystic Garden
    {
        "name": "Crystal Spire",
        "x": 68, "y": 55,
        "schedule": [
            {"artist": "Twopercent",                 "popularity": 0.05, "start": time_to_step(15, 0),  "end": time_to_step(16, 0)},
            {"artist": "Xotix",                      "popularity": 0.08, "start": time_to_step(16, 0),  "end": time_to_step(17, 0)},
            {"artist": "Kade Findley",               "popularity": 0.05, "start": time_to_step(17, 0),  "end": time_to_step(18, 0)},
            {"artist": "Abelation",                  "popularity": 0.08, "start": time_to_step(18, 0),  "end": time_to_step(19, 0)},
            {"artist": "Papajay",                    "popularity": 0.06, "start": time_to_step(19, 0),  "end": time_to_step(20, 0)},
            {"artist": "Austeria",                   "popularity": 0.06, "start": time_to_step(20, 0),  "end": time_to_step(21, 0)},
            {"artist": "SFAM",                       "popularity": 0.25, "start": time_to_step(21, 0),  "end": time_to_step(22, 0)},
        ],
    },
]

SCALE = 35000 / NUM_ATTENDEES

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("Running festival simulation (35k attendees scaled to 2,000 agents)...")
    print("Each step = 15 minutes | 3:00 PM to 11:00 PM\n")

    model = FestivalModel(WIDTH, HEIGHT, NUM_ATTENDEES, stage_configs, listen_radius=4)

    TOTAL_STEPS = 32
    for i in range(TOTAL_STEPS):
        model.step()
        if (i + 1) % 8 == 0:
            hour = 15 + (i * 15) // 60
            minute = (i * 15) % 60
            print(f"  Step {i+1:2d} ({hour}:{minute:02d} PM) complete...")

    # ------------------------------------------------------------------- #
    # RESULTS
    # ------------------------------------------------------------------- #
    df = model.datacollector.get_model_vars_dataframe()
    df.index.name = "Step"

    df["Time"] = [f"{15 + (i*15)//60}:{(i*15)%60:02d}" for i in range(len(df))]

    df_scaled = df.copy()
    for col in ["Forbidden Realm", "Dragons Lair", "Mystic Garden", "Crystal Spire"]:
        df_scaled[f"{col}_est"] = (df[col] * SCALE).astype(int)

    print("\n" + "="*90)
    print("CROWD ESTIMATES BY STAGE (scaled to ~35,000 attendees)")
    print("="*90)
    print(df_scaled[["Time", "Forbidden Realm_est", "Dragons Lair_est", "Mystic Garden_est", "Crystal Spire_est"]].to_string())

    df_scaled.to_csv("data/festival_crowd_density.csv")
    print("\nSaved festival_crowd_density.csv to data/")

    # ------------------------------------------------------------------- #
    # PLOT
    # ------------------------------------------------------------------- #
    fig, ax = plt.subplots(figsize=(16, 8))
    stage_names = ["Forbidden Realm", "Dragons Lair", "Mystic Garden", "Crystal Spire"]
    colors = ["#FF4444", "#44AAFF", "#44DD44", "#FFAA00"]

    for name, color in zip(stage_names, colors):
        ax.plot(df.index + 1, df[name] * SCALE, label=name, linewidth=2.5, color=color)

    tick_positions = list(range(0, 33, 4))
    tick_labels = [f"{15 + (i*15)//60}:{(i*15)%60:02d}" for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45)

    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Estimated Crowd Size", fontsize=12)
    ax.set_title("Festival Crowd Distribution — Real Lineup Simulation", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("data/festival_crowd_plot.png", dpi=150)
    plt.show()
    print("Saved festival_crowd_plot.png to data/")
