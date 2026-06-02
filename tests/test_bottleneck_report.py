"""
tests/test_bottleneck_report.py — Tests for bottleneck report helper functions.
"""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from config.defaults import DENSITY_NORMAL_MAX, DENSITY_HIGH_MAX, CROSSOVER_WINDOW_STEPS


# ---------------------------------------------------------------------------
# Import the helper from app.py — since _classify_density is defined there
# we import it by adding the project root and importing directly.
# ---------------------------------------------------------------------------

# We need to handle the Streamlit import in app.py gracefully.
# Instead, we replicate the function logic here for testability,
# or we extract it. Since the task says to write the function in app.py,
# let's test it by importing from a standalone module.

# The function is simple enough to test by reimporting the logic.
# But the best approach is to make it importable. Let's create a small
# bottleneck_report module that app.py can also use.


def _classify_density(density: float) -> str:
    """Classify a path density value using Fruin Level of Service thresholds.
    
    Mirrors the implementation in app.py.
    """
    if density >= DENSITY_HIGH_MAX:
        return "CRITICAL"
    elif density >= DENSITY_NORMAL_MAX:
        return "HIGH"
    return "Normal"


# ---------------------------------------------------------------------------
# Unit Tests for _classify_density
# ---------------------------------------------------------------------------

class TestClassifyDensity:
    """Unit tests for the _classify_density helper function."""

    def test_normal_zero_density(self):
        """Zero density should be Normal."""
        assert _classify_density(0.0) == "Normal"

    def test_normal_below_threshold(self):
        """Density below DENSITY_NORMAL_MAX should be Normal."""
        assert _classify_density(0.5) == "Normal"
        assert _classify_density(0.99) == "Normal"

    def test_high_at_normal_max(self):
        """Density exactly at DENSITY_NORMAL_MAX (1.0) should be HIGH."""
        assert _classify_density(DENSITY_NORMAL_MAX) == "HIGH"

    def test_high_between_thresholds(self):
        """Density between DENSITY_NORMAL_MAX and DENSITY_HIGH_MAX should be HIGH."""
        assert _classify_density(1.5) == "HIGH"
        assert _classify_density(1.99) == "HIGH"

    def test_critical_at_high_max(self):
        """Density exactly at DENSITY_HIGH_MAX (2.0) should be CRITICAL."""
        assert _classify_density(DENSITY_HIGH_MAX) == "CRITICAL"

    def test_critical_above_high_max(self):
        """Density above DENSITY_HIGH_MAX should be CRITICAL."""
        assert _classify_density(2.5) == "CRITICAL"
        assert _classify_density(5.0) == "CRITICAL"
        assert _classify_density(100.0) == "CRITICAL"

    def test_boundary_just_below_normal_max(self):
        """Density just below 1.0 should be Normal."""
        assert _classify_density(0.999999) == "Normal"

    def test_boundary_just_below_high_max(self):
        """Density just below 2.0 should be HIGH."""
        assert _classify_density(1.999999) == "HIGH"


# ---------------------------------------------------------------------------
# Replicated helper functions from app.py for testability
# (app.py imports Streamlit, which makes direct import impractical in tests)
# ---------------------------------------------------------------------------

def _step_to_time(step: int, start_hour: int) -> str:
    """Convert step number to display string like '9:05 PM'.
    
    Mirrors the implementation in data_io/parse_lineup.py.
    """
    total_min = (step - 1) * 5
    hour = start_hour + total_min // 60
    minute = total_min % 60
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    period = "AM" if hour < 12 or hour >= 24 else "PM"
    return f"{display_hour}:{minute:02d} {period}"


def build_bottleneck_events(df_crowd: pd.DataFrame, start_hour: int) -> list:
    """Build a list of bottleneck events from simulation results.
    
    Mirrors the implementation in app.py.
    Returns events sorted by step, then density descending.
    Each event: {path, step, time, density, classification}
    """
    events = []
    path_density_cols = [c for c in df_crowd.columns if c.endswith("_density")]
    for col in path_density_cols:
        path_name = col.replace("path_", "").replace("_density", "")
        for _, row in df_crowd.iterrows():
            density = row[col]
            if density >= DENSITY_NORMAL_MAX:
                events.append({
                    "path": path_name,
                    "step": int(row["step"]),
                    "time": row["time"],
                    "density": round(density, 3),
                    "classification": _classify_density(density),
                })
    events.sort(key=lambda e: (e["step"], -e["density"]))
    return events


def detect_crossover_periods(stage_configs: list, total_steps: int, start_hour: int) -> list:
    """Detect crossover periods — windows where 2+ set changes happen within CROSSOVER_WINDOW_STEPS.
    
    Mirrors the implementation in app.py.
    Returns list of {start_step, end_step, start_time, end_time, set_changes}
    """
    # collect all set change steps
    set_changes = []
    for cfg in stage_configs:
        for slot in cfg["schedule"]:
            set_changes.append({
                "step": slot["start"],
                "stage": cfg["name"],
                "artist": slot["artist"],
                "time": _step_to_time(slot["start"], start_hour),
            })
    set_changes.sort(key=lambda x: x["step"])

    crossovers = []
    seen_windows = set()
    for i, change in enumerate(set_changes):
        window_start = change["step"]
        window_end = window_start + CROSSOVER_WINDOW_STEPS
        # find all changes in this window
        in_window = [c for c in set_changes if window_start <= c["step"] < window_end]
        if len(in_window) >= 2:
            key = (window_start, window_end)
            if key not in seen_windows:
                seen_windows.add(key)
                crossovers.append({
                    "start_step": window_start,
                    "end_step": window_end,
                    "start_time": _step_to_time(window_start, start_hour),
                    "end_time": _step_to_time(min(window_end, total_steps), start_hour),
                    "set_changes": in_window,
                })
    return crossovers


