"""
run_edc.py — EDC Orlando 2025 Day 3 (Sunday) Simulation

5 stages, real lineup, KML-based venue map with obstacles.
Time: 1:00 PM - 12:00 AM = 11 hours = 44 steps (each step = 15 min)
"""
from model_edc import FestivalModel
from parse_kml import parse_kml, latlon_to_grid
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# --------------------------------------------------------------------------- #
# PARSE VENUE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, meters_per_cell, entry_cells = latlon_to_grid(
    stages_geo, obstacles_geo, paths_geo, bounds, grid_size=200, entry_exit=entry_exit
)

GRID_SIZE = 200
NUM_ATTENDEES = 3000  # scaled down from ~90k
SCALE = 90000 / NUM_ATTENDEES

# build stage name → grid position lookup
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# combine all path cells into one set
all_path_cells = set()
path_routes = []
for p in grid_paths:
    all_path_cells.update(p["cells"])
    path_routes.append({"name": p["name"], "waypoints": p["waypoints"]})

# --------------------------------------------------------------------------- #
# HELPER: convert clock time to step number (1:00 PM = step 1)
# --------------------------------------------------------------------------- #
def time_to_step(hour, minute=0):
    """Convert 24h clock time to step. 13:00 (1 PM) = step 1."""
    total_min = (hour - 13) * 60 + minute
    return max(1, int(total_min / 15) + 1)

# --------------------------------------------------------------------------- #
# ARTIST POPULARITY SCORES
# Based on billing position, EDM scene prominence, streaming numbers
#
# 0.90-1.00 = Headliner (Dom Dolla, Charlotte de Witte, Subtronics)
# 0.70-0.89 = Co-headliner / major draw
# 0.50-0.69 = Strong mid-card
# 0.30-0.49 = Support with a following
# 0.10-0.29 = Undercard / opener
# 0.01-0.09 = Small stage opener
# --------------------------------------------------------------------------- #

# Stage draw weights — represents stage size/reputation independent of artist
# Based on: Kinetic 35%, Circuit 30%, Neon 15%, Stereo 15%, Casa 5%
STAGE_WEIGHTS = {
    "Kinetic Field": 1.0,
    "Circuit Grounds": 0.95,   # basically a second main stage
    "Neon Garden": 0.50,
    "Stereo Bloom": 0.50,
    "Casa Bacardi": 0.08,
}

# How likely someone is to leave their current stage each step
# Low = campers, High = wanderers
STAGE_WANDER_RATE = {
    "Kinetic Field": 0.02,     # campers
    "Circuit Grounds": 0.02,   # campers — second main stage, shoulder to shoulder
    "Neon Garden": 0.10,       # techno crowd explores
    "Stereo Bloom": 0.10,      # bass crowd wanders
    "Casa Bacardi": 0.15,      # small stage, come and go
}

