#!/usr/bin/env python3
"""
scripts/validate_density.py — Validation script for path density output.

Runs the full simulation with the sample EDC Orlando data and default parameters,
then prints a peak density summary per path and asserts that at least one HIGH or
CRITICAL density event occurs during the known Subtronics/Charlotte de Witte
crossover window.

Usage:
    python scripts/validate_density.py

Requirements validated: 11.1, 11.2, 11.3
"""
import os
import sys

# Ensure the project root is on sys.path so imports work from any cwd
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
import pandas as pd

from simulation.model import FestivalModel, Attendee
from simulation.path_flow import PathFlowModel
from data_io.parse_kml import parse_kml, latlon_to_grid
from data_io.parse_lineup import parse_lineup, parse_time, time_to_step, step_to_time
from data_io.path_connections import derive_path_connections
from config.defaults import (
    DEFAULT_NUM_AGENTS,
    DEFAULT_ATTENDANCE,
    DEFAULT_SURGE_LEAD_MIN,
    DEFAULT_LISTEN_RADIUS,
    DEFAULT_PROXIMITY_THRESHOLD_CELLS,
    DENSITY_NORMAL_MAX,
    DENSITY_HIGH_MAX,
)


def classify_density(density: float) -> str:
    """Classify a density value using Fruin Level of Service thresholds."""
    if density >= DENSITY_HIGH_MAX:
        return "CRITICAL"
    elif density >= DENSITY_NORMAL_MAX:
        return "HIGH"
    return "Normal"


