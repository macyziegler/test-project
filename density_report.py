"""
density_report.py — Detailed density output for every area at every time step.
Saves to CSV for easy analysis in Excel.
"""
from run_edc import stage_configs, time_to_step, GRID_SIZE, NUM_ATTENDEES, SCALE, STAGE_WEIGHTS, STAGE_WANDER_RATE, all_path_cells
from simulation.model import FestivalModel, Attendee
from data_io.parse_kml import parse_kml, latlon_to_grid
import pandas as pd
import numpy as np

# --------------------------------------------------------------------------- #
# PARSE MAP
# --------------------------------------------------------------------------- #
stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc, entry_cells = latlon_to_grid(
    stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE
)
stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

# --------------------------------------------------------------------------- #
# DEFINE ZONES — stages, paths, and areas between stages
# --------------------------------------------------------------------------- #
zones = {}

# stage zones (20-cell radius around each stage)
for s in grid_stages:
    cells = set()
    for dx in range(-20, 21):
        for dy in range(-20, 21):
            nx, ny = s["x"] + dx, s["y"] + dy
            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                if np.sqrt(dx**2 + dy**2) <= 20:
                    cells.add((nx, ny))
    zones[f"Stage: {s['name']}"] = cells

# path zones
for p in grid_paths:
    zones[f"Path: {p['name']}"] = p["cells"]

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
# RUN SIMULATION
# --------------------------------------------------------------------------- #
print("Running simulation for density report...")
model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=15,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE,
    path_cells=all_path_cells
)

rows = []

for step in range(1, 45):
    model.step()

    # count agents per zone
    agent_positions = {}
    for a in model.agents:
        if isinstance(a, Attendee):
            pos = (a.pos[0], a.pos[1])
            if pos not in agent_positions:
                agent_positions[pos] = 0
            agent_positions[pos] += 1

    time_str = step_to_time(step)
    playing = now_playing.get(step, {})

    row = {
        "Step": step,
        "Time": time_str,
        "Total_Agents": model.spawned,
        "Total_Attendance_Est": int(model.spawned * SCALE),
    }

    # count per zone
    for zone_name, zone_cells in zones.items():
        count = 0
        for cell in zone_cells:
            count += agent_positions.get(cell, 0)
        est = int(count * SCALE)
        row[f"{zone_name}_agents"] = count
        row[f"{zone_name}_est"] = est

        # for paths, calculate density per meter
        if zone_name.startswith("Path:"):
            path_length_cells = len(zone_cells)
            path_length_m = path_length_cells * mpc
            density_per_m = est / max(path_length_m, 1)
            row[f"{zone_name}_density_per_meter"] = round(density_per_m, 1)

    # add now playing info
    for stage_name in ["Kinetic Field", "Circuit Grounds", "Neon Garden", "Stereo Bloom", "Casa Bacardi"]:
        row[f"Playing: {stage_name}"] = playing.get(stage_name, "—")

    # crowd in transit
    moving = sum(1 for a in model.agents if isinstance(a, Attendee) and not a.arrived)
    row["In_Transit_agents"] = moving
    row["In_Transit_est"] = int(moving * SCALE)
    row["In_Transit_pct"] = round(moving / max(model.spawned, 1) * 100, 1)

    rows.append(row)

    if step % 10 == 0:
        print(f"  Step {step}/44 complete...")

# --------------------------------------------------------------------------- #
# SAVE TO CSV
# --------------------------------------------------------------------------- #
df = pd.DataFrame(rows)
df.to_csv("data/edc_density_report.csv", index=False)
print("\nSaved edc_density_report.csv to data/")

# --------------------------------------------------------------------------- #
# PRINT SUMMARY
# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("DENSITY SUMMARY BY ZONE")
print("=" * 100)

# stage summary
print("\nSTAGE CROWDS (estimated):")
print(f"{'Time':<10}", end="")
for s in grid_stages:
    print(f"  {s['name']:<18}", end="")
print(f"  {'In Transit':<12}")
print("-" * 110)

for _, row in df.iterrows():
    print(f"{row['Time']:<10}", end="")
    for s in grid_stages:
        col_name = f"Stage: {s['name']}_est"
        print(f"  {row[col_name]:>14,}", end="")
    print(f"  {row['In_Transit_pct']:>8.1f}%")

# path summary
print("\n\nPATH CONGESTION (people per meter):")
path_cols = [c for c in df.columns if "density_per_meter" in c]
if path_cols:
    print(f"{'Time':<10}", end="")
    for col in path_cols:
        name = col.replace("Path: ", "").replace("_density_per_meter", "")
        print(f"  {name:<28}", end="")
    print()
    print("-" * 100)
    for _, row in df.iterrows():
        print(f"{row['Time']:<10}", end="")
        for col in path_cols:
            val = row[col]
            flag = " ***" if val > 2.0 else " *" if val > 1.0 else ""
            print(f"  {val:>8.1f}{flag:<20}", end="")
        print()

print("\n*** = Critical density (>2 people/meter)")
print("*   = High density (>1 person/meter)")
print(f"\nFull data saved to data/edc_density_report.csv")