stage_configs = [
    # KINETIC FIELD — main stage
    {
        "name": "Kinetic Field",
        "x": stage_pos["Kinetic Field"][0],
        "y": stage_pos["Kinetic Field"][1],
        "schedule": [
            {"artist": "Ina Nia",                    "popularity": 0.08, "start": time_to_step(13, 0),  "end": time_to_step(13, 30)},
            {"artist": "Baggi",                      "popularity": 0.12, "start": time_to_step(13, 30), "end": time_to_step(14, 25)},
            {"artist": "No Thanks",                  "popularity": 0.15, "start": time_to_step(14, 25), "end": time_to_step(15, 25)},
            {"artist": "Korolova",                   "popularity": 0.30, "start": time_to_step(15, 25), "end": time_to_step(16, 25)},
            {"artist": "Funk Tribu",                 "popularity": 0.25, "start": time_to_step(16, 25), "end": time_to_step(17, 25)},
            {"artist": "Green Velvet B2B Alok",      "popularity": 0.75, "start": time_to_step(17, 25), "end": time_to_step(18, 45), "genre": "tech_house"},
            {"artist": "James Hype",                 "popularity": 0.80, "start": time_to_step(18, 45), "end": time_to_step(19, 55), "genre": "house"},
            {"artist": "Sofi Tukker",                "popularity": 0.85, "start": time_to_step(19, 55), "end": time_to_step(21, 5), "genre": "indie_dance", "genre_clash": 0.25},
            {"artist": "Subtronics",                 "popularity": 0.95, "start": time_to_step(21, 5),  "end": time_to_step(22, 25), "genre": "dubstep", "genre_clash": 0.50},
            {"artist": "Dom Dolla",                  "popularity": 1.00, "start": time_to_step(22, 25), "end": time_to_step(23, 50), "genre": "house", "genre_clash": 0.40},
        ],
    },
    # CIRCUIT GROUNDS
    {
        "name": "Circuit Grounds",
        "x": stage_pos["Circuit Grounds"][0],
        "y": stage_pos["Circuit Grounds"][1],
        "schedule": [
            {"artist": "Discovery Project",          "popularity": 0.08, "start": time_to_step(13, 0),  "end": time_to_step(14, 15)},
            {"artist": "Hills",                      "popularity": 0.12, "start": time_to_step(14, 15), "end": time_to_step(15, 25)},
            {"artist": "Wuki",                       "popularity": 0.30, "start": time_to_step(15, 25), "end": time_to_step(16, 25)},
            {"artist": "Laszewo",                    "popularity": 0.15, "start": time_to_step(16, 25), "end": time_to_step(17, 25)},
            {"artist": "Seven Lions",                "popularity": 0.88, "start": time_to_step(17, 25), "end": time_to_step(18, 40), "genre": "melodic_bass"},
            {"artist": "Max Styler",                 "popularity": 0.35, "start": time_to_step(18, 40), "end": time_to_step(19, 45), "genre": "bass_house", "genre_clash": 0.30},
            {"artist": "The Outlaw",                 "popularity": 0.30, "start": time_to_step(19, 45), "end": time_to_step(20, 45), "genre": "house"},
            {"artist": "Chase & Status",             "popularity": 0.78, "start": time_to_step(20, 45), "end": time_to_step(21, 45), "genre": "dnb", "genre_clash": 0.35},
            {"artist": "Charlotte de Witte",         "popularity": 0.95, "start": time_to_step(21, 45), "end": time_to_step(22, 45), "genre": "techno", "genre_clash": 0.40},
            {"artist": "Knock2",                     "popularity": 0.90, "start": time_to_step(22, 45), "end": time_to_step(23, 55), "genre": "bass_house", "genre_clash": 0.30},
        ],
    },
    # NEON GARDEN
    {
        "name": "Neon Garden",
        "x": stage_pos["Neon Garden"][0],
        "y": stage_pos["Neon Garden"][1],
        "schedule": [
            {"artist": "Dr. Greco",                  "popularity": 0.10, "start": time_to_step(13, 0),  "end": time_to_step(15, 0)},
            {"artist": "Noise Mafia",                "popularity": 0.15, "start": time_to_step(15, 0),  "end": time_to_step(16, 30)},
            {"artist": "OTTA",                       "popularity": 0.20, "start": time_to_step(16, 30), "end": time_to_step(18, 0)},
            {"artist": "999999999",                  "popularity": 0.55, "start": time_to_step(18, 0),  "end": time_to_step(19, 30)},
            {"artist": "Indira Paganotto",           "popularity": 0.60, "start": time_to_step(19, 30), "end": time_to_step(21, 0)},
            {"artist": "Deborah De Luca",            "popularity": 0.65, "start": time_to_step(21, 0),  "end": time_to_step(22, 30)},
            {"artist": "Nico Moreno",                "popularity": 0.55, "start": time_to_step(22, 30), "end": time_to_step(24, 0)},
        ],
    },
    # STEREO BLOOM
    {
        "name": "Stereo Bloom",
        "x": stage_pos["Stereo Bloom"][0],
        "y": stage_pos["Stereo Bloom"][1],
        "schedule": [
            {"artist": "Bad Girl Bailey",            "popularity": 0.08, "start": time_to_step(13, 0),  "end": time_to_step(14, 0)},
            {"artist": "Flozone",                    "popularity": 0.10, "start": time_to_step(14, 0),  "end": time_to_step(15, 0)},
            {"artist": "Eater",                      "popularity": 0.15, "start": time_to_step(15, 0),  "end": time_to_step(16, 15)},
            {"artist": "MPH",                        "popularity": 0.30, "start": time_to_step(16, 15), "end": time_to_step(17, 30)},
            {"artist": "Caspa",                      "popularity": 0.45, "start": time_to_step(17, 30), "end": time_to_step(18, 45), "genre": "dubstep"},
            {"artist": "YDG",                        "popularity": 0.35, "start": time_to_step(18, 45), "end": time_to_step(20, 0), "genre": "riddim", "genre_clash": 0.40},
            {"artist": "ALLEYCVT",                   "popularity": 0.45, "start": time_to_step(20, 0),  "end": time_to_step(21, 15), "genre": "bass_house", "genre_clash": 0.35},
            {"artist": "Wilkinson",                  "popularity": 0.60, "start": time_to_step(21, 15), "end": time_to_step(22, 45)},
            {"artist": "Subtronics B2B LevelUp",     "popularity": 0.88, "start": time_to_step(22, 45), "end": time_to_step(24, 0)},
        ],
    },
    # CASA BACARDI — smallest stage
    {
        "name": "Casa Bacardi",
        "x": stage_pos["Casa Bacardi"][0],
        "y": stage_pos["Casa Bacardi"][1],
        "schedule": [
            {"artist": "Jesse James",                "popularity": 0.05, "start": time_to_step(13, 0),  "end": time_to_step(15, 0)},
            {"artist": "Leisan",                     "popularity": 0.05, "start": time_to_step(15, 0),  "end": time_to_step(17, 0)},
            {"artist": "Slugg",                      "popularity": 0.08, "start": time_to_step(17, 0),  "end": time_to_step(18, 30)},
            {"artist": "Ky William",                 "popularity": 0.10, "start": time_to_step(18, 30), "end": time_to_step(20, 0)},
            {"artist": "Coco & Breezy",              "popularity": 0.15, "start": time_to_step(20, 0),  "end": time_to_step(21, 30)},
            {"artist": "BOLO",                       "popularity": 0.12, "start": time_to_step(21, 30), "end": time_to_step(23, 0)},
        ],
    },
]

