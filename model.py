import mesa
import numpy as np
import math

# --------------------------------------------------------------------------- #
# STAGE AGENT — fixed position on the grid, hosts artists on a schedule
# --------------------------------------------------------------------------- #
class Stage(mesa.Agent):
    def __init__(self, model, name, x, y, schedule):
        """
        schedule: list of dicts, each with:
            {"artist": str, "popularity": float 0-1, "start": int, "end": int}
        """
        super().__init__(model)
        self.name = name
        self.x = x
        self.y = y
        self.schedule = schedule
        self.current_artist = None
        self.current_popularity = 0.0
        self.crowd_count = 0

    def step(self):
        t = self.model.current_step
        self.current_artist = None
        self.current_popularity = 0.0
        for slot in self.schedule:
            if slot["start"] <= t < slot["end"]:
                self.current_artist = slot["artist"]
                self.current_popularity = slot["popularity"]
                break
        # count only attendees who chose this stage AND have arrived
        self.crowd_count = sum(
            1 for a in self.model.agents
            if isinstance(a, Attendee) and a.target_stage == self and a.arrived
        )


# --------------------------------------------------------------------------- #
# ATTENDEE AGENT — picks a stage, walks toward it, stays for the set
# --------------------------------------------------------------------------- #
class Attendee(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.target_stage = None
        self.arrived = False
        self._pick_stage()

    def _pick_stage(self):
        """Choose a stage weighted by popularity cubed."""
        active = [s for s in self.model.stages if s.current_popularity > 0]
        if not active:
            self.target_stage = self.random.choice(self.model.stages)
            self.arrived = False
            return
        # cube weights: 0.05 → 0.000125 vs 1.0 → 1.0 (8000x difference)
        weights = np.array([s.current_popularity ** 3 for s in active])
        probs = weights / weights.sum()
        # small noise for variety
        noisy = probs + np.random.exponential(0.01, size=len(probs))
        noisy = noisy / noisy.sum()
        chosen_idx = np.random.choice(len(active), p=noisy)
        self.target_stage = active[chosen_idx]
        self.arrived = False

    def step(self):
        # re-evaluate: if set ended OR randomly reconsider (10% chance per step)
        if self.target_stage is None or self.target_stage.current_artist is None:
            self._pick_stage()
        elif self.random.random() < 0.10:
            self._pick_stage()

        if self.target_stage is None:
            return

        target_pos = (self.target_stage.x, self.target_stage.y)
        dist = _dist(self.pos, target_pos)

        if dist <= self.model.listen_radius:
            self.arrived = True
            return

        # move toward target (1-2 cells per step)
        self.arrived = False
        speed = self.random.randint(1, 2)
        dx = target_pos[0] - self.pos[0]
        dy = target_pos[1] - self.pos[1]
        norm = max(dist, 0.01)
        new_x = int(round(self.pos[0] + speed * dx / norm))
        new_y = int(round(self.pos[1] + speed * dy / norm))
        # clamp to grid
        new_x = max(0, min(self.model.grid.width - 1, new_x))
        new_y = max(0, min(self.model.grid.height - 1, new_y))
        self.model.grid.move_agent(self, (new_x, new_y))


# --------------------------------------------------------------------------- #
# FESTIVAL MODEL
# --------------------------------------------------------------------------- #
class FestivalModel(mesa.Model):
    def __init__(self, width, height, num_attendees, stage_configs, listen_radius=3):
        """
        stage_configs: list of dicts:
            {"name": str, "x": int, "y": int, "schedule": [...]}
        """
        super().__init__()
        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.listen_radius = listen_radius
        self.current_step = 0

        # create stages
        self.stages = []
        for cfg in stage_configs:
            s = Stage(self, cfg["name"], cfg["x"], cfg["y"], cfg["schedule"])
            self.stages.append(s)
            self.grid.place_agent(s, (cfg["x"], cfg["y"]))

        # create attendees at random positions
        for _ in range(num_attendees):
            a = Attendee(self)
            x = self.random.randrange(width)
            y = self.random.randrange(height)
            self.grid.place_agent(a, (x, y))

        # data collector — crowd count per stage each step
        self.datacollector = mesa.DataCollector(
            model_reporters={
                s.name: (lambda m, sname=s.name: next(
                    st.crowd_count for st in m.stages if st.name == sname
                )) for s in self.stages
            }
        )

    def step(self):
        self.current_step += 1
        # stages update first so attendees see current artist
        for s in self.stages:
            s.step()
        # then attendees move
        for a in self.agents:
            if isinstance(a, Attendee):
                a.step()
        self.datacollector.collect(self)


# --------------------------------------------------------------------------- #
# UTILITY
# --------------------------------------------------------------------------- #
def _dist(pos1, pos2):
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)
