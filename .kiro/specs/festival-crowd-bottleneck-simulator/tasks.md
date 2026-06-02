# Implementation Plan: Festival Crowd Bottleneck Simulator

## Overview

This plan reorganizes the codebase into a clean folder structure, extracts reusable modules from `app.py`, replaces the hardcoded EDC Orlando path mapping with automatic geometry-based derivation, polishes the bottleneck report tab, and adds a full pytest + Hypothesis property-based test suite covering all 15 correctness properties.

Each task builds directly on the previous one. No task depends on code that hasn't been written yet.

---

## Tasks

- [x] 1. Set up the new folder structure and move files into place
  - Create the directories: `simulation/`, `data_io/`, `config/`, `scripts/`, `archive/`, `data/`, `tests/`
  - Add an empty `__init__.py` to `simulation/`, `data_io/`, `config/`, and `tests/`
  - Copy `model_edc.py` → `simulation/model.py` (keep the original in place for now; it will be removed in task 5)
  - Copy `path_flow.py` → `simulation/path_flow.py`
  - Copy `parse_kml.py` → `data_io/parse_kml.py`
  - Move `model.py`, `run_festival.py`, and `heatmap.py` (the original prototype files) → `archive/`
  - Add `data/` to `.gitignore` so output files are never committed
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 10.7_

- [x] 2. Create `config/defaults.py` — centralized constants
  - [x] 2.1 Write `config/defaults.py` with all threshold and default values
    - Define `DENSITY_NORMAL_MAX = 1.0`, `DENSITY_HIGH_MAX = 2.0` (CRITICAL is anything above HIGH)
    - Define `DEFAULT_PATH_WIDTH_M = 8.0`
    - Define `DEFAULT_PROXIMITY_THRESHOLD_CELLS = 30`
    - Define `CROSSOVER_WINDOW_STEPS = 6` (6 steps × 5 min = 30 minutes)
    - Define arrival curve parameters: `ARRIVAL_START_PCT = 0.03`, `ARRIVAL_RAMP_END_PCT = 0.60`, `ARRIVAL_FULL_PCT = 0.75`
    - Define simulation defaults: `DEFAULT_NUM_AGENTS = 2000`, `DEFAULT_ATTENDANCE = 90000`, `DEFAULT_SURGE_LEAD_MIN = 30`, `DEFAULT_LISTEN_RADIUS = 15`
    - _Requirements: 4.1, 4.2, 6.6, 9.1_

- [x] 3. Create `data_io/path_connections.py` — automatic path-to-stage connection derivation
  - [x] 3.1 Write the `_euclidean` helper and `_stages_near_point` function
    - `_euclidean(p1, p2)` returns the straight-line distance between two `(x, y)` grid points
    - `_stages_near_point(point, grid_stages, threshold)` returns the names of all stages whose grid position is within `threshold` cells of `point`
    - _Requirements: 3.1, 3.2_

  - [x] 3.2 Write `derive_path_connections(grid_paths, grid_stages, proximity_threshold_cells=30)`
    - For each path, collect all stages within `proximity_threshold_cells` of any waypoint
    - Build the `connects` list as all ordered pairs of connected stages (both `(A, B)` and `(B, A)`)
    - If fewer than 2 stages are found for a path, add a warning string and return an empty `connects` list for that path
    - Return a list of path flow config dicts: `[{"name", "length_m", "width_m", "connects", "warnings"}, ...]`
    - Calculate `length_m` from waypoint distances multiplied by `meters_per_cell` (accept as a parameter)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.3 Write property test for path-to-stage connection correctness
    - **Property 6: Path-to-Stage Connection Correctness**
    - **Validates: Requirements 3.1, 3.2**
    - Use `hypothesis` strategies to generate random stage grids and path waypoints
    - Assert that a stage appears in the connection list if and only if it is within `proximity_threshold_cells` of at least one waypoint
    - Assert that both `(A, B)` and `(B, A)` are present for every connected pair
    - Place test in `tests/test_path_connections.py`

