"""debug_agents.py — Show where agents are at a specific step."""
from run_edc import stage_configs, GRID_SIZE, NUM_ATTENDEES, STAGE_WEIGHTS, STAGE_WANDER_RATE
from simulation.model import FestivalModel, Attendee
from data_io.parse_kml import parse_kml, latlon_to_grid
import numpy as np

stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml("EDC Orlando Map.kml")
grid_stages, grid_obstacles, grid_paths, obstacle_mask, mpc, entry_cells = latlon_to_grid(stages_geo, obstacles_geo, paths_geo, bounds, grid_size=GRID_SIZE)

model = FestivalModel(
    GRID_SIZE, GRID_SIZE, NUM_ATTENDEES, stage_configs,
    obstacle_mask=obstacle_mask, listen_radius=8,
    stage_weights=STAGE_WEIGHTS, stage_wander_rate=STAGE_WANDER_RATE
)

# run to step 24 (~7 PM)
for i in range(24):
    model.step()

# count agents with no target or stuck
stuck = 0
no_target = 0
by_quadrant = {"NE": 0, "NW": 0, "SE": 0, "SW": 0}
for a in model.agents:
    if isinstance(a, Attendee):
        x, y = a.pos
        if x >= 100 and y >= 100:
            by_quadrant["NE"] += 1
        elif x < 100 and y >= 100:
            by_quadrant["NW"] += 1
        elif x >= 100 and y < 100:
            by_quadrant["SE"] += 1
        else:
            by_quadrant["SW"] += 1
        if a.target_stage is None:
            no_target += 1
        elif not a.arrived and a.target_stage:
            # check if they're far from target
            tx, ty = a.target_stage.x, a.target_stage.y
            dist = np.sqrt((x-tx)**2 + (y-ty)**2)
            if dist > 50:
                stuck += 1

print(f"Total agents: {model.spawned}")
print(f"No target: {no_target}")
print(f"Far from target (>50 cells): {stuck}")
print(f"\nAgents by quadrant:")
for q, c in by_quadrant.items():
    print(f"  {q}: {c}")

# check the problem corner specifically
print(f"\nAgents in problem area (x>150, y<100):")
problem = []
for a in model.agents:
    if isinstance(a, Attendee):
        x, y = a.pos
        if x > 150 and y < 100:
            target = a.target_stage.name if a.target_stage else "None"
            problem.append((x, y, target, a.arrived))

print(f"  Count: {len(problem)}")
if problem:
    from collections import Counter
    targets = Counter(p[2] for p in problem)
    print(f"  Target stages: {dict(targets)}")
    arrived = sum(1 for p in problem if p[3])
    print(f"  Arrived: {arrived}, Still walking: {len(problem) - arrived}")
