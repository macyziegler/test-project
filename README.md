<<<<<<< HEAD
# 🎵 Festival Crowd Flow Simulator

An agent-based simulation that models how crowds move between stages at music festivals. Built to help festival organizers optimize lineups, identify bottlenecks, and balance crowd distribution.

## What It Does

- **Simulates crowd movement** between stages based on artist popularity and set times
- **Generates crowd density charts** showing how many people are at each stage over time
- **Produces congestion heatmaps** highlighting bottleneck areas during set transitions
- **Scales results** from a lightweight agent model up to real attendance numbers

## Project Structure

```
festival_sim/
├── model.py              # Core simulation engine (Stage + Attendee agents)
├── run_festival.py       # Festival configuration + crowd distribution chart
├── heatmap.py            # Congestion heatmaps at set transitions
├── run.py                # Simple 3-stage demo (good for testing)
├── requirements.txt      # Python dependencies
├── README.md             # This file
└── data/                 # Output folder
    ├── crowd_density.csv
    ├── festival_crowd_density.csv
    ├── crowd_density_plot.png
    ├── festival_crowd_plot.png
    └── congestion_heatmap.png
```

## Setup

### 1. Install Python
Download from [python.org/downloads](https://www.python.org/downloads/). Make sure to check **"Add Python to PATH"** during install.

### 2. Install Dependencies
```
cd festival_sim
pip install -r requirements.txt
```

If `pip` doesn't work, try:
```
py -m pip install -r requirements.txt
```

You may also need:
```
pip install networkx
```

### 3. Run the Simulation
```
python run_festival.py
```

Then run the heatmap:
```
python heatmap.py
```

## How to Configure a New Festival

All festival configuration lives in `run_festival.py`. To model a different festival, edit these sections:

### Venue Layout
```python
WIDTH, HEIGHT = 100, 100          # Grid size (each cell ≈ 10m)
NUM_ATTENDEES = 2000              # Scaled agent count (see SCALE below)
```

### Stage Positions
Set `x` and `y` coordinates on the grid to match the venue layout:
```python
{"name": "Main Stage", "x": 50, "y": 90, "schedule": [...]},
{"name": "Side Stage", "x": 15, "y": 15, "schedule": [...]},
```

### Artist Schedules
Each artist needs a name, popularity score (0.0–1.0), and start/end time steps:
```python
{"artist": "Headliner", "popularity": 1.0, "start": time_to_step(22, 0), "end": time_to_step(23, 0)},
```

Use `time_to_step(hour, minute)` to convert clock times (24-hour format) to simulation steps. Each step = 15 minutes.

### Popularity Scoring Guide
| Score | Meaning | Example |
|-------|---------|---------|
| 0.90–1.00 | Headliner / top billing | Zeds Dead, SVDDEN DEATH |
| 0.70–0.89 | Co-headliner / strong draw | Virtual Riot, Liquid Stranger |
| 0.50–0.69 | Mid-card fan favorite | Boogie T, Reaper, Kompany |
| 0.30–0.49 | Support act with a following | Phaseone, Cyclops, Ivy Lab |
| 0.10–0.29 | Undercard / opener | Local acts, early slots |
| 0.01–0.09 | Small/hidden stage acts | Easy-to-miss warehouse stages |

### Attendance Scaling
The simulation runs with fewer agents for performance, then scales up:
```python
NUM_ATTENDEES = 2000              # Agents in simulation
SCALE = 35000 / NUM_ATTENDEES     # Multiply results by 17.5x
```
Adjust `35000` to the real festival attendance.

## How the Model Works

### Agents
- **Stage**: Fixed position on the grid. Hosts artists on a schedule. Tracks crowd count.
- **Attendee**: Picks a stage based on artist popularity (cubed weighting), walks toward it, stays until the set ends or randomly reconsiders (10% chance per step).

### Key Behaviors
- **Popularity cubing**: A 0.05 popularity artist gets 0.000125 weight vs 1.0 for a headliner — an 8,000x difference. This prevents small stages from unrealistically accumulating crowds.
- **Random reconsideration**: Each step, 10% of attendees re-evaluate their stage choice. This simulates people checking the schedule, hearing a set from afar, or following friends.
- **Walking speed**: 1–2 grid cells per step (≈10–20 meters per 15 minutes of real time).
- **Arrival counting**: Only attendees who chose a stage AND arrived within listening radius count toward that stage's crowd.

### Heatmap
Captures agent grid positions at set transition moments and plots density. The bottleneck report identifies the most congested non-stage cells — these represent walkway chokepoints.

## Outputs

| File | Description |
|------|-------------|
| `festival_crowd_density.csv` | Crowd count per stage at each time step |
| `festival_crowd_plot.png` | Line chart of crowd distribution over time |
| `congestion_heatmap.png` | Spatial heatmaps at key set transitions |

## Roadmap

### Near-Term
- [ ] Add food/beverage/restroom nodes and track queue buildup
- [ ] Spotify API integration to auto-pull artist popularity scores
- [ ] Support for multi-day festivals
- [ ] Path constraints (fences, buildings, narrow walkways)

### Medium-Term
- [ ] Schedule optimizer — run N simulations with different lineup orderings, score by crowd balance
- [ ] Streamlit web app — upload a lineup, get results in a browser
- [ ] Capacity limits per stage with overflow behavior

### Long-Term
- [ ] Real-time calibration using cell tower / WiFi density data
- [ ] Weather impact modeling (rain pushes crowds to covered stages)
- [ ] VIP / GA zone separation
- [ ] Emergency evacuation flow modeling

## Tech Stack
- **Python 3.x**
- **Mesa** — agent-based modeling framework
- **NumPy** — math and probability
- **Pandas** — data export
- **Matplotlib** — visualization
=======
# vmconsulting
>>>>>>> 6e364729cf2ed844e10c87c099c78c0b36dfaa85