# --------------------------------------------------------------------------- #
# RUN SIMULATION
# --------------------------------------------------------------------------- #
TOTAL_STEPS = 44  # 1 PM to 12 AM

if __name__ == "__main__":
    print("EDC Orlando 2025 — Day 3 (Sunday)")
    print(f"Grid: {GRID_SIZE}x{GRID_SIZE} (~{meters_per_cell:.1f}m per cell)")
    print(f"Agents: {NUM_ATTENDEES} (scaled to {int(NUM_ATTENDEES * SCALE):,} real attendees)")
    print(f"Steps: {TOTAL_STEPS} (each = 15 min)\n")

    model = FestivalModel(
        GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
        obstacle_mask=obstacle_mask, listen_radius=15,
        stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
        path_cells=all_path_cells, entry_cells=entry_cells,
        path_routes=path_routes
    )

    for i in range(TOTAL_STEPS):
        model.step()
        if (i + 1) % 8 == 0:
            hour = 13 + (i * 15) // 60
            minute = (i * 15) % 60
            print(f"  Step {i+1:2d} ({hour}:{minute:02d}) complete...")

    # ------------------------------------------------------------------- #
    # RESULTS
    # ------------------------------------------------------------------- #
    df = model.datacollector.get_model_vars_dataframe()
    df.index.name = "Step"

    stage_names = [cfg["name"] for cfg in stage_configs]

    df["Time"] = [f"{13 + (i*15)//60}:{(i*15)%60:02d}" for i in range(len(df))]

    df_scaled = df.copy()
    for col in stage_names:
        df_scaled[f"{col}_est"] = (df[col] * SCALE).astype(int)

    est_cols = ["Time"] + [f"{n}_est" for n in stage_names]
    print("\n" + "=" * 110)
    print("CROWD ESTIMATES BY STAGE (scaled to ~90,000 attendees)")
    print("=" * 110)
    print(df_scaled[est_cols].to_string())

    df_scaled.to_csv("data/edc_crowd_density.csv")
    print("\nSaved edc_crowd_density.csv to data/")

    # ------------------------------------------------------------------- #
    # PLOT
    # ------------------------------------------------------------------- #
    fig, ax = plt.subplots(figsize=(18, 8))
    colors = ["#FF4444", "#44AAFF", "#AA44FF", "#44DD44", "#FFAA00"]

    for name, color in zip(stage_names, colors):
        ax.plot(df.index + 1, df[name] * SCALE, label=name, linewidth=2.5, color=color)

    tick_positions = list(range(0, TOTAL_STEPS + 1, 4))
    tick_labels = [f"{13 + (i*15)//60}:{(i*15)%60:02d}" for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45)

    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Estimated Crowd Size", fontsize=12)
    ax.set_title("EDC Orlando 2025 Day 3 — Crowd Distribution", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("data/edc_crowd_plot.png", dpi=150)
    plt.show()
    print("Saved edc_crowd_plot.png to data/")