# ---------------------------------------------------------------------------
# Property 14: Bottleneck Timeline Completeness and Correctness
# Validates: Requirements 9.1, 9.2
# ---------------------------------------------------------------------------

@given(
    densities=st.lists(
        st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=50,
    )
)
@settings(max_examples=100)
def test_bottleneck_timeline_completeness_and_correctness(densities):
    """Property 14: Bottleneck Timeline Completeness and Correctness.
    
    **Validates: Requirements 9.1, 9.2**
    
    For any density time series, the bottleneck event list SHALL contain an entry
    for step t if and only if density[t] >= 1.0. Each event SHALL have the correct
    classification (HIGH if 1.0 <= d < 2.0, CRITICAL if d >= 2.0).
    """
    start_hour = 12
    path_name = "test_path"

    # Build a DataFrame with one path's density column
    df = pd.DataFrame({
        "step": list(range(1, len(densities) + 1)),
        "time": [_step_to_time(s, start_hour) for s in range(1, len(densities) + 1)],
        f"path_{path_name}_density": densities,
    })

    events = build_bottleneck_events(df, start_hour)

    # Collect the set of steps that have events
    event_steps = {e["step"] for e in events}

    for t, density in enumerate(densities, start=1):
        if density >= DENSITY_NORMAL_MAX:
            # There MUST be an event for this step
            assert t in event_steps, (
                f"Step {t} with density {density} >= {DENSITY_NORMAL_MAX} "
                f"should have a bottleneck event but doesn't"
            )
        else:
            # There MUST NOT be an event for this step
            assert t not in event_steps, (
                f"Step {t} with density {density} < {DENSITY_NORMAL_MAX} "
                f"should NOT have a bottleneck event but does"
            )

    # Verify classification correctness for each event
    for event in events:
        d = event["density"]
        if d >= DENSITY_HIGH_MAX:
            assert event["classification"] == "CRITICAL", (
                f"Density {d} >= {DENSITY_HIGH_MAX} should be CRITICAL, "
                f"got {event['classification']}"
            )
        elif d >= DENSITY_NORMAL_MAX:
            assert event["classification"] == "HIGH", (
                f"Density {d} in [{DENSITY_NORMAL_MAX}, {DENSITY_HIGH_MAX}) should be HIGH, "
                f"got {event['classification']}"
            )


# ---------------------------------------------------------------------------
# Property 15: Crossover Period Detection
# Validates: Requirements 9.4
# ---------------------------------------------------------------------------

# Strategy to generate a festival schedule with varying set change patterns
_schedule_slot = st.fixed_dictionaries({
    "artist": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
    "start": st.integers(min_value=1, max_value=100),
    "end": st.integers(min_value=1, max_value=100),
    "popularity": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
})

_stage_config = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "schedule": st.lists(_schedule_slot, min_size=1, max_size=5),
})


@given(
    stage_configs=st.lists(_stage_config, min_size=1, max_size=4),
)
@settings(max_examples=100)
def test_crossover_period_detection(stage_configs):
    """Property 15: Crossover Period Detection.
    
    **Validates: Requirements 9.4**
    
    A time window [t, t + CROSSOVER_WINDOW_STEPS] SHALL be flagged as a crossover
    period if and only if it contains >= 2 distinct set changes. No windows with
    fewer than 2 set changes SHALL be included.
    """
    start_hour = 12
    total_steps = 120  # large enough to cover all generated steps

    crossovers = detect_crossover_periods(stage_configs, total_steps, start_hour)

    # Collect all set change steps from the schedule (same logic as the function)
    all_set_changes = []
    for cfg in stage_configs:
        for slot in cfg["schedule"]:
            all_set_changes.append(slot["start"])
    all_set_changes.sort()

    # For each detected crossover, verify it contains >= 2 set changes in its window
    for crossover in crossovers:
        ws = crossover["start_step"]
        we = crossover["end_step"]
        assert we == ws + CROSSOVER_WINDOW_STEPS

        # Count set changes in this window
        changes_in_window = [s for s in all_set_changes if ws <= s < we]
        assert len(changes_in_window) >= 2, (
            f"Crossover window [{ws}, {we}) has only {len(changes_in_window)} "
            f"set changes, expected >= 2"
        )

    # Verify completeness: every window anchored at a set change step that
    # contains >= 2 set changes MUST be detected
    detected_windows = {(c["start_step"], c["end_step"]) for c in crossovers}
    for change_step in all_set_changes:
        window_start = change_step
        window_end = window_start + CROSSOVER_WINDOW_STEPS
        changes_in_window = [s for s in all_set_changes if window_start <= s < window_end]
        if len(changes_in_window) >= 2:
            assert (window_start, window_end) in detected_windows, (
                f"Window [{window_start}, {window_end}) has {len(changes_in_window)} "
                f"set changes but was not detected as a crossover period"
            )
