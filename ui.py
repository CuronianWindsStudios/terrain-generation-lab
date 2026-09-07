"""Experiment UI for the terrain generator. Start with: streamlit run ui.py"""
from __future__ import annotations

import random
from pathlib import Path

import streamlit as st

from terrain.config import Config, GenerationError, UNREAL_SIZES
from terrain.experiment import build_overrides, generate, save_result

WORK_DIR = Path("out") / "ui"
DEFAULTS = Config()
SIZES = [s for s in UNREAL_SIZES if s <= 2017]

st.set_page_config(page_title="Terrain experiments", layout="wide")

if "seed" not in st.session_state:
    st.session_state.seed = DEFAULTS.seed


def set_seed(seed: int) -> None:
    """Runs as a button callback, before the rerun, so the seed widget accepts the change."""
    st.session_state.seed = int(seed)
    st.session_state.pending_run = True


def random_seed() -> None:
    set_seed(random.randint(0, 999_999))


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("Terrain experiments")
    st.number_input("Seed", min_value=0, max_value=999_999, step=1, key="seed")
    st.button("Random seed", on_click=random_seed, width="stretch")
    size = st.selectbox("Size", SIZES, index=SIZES.index(DEFAULTS.size))
    diameter = st.slider("Circle diameter %", 10.0, 100.0, DEFAULTS.circle.diameter_pct, 1.0)

    with st.expander("Landmasses"):
        lm = DEFAULTS.landmass
        threshold = st.slider("Land threshold", 0.05, 0.6, lm.threshold, 0.01,
                              help="Lower gives more land and more ragged coasts.")
        channel_pct = st.slider("Channel width %", 0.0, 50.0, lm.channel_pct, 1.0,
                                help="Width of the sea between the landmasses.")
        warp_pct = st.slider("Shape warp %", 0.0, 40.0, lm.warp_pct, 1.0)
        noise_frequency = st.slider("Noise frequency", 1.0, 12.0, lm.noise.frequency, 0.5)
        noise_octaves = st.slider("Noise octaves", 1, 9, lm.noise.octaves, 1)
        radius_min, radius_max = st.slider("Falloff radius % range", 30.0, 200.0,
                                           (lm.radius_pct[0], lm.radius_pct[1]), 5.0)
        seed_area_pct = st.slider("Seed area %", 10.0, 90.0, lm.seed_area_pct, 5.0)
        min_separation_pct = st.slider("Min seed separation %", 10.0, 120.0, lm.min_separation_pct, 5.0)

    with st.expander("Biomes"):
        bi = DEFAULTS.biomes
        biome_warp_px = st.slider("Border warp px", 0.0, 200.0, bi.warp.strength_px, 5.0)
        seeds_min, seeds_max = st.slider("Regions per landmass", 5, 12,
                                         (bi.seeds_per_landmass[0], bi.seeds_per_landmass[1]), 1)
        coast_band_px = st.slider("Coast band px", 5.0, 120.0, bi.coast_band_px, 5.0)

    with st.expander("Heightmap"):
        hm = DEFAULTS.heightmap
        coast_distance_px = st.slider("Coast rise distance px", 10.0, 300.0, hm.coast_distance_px, 10.0)
        profile_blur_px = st.slider("Biome blend px", 1.0, 80.0, hm.profile_blur_px, 1.0)
        seabed_depth = st.slider("Seabed depth", 0.05, 1.0, hm.seabed_depth, 0.05)
        profile_values = {}
        for t in bi.types:
            p = hm.profiles[t.name]
            st.caption(t.label)
            c1, c2 = st.columns(2)
            profile_values[f"profile_{t.name}_base"] = c1.slider(
                "base", 0.0, 1.0, p.base, 0.01, key=f"base_{t.name}")
            profile_values[f"profile_{t.name}_amplitude"] = c2.slider(
                "amplitude", 0.0, 1.0, p.amplitude, 0.01, key=f"amp_{t.name}")

    debug = st.checkbox("Record sub-steps", value=True)
    run = st.button("Generate", type="primary", width="stretch")

