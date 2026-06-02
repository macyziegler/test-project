"""
model_edc.py — Festival simulation model.

Simple, proven approach:
- Agents pick stages based on popularity × stage weight
- Crowd counting is intent-based (who chose which stage)
- Path density is calculated analytically from crowd flow between stages
"""
import mesa
import numpy as np
import math


def _dist(pos1, pos2):
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)


class Stage(mesa.Agent):
    def __init__(self, model, name, x, y, schedule):
        super().__init__(model)
        self.name = name
        self.x = x
        self.y = y
        self.schedule = schedule
        self.current_artist = None
        self.current_popularity = 0.0
        self.current_genre = None
        self.genre_clash = 0.0
        self.crowd_count = 0
        self.prev_crowd_count = 0

    def step(self):
        t = self.model.current_step
        prev_artist = self.current_artist
        prev_genre = self.current_genre
        self.current_artist = None
        self.current_popularity = 0.0
        self.current_genre = None
        self.genre_clash = 0.0
        for slot in self.schedule:
            if slot["start"] <= t < slot["end"]:
                self.current_artist = slot["artist"]
                self.current_popularity = slot["popularity"]
                self.current_genre = slot.get("genre", "edm")
                if self.current_artist != prev_artist and prev_genre and self.current_genre != prev_genre:
                    self.genre_clash = slot.get("genre_clash", 0.0)
                break
        self.prev_crowd_count = self.crowd_count
        self.crowd_count = sum(
            1 for a in self.model.agents
            if isinstance(a, Attendee) and a.target_stage == self
        )


