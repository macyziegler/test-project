"""
tests/test_parse_lineup.py — Property-based tests for data_io/parse_lineup.py

Covers:
- Property 4: Lineup Column Validation (Requirements 2.1, 2.3)
- Property 5: Time Conversion Monotonicity (Requirements 2.2)
"""

import pandas as pd
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from data_io.parse_lineup import parse_lineup, time_to_step, step_to_time


# ---------------------------------------------------------------------------
# Property 4: Lineup Column Validation
# **Validates: Requirements 2.1, 2.3**
#
# For any DataFrame, parse_lineup succeeds if and only if all 5 required
# columns (stage, artist, start_time, end_time, popularity) are present.
# The absence of any single required column causes the parser to return an
# error, regardless of what other columns are present.
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = ["stage", "artist", "start_time", "end_time", "popularity"]
EXTRA_COLUMNS = ["genre", "notes", "day", "order", "duration"]


@given(
    columns_subset=st.frozensets(
        st.sampled_from(REQUIRED_COLUMNS), min_size=0, max_size=5
    ),
    extra_cols=st.frozensets(
        st.sampled_from(EXTRA_COLUMNS), min_size=0, max_size=3
    ),
)
@settings(max_examples=100)
def test_parse_lineup_succeeds_iff_all_required_columns_present(columns_subset, extra_cols):
    """Property 4: Lineup Column Validation

    **Validates: Requirements 2.1, 2.3**

    parse_lineup succeeds if and only if all 5 required columns are present.
    """
    all_columns = list(columns_subset) + list(extra_cols)

    # Build a minimal DataFrame with the selected columns
    if not all_columns:
        df = pd.DataFrame()
    else:
        # Create one row of dummy data so the DataFrame has the columns
        row_data = {}
        for col in all_columns:
            if col == "popularity":
                row_data[col] = [0.5]
            elif col in ("start_time", "end_time"):
                row_data[col] = ["3:00pm"] if col == "start_time" else ["4:00pm"]
            else:
                row_data[col] = ["test"]
        df = pd.DataFrame(row_data)

    # Provide minimal valid arguments for the other params
    stage_positions = {"test": (50, 50)}
    genre_similarity = {}
    start_hour = 12

    result = parse_lineup(df, stage_positions, genre_similarity, start_hour)

    has_all_required = set(REQUIRED_COLUMNS).issubset(set(all_columns))

    if has_all_required:
        assert result.success is True, (
            f"Expected success=True when all required columns present, "
            f"but got errors: {result.errors}"
        )
    else:
        assert result.success is False, (
            f"Expected success=False when columns={all_columns} "
            f"(missing: {set(REQUIRED_COLUMNS) - set(all_columns)})"
        )
        assert len(result.errors) > 0, "Expected at least one error message"


# ---------------------------------------------------------------------------
# Property 5: Time Conversion Monotonicity
# **Validates: Requirements 2.2**
#
# For any two valid times T1 < T2 (in the same festival day),
# time_to_step(T1) < time_to_step(T2) (or <= if within same 5-min bucket).
# Additionally, step_to_time(time_to_step(T)) round-trips to the same clock
# time within 5-minute rounding.
# ---------------------------------------------------------------------------

# Strategy: generate valid festival hours (start_hour through start_hour + 14h)
# and minutes (0-59). start_hour is typically 12-18.
@given(
    start_hour=st.integers(min_value=12, max_value=18),
    h1_offset=st.integers(min_value=0, max_value=13),
    m1=st.integers(min_value=0, max_value=59),
    h2_offset=st.integers(min_value=0, max_value=13),
    m2=st.integers(min_value=0, max_value=59),
)
@settings(max_examples=100)
def test_time_to_step_monotonicity(start_hour, h1_offset, m1, h2_offset, m2):
    """Property 5: Time Conversion Monotonicity

    **Validates: Requirements 2.2**

    For any two valid times where T1 < T2, time_to_step(T1) <= time_to_step(T2).
    When T1 and T2 are in different 5-minute buckets, strict inequality holds.
    """
    hour1 = start_hour + h1_offset
    hour2 = start_hour + h2_offset

    # Total minutes from start for each time
    total_min1 = (hour1 - start_hour) * 60 + m1
    total_min2 = (hour2 - start_hour) * 60 + m2

    # Only test when both times are after start and T1 < T2
    assume(total_min1 >= 0)
    assume(total_min2 >= 0)
    assume(total_min1 < total_min2)

    step1 = time_to_step(hour1, m1, start_hour)
    step2 = time_to_step(hour2, m2, start_hour)

    # Monotonicity: T1 < T2 implies step1 <= step2
    assert step1 <= step2, (
        f"Monotonicity violated: time ({hour1}:{m1:02d}) → step {step1}, "
        f"time ({hour2}:{m2:02d}) → step {step2}, start_hour={start_hour}"
    )

    # Strict monotonicity when in different 5-minute buckets
    bucket1 = total_min1 // 5
    bucket2 = total_min2 // 5
    if bucket1 < bucket2:
        assert step1 < step2, (
            f"Strict monotonicity violated: bucket {bucket1} vs {bucket2}, "
            f"but step {step1} >= step {step2}"
        )


@given(
    start_hour=st.integers(min_value=12, max_value=18),
    h_offset=st.integers(min_value=0, max_value=11),
    m=st.integers(min_value=0, max_value=59),
)
@settings(max_examples=100)
def test_time_to_step_round_trip(start_hour, h_offset, m):
    """Property 5: Time Conversion Monotonicity (round-trip)

    **Validates: Requirements 2.2**

    step_to_time(time_to_step(T)) produces a time string representing the same
    clock time as T within 5-minute rounding.

    We constrain hours to start_hour through start_hour+11 (i.e. hour < 24)
    because step_to_time uses 12h AM/PM display which is well-defined for
    hours 0-23. Festival schedules typically run from afternoon through
    late night within this range.
    """
    hour = start_hour + h_offset
    total_min = h_offset * 60 + m

    # Ensure we stay within the 24h clock (step_to_time's display logic)
    assume(hour < 24)
    assume(total_min >= 0)

    step = time_to_step(hour, m, start_hour)
    time_str = step_to_time(step, start_hour)

    # Parse the time string back to verify round-trip
    # step_to_time returns format like "3:05 PM" or "12:00 AM"
    parts = time_str.split()
    assert len(parts) == 2, f"Unexpected time format: {time_str}"
    time_part, period = parts
    hh, mm = time_part.split(":")
    hh = int(hh)
    mm = int(mm)

    # Convert back to 24h
    if period == "PM" and hh != 12:
        hh += 12
    elif period == "AM" and hh == 12:
        hh = 0  # midnight

    # Reconstruct total minutes from start
    reconstructed_total_min = (hh - start_hour) * 60 + mm

    # Handle wrap-around for AM times that represent next-day hours
    if reconstructed_total_min < 0:
        reconstructed_total_min += 24 * 60

    # The round-trip should be within 5 minutes (one bucket)
    original_rounded = (total_min // 5) * 5
    assert reconstructed_total_min == original_rounded, (
        f"Round-trip failed: original ({hour}:{m:02d}, total_min={total_min}) "
        f"→ step {step} → '{time_str}' → reconstructed_total_min={reconstructed_total_min}, "
        f"expected {original_rounded}"
    )
