"""
app.py — Festival Crowd Flow Simulator (Streamlit App)
Upload a venue map (KML) and lineup, run the simulation, explore results interactively.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import tempfile
import os
import math

from simulation.model import FestivalModel, Attendee, Stage
from data_io.parse_kml import parse_kml, latlon_to_grid
from simulation.path_flow import PathFlowModel
from data_io.parse_lineup import parse_lineup, parse_time, time_to_step, step_to_time, LineupParseResult
from data_io.path_connections import derive_path_connections
from config.defaults import *


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def _classify_density(density: float) -> str:
    """Classify a path density value using Fruin Level of Service thresholds."""
    if density >= DENSITY_HIGH_MAX:
        return "CRITICAL"
    elif density >= DENSITY_NORMAL_MAX:
        return "HIGH"
    return "Normal"


def build_bottleneck_events(df_crowd: pd.DataFrame, start_hour: int) -> list[dict]:
    """Build a list of bottleneck events from simulation results.
    
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


def detect_crossover_periods(stage_configs: list[dict], total_steps: int, start_hour: int) -> list[dict]:
    """Detect crossover periods — windows where 2+ set changes happen within CROSSOVER_WINDOW_STEPS.
    
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
                "time": step_to_time(slot["start"], start_hour),
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
                    "start_time": step_to_time(window_start, start_hour),
                    "end_time": step_to_time(min(window_end, total_steps), start_hour),
                    "set_changes": in_window,
                })
    return crossovers


# --------------------------------------------------------------------------- #
# PAGE CONFIG
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Festival Crowd Flow Simulator",
    page_icon="🎵",
    layout="wide"
)

st.title("🎵 Festival Crowd Flow Simulator")
st.markdown("Upload a venue map and lineup to simulate crowd flow, detect bottlenecks, and optimize scheduling.")

# --------------------------------------------------------------------------- #
# SIDEBAR — INPUTS
# --------------------------------------------------------------------------- #
st.sidebar.header("📁 Upload Venue & Lineup")

kml_file = st.sidebar.file_uploader("Upload venue KML file", type=["kml"])
lineup_file = st.sidebar.file_uploader("Upload lineup CSV", type=["csv"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Simulation Settings")
attendance = st.sidebar.number_input("Total Attendance", min_value=1000, max_value=500000, value=90000, step=5000)
num_agents = st.sidebar.slider("Simulation Agents", min_value=500, max_value=5000, value=2000, step=500,
                                help="More agents = more accurate but slower. 2000 is a good balance.")
grid_size = 200

# --------------------------------------------------------------------------- #
# LINEUP CSV FORMAT HELP
# --------------------------------------------------------------------------- #
with st.sidebar.expander("📋 Lineup CSV Format"):
    st.markdown("""
    Your CSV should have these columns:
    ```
    stage,artist,start_time,end_time,popularity,genre
    ```
    Example:
    ```
    Kinetic Field,Dom Dolla,10:25pm,11:50pm,1.0,house
    Kinetic Field,Subtronics,9:05pm,10:20pm,0.95,dubstep
    Circuit Grounds,Charlotte de Witte,9:45pm,10:45pm,0.95,techno
    ```
    - **popularity**: 0.0 to 1.0 (headliner = 1.0)
    - **genre**: optional, used for genre clash detection
    """)

# --------------------------------------------------------------------------- #
# PROCESS UPLOADS
# --------------------------------------------------------------------------- #
if kml_file and lineup_file:
    # save KML to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".kml") as tmp:
        tmp.write(kml_file.read())
        kml_path = tmp.name

    # parse KML
    try:
        stages_geo, obstacles_geo, paths_geo, bounds, entry_exit = parse_kml(kml_path)
        grid_stages, grid_obstacles, grid_paths, obstacle_mask, meters_per_cell, entry_cells = latlon_to_grid(
            stages_geo, obstacles_geo, paths_geo, bounds, grid_size=grid_size, entry_exit=entry_exit
        )
        stage_names = [s["name"] for s in grid_stages]
        stage_pos = {s["name"]: (s["x"], s["y"]) for s in grid_stages}

        st.success(f"✅ Venue loaded: {len(stage_names)} stages, {len(grid_obstacles)} obstacles, {len(grid_paths)} paths")

        # show venue info
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Stages found:**")
            for s in grid_stages:
                st.markdown(f"- {s['name']} (grid: {s['x']}, {s['y']})")
        with col2:
            st.markdown("**Obstacles:**")
            for o in grid_obstacles:
                st.markdown(f"- {o['name']} ({len(o['cells'])} cells)")
            st.markdown("**Paths:**")
            for p in grid_paths:
                st.markdown(f"- {p['name']} ({len(p['waypoints'])} waypoints)")

    except Exception as e:
        st.error(f"Error parsing KML: {e}")
        st.stop()

    # parse lineup CSV
    try:
        df_lineup = pd.read_csv(lineup_file)
        required_cols = ["stage", "artist", "start_time", "end_time", "popularity"]
        missing = [c for c in required_cols if c not in df_lineup.columns]
        if missing:
            st.error(f"Missing columns in lineup CSV: {missing}")
            st.stop()

        st.success(f"✅ Lineup loaded: {len(df_lineup)} sets across {df_lineup['stage'].nunique()} stages")

    except Exception as e:
        st.error(f"Error parsing lineup CSV: {e}")
        st.stop()

    # stage weight sliders
    st.sidebar.markdown("---")
    st.sidebar.header("🎚️ Stage Weights")
    st.sidebar.markdown("How much does each stage draw independent of artist? (0.0 - 1.0)")
    default_weights = {
        "Kinetic Field": 1.0,
        "Circuit Grounds": 0.95,
        "Stereo Bloom": 0.5,
        "Neon Garden": 0.5,
        "Casa Bacardi": 0.3,
    }
    stage_weights = {}
    for name in stage_names:
        stage_weights[name] = st.sidebar.slider(
            f"{name}", min_value=0.0, max_value=1.0, value=default_weights.get(name, 0.5), step=0.05, key=f"weight_{name}"
        )

    # wander rates per stage
    st.sidebar.markdown("---")
    st.sidebar.header("🚶 Crowd Behavior")
    st.sidebar.markdown("How likely someone leaves their stage each 5-min step. Lower = campers, Higher = wanderers.")
    default_wander = {
        "Kinetic Field": 0.01,
        "Circuit Grounds": 0.01,
        "Stereo Bloom": 0.03,
        "Neon Garden": 0.03,
        "Casa Bacardi": 0.05,
    }
    stage_wander_rate = {}
    for name in stage_names:
        stage_wander_rate[name] = st.sidebar.slider(
            f"{name} wander rate", 0.005, 0.10, default_wander.get(name, 0.02), 0.005, key=f"wander_{name}"
        )

    # surge timing
    st.sidebar.markdown("---")
    st.sidebar.header("⏱️ Surge Timing")
    surge_lead_time = st.sidebar.select_slider(
        "How early do people start moving to next set?",
        options=[5, 10, 15, 20, 30, 45, 60],
        value=30,
        format_func=lambda x: f"{x} min before ({x//5} steps)",
        key="surge_lead",
        help="Larger venues = people leave earlier. This controls when the set change surge triggers."
    )
    surge_lead_steps = surge_lead_time // 5

    st.sidebar.markdown("---")
    st.sidebar.header("🏟️ Stage Tiers")
    st.sidebar.markdown("**Major**: Big stages that compete evenly (linear weighting)  \n**Minor**: Niche stages that need a specific draw (squared weighting)")
    major_stages = []
    default_tiers = {"Kinetic Field": "Major", "Circuit Grounds": "Major"}
    for name in stage_names:
        tier = st.sidebar.selectbox(
            f"{name}", ["Major", "Minor"],
            index=0 if default_tiers.get(name, "Minor") == "Major" else 1,
            key=f"tier_{name}"
        )
        if tier == "Major":
            major_stages.append(name)

    # genre clash settings
    st.sidebar.markdown("---")
    st.sidebar.header("🎵 Genre Clash")
    st.sidebar.markdown("Upload a genre similarity matrix to control how much crowd turnover happens when genres change. Clash rate = 1 - similarity.")
    genre_sim_file = st.sidebar.file_uploader(
        "Upload genre similarity matrix (CSV)", type=["csv"], key="genre_sim",
        help="Matrix of genre-to-genre similarity (0.0-1.0). If not uploaded, all genre changes trigger 100% re-evaluation."
    )

    # parse genre similarity matrix
    genre_similarity = {}
    if genre_sim_file:
        try:
            df_sim = pd.read_csv(genre_sim_file, index_col=0)
            for g1 in df_sim.index:
                for g2 in df_sim.columns:
                    genre_similarity[(str(g1).strip(), str(g2).strip())] = float(df_sim.loc[g1, g2])
            st.sidebar.success(f"✅ Loaded {len(df_sim)} genres")
        except Exception as e:
            st.sidebar.error(f"Error loading genre matrix: {e}")

    # show lineup with calculated clash rates
    with st.expander("📋 View Lineup & Genre Clash Rates"):
        display_df = df_lineup.copy()
        clash_display = []
        for stage_name in display_df["stage"].unique():
            stage_df = display_df[display_df["stage"] == stage_name].sort_values("start_time")
            prev_g = None
            for idx, row in stage_df.iterrows():
                g = row.get("genre", None)
                if pd.notna(g) and prev_g and prev_g != g:
                    sim = genre_similarity.get(
                        (prev_g, g), genre_similarity.get((g, prev_g), 0.0)
                    )
                    clash = 1.0 - sim
                    clash_display.append({"idx": idx, "clash_rate": f"{clash:.0%}", "similarity": f"{sim:.1f}", "prev_genre": prev_g})
                else:
                    clash_display.append({"idx": idx, "clash_rate": "—", "similarity": "—", "prev_genre": "—"})
                prev_g = g if pd.notna(g) else prev_g
        if clash_display:
            clash_df = pd.DataFrame(clash_display).set_index("idx")
            display_df = display_df.join(clash_df)
        st.dataframe(display_df, use_container_width=True)

    # --------------------------------------------------------------------------- #
    # BUILD STAGE CONFIGS FROM CSV
    # --------------------------------------------------------------------------- #
    # find earliest start time
    all_times = []
    for _, row in df_lineup.iterrows():
        h, m = parse_time(row["start_time"])
        all_times.append(h * 60 + m)
        h, m = parse_time(row["end_time"])
        all_times.append(h * 60 + m)

    start_hour = min(all_times) // 60

    lineup_result = parse_lineup(df_lineup, stage_pos, genre_similarity, start_hour)
    for err in lineup_result.errors:
        st.error(err)
    if not lineup_result.success:
        st.stop()
    for warn in lineup_result.warnings:
        st.warning(warn)
    stage_configs = lineup_result.stage_configs
    total_steps = lineup_result.total_steps

    # combine path cells and build route info
    all_path_cells = set()
    path_routes = []
    for p in grid_paths:
        all_path_cells.update(p["cells"])
        path_routes.append({"name": p["name"], "waypoints": p["waypoints"]})

    # --------------------------------------------------------------------------- #
    # DERIVE PATH-TO-STAGE CONNECTIONS (Requirement 3.3 — shown before simulation)
    # --------------------------------------------------------------------------- #
    derived_configs = derive_path_connections(grid_paths, grid_stages, meters_per_cell, proximity_threshold_cells=DEFAULT_PROXIMITY_THRESHOLD_CELLS)
    derived_lookup = {cfg["name"]: cfg for cfg in derived_configs}

    # display any warnings from connection derivation
    for cfg in derived_configs:
        for warning_msg in cfg.get("warnings", []):
            st.warning(f"⚠️ Path connection warning: {warning_msg}")

    # show detected connections so the user can verify them before running
    with st.expander("🔗 Detected Path-to-Stage Connections"):
        for cfg in derived_configs:
            connects = cfg.get("connects", [])
            if connects:
                pairs = ", ".join(f"{a} ↔ {b}" for a, b in connects if connects.index((a, b)) % 2 == 0)
                st.markdown(f"**{cfg['name']}** ({cfg['length_m']:.0f} m): {pairs}")
            else:
                st.markdown(f"**{cfg['name']}**: _(no connections detected)_")

    # --------------------------------------------------------------------------- #
    # RUN SIMULATION
    # --------------------------------------------------------------------------- #
    if st.button("🚀 Run Simulation", type="primary"):
        scale = attendance / num_agents

        progress = st.progress(0, text="Running simulation...")
        model = FestivalModel(
            grid_size, grid_size, num_agents, stage_configs,
            obstacle_mask=obstacle_mask, listen_radius=15,
            stage_weights=stage_weights, stage_wander_rate=stage_wander_rate,
            path_cells=all_path_cells, entry_cells=entry_cells,
            path_routes=path_routes, major_stages=major_stages,
            genre_similarity=genre_similarity,
            surge_lead_steps=surge_lead_steps
        )

        # build path flow configs from derived connections
        path_flow_configs = []
        for p in grid_paths:
            derived = derived_lookup.get(p["name"], {})
            path_flow_configs.append({
                "name": p["name"],
                "length_m": derived.get("length_m", 150.0),
                "width_m": derived.get("width_m", p.get("width_m", 8.0)),
                "connects": derived.get("connects", []),
            })

        path_flow = PathFlowModel(path_flow_configs, scale=scale, step_duration_min=5)

        # capture data
        all_frames = []
        crowd_data = []

        for step in range(1, total_steps + 1):
            model.step()
            progress.progress(step / total_steps, text=f"Simulating step {step}/{total_steps}...")

            # crowd counts
            to_spawn_count = model.spawned
            row = {"step": step, "time": step_to_time(step, start_hour)}
            for s in model.stages:
                row[s.name] = int(s.crowd_count * scale)

            # agents in transit
            moving = sum(1 for a in model.agents if isinstance(a, Attendee) and not a.arrived)
            row["in_transit"] = int(moving * scale)
            row["in_transit_pct"] = round(moving / max(model.spawned, 1) * 100, 1)

            # path density — pipe model: feed flow into paths, advance, read density
            path_flow.process_flow(model.stage_flow)
            path_results = path_flow.step()

            # debug: track total flow
            if step <= 3 or step % 20 == 0:
                total_flow = sum(model.stage_flow.values()) if model.stage_flow else 0
                print(f"  Step {step}: stage_flow entries={len(model.stage_flow)}, total_switches={total_flow}, paths={path_results}")

            for p_name, p_result in path_results.items():
                row[f"path_{p_name}_density"] = round(p_result["density"], 3)
                row[f"path_{p_name}_total"] = p_result["total_on_path"]
                row[f"path_{p_name}_speed"] = round(p_result["speed"], 1)

            crowd_data.append(row)

            # capture agent positions for animation
            xs, ys, colors = [], [], []
            stage_color_map = {}
            color_list = ["#FF4444", "#44AAFF", "#AA44FF", "#44DD44", "#FFAA00", "#FF88CC", "#88FFCC"]
            for i, cfg in enumerate(stage_configs):
                stage_color_map[cfg["name"]] = color_list[i % len(color_list)]

            for a in model.agents:
                if isinstance(a, Attendee):
                    xs.append(a.pos[0])
                    ys.append(a.pos[1])
                    colors.append(stage_color_map.get(
                        a.target_stage.name if a.target_stage else "", "#888888"
                    ))

            all_frames.append({"xs": xs, "ys": ys, "colors": colors})

        progress.empty()
        st.success("✅ Simulation complete!")

        df_crowd = pd.DataFrame(crowd_data)

        # store in session state
        st.session_state["df_crowd"] = df_crowd
        st.session_state["all_frames"] = all_frames
        st.session_state["stage_configs"] = stage_configs
        st.session_state["stage_color_map"] = stage_color_map
        st.session_state["grid_stages"] = grid_stages
        st.session_state["grid_obstacles"] = grid_obstacles
        st.session_state["grid_paths"] = grid_paths
        st.session_state["obstacle_mask"] = obstacle_mask
        st.session_state["stage_pos"] = stage_pos
        st.session_state["total_steps"] = total_steps
        st.session_state["start_hour"] = start_hour
        st.session_state["stages_geo"] = stages_geo
        st.session_state["bounds"] = bounds
        st.session_state["meters_per_cell"] = meters_per_cell
        st.session_state["scale"] = scale

    # --------------------------------------------------------------------------- #
    # DISPLAY RESULTS
    # --------------------------------------------------------------------------- #
    if "df_crowd" in st.session_state:
        df_crowd = st.session_state["df_crowd"]
        all_frames = st.session_state["all_frames"]
        stage_color_map = st.session_state["stage_color_map"]
        total_steps = st.session_state["total_steps"]
        s_hour = st.session_state["start_hour"]

        st.markdown("---")

        # TABS
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Crowd Chart", "🛰️ Crowd Heatmap", "⚠️ Bottlenecks", "📋 Raw Data"])

        # TAB 1: CROWD CHART
        with tab1:
            st.subheader("Crowd Distribution Over Time")
            stage_cols = [c for c in df_crowd.columns if c not in ["step", "time", "in_transit", "in_transit_pct"] and "path_" not in c]

            fig = go.Figure()
            for col in stage_cols:
                fig.add_trace(go.Scatter(
                    x=df_crowd["time"], y=df_crowd[col],
                    name=col, mode="lines", line=dict(width=3)
                ))
            fig.update_layout(
                xaxis_title="Time", yaxis_title="Estimated Crowd",
                height=500, template="plotly_dark",
                legend=dict(orientation="h", yanchor="bottom", y=1.02)
            )
            st.plotly_chart(fig, use_container_width=True)

        # TAB 2: SATELLITE HEATMAP
        with tab2:
            st.subheader("Crowd Heatmap — Satellite View")

            # auto-play controls
            col_play, col_speed = st.columns([1, 1])
            with col_play:
                auto_play = st.checkbox("▶️ Auto-play", value=False, key="auto_play")
            with col_speed:
                play_speed = st.selectbox("Speed", ["Slow (3s)", "Normal (1.5s)", "Fast (0.5s)"], index=1, key="play_speed")

            speed_map = {"Slow (3s)": 3.0, "Normal (1.5s)": 1.5, "Fast (0.5s)": 0.5}
            delay = speed_map[play_speed]

            # step selector
            step_labels = {i: f"Step {i+1} — {step_to_time(i+1, s_hour)}" for i in range(total_steps)}

            if auto_play:
                import time as time_module
                step_container = st.empty()
                map_container = st.empty()
                info_container = st.empty()
                playing_container = st.empty()

                for step_idx in range(total_steps):
                    time_label = step_to_time(step_idx + 1, s_hour)
                    step_container.markdown(f"### Step {step_idx + 1} — {time_label}")

                    # now playing info
                    playing_lines = ""
                    for cfg in st.session_state["stage_configs"]:
                        current_artist = "—"
                        is_change = False
                        for slot in cfg["schedule"]:
                            if slot["start"] <= step_idx + 1 < slot["end"]:
                                current_artist = slot["artist"]
                                if slot["start"] == step_idx + 1:
                                    is_change = True
                                break
                        change_flag = " 🔄 SET CHANGE" if is_change else ""
                        clash_flag = ""
                        if is_change:
                            for slot in cfg["schedule"]:
                                if slot["start"] == step_idx + 1 and slot.get("genre_clash", 0) > 0:
                                    clash_flag = " ⚡ GENRE CLASH"
                        playing_lines += f"**{cfg['name']}**: {current_artist}{change_flag}{clash_flag}  \n"
                    playing_container.markdown(playing_lines)

                    # build map
                    frame = all_frames[step_idx]
                    venue_bounds = st.session_state["bounds"]
                    all_lats_b = [c[0] for c in venue_bounds]
                    all_lons_b = [c[1] for c in venue_bounds]
                    bmin_lat, bmax_lat = min(all_lats_b), max(all_lats_b)
                    bmin_lon, bmax_lon = min(all_lons_b), max(all_lons_b)
                    lat_pad = (bmax_lat - bmin_lat) * 0.05
                    lon_pad = (bmax_lon - bmin_lon) * 0.05
                    min_lat_p = bmin_lat - lat_pad
                    max_lat_p = bmax_lat + lat_pad
                    min_lon_p = bmin_lon - lon_pad
                    max_lon_p = bmax_lon + lon_pad

                    def grid_to_latlon(gx, gy):
                        lon = min_lon_p + (gx / (grid_size - 1)) * (max_lon_p - min_lon_p)
                        lat = min_lat_p + (gy / (grid_size - 1)) * (max_lat_p - min_lat_p)
                        return lat, lon

                    agent_lats, agent_lons = [], []
                    for gx, gy in zip(frame["xs"], frame["ys"]):
                        lat, lon = grid_to_latlon(gx, gy)
                        agent_lats.append(lat)
                        agent_lons.append(lon)

                    fig_map = go.Figure()
                    agent_scale = st.session_state["scale"]
                    z_values = [agent_scale] * len(agent_lats)
                    fig_map.add_trace(go.Densitymapbox(
                        lat=agent_lats, lon=agent_lons,
                        z=z_values, radius=20,
                        colorscale=[[0.0,"rgba(0,0,0,0)"],[0.1,"rgba(0,150,0,0.3)"],[0.2,"rgba(255,255,0,0.4)"],[0.4,"rgba(255,165,0,0.6)"],[0.6,"rgba(255,69,0,0.7)"],[0.8,"rgba(255,0,0,0.85)"],[1.0,"rgba(139,0,0,0.95)"]],
                        zmin=0, zmax=agent_scale * 8,
                        showscale=True, colorbar=dict(title="Est. People"), name="Crowd",
                    ))
                    for s_geo in st.session_state["stages_geo"]:
                        fig_map.add_trace(go.Scattermapbox(
                            lat=[s_geo["lat"]], lon=[s_geo["lon"]], mode="markers+text",
                            marker=dict(size=16, color=stage_color_map.get(s_geo["name"], "white"), symbol="circle"),
                            text=[s_geo["name"]], textposition="top center",
                            textfont=dict(size=12, color="white"),
                            name=s_geo["name"], showlegend=True
                        ))
                    center_lat = (bmin_lat + bmax_lat) / 2
                    center_lon = (bmin_lon + bmax_lon) / 2
                    fig_map.update_layout(
                        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=16.5),
                        height=750, margin=dict(l=0, r=0, t=30, b=0),
                        legend=dict(bgcolor="rgba(0,0,0,0.7)", font=dict(color="white"))
                    )
                    map_container.plotly_chart(fig_map, use_container_width=True)

                    # crowd counts
                    row_data = df_crowd.iloc[step_idx]
                    info_cols = info_container.columns(len(stage_color_map))
                    for i, (name, color) in enumerate(stage_color_map.items()):
                        if name in row_data:
                            info_cols[i].metric(name, f"{int(row_data[name]):,}")

                    time_module.sleep(delay)

            else:
                # manual slider mode
                step_idx = st.select_slider(
                    "Time", options=list(range(total_steps)),
                    format_func=lambda x: step_labels[x],
                    key="map_slider"
                )
                time_label = step_to_time(step_idx + 1, s_hour)
                st.markdown(f"### Step {step_idx + 1} — {time_label}")

                # now playing display
                now_cols = st.columns(len(st.session_state["stage_configs"]))
                for i, cfg in enumerate(st.session_state["stage_configs"]):
                    current_artist = "—"
                    is_change = False
                    clash = False
                    for slot in cfg["schedule"]:
                        if slot["start"] <= step_idx + 1 < slot["end"]:
                            current_artist = slot["artist"]
                            if slot["start"] == step_idx + 1:
                                is_change = True
                                if slot.get("genre_clash", 0) > 0:
                                    clash = True
                            break
                    status = "🎵 Now Playing"
                    if is_change and clash:
                        status = "🔄⚡ SET CHANGE + GENRE CLASH"
                    elif is_change:
                        status = "🔄 SET CHANGE"
                    now_cols[i].markdown(f"**{cfg['name']}**  \n{current_artist}  \n*{status}*")

                frame = all_frames[step_idx]
                venue_bounds = st.session_state["bounds"]

            # convert grid positions back to lat/lon
            all_lats_b = [c[0] for c in venue_bounds]
            all_lons_b = [c[1] for c in venue_bounds]
            min_lat, max_lat = min(all_lats_b), max(all_lats_b)
            min_lon, max_lon = min(all_lons_b), max(all_lons_b)
            lat_pad = (max_lat - min_lat) * 0.05
            lon_pad = (max_lon - min_lon) * 0.05
            min_lat_p = min_lat - lat_pad
            max_lat_p = max_lat + lat_pad
            min_lon_p = min_lon - lon_pad
            max_lon_p = max_lon + lon_pad

            def grid_to_latlon(gx, gy):
                lon = min_lon_p + (gx / (grid_size - 1)) * (max_lon_p - min_lon_p)
                lat = min_lat_p + (gy / (grid_size - 1)) * (max_lat_p - min_lat_p)
                return lat, lon

            agent_lats = []
            agent_lons = []
            for gx, gy in zip(frame["xs"], frame["ys"]):
                lat, lon = grid_to_latlon(gx, gy)
                agent_lats.append(lat)
                agent_lons.append(lon)

            fig_map = go.Figure()

            # density heatmap layer — scaled to real attendance
            # each agent represents (attendance/num_agents) real people
            # radius in pixels controls visual spread
            agent_scale = st.session_state["scale"]
            mpc = st.session_state["meters_per_cell"]
            # z-values represent scaled crowd count per agent position
            z_values = [agent_scale] * len(agent_lats)  # each dot = scale people

            fig_map.add_trace(go.Densitymapbox(
                lat=agent_lats, lon=agent_lons,
                z=z_values,
                radius=20,
                colorscale=[
                    [0.0, "rgba(0,0,0,0)"],        # 0 — empty
                    [0.1, "rgba(0,150,0,0.3)"],     # comfortable
                    [0.2, "rgba(255,255,0,0.4)"],   # noticeable
                    [0.4, "rgba(255,165,0,0.6)"],   # crowded (2.0/m²)
                    [0.6, "rgba(255,69,0,0.7)"],    # uncomfortable (3.0/m²)
                    [0.8, "rgba(255,0,0,0.85)"],    # packed (4.0/m²)
                    [1.0, "rgba(139,0,0,0.95)"],    # dangerous (5.0+/m²)
                ],
                zmin=0,
                zmax=agent_scale * 8,  # fixed scale across all steps
                showscale=True,
                colorbar=dict(
                    title="Est. People",
                    tickvals=[0, agent_scale*2, agent_scale*4, agent_scale*6, agent_scale*8],
                    ticktext=["0", "Comfortable", "Crowded", "Uncomfortable", "Packed"],
                ),
                name="Crowd Density",
            ))

            # stage markers
            for s_geo in st.session_state["stages_geo"]:
                fig_map.add_trace(go.Scattermapbox(
                    lat=[s_geo["lat"]], lon=[s_geo["lon"]],
                    mode="markers+text",
                    marker=dict(
                        size=16,
                        color=stage_color_map.get(s_geo["name"], "white"),
                        symbol="circle",
                    ),
                    text=[s_geo["name"]], textposition="top center",
                    textfont=dict(size=12, color="white"),
                    name=s_geo["name"], showlegend=True
                ))

            center_lat = (min_lat + max_lat) / 2
            center_lon = (min_lon + max_lon) / 2

            fig_map.update_layout(
                mapbox=dict(
                    style="open-street-map",
                    center=dict(lat=center_lat, lon=center_lon),
                    zoom=16.5,
                ),
                height=750,
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(
                    bgcolor="rgba(0,0,0,0.7)",
                    font=dict(color="white"),
                )
            )
            st.plotly_chart(fig_map, use_container_width=True)

            # show crowd counts below the map
            st.markdown("**Crowd at this moment:**")
            row_data = df_crowd.iloc[step_idx]
            cols = st.columns(len(stage_color_map))
            for i, (name, color) in enumerate(stage_color_map.items()):
                if name in row_data:
                    cols[i].metric(name, f"{int(row_data[name]):,}")

        # TAB 3: BOTTLENECKS
        with tab3:
            st.subheader("⚠️ Bottleneck Report")

            # Retrieve stage_configs and timing info from session state
            _stage_configs = st.session_state["stage_configs"]
            _total_steps = st.session_state["total_steps"]
            _start_hour = st.session_state["start_hour"]

            # Build bottleneck events and detect crossover periods
            bottleneck_events = build_bottleneck_events(df_crowd, _start_hour)
            crossover_periods = detect_crossover_periods(_stage_configs, _total_steps, _start_hour)

            if not bottleneck_events:
                st.success("✅ No paths exceeded the HIGH density threshold during this simulation.")
            else:
                # --- Event Table with color-coded rows ---
                st.markdown("### Bottleneck Events Timeline")
                events_df = pd.DataFrame(bottleneck_events)
                events_display = events_df[["path", "time", "density", "classification"]].rename(
                    columns={
                        "path": "Path",
                        "time": "Time",
                        "density": "Density (people/m²)",
                        "classification": "Level",
                    }
                )

                def _highlight_level(row):
                    if row["Level"] == "CRITICAL":
                        return ["background-color: rgba(255, 0, 0, 0.3); color: red"] * len(row)
                    elif row["Level"] == "HIGH":
                        return ["background-color: rgba(255, 165, 0, 0.3); color: orange"] * len(row)
                    return [""] * len(row)

                styled_df = events_display.style.apply(_highlight_level, axis=1)
                st.dataframe(styled_df, use_container_width=True)

            # --- Per-path density line chart with threshold lines and crossover bands ---
            path_density_cols = [c for c in df_crowd.columns if c.endswith("_density")]

            if path_density_cols:
                st.markdown("### Per-Path Density Over Time")
                fig_path = go.Figure()

                for col in path_density_cols:
                    path_name = col.replace("path_", "").replace("_density", "")
                    fig_path.add_trace(go.Scatter(
                        x=df_crowd["time"], y=df_crowd[col],
                        name=path_name, mode="lines", line=dict(width=2)
                    ))

                # Horizontal threshold lines
                fig_path.add_hline(
                    y=DENSITY_NORMAL_MAX, line_dash="dash", line_color="orange",
                    annotation_text="HIGH threshold",
                    annotation_position="top left",
                )
                fig_path.add_hline(
                    y=DENSITY_HIGH_MAX, line_dash="dash", line_color="red",
                    annotation_text="CRITICAL threshold",
                    annotation_position="top left",
                )

                # Highlight crossover periods as shaded vertical bands
                for cp in crossover_periods:
                    # Map crossover start/end steps to time labels for x-axis
                    cp_start_time = step_to_time(cp["start_step"], _start_hour)
                    cp_end_time = step_to_time(cp["end_step"], _start_hour)

                    # Build label showing which set changes overlap
                    change_labels = [f"{c['stage']}: {c['artist']}" for c in cp["set_changes"]]
                    band_label = " / ".join(change_labels[:3])  # limit to 3 for readability
                    if len(change_labels) > 3:
                        band_label += f" (+{len(change_labels) - 3} more)"

                    fig_path.add_vrect(
                        x0=cp_start_time, x1=cp_end_time,
                        fillcolor="rgba(255, 255, 0, 0.1)",
                        line_width=0,
                        annotation_text=band_label,
                        annotation_position="top left",
                        annotation_font_size=9,
                        annotation_font_color="yellow",
                    )

                fig_path.update_layout(
                    xaxis_title="Time",
                    yaxis_title="Density (people/m²)",
                    height=500,
                    template="plotly_dark",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig_path, use_container_width=True)

            # --- Transit chart ---
            st.markdown("### Crowd In Transit")
            fig_transit = go.Figure()
            fig_transit.add_trace(go.Scatter(
                x=df_crowd["time"], y=df_crowd["in_transit_pct"],
                name="% In Transit", fill="tozeroy", line=dict(color="#FF6B6B")
            ))
            fig_transit.update_layout(
                xaxis_title="Time", yaxis_title="% of Crowd Moving",
                height=300, template="plotly_dark"
            )
            st.plotly_chart(fig_transit, use_container_width=True)

        # TAB 4: RAW DATA
        with tab4:
            st.subheader("Full Simulation Data")
            st.dataframe(df_crowd, use_container_width=True)

            csv = df_crowd.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, "crowd_simulation.csv", "text/csv")

    # cleanup temp file
    try:
        os.unlink(kml_path)
    except:
        pass

else:
    # no files uploaded yet — show instructions
    st.markdown("---")
    st.markdown("""
    ## Getting Started

    1. **Upload a venue KML file** — Create in Google Earth with:
       - 📍 Placemarks for each stage
       - 📐 Polygons for obstacles (water, barriers, vendor areas)
       - 📏 Lines for walking paths between stages

    2. **Upload a lineup CSV** with columns:
       ```
       stage, artist, start_time, end_time, popularity, genre
       ```

    3. **Adjust settings** in the sidebar — stage weights, attendance, crowd behavior

    4. **Run the simulation** and explore the results!

    ---
    ### Example Lineup CSV
    """)

    example_df = pd.DataFrame({
        "stage": ["Main Stage", "Main Stage", "Second Stage", "Second Stage"],
        "artist": ["Opener", "Headliner", "Support Act", "Co-Headliner"],
        "start_time": ["3:00pm", "9:00pm", "4:00pm", "8:00pm"],
        "end_time": ["5:00pm", "11:00pm", "6:00pm", "10:00pm"],
        "popularity": [0.3, 1.0, 0.4, 0.8],
        "genre": ["house", "dubstep", "techno", "dnb"]
    })
    st.dataframe(example_df, use_container_width=True)