class Attendee(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.target_stage = None
        self.prev_stage = None
        self.arrived = False
        self.switched_this_step = False
        self._pick_stage()

    def _pick_stage(self):
        self.prev_stage = self.target_stage
        active = [s for s in self.model.stages if s.current_popularity > 0]
        if not active:
            self.target_stage = self.random.choice(self.model.stages)
            self.arrived = False
            self.switched_this_step = (self.target_stage != self.prev_stage)
            return
        # hybrid weighting: linear for major stages, squared for minor
        raw = np.array([
            s.current_popularity * self.model.stage_weights.get(s.name, 1.0)
            for s in active
        ])
        weights = np.array([
            r if s.name in self.model.major_stages else r ** 2
            for r, s in zip(raw, active)
        ])
        probs = weights / weights.sum()
        noisy = probs + np.random.exponential(0.02, size=len(probs))
        noisy = noisy / noisy.sum()
        chosen_idx = np.random.choice(len(active), p=noisy)
        self.target_stage = active[chosen_idx]
        self.arrived = False
        self.switched_this_step = (self.target_stage != self.prev_stage)

    def step(self):
        self.switched_this_step = False

        if self.target_stage is None:
            self._pick_stage()
        elif self.target_stage.current_artist is None:
            t = self.model.current_step
            next_soon = any(
                slot["start"] <= t + 3 and slot["start"] > t
                for slot in self.target_stage.schedule
            )
            if not next_soon:
                self._pick_stage()
        else:
            # genre clash at current stage — rate = 1 - similarity
            if self.target_stage.genre_clash > 0 and self.random.random() < self.target_stage.genre_clash:
                self._pick_stage()
            else:
                # set change surge: check if a new act just started elsewhere
                surge = False
                if self.target_stage.current_artist and self.target_stage.current_popularity > 0:
                    my_score = (
                        self.target_stage.current_popularity
                        * self.model.stage_weights.get(self.target_stage.name, 1.0)
                    )
                    my_genre = self.target_stage.current_genre or "edm"

                    for s in self.model.stages:
                        if s == self.target_stage:
                            continue
                        for slot in s.schedule:
                            # surge triggers BEFORE set starts (anticipation)
                            steps_until_start = slot["start"] - self.model.current_step
                            if 0 < steps_until_start <= self.model.surge_lead_steps:
                                new_score = slot["popularity"] * self.model.stage_weights.get(s.name, 1.0)
                                # surge from score gap
                                score_surge = min(0.5, max(0, (new_score - my_score) / max(my_score, 0.01)))
                                # multiply by genre similarity
                                new_genre = slot.get("genre", "edm")
                                sim = self.model.genre_similarity.get(
                                    (my_genre, new_genre),
                                    self.model.genre_similarity.get((new_genre, my_genre), 0.5)
                                )
                                surge_chance = score_surge * sim
                                if self.random.random() < surge_chance:
                                    surge = True
                                    break
                        if surge:
                            break

                if surge:
                    self._pick_stage()
                elif self.random.random() < self.model.stage_wander_rate.get(self.target_stage.name, 0.10):
                    self._pick_stage()

        # move toward target for heatmap visualization
        if self.target_stage and self.pos:
            target_pos = (self.target_stage.x, self.target_stage.y)
            dist = _dist(self.pos, target_pos)
            if dist <= self.model.listen_radius:
                self.arrived = True
            else:
                self.arrived = False
                speed = self.random.randint(40, 80)
                self._move_direct(target_pos, speed)

    def _move_direct(self, target, speed):
        mask = self.model.obstacle_mask
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        norm = max(_dist(self.pos, target), 0.01)
        new_x = int(round(self.pos[0] + speed * dx / norm))
        new_y = int(round(self.pos[1] + speed * dy / norm))
        new_x = max(0, min(self.model.grid.width - 1, new_x))
        new_y = max(0, min(self.model.grid.height - 1, new_y))
        if not mask[new_y][new_x]:
            self.model.grid.move_agent(self, (new_x, new_y))
            return
        base_angle = math.atan2(dy, dx)
        for offset in [math.pi/6, -math.pi/6, math.pi/4, -math.pi/4, math.pi/3, -math.pi/3, math.pi/2, -math.pi/2]:
            angle = base_angle + offset
            nx = int(round(self.pos[0] + speed * math.cos(angle)))
            ny = int(round(self.pos[1] + speed * math.sin(angle)))
            nx = max(0, min(self.model.grid.width - 1, nx))
            ny = max(0, min(self.model.grid.height - 1, ny))
            if not mask[ny][nx]:
                self.model.grid.move_agent(self, (nx, ny))
                return


class FestivalModel(mesa.Model):
    def __init__(self, width, height, num_attendees, stage_configs,
                 obstacle_mask=None, listen_radius=4, stage_weights=None,
                 stage_wander_rate=None, path_cells=None, entry_cells=None,
                 path_routes=None, major_stages=None, genre_similarity=None,
                 surge_lead_steps=2):
        super().__init__()
        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.listen_radius = listen_radius
        self.current_step = 0
        self.obstacle_mask = obstacle_mask if obstacle_mask is not None else np.zeros((height, width), dtype=bool)
        self.stage_weights = stage_weights or {}
        self.stage_wander_rate = stage_wander_rate or {}
        self.path_cells = path_cells or set()
        self.entry_cells = list(entry_cells) if entry_cells else None
        self.path_routes = path_routes or []
        self.major_stages = set(major_stages) if major_stages else set()
        self.genre_similarity = genre_similarity or {}
        self.surge_lead_steps = surge_lead_steps
        self.density_grid = np.zeros((height, width), dtype=int)

        # track flow between stages for analytical path density
        self.stage_flow = {}  # {(from_stage, to_stage): count}

        self.stages = []
        for cfg in stage_configs:
            s = Stage(self, cfg["name"], cfg["x"], cfg["y"], cfg["schedule"])
            self.stages.append(s)
            self.grid.place_agent(s, (cfg["x"], cfg["y"]))

        self.walkable_cells = list(zip(*np.where(~self.obstacle_mask)))
        self.total_to_spawn = num_attendees
        self.spawned = 0
        self.arrival_schedule = self._build_arrival_schedule(num_attendees)

        self.datacollector = mesa.DataCollector(
            model_reporters={
                s.name: (lambda m, sname=s.name: next(
                    st.crowd_count for st in m.stages if st.name == sname
                )) for s in self.stages
            }
        )

    def _build_arrival_schedule(self, num_attendees):
        max_step = 1
        for s in self.stages:
            for slot in s.schedule:
                if slot["end"] > max_step:
                    max_step = slot["end"]
        ramp_end = int(max_step * 0.60)
        full_by = int(max_step * 0.75)
        schedule = [(1, int(num_attendees * 0.03))]
        steps_in_ramp = max(1, ramp_end - 1)
        for i in range(1, steps_in_ramp + 1):
            pct = 0.03 + 0.87 * (i / steps_in_ramp)
            schedule.append((1 + i, int(num_attendees * pct)))
        for step in range(ramp_end + 1, full_by + 1):
            pct = 0.90 + 0.10 * ((step - ramp_end) / max(1, full_by - ramp_end))
            schedule.append((step, int(num_attendees * pct)))
        schedule.append((full_by + 1, num_attendees))
        return schedule

    def _spawn_arrivals(self):
        target_count = 0
        for step_threshold, count in self.arrival_schedule:
            if self.current_step >= step_threshold:
                target_count = count
        to_spawn = target_count - self.spawned
        for _ in range(to_spawn):
            if self.entry_cells:
                idx = self.random.randrange(len(self.entry_cells))
                x, y = self.entry_cells[idx]
            else:
                idx = self.random.randrange(len(self.walkable_cells))
                y, x = self.walkable_cells[idx]
            a = Attendee(self)
            self.grid.place_agent(a, (x, y))
        self.spawned = target_count

    def step(self):
        self.current_step += 1
        self._spawn_arrivals()

        # reset flow tracking
        self.stage_flow = {}

        for s in self.stages:
            s.step()
        for a in self.agents:
            if isinstance(a, Attendee):
                a.step()
                # track stage switches for flow analysis
                if a.switched_this_step and a.prev_stage and a.target_stage:
                    key = (a.prev_stage.name, a.target_stage.name)
                    self.stage_flow[key] = self.stage_flow.get(key, 0) + 1

        self.datacollector.collect(self)
