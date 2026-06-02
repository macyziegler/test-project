# Requirements Document

## Introduction

The Festival Crowd Bottleneck Simulator is a web-based tool built for Vantage Methods, a festival consulting business. It helps festival organizers understand where and when crowds will pile up on shared walkways — especially during the minutes when one set ends and another begins at a different stage, causing large waves of people to move at the same time.

The tool takes a venue map (KML file) and a stage schedule (CSV file) as inputs, runs an agent-based simulation of crowd movement, and produces an animated heatmap showing crowd density and bottleneck risk across the festival day. The goal is to give organizers a clear, visual answer to the question: "Where will people collide on the pathways, and when?"

The codebase already has a working simulation engine (`model_edc.py`), a KML parser (`parse_kml.py`), a path congestion model (`path_flow.py`), and a Streamlit app (`app.py`). This spec covers the work needed to fix broken imports, reorganize the project into a clean folder structure, make the app work for any festival (not just EDC Orlando), and polish the bottleneck reporting tab.

---

## Glossary

- **Simulator**: The full Python/Streamlit application described in this document.
- **KML File**: A map file format (used by Google Maps/Earth) that describes the venue — stage locations, walkable paths, obstacles, and the venue boundary.
- **Lineup CSV**: A spreadsheet file listing every artist performing, which stage they're on, their start and end times, their popularity score (0.0–1.0), and optionally their music genre.
- **Agent**: A simulated festival-goer. The simulation runs with a reduced number of agents (e.g., 2,000) and scales the results up to match the real expected attendance.
- **Stage**: A performance area within the venue. Stages are defined as point markers in the KML file.
- **Path / Walkway**: A corridor connecting two areas of the venue. Paths are defined as lines in the KML file.
- **Path Density**: How crowded a walkway is, measured in people per square meter (people/m²). Calculated from the number of people flowing through a path divided by its physical dimensions.
- **Bottleneck**: A moment when a path's density crosses a threshold that indicates uncomfortable or dangerous crowding.
- **Level of Service (LoS)**: A crowd safety standard (Fruin's LoS) that defines density thresholds: Normal (< 1.0 people/m²), HIGH (1.0–2.0 people/m²), and CRITICAL (> 2.0 people/m²).
- **Set Change**: The moment when one artist's performance ends and the next begins. This is the primary trigger for large crowd movements.
- **Crossover Period**: The window of time around a set change when crowds from multiple stages are moving simultaneously, creating the highest bottleneck risk.
- **Genre Clash**: When two consecutive artists at the same stage play very different music genres, causing a higher percentage of the existing crowd to leave and seek a different stage.
- **Surge**: The wave of people who start moving toward a stage before a highly anticipated set begins.
- **Popularity Score**: A number from 0.0 to 1.0 representing how much draw an artist has. A headliner is 1.0; an early-day opener might be 0.05.
- **Stage Weight**: A number from 0.0 to 1.0 representing how much a stage draws people independent of who is performing (based on size, production quality, location, etc.).
- **Scale Factor**: The ratio of real attendance to simulation agents. If 90,000 people attend and 2,000 agents are simulated, the scale factor is 45 — every agent represents 45 real people.
- **Obstacle**: A physical feature in the venue (water, barriers, vendor areas) that blocks crowd movement. Defined as polygons in the KML file.
- **Entry/Exit Zone**: The area where attendees enter the venue. Defined as a polygon in the KML file. Agents spawn here at the start of the simulation.
- **Grid**: The internal 200×200 cell representation of the venue used by the simulation engine.
- **Heatmap**: A color-coded map overlay showing crowd density — green for low density, yellow/orange for moderate, red for high, dark red for critical.
- **Genre Similarity Matrix**: An optional CSV file where each cell represents how similar two music genres are (0.0 = completely different, 1.0 = identical). Controls how much crowd turnover happens when genres change between sets.

---

## Requirements

### Requirement 1: Load and Parse the Venue Map

**User Story:** As a festival consultant, I want to upload a KML venue map so that the simulator knows where stages, walkways, obstacles, and entry points are located.

#### Acceptance Criteria

1. WHEN a user uploads a KML file, THE Simulator SHALL parse all point placemarks as stage locations and extract their names and latitude/longitude coordinates.
2. WHEN a user uploads a KML file, THE Simulator SHALL parse all line placemarks as walkable paths and extract their names and coordinate sequences.
3. WHEN a user uploads a KML file, THE Simulator SHALL parse all polygon placemarks as either the venue boundary, the entry/exit zone, or obstacles, based on the placemark name.
4. WHEN a KML file is parsed, THE Simulator SHALL convert all latitude/longitude coordinates to positions on a 200×200 internal grid that preserves real-world distances and proportions.
5. IF a KML file cannot be parsed (e.g., malformed XML, missing venue boundary polygon), THEN THE Simulator SHALL display a clear error message explaining what went wrong and stop all further processing.
6. IF coordinate conversion fails after the KML structure itself parses successfully, THEN THE Simulator SHALL treat the failure as a parse error, display a clear error message, and stop all further processing.
7. IF any other processing step fails after a successful parse, THEN THE Simulator SHALL display a clear error message and stop all further processing.
8. WHEN a KML file is successfully parsed, THE Simulator SHALL display a summary listing all stages found, all obstacles found, and all paths found.

---

### Requirement 2: Load and Parse the Stage Lineup

**User Story:** As a festival consultant, I want to upload a lineup CSV so that the simulator knows which artists are performing, when, and how popular they are.

#### Acceptance Criteria

1. WHEN a user uploads a lineup CSV, THE Simulator SHALL accept files with the columns: `stage`, `artist`, `start_time`, `end_time`, `popularity`, and optionally `genre`.
2. WHEN a lineup CSV is parsed, THE Simulator SHALL convert all time values (supporting both 12-hour formats like `9:05pm` and 24-hour formats like `21:05`) to internal simulation time steps, where each step represents 5 minutes.
3. IF a lineup CSV is missing any required column (`stage`, `artist`, `start_time`, `end_time`, `popularity`), THEN THE Simulator SHALL display an error message listing the missing columns and stop processing.
4. IF a stage name in the lineup CSV does not match any stage name found in the KML file, THEN THE Simulator SHALL display a warning for that stage and skip it rather than crashing. THE Simulator SHALL only skip stages due to name mismatches, not for other data issues within a matching stage entry.
5. WHEN a lineup CSV is successfully parsed, THE Simulator SHALL display a confirmation showing the number of sets loaded and the number of unique stages.

---

### Requirement 3: Derive Path-to-Stage Connections from the KML Map

**User Story:** As a festival consultant, I want the simulator to automatically figure out which paths connect which stages so that I don't have to manually configure this for every new venue.

#### Acceptance Criteria

1. WHEN a KML file is parsed, THE Simulator SHALL automatically determine which stages each path connects by finding the two stages whose grid positions are closest to the path's start and end waypoints.
2. THE Simulator SHALL support paths that connect more than two stages by identifying all stages within a configurable proximity threshold of any point along the path.
3. WHEN path-to-stage connections are derived, THE Simulator SHALL display the detected connections so the user can verify them before running the simulation.
4. IF no path connections can be derived for a path — whether due to venue layout (no stages near either end) or a technical failure such as invalid coordinates — THEN THE Simulator SHALL display a warning for that path and exclude it from the path density calculation.
5. THE Simulator SHALL NOT require any hardcoded venue-specific path-to-stage mappings in the application code.

---

### Requirement 4: Configure Simulation Parameters

**User Story:** As a festival consultant, I want to adjust simulation settings so that I can tune the model to match the specific characteristics of each festival.

#### Acceptance Criteria

1. THE Simulator SHALL allow the user to set the total expected attendance as a whole number between 1,000 and 500,000.
2. THE Simulator SHALL allow the user to set the number of simulation agents as a whole number between 500 and 5,000, with a default of 2,000. THE Simulator SHALL enforce that the number of agents cannot exceed the total attendance value.
3. WHILE the simulation has not yet been run, THE Simulator SHALL display a status indicator showing that the simulation is ready to run.
4. THE Simulator SHALL allow the user to assign a stage weight (0.0 to 1.0) to each stage found in the KML file, representing how much that stage draws people independent of the performing artist.
5. THE Simulator SHALL allow the user to assign a wander rate (0.5% to 10% per 5-minute step) to each stage, representing how likely an attendee is to spontaneously reconsider their stage choice.
6. THE Simulator SHALL allow the user to classify each stage as either "Major" (linear popularity weighting) or "Minor" (squared popularity weighting).
7. THE Simulator SHALL allow the user to set the surge lead time — how many minutes before a set starts that people begin moving toward it — using a selector with options: 5, 10, 15, 20, 30, 45, or 60 minutes.
8. WHERE a genre similarity matrix CSV is uploaded, THE Simulator SHALL use it to calculate genre clash rates and surge probabilities. WHERE no matrix is uploaded, THE Simulator SHALL default to 0.5 similarity for all genre pairs.

---

### Requirement 5: Run the Crowd Movement Simulation

**User Story:** As a festival consultant, I want the simulator to model how crowds move between stages throughout the day so that I can see realistic crowd flow patterns.

#### Acceptance Criteria

1. WHEN the user clicks "Run Simulation", THE Simulator SHALL execute the agent-based model for the full duration of the festival schedule, advancing in 5-minute time steps.
2. WHILE the simulation is running, THE Simulator SHALL display a progress indicator showing the current step and total steps.
3. THE Simulator SHALL model crowd movement using four triggers in this order of priority: (a) set ends with no upcoming act within 15 minutes, (b) genre clash when a new artist starts, (c) set change surge when a high-popularity act starts at another stage, (d) random wander rate.
4. THE Simulator SHALL scale all agent counts to real attendance by multiplying by the Scale Factor (total attendance ÷ number of agents).
5. THE Simulator SHALL spawn agents gradually over the first 75% of the festival duration, starting at 3% of total attendance at gates open and reaching 100% by 75% through the event.
6. THE Simulator SHALL spawn all agents within the Entry/Exit zone defined in the KML file. IF no Entry/Exit zone is defined in the KML, THEN THE Simulator SHALL display an error and stop the simulation from starting.
7. WHEN the simulation completes, THE Simulator SHALL store all results in the application session so the user can explore them without re-running.

---

### Requirement 6: Calculate Path Density

**User Story:** As a festival consultant, I want to know how crowded each walkway gets at every point in time so that I can identify which paths are at risk of dangerous crowding.

#### Acceptance Criteria

1. WHEN the simulation runs, THE Simulator SHALL calculate path density for each path at each 5-minute time step using the pipe model: people entering the path are tracked until they exit, and density equals total people on the path divided by path area (length × width).
2. THE Simulator SHALL reduce simulated walking speed based on effective density (including counter-flow penalties) using Fruin's Level of Service thresholds: free flow (< 0.5 people/m² → 50 m/min), slightly restricted (0.5–1.0 → 40 m/min), restricted (1.0–2.0 → 25 m/min), severely restricted (2.0–3.0 → 15 m/min), shuffling (3.0–4.0 → 8 m/min), gridlock (> 4.0 → 3 m/min).
3. THE Simulator SHALL apply a counter-flow penalty when people are moving in both directions on the same path simultaneously, increasing the effective density by up to 50% of the counter-flow ratio.
4. THE Simulator SHALL distribute crowd flow across multiple parallel paths connecting the same two stages, weighted by each path's width.
5. THE Simulator SHALL use path width values extracted from the KML file. IF a path's width cannot be determined from the KML, THEN THE Simulator SHALL use a default width of 8.0 meters.
6. THE Simulator SHALL classify each path's density at each time step as one of three levels: Normal (< 1.0 people/m²), HIGH (1.0–2.0 people/m²), or CRITICAL (> 2.0 people/m²).

---

### Requirement 7: Display the Animated Crowd Heatmap

**User Story:** As a festival consultant, I want to see an animated map of crowd density over time so that I can visually understand where and when crowds are heaviest.

#### Acceptance Criteria

1. WHEN simulation results are available, THE Simulator SHALL display a heatmap overlaid on a satellite map of the venue, showing crowd density at each time step.
2. THE Heatmap SHALL use a color scale that transitions at evenly spaced density quartiles: green (0–25% of max density), yellow (25–50%), orange (50–75%), and dark red (75–100%), with transparency at zero density so the satellite map is visible underneath.
3. THE Simulator SHALL allow the user to step through time manually using a slider labeled with the real clock time (e.g., "9:05 PM").
4. THE Simulator SHALL allow the user to auto-play the animation at three speeds: Slow (3 seconds per step), Normal (1.5 seconds per step), and Fast (0.5 seconds per step).
5. WHILE the heatmap is displayed, THE Simulator SHALL show which artist is currently performing at each stage, and flag set changes and genre clashes with visual indicators.
6. THE Simulator SHALL display each stage as a labeled marker on the map, color-coded to match the crowd chart.

---

### Requirement 8: Display the Crowd Distribution Chart

**User Story:** As a festival consultant, I want to see a line chart of crowd counts at each stage over time so that I can understand how attendance shifts throughout the day.

#### Acceptance Criteria

1. WHEN simulation results are available, THE Simulator SHALL display a line chart with one line per stage, showing the estimated real crowd count (scaled from agents) at each 5-minute time step. THE Chart SHALL display even when all stages have zero crowd count throughout the entire time period.
2. THE Chart SHALL use the x-axis for time (displayed as real clock times) and the y-axis for estimated crowd count.
3. THE Chart SHALL include a legend identifying each stage by name and color.

---

### Requirement 9: Display the Bottleneck Report

**User Story:** As a festival consultant, I want a clear report of when and where bottlenecks occur so that I can quickly identify the highest-risk moments and share findings with clients.

#### Acceptance Criteria

1. WHEN simulation results are available, THE Simulator SHALL display a bottleneck tab showing a timeline of every moment when any path's density crosses the HIGH threshold (≥ 1.0 people/m²) or CRITICAL threshold (≥ 2.0 people/m²).
2. THE Bottleneck Report SHALL display each event with: the path name, the time it occurred, the density level reached, and the density classification (HIGH or CRITICAL).
3. THE Bottleneck Report SHALL display a per-path density chart over time, with horizontal reference lines marking the HIGH and CRITICAL thresholds.
4. THE Bottleneck Report SHALL highlight crossover periods — time windows where two or more set changes occur within 30 minutes of each other — as these are the highest-risk moments.
5. WHEN simulation results are available, THE Simulator SHALL display the bottleneck tab. IF no bottleneck events occurred during the simulation, THE Bottleneck Tab SHALL display a message confirming that no paths exceeded the HIGH threshold.

---

### Requirement 10: Organize the Codebase into a Clean Folder Structure

**User Story:** As a developer working on this project, I want the code organized into logical folders so that it's easy to find files, fix bugs, and add new features.

#### Acceptance Criteria

1. THE Simulator's source code SHALL be organized into the following top-level folders: `simulation/` (model and path flow logic), `data_io/` (KML parser and lineup parser), `config/` (venue-specific configuration), `scripts/` (standalone run scripts and reports), and `archive/` (old prototype files no longer in active use).
2. THE file `model_edc.py` SHALL be moved to `simulation/model.py`.
3. THE file `path_flow.py` SHALL be moved to `simulation/path_flow.py`.
4. THE file `parse_kml.py` SHALL be moved to `data_io/parse_kml.py`.
5. THE files `heatmap_edc.py`, `crowd_animation.py`, `density_report.py`, and `debug_agents.py` SHALL have their imports updated to match the new file locations so that they no longer produce import errors.
6. THE files `model.py`, `run_festival.py`, and `heatmap.py` (the original prototype files) SHALL be moved to `archive/`.
7. THE project SHALL include a `data/` directory that is listed in `.gitignore` so that output files are not committed to version control.
8. WHEN the application is run from a fresh clone of the repository, THE Simulator SHALL start without import errors or missing directory errors.

---

### Requirement 11: Validate Path Density Against Documented Assumptions

**User Story:** As a developer, I want to verify that the path density numbers the simulator produces are consistent with the documented assumptions so that I can trust the output.

#### Acceptance Criteria

1. THE Simulator SHALL calculate path density values that are consistent with the Fruin Level of Service thresholds documented in `ASSUMPTIONS.md`: Normal (< 1.0 people/m²), HIGH (1.0–2.0 people/m²), CRITICAL (> 2.0 people/m²).
2. WHEN the simulation runs with the sample EDC Orlando lineup and map, THE Simulator SHALL produce at least one HIGH or CRITICAL density event on a path during a known crossover period (e.g., when Subtronics ends at Kinetic Field and Charlotte de Witte starts at Circuit Grounds simultaneously).
3. THE Simulator SHALL include a validation script that runs the simulation with the sample data and prints a summary of peak densities per path, so a developer can confirm the numbers make sense without opening the full app.