def main():
    # Create data/ directory for any output files
    os.makedirs(os.path.join(_PROJECT_ROOT, "data"), exist_ok=True)

    # -------------------------------------------------------------------------
    # Load venue map and lineup from project root
    # -------------------------------------------------------------------------
    kml_path = os.path.join(_PROJECT_ROOT, "EDC Orlando Map.kml")
    lineup_path = os.path.join(_PROJECT_ROOT, "sample_lineup.csv")

    if not os.path.exists(kml_path):
        print(f"ERROR: KML file not found: {kml_path}")
        sys.exit(1)
    if not os.path.exists(lineup_path):
        print(f"ERROR: Lineup CSV not found: {lineup_path}")
        sys.exit(1)

    print("=" * 70)
    print("FESTIVAL CROWD BOTTLENECK SIMULATOR — DENSITY VALIDATION")
    print("=" * 70)
    print()

    # Parse KML
    print("Parsing venue KML...")
    stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml(kml_path)
    grid_stages, grid_obstacles, grid_paths, obstacle_mask, meters_per_cell, entry_cells = (
        latlon_to_grid(stages_geo, obstacles_geo, paths_geo, bounds, grid_size=200, entry_exit=entry_exit)
    )
    stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}
    print(f"  Stages: {[s['name'] for s in grid_stages]}")
    print(f"  Paths:  {[p['name'] for p in grid_paths]}")
    print()

    # Parse lineup
    print("Parsing lineup CSV...")
    df_lineup = pd.read_csv(lineup_path)

    # Load genre similarity matrix if available
    genre_similarity = {}
    genre_sim_path = os.path.join(_PROJECT_ROOT, "genre_similarity.csv")
    if os.path.exists(genre_sim_path):
        df_sim = pd.read_csv(genre_sim_path, index_col=0)
        for g1 in df_sim.index:
            for g2 in df_sim.columns:
                genre_similarity[(str(g1).strip(), str(g2).strip())] = float(df_sim.loc[g1, g2])
        print(f"  Loaded genre similarity matrix ({len(df_sim)} genres)")

    # Determine start hour from lineup
    all_times = []
    for _, row in df_lineup.iterrows():
        h, m = parse_time(row["start_time"])
        all_times.append(h * 60 + m)
        h, m = parse_time(row["end_time"])
        all_times.append(h * 60 + m)
    start_hour = min(all_times) // 60

    lineup_result = parse_lineup(df_lineup, stage_pos, genre_similarity, start_hour)
    if not lineup_result.success:
        print(f"ERROR: Lineup parse failed: {lineup_result.errors}")
        sys.exit(1)
    for warn in lineup_result.warnings:
        print(f"  WARNING: {warn}")

    stage_configs = lineup_result.stage_configs
    total_steps = lineup_result.total_steps
    print(f"  Sets loaded: {sum(len(cfg['schedule']) for cfg in stage_configs)}")
    print(f"  Total steps: {total_steps} ({total_steps * 5} minutes)")
    print()

    # -------------------------------------------------------------------------
    # Derive path-to-stage connections
    # -------------------------------------------------------------------------
    print("Deriving path-to-stage connections...")
    derived_configs = derive_path_connections(
        grid_paths, grid_stages, meters_per_cell,
        proximity_threshold_cells=DEFAULT_PROXIMITY_THRESHOLD_CELLS,
    )
    for cfg in derived_configs:
        connects = cfg.get("connects", [])
        for warning_msg in cfg.get("warnings", []):
            print(f"  WARNING: {warning_msg}")
        if connects:
            unique_pairs = [(a, b) for a, b in connects if a < b]
            print(f"  {cfg['name']}: connects {', '.join(f'{a} <-> {b}' for a, b in unique_pairs)}")
        else:
            print(f"  {cfg['name']}: no connections detected")
    print()

    # -------------------------------------------------------------------------
    # Run simulation with default parameters
    # -------------------------------------------------------------------------
    num_agents = DEFAULT_NUM_AGENTS
    attendance = DEFAULT_ATTENDANCE
    scale = attendance / num_agents
    surge_lead_steps = DEFAULT_SURGE_LEAD_MIN // 5  # 30 min / 5 min per step = 6

    print(f"Running simulation: {num_agents} agents, {attendance} attendance, scale={scale:.1f}x")
    print(f"  Surge lead: {DEFAULT_SURGE_LEAD_MIN} min ({surge_lead_steps} steps)")
    print()

    # Combine path cells
    all_path_cells = set()
    path_routes = []
    for p in grid_paths:
        all_path_cells.update(p["cells"])
        path_routes.append({"name": p["name"], "waypoints": p["waypoints"]})

    # Default stage weights and wander rates (matching app.py defaults)
    stage_weights = {
        "Kinetic Field": 1.0,
        "Circuit Grounds": 0.95,
        "Stereo Bloom": 0.5,
        "Neon Garden": 0.5,
        "Casa Bacardi": 0.3,
    }
    stage_wander_rate = {
        "Kinetic Field": 0.01,
        "Circuit Grounds": 0.01,
        "Stereo Bloom": 0.03,
        "Neon Garden": 0.03,
        "Casa Bacardi": 0.05,
    }
    major_stages = ["Kinetic Field", "Circuit Grounds"]

    # Create the model
    model = FestivalModel(
        width=200,
        height=200,
        num_attendees=num_agents,
        stage_configs=stage_configs,
        obstacle_mask=obstacle_mask,
        listen_radius=DEFAULT_LISTEN_RADIUS,
        stage_weights=stage_weights,
        stage_wander_rate=stage_wander_rate,
        path_cells=all_path_cells,
        entry_cells=entry_cells,
        path_routes=path_routes,
        major_stages=major_stages,
        genre_similarity=genre_similarity,
        surge_lead_steps=surge_lead_steps,
    )

    # Build path flow configs from derived connections
    path_flow_configs = []
    derived_lookup = {cfg["name"]: cfg for cfg in derived_configs}
    for p in grid_paths:
        derived = derived_lookup.get(p["name"], {})
        path_flow_configs.append({
            "name": p["name"],
            "length_m": derived.get("length_m", 150.0),
            "width_m": derived.get("width_m", p.get("width_m", 8.0)),
            "connects": derived.get("connects", []),
        })

    path_flow = PathFlowModel(path_flow_configs, scale=scale, step_duration_min=5)

    # Run the simulation loop
    crowd_data = []
    for step in range(1, total_steps + 1):
        model.step()

        row = {"step": step, "time": step_to_time(step, start_hour)}

        # Path density — pipe model
        path_flow.process_flow(model.stage_flow)
        path_results = path_flow.step()

        for p_name, p_result in path_results.items():
            row[f"path_{p_name}_density"] = round(p_result["density"], 3)
            row[f"path_{p_name}_total"] = p_result["total_on_path"]
            row[f"path_{p_name}_speed"] = round(p_result["speed"], 1)

        crowd_data.append(row)

        # Progress indicator every 20 steps
        if step % 20 == 0 or step == total_steps:
            print(f"  Step {step}/{total_steps}...", end="\r")

    print(f"  Simulation complete ({total_steps} steps).          ")
    print()

    df_crowd = pd.DataFrame(crowd_data)

    # -------------------------------------------------------------------------
    # Peak density summary table
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("PEAK DENSITY SUMMARY PER PATH")
    print("=" * 70)
    print(f"{'Path':<30} {'Peak Density':>14} {'Time of Peak':<14} {'Classification'}")
    print("-" * 70)

    path_density_cols = [c for c in df_crowd.columns if c.endswith("_density")]
    peak_events = []

    for col in path_density_cols:
        path_name = col.replace("path_", "").replace("_density", "")
        peak_idx = df_crowd[col].idxmax()
        peak_density = df_crowd[col].iloc[peak_idx]
        peak_time = df_crowd["time"].iloc[peak_idx]
        peak_step = df_crowd["step"].iloc[peak_idx]
        classification = classify_density(peak_density)

        print(f"{path_name:<30} {peak_density:>10.3f} /m²  {peak_time:<14} {classification}")

        peak_events.append({
            "path": path_name,
            "peak_density": peak_density,
            "peak_step": int(peak_step),
            "peak_time": peak_time,
            "classification": classification,
        })

    print("-" * 70)
    print()

    # -------------------------------------------------------------------------
    # Crossover window assertion: Subtronics / Charlotte de Witte
    # -------------------------------------------------------------------------
    # Subtronics at Kinetic Field: 9:05pm - 10:25pm
    # Charlotte de Witte at Circuit Grounds: 9:45pm - 10:45pm
    # The crossover window is the period around when Subtronics ends (10:25pm)
    # and Charlotte de Witte starts (9:45pm). People surge toward Circuit Grounds
    # before CdW starts and leave Kinetic Field when Subtronics ends.
    # We check the broader window from CdW start to shortly after Subtronics ends.

    cdw_start_h, cdw_start_m = parse_time("9:45pm")
    subtronics_end_h, subtronics_end_m = parse_time("10:25pm")

    crossover_start_step = time_to_step(cdw_start_h, cdw_start_m, start_hour)
    crossover_end_step = time_to_step(subtronics_end_h, subtronics_end_m, start_hour) + 2  # +2 steps buffer

    print(f"Checking crossover window: step {crossover_start_step} to {crossover_end_step}")
    print(f"  (Charlotte de Witte starts 9:45pm, Subtronics ends 10:25pm)")
    print()

    # Find HIGH or CRITICAL events in the crossover window
    crossover_events = []
    for col in path_density_cols:
        path_name = col.replace("path_", "").replace("_density", "")
        window_df = df_crowd[
            (df_crowd["step"] >= crossover_start_step) & (df_crowd["step"] <= crossover_end_step)
        ]
        for _, row in window_df.iterrows():
            density = row[col]
            if density >= DENSITY_NORMAL_MAX:
                crossover_events.append({
                    "path": path_name,
                    "step": int(row["step"]),
                    "time": row["time"],
                    "density": density,
                    "classification": classify_density(density),
                })

    if crossover_events:
        print(f"✅ PASS: Found {len(crossover_events)} HIGH/CRITICAL event(s) during crossover window:")
        for evt in sorted(crossover_events, key=lambda e: -e["density"])[:5]:
            print(f"    {evt['path']} at {evt['time']}: {evt['density']:.3f} /m² ({evt['classification']})")
        print()
        print("Density validation PASSED.")
        sys.exit(0)
    else:
        print("❌ FAIL: No HIGH or CRITICAL density events found during the")
        print("   Subtronics/Charlotte de Witte crossover window.")
        print()
        print("   Expected at least one path to reach >= 1.0 people/m² between")
        print(f"   steps {crossover_start_step}-{crossover_end_step} "
              f"({step_to_time(crossover_start_step, start_hour)} - "
              f"{step_to_time(crossover_end_step, start_hour)}).")
        print()
        print("   This may indicate a problem with:")
        print("   - Path-to-stage connection derivation (no paths connect Kinetic/Circuit)")
        print("   - Surge lead timing (agents not moving early enough)")
        print("   - Scale factor (too few agents to generate realistic density)")
        print()
        print("Density validation FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
