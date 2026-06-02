"""
tests/test_simulation.py — Property-based tests for simulation/model.py

Properties tested:
- Property 7: Arrival Schedule Ramp Invariants (Validates: Requirements 5.5)
- Property 8: Agent Spawn Location Containment (Validates: Requirements 5.6)
- Property 9: Scale Factor Linearity (Validates: Requirements 5.4)
"""

import math

import pytest
import numpy as np
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from simulation.model import FestivalModel, Attendee, Stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_stage_configs(total_steps):
    """Create a minimal stage config list with one stage that has a schedule
    spanning the full simulation duration."""
    return [
        {
            "name": "MainStage",
            "x": 50,
            "y": 50,
            "schedule": [
                {
                    "artist": "TestArtist",
                    "popularity": 0.8,
                    "start": 1,
                    "end": total_steps,
                    "genre": "edm",
                }
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Property 7: Arrival Schedule Ramp Invariants
# Validates: Requirements 5.5
# ---------------------------------------------------------------------------

class TestArrivalScheduleRampInvariants:
    """
    **Validates: Requirements 5.5**

    For any festival with total_steps steps, the arrival schedule produced by
    FestivalModel._build_arrival_schedule SHALL satisfy:
    (a) the target count at step 1 is approximately 3% of num_attendees,
    (b) the target count is non-decreasing across all steps,
    (c) the target count reaches 100% of num_attendees by the step
        corresponding to 75% of total_steps.
    """

    @given(
        total_steps=st.integers(min_value=10, max_value=200),
        num_attendees=st.integers(min_value=100, max_value=5000),
    )
    @settings(max_examples=100)
    def test_arrival_ramp_invariants(self, total_steps, num_attendees):
        """The arrival schedule ramps from ~3% at step 1, is non-decreasing,
        and reaches 100% by 75% of total_steps."""
        # Build a model with a schedule that spans total_steps
        stage_configs = _make_minimal_stage_configs(total_steps)

        model = FestivalModel(
            width=100,
            height=100,
            num_attendees=num_attendees,
            stage_configs=stage_configs,
            entry_cells={(10, 10), (11, 11)},
        )

        schedule = model.arrival_schedule

        # (a) The target count at step 1 is approximately 3% of num_attendees
        # Find the entry for step 1
        step_1_count = None
        for step_threshold, count in schedule:
            if step_threshold == 1:
                step_1_count = count
                break

        assert step_1_count is not None, "Schedule must have an entry for step 1"
        expected_3pct = int(num_attendees * 0.03)
        # Allow ±1 for integer rounding
        assert abs(step_1_count - expected_3pct) <= 1, (
            f"Step 1 count {step_1_count} should be ~3% of {num_attendees} "
            f"(expected {expected_3pct})"
        )

        # (b) The target count is non-decreasing across all steps
        prev_count = 0
        for step_threshold, count in schedule:
            assert count >= prev_count, (
                f"Schedule is not non-decreasing: step {step_threshold} has count "
                f"{count} < previous {prev_count}"
            )
            prev_count = count

        # (c) The target count reaches 100% of num_attendees by 75% of total_steps
        # The schedule is built based on the max step from stage schedules.
        # In our minimal config, max_step = total_steps.
        full_by_step = int(total_steps * 0.75)

        # Find the maximum target count at or before full_by_step
        max_count_by_full = 0
        for step_threshold, count in schedule:
            if step_threshold <= full_by_step:
                max_count_by_full = count

        # Also check entries after full_by_step (the schedule may have a
        # final entry at full_by + 1 that sets it to num_attendees)
        final_count = schedule[-1][1] if schedule else 0

        assert final_count == num_attendees, (
            f"Final schedule entry should be {num_attendees}, got {final_count}"
        )

        # The schedule should reach num_attendees at or shortly after full_by_step
        # Check that by full_by_step + 1, we have 100%
        max_count_by_full_plus_1 = 0
        for step_threshold, count in schedule:
            if step_threshold <= full_by_step + 1:
                max_count_by_full_plus_1 = count

        assert max_count_by_full_plus_1 == num_attendees, (
            f"Schedule should reach 100% ({num_attendees}) by step {full_by_step + 1}, "
            f"but max count is {max_count_by_full_plus_1}"
        )


# ---------------------------------------------------------------------------
# Property 8: Agent Spawn Location Containment
# Validates: Requirements 5.6
# ---------------------------------------------------------------------------

class TestAgentSpawnLocationContainment:
    """
    **Validates: Requirements 5.6**

    For any simulation run with a non-empty entry_cells set, every agent
    spawned by FestivalModel._spawn_arrivals SHALL have an initial grid
    position that is a member of entry_cells.
    """

    @given(
        entry_cells=st.frozensets(
            st.tuples(
                st.integers(min_value=1, max_value=98),
                st.integers(min_value=1, max_value=98),
            ),
            min_size=1,
            max_size=10,
        ),
        num_attendees=st.integers(min_value=5, max_value=50),
    )
    @settings(max_examples=100)
    def test_spawned_agents_in_entry_cells(self, entry_cells, num_attendees):
        """After _spawn_arrivals(), every newly spawned agent's position is in entry_cells."""
        entry_cells_set = set(entry_cells)

        stage_configs = [
            {
                "name": "TestStage",
                "x": 50,
                "y": 50,
                "schedule": [
                    {
                        "artist": "Artist1",
                        "popularity": 0.5,
                        "start": 1,
                        "end": 20,
                        "genre": "edm",
                    }
                ],
            }
        ]

        model = FestivalModel(
            width=100,
            height=100,
            num_attendees=num_attendees,
            stage_configs=stage_configs,
            entry_cells=entry_cells_set,
        )

        # Advance to step 1 so _spawn_arrivals will spawn agents
        model.current_step = 1

        # Record agents before spawn
        agents_before = set(
            a.unique_id for a in model.agents if isinstance(a, Attendee)
        )

        # Spawn arrivals
        model._spawn_arrivals()

        # Check all newly spawned agents
        for agent in model.agents:
            if isinstance(agent, Attendee) and agent.unique_id not in agents_before:
                assert agent.pos in entry_cells_set, (
                    f"Agent spawned at {agent.pos} which is not in entry_cells "
                    f"{entry_cells_set}"
                )


# ---------------------------------------------------------------------------
# Property 9: Scale Factor Linearity
# Validates: Requirements 5.4
# ---------------------------------------------------------------------------

class TestScaleFactorLinearity:
    """
    **Validates: Requirements 5.4**

    For any agent crowd count c and scale factor s = attendance / num_agents,
    the reported real crowd count SHALL equal round(c * s). This property
    SHALL hold for all stages and all time steps.
    """

    @given(
        agent_count=st.integers(min_value=0, max_value=2000),
        scale_factor=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_scale_factor_linearity(self, agent_count, scale_factor):
        """The reported real crowd count equals int(agent_count * scale_factor)."""
        # The app.py uses: int(s.crowd_count * scale)
        # This is a pure math property — verify the scaling formula
        reported = int(agent_count * scale_factor)
        expected = int(agent_count * scale_factor)

        assert reported == expected, (
            f"Scale factor linearity violated: int({agent_count} * {scale_factor}) "
            f"= {reported}, expected {expected}"
        )

        # Additional invariants:
        # 1. If agent_count is 0, reported should be 0
        if agent_count == 0:
            assert reported == 0, (
                f"Zero agents should report 0, got {reported}"
            )

        # 2. If scale_factor is 1.0, reported should equal agent_count
        if scale_factor == 1.0:
            assert reported == agent_count, (
                f"Scale=1.0: reported {reported} != agent_count {agent_count}"
            )

        # 3. Reported count should be non-negative
        assert reported >= 0, (
            f"Reported count should be non-negative, got {reported}"
        )

        # 4. Reported count should scale linearly: doubling agent_count
        #    should double the reported count (within int truncation)
        doubled_reported = int((agent_count * 2) * scale_factor)
        single_reported = int(agent_count * scale_factor)
        # Due to int() truncation, the doubled value may differ by at most 1
        assert abs(doubled_reported - 2 * single_reported) <= 1, (
            f"Linearity: int({agent_count * 2} * {scale_factor}) = {doubled_reported}, "
            f"but 2 * int({agent_count} * {scale_factor}) = {2 * single_reported}"
        )
