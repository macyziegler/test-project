"""
config/defaults.py — Centralized constants for the Festival Crowd Bottleneck Simulator.

All magic numbers live here so they can be imported by any module without
creating circular dependencies. No Streamlit or simulation imports allowed.
"""

# ---------------------------------------------------------------------------
# Density thresholds (people / m²) — Fruin Level of Service
# ---------------------------------------------------------------------------

# Below this value: Normal (LoS A/B/C)
DENSITY_NORMAL_MAX = 1.0

# Below this value: HIGH; at or above this value: CRITICAL (LoS E/F)
DENSITY_HIGH_MAX = 2.0

# ---------------------------------------------------------------------------
# Path geometry defaults
# ---------------------------------------------------------------------------

# Default path width used when the KML <description> tag does not specify one
DEFAULT_PATH_WIDTH_M = 8.0

# ---------------------------------------------------------------------------
# Path-to-stage connection derivation
# ---------------------------------------------------------------------------

# Maximum grid-cell distance from a path waypoint to a stage for the stage
# to be considered "connected" to that path
DEFAULT_PROXIMITY_THRESHOLD_CELLS = 85

# ---------------------------------------------------------------------------
# Crossover detection
# ---------------------------------------------------------------------------

# Sliding window size for crossover period detection.
# 6 steps × 5 min/step = 30-minute window.
CROSSOVER_WINDOW_STEPS = 6

# ---------------------------------------------------------------------------
# Arrival curve parameters
# (expressed as fractions of total_steps)
# ---------------------------------------------------------------------------

# Fraction of total_steps at which the first agents arrive (ramp start)
ARRIVAL_START_PCT = 0.03

# Fraction of total_steps at which the arrival ramp reaches full rate
ARRIVAL_RAMP_END_PCT = 0.60

# Fraction of total_steps by which 100 % of attendees have arrived
ARRIVAL_FULL_PCT = 0.75

# ---------------------------------------------------------------------------
# Simulation defaults
# ---------------------------------------------------------------------------

# Number of simulated agents (scaled up to DEFAULT_ATTENDANCE for reporting)
DEFAULT_NUM_AGENTS = 2000

# Real-world attendance figure used to compute the scale factor
DEFAULT_ATTENDANCE = 90000

# How many minutes before a set ends that agents begin moving to the next stage
DEFAULT_SURGE_LEAD_MIN = 30

# Radius (in grid cells) within which an agent can "hear" a stage and decide
# to stay or move toward it
DEFAULT_LISTEN_RADIUS = 15