- [x] 4. Create `data_io/parse_lineup.py` — extracted from `app.py`
  - [x] 4.1 Move the time utility functions out of `app.py` into `data_io/parse_lineup.py`
    - Copy `parse_time(time_str)` — parses `"9:05pm"` or `"21:05"` → `(hour_24, minute)`
    - Copy `time_to_step(hour, minute, start_hour)` — converts 24h time to simulation step
    - Copy `step_to_time(step, start_hour)` — converts step number to display string like `"9:05 PM"`
    - _Requirements: 2.2_

  - [x] 4.2 Write the `LineupParseResult` dataclass and `parse_lineup` function
    - Define `LineupParseResult` with fields: `stage_configs`, `total_steps`, `warnings`, `errors`, `success`
    - `parse_lineup(df, stage_positions, genre_similarity, start_hour)` validates required columns, converts times to steps, builds `stage_configs` list for `FestivalModel`, and returns a `LineupParseResult`
    - If any required column is missing, set `success=False` and populate `errors`
    - If a stage name in the CSV doesn't match any KML stage, add a warning and skip that stage
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 4.3 Write property test for lineup column validation
    - **Property 4: Lineup Column Validation**
    - **Validates: Requirements 2.1, 2.3**
    - Use `hypothesis` to generate all possible subsets of the 5 required columns
    - Assert `parse_lineup` succeeds if and only if all 5 required columns are present
    - Place test in `tests/test_parse_lineup.py`

  - [x]* 4.4 Write property test for time conversion monotonicity
    - **Property 5: Time Conversion Monotonicity**
    - **Validates: Requirements 2.2**
    - Use `hypothesis` to generate pairs of random valid times where T1 < T2
    - Assert `time_to_step(T1) < time_to_step(T2)`
    - Assert `step_to_time(time_to_step(T))` round-trips to the same clock time within 5-minute rounding
    - Place test in `tests/test_parse_lineup.py`

- [x] 5. Update `app.py` to use the new modules and remove the hardcoded EDC path map
  - [x] 5.1 Replace imports at the top of `app.py`
    - Change `from model_edc import ...` → `from simulation.model import FestivalModel, Attendee, Stage`
    - Change `from parse_kml import ...` → `from data_io.parse_kml import parse_kml, latlon_to_grid`
    - Change `from path_flow import ...` → `from simulation.path_flow import PathFlowModel`
    - Add `from data_io.parse_lineup import parse_lineup, parse_time, time_to_step, step_to_time`
    - Add `from data_io.path_connections import derive_path_connections`
    - Add `from config.defaults import *`
    - _Requirements: 10.5, 10.8_

  - [x] 5.2 Replace the hardcoded `path_stage_map` block with `derive_path_connections`
    - Remove the `path_stage_map` dict (the one that hardcodes `"Kinetic to Circuit Path"`, `"Casa to Stereo"`, etc.)
    - After parsing the KML, call `derive_path_connections(grid_paths, grid_stages, meters_per_cell)` to get `path_flow_configs`
    - Display any warnings from `derive_path_connections` using `st.warning()`
    - Display the detected path-to-stage connections so the user can verify them (Requirement 3.3)
    - _Requirements: 3.3, 3.4, 3.5_

  - [x] 5.3 Replace the inline lineup parsing logic with `parse_lineup`
    - Remove the inline `stage_configs` building loop from `app.py`
    - Call `parse_lineup(df_lineup, stage_pos, genre_similarity, start_hour)` instead
    - Check `result.success`; if False, display `result.errors` and call `st.stop()`
    - Display `result.warnings` as `st.warning()` messages
    - _Requirements: 2.1, 2.3, 2.4, 2.5_

  - [x] 5.4 Checkpoint — verify the app starts without import errors
    - Run `python -c "from simulation.model import FestivalModel; from data_io.parse_kml import parse_kml; from data_io.path_connections import derive_path_connections"` and confirm no errors
    - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Fix broken imports in the four script files
  - [x] 6.1 Update `heatmap_edc.py` imports
    - Change `from model_edc import ...` → `from simulation.model import FestivalModel, Attendee`
    - Change `from parse_kml import ...` → `from data_io.parse_kml import parse_kml, latlon_to_grid`
    - Update the `parse_kml` call signature to match the current 5-return-value signature (it currently expects 3 return values but the function now returns 5)
    - _Requirements: 10.5_

  - [x] 6.2 Update `crowd_animation.py` imports
    - Change `from model_edc import ...` → `from simulation.model import FestivalModel, Attendee`
    - Change `from parse_kml import ...` → `from data_io.parse_kml import parse_kml, latlon_to_grid`
    - _Requirements: 10.5_

  - [x] 6.3 Update `density_report.py` imports
    - Change `from model_edc import ...` → `from simulation.model import FestivalModel, Attendee`
    - Change `from parse_kml import ...` → `from data_io.parse_kml import parse_kml, latlon_to_grid`
    - _Requirements: 10.5_

  - [x] 6.4 Update `debug_agents.py` imports
    - Change `from model_edc import ...` → `from simulation.model import FestivalModel, Attendee`
    - Change `from parse_kml import ...` → `from data_io.parse_kml import parse_kml, latlon_to_grid`
    - _Requirements: 10.5_

