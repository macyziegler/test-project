# Model Assumptions (Current Version)

## 1. Stage Selection

### Hybrid Weighting
- Each stage has a combined score: `artist_popularity × stage_weight`
- **Major stages** (user-selected): score is used as-is (linear)
- **Minor stages**: score is squared (suppresses small stages)
- Agents pick a stage probabilistically based on these scores plus small random noise
- This means two major stages with equally popular acts split the crowd roughly evenly, while minor stages need a significantly popular act to draw people

### Stage Weights
- User-configurable per stage (0.0 - 1.0)
- Represents the stage's draw independent of who's playing (size, production, brand, location)
- Example: Kinetic Field = 1.0, Casa Bacardi = 0.08

### Stage Tiers
- **Major**: Linear weighting — these stages compete head-to-head based on artist popularity
- **Minor**: Squared weighting — these stages are niche and need a specific draw to attract people
- User selects which tier each stage belongs to via dropdown

## 2. Crowd Movement Triggers

There are four reasons an agent reconsiders their stage choice. They are checked in this order each step:

### A. Set Ends (No Next Act)
- When a set ends and no next act starts within 15 minutes (3 steps), all agents at that stage reconsider
- If the next act starts within 15 minutes, agents stay put (waiting for changeover)

### B. Genre Clash
- When a new artist's genre differs from the previous artist at the same stage
- **Clash rate = 1 - genre_similarity**
- Genre similarity comes from the uploaded similarity matrix (0.0 = completely different crowds, 1.0 = identical fans)
- If no similarity matrix is uploaded, all genre changes default to 0.5 similarity (50% clash)
- Only triggers on the first step of the new artist's set
- Example: indie_dance → dubstep (similarity 0.1) = 90% of crowd reconsiders
- Example: dubstep → riddim (similarity 0.9) = 10% of crowd reconsiders
- Example: country → country (similarity 1.0) = 0% clash

### C. Set Change Surge
- When a new artist starts at ANY stage, agents at OTHER stages may be pulled toward it
- Surge chance is calculated from two factors:

**Factor 1 — Score gap (how much better is the new act vs what I'm watching?):**
```
score_gap_surge = min(50%, max(0%, (new_act_score - my_current_score) / my_current_score))
```
- If the new act is a big upgrade, surge is high (capped at 50%)
- If I'm already watching something equally good, surge is near 0%

**Factor 2 — Genre similarity (would I actually enjoy the new act?):**
```
genre_sim = similarity(my_current_genre, new_act_genre)
```
- If genres are similar, I'm likely to be interested
- If genres are completely different, I probably don't care

**Final surge chance:**
```
surge = score_gap_surge × genre_similarity
```

- No arbitrary percentages — entirely derived from popularity, stage weights, and genre similarity
- The 50% cap is the only fixed assumption: at most half the crowd at any stage will leave for a single new act
- Triggers BEFORE the set starts (anticipation, not reaction)
- Surge lead time is configurable: 5-60 minutes before set start (default 30 min)
- Larger venues = longer lead time (people leave earlier to walk farther)

### D. Wander Rate
- Each 5-minute step, a small percentage of agents randomly reconsider regardless of what's happening
- Configurable per stage via sidebar sliders
- Represents general restlessness, checking the schedule, following friends
- Typical values: 0.5-2% per step for main stages (campers), 3-5% for niche stages (explorers), 5-10% for small stages (come and go)

## 3. Genre Similarity Matrix

### Structure
- CSV file with genres as both rows and columns
- Each cell = similarity between two genres (0.0 to 1.0)
- Symmetric: similarity(A, B) = similarity(B, A)
- Diagonal = 1.0 (a genre is identical to itself)

### How It's Used
- **Genre clash**: clash_rate = 1 - similarity
- **Set change surge**: surge is multiplied by similarity between current and new genre
- **If not uploaded**: defaults to 0.5 similarity for all genre pairs (moderate clash on any change)

### Why It Matters
- EDC (many genres): high diversity means frequent, severe genre clashes that drive crowd movement
- Country festival (one genre): all similarities near 1.0, so genre barely affects movement — crowd moves based purely on artist popularity
- The matrix is the single control point for genre-driven behavior

## 4. Crowd Counting

### Intent-Based
- An agent counts toward a stage's crowd the moment they choose it
- Physical grid position is only used for heatmap visualization
- This represents demand ("who wants to be there"), which is the relevant metric for planning

### Scaling
- Simulation runs with reduced agents (default 2,000) for performance
- All counts multiplied by `attendance / num_agents`
- Assumes behavior scales linearly

## 5. Path Density (Analytical)

### Flow-Based Calculation
- Counts how many agents switched between stages that a path connects each step
- Density = total people flowing / (path width × path length)
- Each path is mapped to the stage pairs it connects

### Path Widths (Real Measurements, EDC Orlando)
- Kinetic to Circuit Path: 37 ft (11.3m)
- Casa to Stereo: 32 ft (9.8m)
- Casa to Stereo route 2: 20 ft (6.1m)

### Density Thresholds
- < 1.0 people/m: Normal flow
- 1.0 - 2.0 people/m: HIGH — uncomfortable
- > 2.0 people/m: CRITICAL — gridlock

## 6. Venue & Map

### From KML File
- Stage positions from placemarks (lat/lon → 200×200 grid)
- Obstacles from polygons (water, barriers, vendors, carnival)
- Walking paths from lines (expanded to corridors based on real width)
- Entry/Exit polygon defines where agents spawn
- Venue boundary defines walkable area

### Grid
- 200×200 cells derived from KML bounding box
- Preserves real-world distances and proportions
- Cell size varies by venue

## 7. Arrival

### Gradual Arrival Curve
- 3% at gates open
- Ramps to 90% by 60% through the festival
- 100% by 75% through the festival
- All agents spawn at the Entry/Exit polygon
- No early departures — simulation stops when last set ends

## 8. What Is NOT Modeled

- No stage capacity limits
- No physical crowd density slowdown
- No counter-flow friction on paths
- No group behavior (friends moving together)
- No food/water/restroom stops
- No VIP vs GA separation
- No weather effects
- No fatigue or rest
- No early departures or re-entry
- No sound bleed between stages
- No time-varying popularity within a set
- Path density is analytical (from flow counts), not from physical agent positions

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Intent-based crowd counting | Position-based was unreliable — agents couldn't reach distant stages fast enough on the grid |
| Analytical path density | Physical path-following caused agents to get stuck and broke crowd distribution |
| Hybrid major/minor weighting | Squaring everything made the #2 stage too weak; linear everything made small stages too strong |
| Genre clash = 1 - similarity | Clean formula, no arbitrary multiplier, fully controlled by the similarity matrix |
| Surge = score_gap × genre_similarity | Derived entirely from user inputs, no magic numbers except the 50% cap |
| 50% surge cap | Defensible: even for the most compelling new act, at least half the current crowd stays committed |
| 5-minute time steps | 3× more resolution than 15-min; captures set transitions precisely; matches real crowd reaction speed |
