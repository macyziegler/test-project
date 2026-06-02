"""
path_flow.py — Path congestion simulation.

Models each path as a pipe that people enter, traverse, and exit.
Tracks density over time with realistic walk speeds and feedback loops.
"""
import math


class PathSegment:
    """A single walkway between two areas. People enter, walk through, and exit."""

    def __init__(self, name, length_m, width_m, step_duration_min=5):
        self.name = name
        self.length_m = length_m
        self.width_m = width_m
        self.step_duration_min = step_duration_min
        self.area_m2 = length_m * width_m

        # people currently on the path, each with remaining steps to exit
        # list of {"remaining_steps": int, "direction": str}
        self.people_on_path = []

        # metrics per step
        self.current_density = 0.0          # people per m²
        self.current_flow_rate = 0          # people entering this step
        self.current_total_on_path = 0      # total people on path right now
        self.current_walk_speed_mpm = 80.0  # meters per minute (current, after slowdown)

        # history for reporting
        self.history = []

    def _base_walk_speed(self):
        """Normal walking speed in meters per minute in a festival crowd."""
        return 50.0  # ~3 km/h, slower than normal due to crowd, stopping, looking around

    def _density_adjusted_speed(self, density_per_m2):
        """Reduce walking speed based on crowd density.

        Based on Fruin's Level of Service:
        - < 0.5 /m²: free flow (50 m/min)
        - 0.5-1.0: slightly restricted (40 m/min)
        - 1.0-2.0: restricted movement (25 m/min)
        - 2.0-3.0: severely restricted (15 m/min)
        - 3.0-4.0: shuffling (8 m/min)
        - 4.0+: gridlock (3 m/min)
        """
        if density_per_m2 < 0.5:
            return 50.0
        elif density_per_m2 < 1.0:
            return 40.0
        elif density_per_m2 < 2.0:
            return 25.0
        elif density_per_m2 < 3.0:
            return 15.0
        elif density_per_m2 < 4.0:
            return 8.0
        else:
            return 3.0

    def _steps_to_traverse(self, speed_mpm):
        """How many 5-min steps to walk the full path length at given speed."""
        if speed_mpm <= 0:
            return 100  # effectively stuck
        time_min = self.length_m / speed_mpm
        steps = max(1, math.ceil(time_min / self.step_duration_min))
        return steps

    def add_people(self, count, direction="forward"):
        """Add people entering the path this step."""
        # cap entries based on path capacity — can't exceed physical space
        max_capacity = int(self.area_m2 * 5.0)  # absolute max: 5 people/m² everywhere
        current_count = len(self.people_on_path)
        available = max(0, max_capacity - current_count)
        actual_entering = min(count, available)

        # calculate how long they'll take based on current density
        speed = self._density_adjusted_speed(self.current_density)
        steps_needed = self._steps_to_traverse(speed)

        for _ in range(actual_entering):
            self.people_on_path.append({
                "remaining_steps": steps_needed,
                "direction": direction
            })
        self.current_flow_rate += actual_entering

    def step(self):
        """Advance one time step. Move people through, update density."""
        self.current_flow_rate = 0
        exited = 0

        # recalculate speed based on current density (feedback loop)
        speed = self._density_adjusted_speed(self.current_density)
        self.current_walk_speed_mpm = speed

        # advance everyone on the path
        still_on_path = []
        for person in self.people_on_path:
            person["remaining_steps"] -= 1
            if person["remaining_steps"] <= 0:
                exited += 1
            else:
                still_on_path.append(person)

        self.people_on_path = still_on_path
        self.current_total_on_path = len(self.people_on_path)

        # update density
        self.current_density = self.current_total_on_path / max(self.area_m2, 1)

        # count counter-flow (people going opposite directions)
        forward = sum(1 for p in self.people_on_path if p["direction"] == "forward")
        backward = self.current_total_on_path - forward
        counter_flow_ratio = min(forward, backward) / max(self.current_total_on_path, 1)

        # counter-flow penalty: if significant two-way traffic, effective density is higher
        effective_density = self.current_density * (1 + counter_flow_ratio * 0.5)

        # store history
        self.history.append({
            "total_on_path": self.current_total_on_path,
            "density_per_m2": round(self.current_density, 3),
            "effective_density": round(effective_density, 3),
            "walk_speed_mpm": round(self.current_walk_speed_mpm, 1),
            "entered": self.current_flow_rate,
            "exited": exited,
            "forward": forward,
            "backward": backward,
            "counter_flow_ratio": round(counter_flow_ratio, 2),
        })

        return {
            "density": effective_density,
            "total_on_path": self.current_total_on_path,
            "speed": self.current_walk_speed_mpm,
            "exited": exited,
        }


class PathFlowModel:
    """Manages all path segments and distributes crowd flow between them."""

    def __init__(self, path_flow_configs, scale=1.0, step_duration_min=5):
        """
        path_configs: list of {
            "name": str,
            "length_m": float,
            "width_m": float,
            "connects": [(stage_a, stage_b), ...]  # which stage pairs use this path
        }
        scale: multiplier from agents to real people
        """
        self.scale = scale
        self.step_duration_min = step_duration_min
        self.paths = {}
        self.path_connections = {}  # (stage_a, stage_b) -> [path_name, ...]

        for cfg in path_flow_configs:
            self.paths[cfg["name"]] = PathSegment(
                name=cfg["name"],
                length_m=cfg["length_m"],
                width_m=cfg["width_m"],
                step_duration_min=step_duration_min
            )
            for pair in cfg["connects"]:
                # store both directions
                key_fwd = (pair[0], pair[1])
                key_rev = (pair[1], pair[0])
                if key_fwd not in self.path_connections:
                    self.path_connections[key_fwd] = []
                if key_rev not in self.path_connections:
                    self.path_connections[key_rev] = []
                self.path_connections[key_fwd].append(cfg["name"])
                self.path_connections[key_rev].append(cfg["name"])

    def process_flow(self, stage_flow):
        """
        Take the stage_flow dict from the main model and distribute people onto paths.

        stage_flow: {(from_stage, to_stage): agent_count}
        """
        for (from_stage, to_stage), agent_count in stage_flow.items():
            real_people = int(agent_count * self.scale)
            if real_people <= 0:
                continue

            # direct lookup — both directions are stored
            key = (from_stage, to_stage)
            path_names = self.path_connections.get(key, [])

            if not path_names:
                continue

            # deduplicate path names
            path_names = list(set(path_names))

            # split flow across available paths (weighted by width)
            total_width = sum(self.paths[pn].width_m for pn in path_names)
            for pn in path_names:
                share = self.paths[pn].width_m / total_width
                people_on_this_path = int(real_people * share)

                # determine direction
                direction = "forward" if from_stage < to_stage else "backward"
                self.paths[pn].add_people(people_on_this_path, direction)

    def step(self):
        """Advance all paths one step. Returns density report."""
        results = {}
        for name, path in self.paths.items():
            results[name] = path.step()
        return results

    def get_report(self):
        """Get full history for all paths."""
        report = {}
        for name, path in self.paths.items():
            report[name] = {
                "history": path.history,
                "length_m": path.length_m,
                "width_m": path.width_m,
            }
        return report