values = {
    "seed": int(st.session_state.seed), "size": int(size), "diameter": float(diameter),
    "threshold": threshold, "channel_pct": channel_pct, "warp_pct": warp_pct,
    "noise_frequency": noise_frequency, "noise_octaves": int(noise_octaves),
    "radius_min": radius_min, "radius_max": radius_max,
    "seed_area_pct": seed_area_pct, "min_separation_pct": min_separation_pct,
    "biome_warp_px": biome_warp_px, "seeds_min": int(seeds_min), "seeds_max": int(seeds_max),
    "coast_band_px": coast_band_px, "coast_distance_px": coast_distance_px,
    "profile_blur_px": profile_blur_px, "seabed_depth": seabed_depth,
    **profile_values,
}
overrides = build_overrides(values)


@st.cache_data(show_spinner=False)
def cached_generate(overrides: dict, debug: bool):
    return generate(overrides, WORK_DIR, debug=debug)


# ---------------------------------------------------------------- generate
if run or st.session_state.pop("pending_run", False) or "result" not in st.session_state:
    with st.spinner("Generating..."):
        try:
            st.session_state.result = cached_generate(overrides, debug)
            st.session_state.error = None
        except GenerationError as exc:
            st.session_state.error = str(exc)

if st.session_state.get("error"):
    st.error(st.session_state.error)

result = st.session_state.get("result")
if result is not None:
    cfg = result.config
    retries = (result.seeds_used["landmass"] - cfg.seed) + (result.seeds_used["biomes"] - cfg.seed)
    st.caption(
        f"Seed {cfg.seed}, size {cfg.size}, diameter {cfg.circle.diameter_pct:g} %, "
        f"{result.seconds:.1f} s, retries {retries}. Files in `{result.out_dir}`."
    )
    c1, c2, c3 = st.columns(3)
    c1.image(str(result.biomes_color), caption="Biomes and sub-types", width="stretch")
    c2.image(str(result.height_shaded), caption="Hill shade", width="stretch")
    c3.image(str(result.heightmap), caption="Heightmap, 8-bit preview of the 16-bit file", width="stretch")

    with st.expander("Steps", expanded=False):
        if not result.steps:
            st.write("Select 'Record sub-steps' and generate again to see the steps.")
        for rec in result.steps:
            st.markdown(f"**Step {rec.step_id}: {rec.title}**")
            st.write(rec.description)
            if rec.params:
                st.table({"parameter": list(rec.params), "value": [str(v) for v in rec.params.values()]})
            if rec.filename:
                st.image(str(result.out_dir / rec.filename), width=400)

# ---------------------------------------------------------------- seed browser
with st.expander("Seed browser"):
    st.write("Generates 6 seeds at size 253 with the current parameters.")
    start = st.number_input("Start seed", min_value=0, max_value=999_999, value=int(st.session_state.seed))
    if st.button("Browse 6 seeds"):
        st.session_state.browse = [int(start) + i for i in range(6)]
    for row in range(0, len(st.session_state.get("browse", [])), 3):
        cols = st.columns(3)
        for col, s in zip(cols, st.session_state.browse[row:row + 3]):
            small = dict(overrides)
            small["seed"] = s
            small["size"] = 253
            try:
                r = cached_generate(small, False)
                col.image(str(r.biomes_color), caption=f"Seed {s}", width="stretch")
            except GenerationError as exc:
                col.error(f"Seed {s}: {exc}")
            col.button("Use this seed", key=f"use_{s}", on_click=set_seed, args=(s,))

# ---------------------------------------------------------------- save
with st.expander("Save"):
    target = st.text_input("Folder", value=str(Path("out") / "saved" / f"seed_{st.session_state.seed}"))
    if st.button("Save Unreal files and config"):
        if result is None:
            st.warning("Generate first.")
        else:
            files = save_result(result, target)
            st.success(f"Wrote {len(files)} files to {target}.")