- [x] 7. Build the bottleneck report tab in `app.py`
  - [x] 7.1 Write `_classify_density(density)` helper function
    - Returns `"CRITICAL"` if `density >= DENSITY_HIGH_MAX`, `"HIGH"` if `density >= DENSITY_NORMAL_MAX`, else `"Normal"`
    - Import thresholds from `config.defaults`
    - _Requirements: 6.6, 9.1, 9.2_

  - [x] 7.2 Write `build_bottleneck_events(df_crowd, start_hour)` function
    - Scan every `path_<name>_density` column in `df_crowd` for values ≥ `DENSITY_NORMAL_MAX`
    - For each such row, create a `BottleneckEvent` dict: `{path, step, time, density, classification}`
    - Return the list sorted by step, then by density descending
    - _Requirements: 9.1, 9.2_

  - [x] 7.3 Write `detect_crossover_periods(stage_configs, total_steps, start_hour)` function
    - Scan the schedule for all set changes (moments when a new artist starts at any stage)
    - A crossover period is any window of `CROSSOVER_WINDOW_STEPS` steps that contains ≥ 2 set changes
    - Return a list of `CrossoverPeriod` dicts: `{start_step, end_step, start_time, end_time, set_changes}`
    - _Requirements: 9.4_

  - [x] 7.4 Wire the bottleneck tab UI in `app.py`
    - In the `"⚠️ Bottlenecks"` tab, call `build_bottleneck_events` and `detect_crossover_periods`
    - If no events: display `"✅ No paths exceeded the HIGH density threshold during this simulation."`
    - If events exist: display a table with columns: Path, Time, Density (people/m²), Level — with CRITICAL rows highlighted in red and HIGH rows in orange
    - Display a per-path density line chart using Plotly with horizontal dashed lines at `DENSITY_NORMAL_MAX` (1.0) and `DENSITY_HIGH_MAX` (2.0), labeled "HIGH threshold" and "CRITICAL threshold"
    - Highlight crossover periods on the chart as shaded vertical bands with a label showing which set changes overlap
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x]* 7.5 Write property test for bottleneck timeline completeness
    - **Property 14: Bottleneck Timeline Completeness and Correctness**
    - **Validates: Requirements 9.1, 9.2**
    - Use `hypothesis` to generate random density time series (lists of floats 0.0–5.0)
    - Assert the event list contains an entry for step `t` if and only if `density[t] >= 1.0`
    - Assert each event has the correct classification (HIGH vs CRITICAL)
    - Place test in `tests/test_bottleneck_report.py`

  - [x]* 7.6 Write property test for crossover period detection
    - **Property 15: Crossover Period Detection**
    - **Validates: Requirements 9.4**
    - Use `hypothesis` to generate random festival schedules with varying set change patterns
    - Assert a window is flagged as a crossover period if and only if it contains ≥ 2 set changes
    - Assert no windows with fewer than 2 set changes are included
    - Place test in `tests/test_bottleneck_report.py`

- [x] 8. Set up pytest and Hypothesis, then write the KML and path flow property tests
  - [x] 8.1 Install pytest and hypothesis, create `tests/__init__.py` and `pytest.ini`
    - Add `pytest` and `hypothesis` to `requirements.txt` (pin to current stable versions)
    - Create `pytest.ini` at the project root with `[pytest]` section and `testpaths = tests`
    - Create `tests/__init__.py` (empty file so pytest discovers the package)
    - _Requirements: (testing infrastructure)_

  - [x] 8.2 Write property tests for KML point and line placemark round-trip
    - **Property 1: KML Point and Line Placemarks Round-Trip**
    - **Validates: Requirements 1.1, 1.2**
    - Use `hypothesis` to generate synthetic KML strings with N point placemarks and M line placemarks
    - Assert `parse_kml` returns exactly N stages and M paths, each with matching name and coordinates
    - Place test in `tests/test_parse_kml.py`

  - [x] 8.3 Write property test for KML polygon classification by name
    - **Property 2: KML Polygon Classification by Name**
    - **Validates: Requirements 1.3**
    - Generate KML documents with polygons of various names
    - Assert `"EDC OuterBounds"` → `venue_bounds`, `"Entry/Exit"` → `entry_exit`, all others → `obstacles`
    - Place test in `tests/test_parse_kml.py`

  - [x] 8.4 Write property test for grid coordinate bounds and ordering
    - **Property 3: Grid Coordinate Bounds and Ordering**
    - **Validates: Requirements 1.4**
    - Use `hypothesis` to generate pairs of lat/lon points within a valid bounding box
    - Assert all grid x and y values are in `[0, grid_size - 1]`
    - Assert a strictly-north point has a strictly-greater y-grid value; a strictly-east point has a strictly-greater x-grid value
    - Place test in `tests/test_parse_kml.py`

  - [x] 8.5 Write property test for path density invariant
    - **Property 10: Path Density Invariant**
    - **Validates: Requirements 6.1**
    - Use `hypothesis` to generate `PathSegment` instances with random dimensions and random numbers of people
    - After calling `step()`, assert `current_density == len(people_on_path) / (length_m * width_m)`
    - Place test in `tests/test_path_flow.py`

  - [x] 8.6 Write property test for density tier classification and Fruin LoS speed
    - **Property 11: Density Tier Classification**
    - **Validates: Requirements 6.2, 6.6, 11.1**
    - Use `hypothesis` to generate random density float values
    - Assert the speed function and classification match the Fruin LoS table exactly for all six tiers
    - Place test in `tests/test_path_flow.py`

  - [x] 8.7 Write property test for counter-flow effective density non-decrease
    - **Property 12: Counter-Flow Effective Density Non-Decrease**
    - **Validates: Requirements 6.3**
    - Use `hypothesis` to generate `PathSegment` states with people traveling in both directions
    - Assert `effective_density >= current_density` whenever both directions have at least one person
    - Assert `effective_density == current_density` when all travelers move in the same direction
    - Place test in `tests/test_path_flow.py`

  - [x] 8.8 Write property test for width-proportional flow distribution
    - **Property 13: Width-Proportional Flow Distribution**
    - **Validates: Requirements 6.4**
    - Use `hypothesis` to generate sets of parallel paths with random widths and a random total flow `F`
    - Assert each path receives `F × (width_i / sum(widths))` people (within integer rounding)
    - Assert the sum of all assigned flows equals `F`
    - Place test in `tests/test_path_flow.py`

