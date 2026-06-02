"""
tests/test_path_flow.py — Property-based tests for simulation/path_flow.py

Properties tested:
- Property 10: Path Density Invariant (Validates: Requirements 6.1)
- Property 11: Density Tier Classification (Validates: Requirements 6.2, 6.6, 11.1)
- Property 12: Counter-Flow Effective Density Non-Decrease (Validates: Requirements 6.3)
- Property 13: Width-Proportional Flow Distribution (Validates: Requirements 6.4)
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from simulation.path_flow import PathSegment, PathFlowModel


# ---------------------------------------------------------------------------
# Property 10: Path Density Invariant
# Validates: Requirements 6.1
# ---------------------------------------------------------------------------

class TestPathDensityInvariant:
    """
    **Validates: Requirements 6.1**

    For any PathSegment with area A = length_m × width_m and N people currently
    on the path, current_density SHALL equal N / A. This invariant SHALL hold
    after every call to PathSegment.step().
    """

    @given(
        length_m=st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        width_m=st.floats(min_value=2.0, max_value=30.0, allow_nan=False, allow_infinity=False),
        num_people=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=100)
    def test_density_equals_people_divided_by_area(self, length_m, width_m, num_people):
        """After step(), current_density == len(people_on_path) / (length_m * width_m)."""
        segment = PathSegment(name="test_path", length_m=length_m, width_m=width_m)

        # Add people to the path
        if num_people > 0:
            segment.add_people(num_people, direction="forward")

        # Step the simulation
        segment.step()

        # After step, some people may have exited. The invariant is about
        # the people still on the path after the step.
        expected_density = len(segment.people_on_path) / (length_m * width_m)

        assert segment.current_density == pytest.approx(expected_density, rel=1e-9), (
            f"Expected density {expected_density}, got {segment.current_density}. "
            f"People on path: {len(segment.people_on_path)}, area: {length_m * width_m}"
        )


# ---------------------------------------------------------------------------
# Property 11: Density Tier Classification
# Validates: Requirements 6.2, 6.6, 11.1
# ---------------------------------------------------------------------------

class TestDensityTierClassification:
    """
    **Validates: Requirements 6.2, 6.6, 11.1**

    For any effective density value d, the Fruin LoS speed function SHALL satisfy:
    - d < 0.5 → speed = 50 m/min
    - 0.5 ≤ d < 1.0 → speed = 40 m/min
    - 1.0 ≤ d < 2.0 → speed = 25 m/min
    - 2.0 ≤ d < 3.0 → speed = 15 m/min
    - 3.0 ≤ d < 4.0 → speed = 8 m/min
    - d ≥ 4.0 → speed = 3 m/min
    """

    @given(
        density=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_fruin_los_speed_tiers(self, density):
        """_density_adjusted_speed returns the correct speed for each Fruin LoS tier."""
        segment = PathSegment(name="test", length_m=100.0, width_m=10.0)
        speed = segment._density_adjusted_speed(density)

        if density < 0.5:
            assert speed == 50.0, f"d={density}: expected 50.0, got {speed}"
        elif density < 1.0:
            assert speed == 40.0, f"d={density}: expected 40.0, got {speed}"
        elif density < 2.0:
            assert speed == 25.0, f"d={density}: expected 25.0, got {speed}"
        elif density < 3.0:
            assert speed == 15.0, f"d={density}: expected 15.0, got {speed}"
        elif density < 4.0:
            assert speed == 8.0, f"d={density}: expected 8.0, got {speed}"
        else:
            assert speed == 3.0, f"d={density}: expected 3.0, got {speed}"

    @given(
        density=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_density_classification(self, density):
        """Density classification matches Fruin LoS thresholds."""
        # Classification logic as defined in requirements:
        # Normal: < 1.0, HIGH: 1.0-2.0, CRITICAL: > 2.0
        if density < 1.0:
            expected_class = "Normal"
        elif density < 2.0:
            expected_class = "HIGH"
        else:
            expected_class = "CRITICAL"

        # Verify the speed function is consistent with classification
        segment = PathSegment(name="test", length_m=100.0, width_m=10.0)
        speed = segment._density_adjusted_speed(density)

        if expected_class == "Normal":
            # Normal: speed should be >= 40 (free flow or slightly restricted)
            assert speed >= 40.0, (
                f"d={density}, class=Normal, but speed={speed} < 40"
            )
        elif expected_class == "HIGH":
            # HIGH: speed should be 25 (restricted movement)
            assert speed == 25.0, (
                f"d={density}, class=HIGH, but speed={speed} != 25"
            )
        else:
            # CRITICAL: speed should be <= 15
            assert speed <= 15.0, (
                f"d={density}, class=CRITICAL, but speed={speed} > 15"
            )


# ---------------------------------------------------------------------------
# Property 12: Counter-Flow Effective Density Non-Decrease
# Validates: Requirements 6.3
# ---------------------------------------------------------------------------

class TestCounterFlowEffectiveDensity:
    """
    **Validates: Requirements 6.3**

    For any PathSegment with at least one person traveling in each direction,
    the effective_density computed after step() SHALL be >= current_density.
    When all travelers move in the same direction, effective_density SHALL
    equal current_density.
    """

    @given(
        length_m=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        width_m=st.floats(min_value=3.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        forward_count=st.integers(min_value=1, max_value=50),
        backward_count=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_counter_flow_increases_effective_density(
        self, length_m, width_m, forward_count, backward_count
    ):
        """When people travel in both directions, effective_density >= current_density."""
        segment = PathSegment(name="test", length_m=length_m, width_m=width_m)

        # Add people in both directions
        segment.add_people(forward_count, direction="forward")
        segment.add_people(backward_count, direction="backward")

        # Step to compute densities
        result = segment.step()

        # After step, check that people remain on path in both directions
        forward_on_path = sum(1 for p in segment.people_on_path if p["direction"] == "forward")
        backward_on_path = len(segment.people_on_path) - forward_on_path

        # The effective density from step result includes counter-flow penalty
        effective_density = result["density"]

        if forward_on_path > 0 and backward_on_path > 0:
            # Counter-flow: effective_density >= current_density
            assert effective_density >= segment.current_density - 1e-9, (
                f"effective_density={effective_density} < current_density={segment.current_density} "
                f"with forward={forward_on_path}, backward={backward_on_path}"
            )
        elif len(segment.people_on_path) > 0:
            # Single direction: effective_density == current_density
            assert effective_density == pytest.approx(segment.current_density, rel=1e-9), (
                f"Single direction: effective_density={effective_density} != "
                f"current_density={segment.current_density}"
            )

    @given(
        length_m=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        width_m=st.floats(min_value=3.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=1, max_value=100),
        direction=st.sampled_from(["forward", "backward"]),
    )
    @settings(max_examples=100)
    def test_single_direction_effective_equals_current(
        self, length_m, width_m, count, direction
    ):
        """When all travelers move in the same direction, effective_density == current_density."""
        segment = PathSegment(name="test", length_m=length_m, width_m=width_m)

        # Add people in one direction only
        segment.add_people(count, direction=direction)

        # Step to compute densities
        result = segment.step()

        effective_density = result["density"]

        # All in same direction → no counter-flow penalty
        assert effective_density == pytest.approx(segment.current_density, rel=1e-9), (
            f"Single direction ({direction}): effective_density={effective_density} != "
            f"current_density={segment.current_density}"
        )


# ---------------------------------------------------------------------------
# Property 13: Width-Proportional Flow Distribution
# Validates: Requirements 6.4
# ---------------------------------------------------------------------------

class TestWidthProportionalFlowDistribution:
    """
    **Validates: Requirements 6.4**

    For any set of parallel paths connecting the same two stages and any total
    flow F, PathFlowModel.process_flow SHALL assign to each path a flow
    proportional to its width: flow_i = F × (width_i / sum(widths)).
    The sum of all assigned flows SHALL equal F (within integer rounding).
    """

    @given(
        widths=st.lists(
            st.floats(min_value=3.0, max_value=30.0, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=5,
        ),
        total_flow=st.integers(min_value=10, max_value=500),
        scale=st.floats(min_value=1.0, max_value=1.0),  # scale=1 so agent_count == real_people
    )
    @settings(max_examples=100)
    def test_flow_distributed_by_width(self, widths, total_flow, scale):
        """Each parallel path receives flow proportional to its width."""
        # Create parallel paths all connecting the same two stages
        path_configs = []
        for i, w in enumerate(widths):
            path_configs.append({
                "name": f"path_{i}",
                "length_m": 100.0,
                "width_m": w,
                "connects": [("StageA", "StageB")],
            })

        model = PathFlowModel(path_flow_configs=path_configs, scale=scale)

        # Record initial people counts (should be 0)
        initial_counts = {name: len(p.people_on_path) for name, p in model.paths.items()}

        # Process flow from StageA to StageB
        stage_flow = {("StageA", "StageB"): total_flow}
        model.process_flow(stage_flow)

        # Check distribution
        total_width = sum(widths)
        total_assigned = 0

        for i, w in enumerate(widths):
            path_name = f"path_{i}"
            people_added = len(model.paths[path_name].people_on_path) - initial_counts[path_name]
            expected = int(total_flow * (w / total_width))

            # Allow for integer rounding (±1)
            assert abs(people_added - expected) <= 1, (
                f"Path {path_name} (width={w}): expected ~{expected} people, got {people_added}. "
                f"total_flow={total_flow}, total_width={total_width}"
            )
            total_assigned += people_added

        # The sum of all assigned flows should equal total_flow within rounding
        # Due to int() truncation on each path, the sum may be less than total_flow
        # but should not exceed it
        assert total_assigned <= total_flow, (
            f"Total assigned {total_assigned} exceeds total flow {total_flow}"
        )
        # The loss due to rounding should be at most (num_paths - 1)
        max_rounding_loss = len(widths)
        assert total_flow - total_assigned <= max_rounding_loss, (
            f"Rounding loss {total_flow - total_assigned} exceeds max expected {max_rounding_loss}. "
            f"total_flow={total_flow}, assigned={total_assigned}"
        )
