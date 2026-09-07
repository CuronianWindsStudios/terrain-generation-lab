"""Experiment UI for the terrain generator. Start with: streamlit run ui.py"""
from __future__ import annotations

import random
from pathlib import Path

import streamlit as st

from terrain.config import NOISE_TYPES, SUBTYPE_LETTERS, Config, GenerationError, Profile, UNREAL_SIZES
from terrain.experiment import PROFILE_FIELDS, build_overrides, generate, profile_preview, save_result
from terrain.export import SEA_COLOR, biome_color

WORK_DIR = Path("out") / "ui"
PREVIEW_PX = 200
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


def swatch(rgb: tuple[int, int, int], label: str) -> str:
    r, g, b = rgb
    return (
        f'<span style="display:inline-block;width:14px;height:14px;border-radius:3px;'
        f'background:rgb({r},{g},{b});vertical-align:middle;margin-right:6px;'
        f'border:1px solid rgba(0,0,0,0.25)"></span>{label}'
    )


def legend_html(cfg: Config, subtypes: bool) -> str:
    """One row per biome type. With sub-types, the row shows the A, B, and C swatches."""
    rows = [f"<div>{swatch(SEA_COLOR, 'Sea')}</div>"]
    for i, t in enumerate(cfg.biomes.types):
        if subtypes:
            parts = [swatch(biome_color(i, s), letter) for s, letter in enumerate(SUBTYPE_LETTERS)]
            rows.append(f"<div><b>{t.label}</b>: " + " &nbsp; ".join(parts) + "</div>")
        else:
            rows.append(f"<div>{swatch(biome_color(i), t.label)}</div>")
    return '<div style="line-height:1.9">' + "".join(rows) + "</div>"


@st.cache_data(show_spinner=False)
def cached_preview(size: int, seed: int, biome_index: int, **fields):
    """A true-scale crop of the biome height at the map center, as a hill shade."""
    return profile_preview(Profile(**fields), size, seed, biome_index, PREVIEW_PX)


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
        seabed_depth = st.slider("Seabed depth", 0.05, 1.0, hm.seabed_depth, 0.05)

    st.caption("Height profile of each biome")
    profile_values = {}
    for i, t in enumerate(bi.types):
        p = hm.profiles[t.name]
        k = f"profile_{t.name}_"
        with st.expander(t.label):
            thumbnail = st.empty()
            profile_values[k + "base"] = st.slider(
                "Base height", -0.3, 1.0, p.base, 0.01, key=k + "base",
                help="Lowest height of the biome. Below 0 is under the sea level, so pools form.")
            profile_values[k + "amplitude"] = st.slider(
                "Hill amplitude", 0.0, 1.0, p.amplitude, 0.01, key=k + "amplitude",
                help="Height of the hills above the base.")
            profile_values[k + "noise"] = st.selectbox(
                "Noise type", NOISE_TYPES, index=NOISE_TYPES.index(p.noise), key=k + "noise",
                help="fractal: rolling hills. ridged: sharp crests. billow: round bulges.")
            profile_values[k + "frequency"] = st.slider(
                "Frequency", 1.0, 16.0, p.frequency, 0.5, key=k + "frequency")
            profile_values[k + "octaves"] = int(st.slider(
                "Octaves", 1, 9, p.octaves, 1, key=k + "octaves"))
            profile_values[k + "lacunarity"] = st.slider(
                "Lacunarity", 1.5, 4.0, p.lacunarity, 0.1, key=k + "lacunarity",
                help="Frequency multiplier of each next octave.")
            profile_values[k + "persistence"] = st.slider(
                "Persistence", 0.1, 1.0, p.persistence, 0.05, key=k + "persistence",
                help="Amplitude multiplier of each next octave.")
            profile_values[k + "blend_px"] = st.slider(
                "Blend px", 1.0, 80.0, p.blend_px, 1.0, key=k + "blend_px",
                help="Blur of this biome at its border.")
            fields = {f: profile_values[k + f] for f in PROFILE_FIELDS}
            thumbnail.image(
                cached_preview(int(size), int(st.session_state.seed), i, **fields),
                caption=f"{PREVIEW_PX} px at the map center, true scale. Blue is below sea level.",
                width="stretch",
            )

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
    "seabed_depth": seabed_depth,
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
    show_subtypes = st.toggle("Show sub-types A, B, C", value=True,
                              help="Off: one color per biome type, whatever the sub-type.")
    c1, c2, c3 = st.columns(3)
    if show_subtypes:
        c1.image(str(result.biomes_color), caption="Biomes and sub-types", width="stretch")
    else:
        c1.image(str(result.biomes_type_color), caption="Biome types", width="stretch")
    c1.markdown(legend_html(cfg, show_subtypes), unsafe_allow_html=True)
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
    st.toggle("Show sub-types in thumbnails", value=True, key="browse_subtypes")
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
                thumb = r.biomes_color if st.session_state.get("browse_subtypes", True) else r.biomes_type_color
                col.image(str(thumb), caption=f"Seed {s}", width="stretch")
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
