"""
data_io/parse_lineup.py — Time utility functions and lineup parsing for the Festival Crowd Bottleneck Simulator.

This module provides:
  - parse_time: converts a time string like "9:05pm" or "21:05" to a (hour_24, minute) tuple
  - time_to_step: converts a 24-hour clock time to a simulation step number (each step = 5 minutes)
  - step_to_time: converts a simulation step number back to a human-readable display string like "9:05 PM"

Task 4.2 will add LineupParseResult and parse_lineup on top of these utilities.
"""


def time_to_step(hour, minute=0, start_hour=None):
    """Convert 24h clock time to step. Each step = 5 minutes."""
    total_min = (hour - start_hour) * 60 + minute
    return max(1, int(total_min / 5) + 1)


def step_to_time(step, start_hour):
    total_min = (step - 1) * 5
    hour = start_hour + total_min // 60
    minute = total_min % 60
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    period = "AM" if hour < 12 or hour >= 24 else "PM"
    return f"{display_hour}:{minute:02d} {period}"


def parse_time(time_str):
    """Parse time string like '3:00pm' or '15:00' to (hour24, minute)."""
    time_str = time_str.strip().lower().replace(" ", "")
    is_pm = "pm" in time_str
    is_am = "am" in time_str
    time_str = time_str.replace("pm", "").replace("am", "")

    if ":" in time_str:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    else:
        hour = int(time_str)
        minute = 0

    if is_pm and hour != 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 24  # midnight end-of-day, not start-of-day
    elif is_am and hour < 6:
        hour += 24  # early morning = next day (1am-5am)

    return hour, minute


# ---------------------------------------------------------------------------
# Task 4.2 additions: LineupParseResult dataclass and parse_lineup function
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
import pandas as pd


@dataclass
class LineupParseResult:
    """Result object returned by parse_lineup.

    Attributes:
        stage_configs: List of stage config dicts ready for FestivalModel.
        total_steps:   Total simulation steps derived from the lineup.
        warnings:      Non-fatal issues (e.g. stage name not in stage_positions).
        errors:        Fatal issues (e.g. missing required columns, unparseable times).
        success:       True when errors is empty.
    """
    stage_configs: list = field(default_factory=list)
    total_steps: int = 0
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    success: bool = True


def parse_lineup(df, stage_positions, genre_similarity, start_hour):
    """Parse a lineup DataFrame into stage configs for FestivalModel.

    Args:
        df:               pandas DataFrame loaded from the uploaded CSV.
        stage_positions:  dict mapping stage name → (x, y) grid position.
        genre_similarity: dict mapping (genre1, genre2) → float similarity score.
        start_hour:       int, the festival start hour in 24-hour format.

    Returns:
        LineupParseResult with stage_configs, total_steps, warnings, errors,
        and success flag.
    """
    result = LineupParseResult()

    # ------------------------------------------------------------------
    # 1. Validate required columns
    # ------------------------------------------------------------------
    required_cols = ["stage", "artist", "start_time", "end_time", "popularity"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        result.errors.append(f"Missing required columns: {missing}")
        result.success = False
        return result

    # ------------------------------------------------------------------
    # 2. Compute total_steps from the full time range in the CSV
    # ------------------------------------------------------------------
    all_minutes = []
    for _, row in df.iterrows():
        try:
            h, m = parse_time(row["start_time"])
            all_minutes.append(h * 60 + m)
            h, m = parse_time(row["end_time"])
            all_minutes.append(h * 60 + m)
        except Exception as exc:
            result.errors.append(
                f"Unparseable time in row for artist '{row.get('artist', '?')}': {exc}"
            )
            result.success = False

    if not result.success:
        return result

    end_minutes = max(all_minutes)
    # Mirror app.py: cap at 11:40 PM (23:40) to avoid end-of-festival noise
    cutoff_minutes = min(end_minutes, 23 * 60 + 40)
    result.total_steps = max(1, (cutoff_minutes - start_hour * 60) // 5)

    # ------------------------------------------------------------------
    # 3. Build per-stage schedule entries
    # ------------------------------------------------------------------
    for stage_name in df["stage"].unique():
        if stage_name not in stage_positions:
            result.warnings.append(
                f"Stage '{stage_name}' in lineup not found in stage_positions. Skipping."
            )
            continue

        stage_df = df[df["stage"] == stage_name].sort_values("start_time")
        schedule = []
        prev_genre = None

        for _, row in stage_df.iterrows():
            sh, sm = parse_time(row["start_time"])
            eh, em = parse_time(row["end_time"])

            entry = {
                "artist": row["artist"],
                "popularity": float(row["popularity"]),
                "start": time_to_step(sh, sm, start_hour),
                "end": time_to_step(eh, em, start_hour),
            }

            if "genre" in row and pd.notna(row.get("genre")):
                entry["genre"] = row["genre"]
                if prev_genre and prev_genre != row["genre"]:
                    # genre_clash = 1 - similarity (mirrors app.py logic)
                    sim = genre_similarity.get(
                        (prev_genre, row["genre"]),
                        genre_similarity.get((row["genre"], prev_genre), 0.0),
                    )
                    entry["genre_clash"] = 1.0 - sim
                prev_genre = row["genre"]

            schedule.append(entry)

        result.stage_configs.append({
            "name": stage_name,
            "x": stage_positions[stage_name][0],
            "y": stage_positions[stage_name][1],
            "schedule": schedule,
        })

    return result