- [x] 9. Write the simulation property tests
  - [x] 9.1 Write property test for arrival schedule ramp invariants
    - **Property 7: Arrival Schedule Ramp Invariants**
    - **Validates: Requirements 5.5**
    - Use `hypothesis` to generate random `total_steps` and `num_attendees` values
    - Assert the target count at step 1 is approximately 3% of `num_attendees`
    - Assert the target count is non-decreasing across all steps
    - Assert the target count reaches 100% of `num_attendees` by the step corresponding to 75% of `total_steps`
    - Place test in `tests/test_simulation.py`

  - [x] 9.2 Write property test for agent spawn location containment
    - **Property 8: Agent Spawn Location Containment**
    - **Validates: Requirements 5.6**
    - Use `hypothesis` to generate a non-empty set of `entry_cells` and a small `FestivalModel`
    - After calling `_spawn_arrivals()`, assert every newly spawned agent's position is in `entry_cells`
    - Place test in `tests/test_simulation.py`

  - [x] 9.3 Write property test for scale factor linearity
    - **Property 9: Scale Factor Linearity**
    - **Validates: Requirements 5.4**
    - Use `hypothesis` to generate random agent crowd counts and scale factors
    - Assert the reported real crowd count equals `round(c * s)` for all stages and all time steps
    - Place test in `tests/test_simulation.py`

- [x] 10. Create `scripts/validate_density.py` — the validation script
  - [x] 10.1 Write `scripts/validate_density.py`
    - Import from `simulation.model`, `data_io.parse_kml`, `data_io.parse_lineup`, `data_io.path_connections`, and `config.defaults`
    - Call `os.makedirs("data", exist_ok=True)` before writing any output files
    - Load `EDC Orlando Map.kml` and `sample_lineup.csv` from the project root
    - Run the full simulation with default parameters (2,000 agents, 90,000 attendance)
    - Print a peak density summary table per path (path name, peak density, time of peak, classification)
    - Assert that at least one HIGH or CRITICAL event occurs during the known Subtronics/Charlotte de Witte crossover window
    - Exit with a non-zero code and a clear message if the assertion fails
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 10.2 Checkpoint — run the full test suite and the validation script
    - Run `pytest tests/ -v` and confirm all tests pass
    - Run `python scripts/validate_density.py` and confirm it prints a density summary and exits cleanly
    - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. The app will work correctly without them; they exist to verify correctness properties.
- Each task references specific requirements for traceability.
- The simulation logic in `model_edc.py` and `path_flow.py` is **not changed** — only moved and re-imported. This preserves all proven behavior.
- The hardcoded `path_stage_map` in `app.py` is the single most important thing to remove. Once `derive_path_connections` is wired in, the app works for any KML venue.
- Property tests use `hypothesis` with `@settings(max_examples=100)` to keep the suite fast while still exploring a wide input space.
- The `data/` directory is gitignored. The `scripts/validate_density.py` script creates it automatically before writing output.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["3.1", "4.1", "8.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "8.2", "8.3", "8.4"] },
    { "id": 3, "tasks": ["3.3", "4.3", "4.4", "5.1", "8.5", "8.6", "8.7", "8.8"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.1", "6.2", "6.3", "6.4"] },
    { "id": 5, "tasks": ["5.4", "7.1", "9.1", "9.2", "9.3"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4"] },
    { "id": 8, "tasks": ["7.5", "7.6", "10.1"] },
    { "id": 9, "tasks": ["10.2"] }
  ]
}
```
