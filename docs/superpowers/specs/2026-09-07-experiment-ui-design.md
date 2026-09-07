# Experiment UI Design

Date: 2026-09-07
Status: approved

## 1. Goal

A local web page to run experiments with the terrain generator: change the seed and the
parameters, generate, look at the results and the sub-steps, browse seeds, and save a result.

## 2. Decisions

| Item | Value |
|---|---|
| Stack | Streamlit, one file `ui.py` at the project root |
| Helpers | `terrain/experiment.py`: pure functions, tested with pytest |
| Start | `streamlit run ui.py` |
| Work folder | `out/ui/` for generated files. Saved results go to a folder the user names. |

## 3. Layout

Sidebar:

- Seed (number input) and a "Random seed" button.
- Size (select: 127, 253, 505, 1009, 2017) and diameter (slider 10 to 100).
- Expander "Landmasses": threshold, channel_pct, warp_pct, noise frequency, noise octaves,
  radius_pct range, seed_area_pct, min_separation_pct.
- Expander "Biomes": warp strength_px, seeds_per_landmass range, coast_band_px.
- Expander "Heightmap": coast_distance_px and seabed_depth.
- One expander per biome type, at the root of the sidebar. At the top, a live thumbnail: a
  true-scale crop of the biome height at the map center, as a hill shade, with water in blue.
  Below it: base, amplitude, noise type, frequency, octaves, lacunarity, persistence, and
  blend_px.
- "Generate" button.

Main area:

- A status line: seed used, size, time in seconds, retries.
- Three columns: color biome map, hill shade, heightmap (as an 8-bit preview).
- Expander "Steps": every sub-step in order with its title, its description, its parameters,
  and its image.
- Expander "Seed browser": a start seed and a "Browse 6 seeds" button. The browser generates
  6 seeds at size 253 and shows the color biome maps in a grid. A "Use this seed" button
  under each thumbnail sets the seed in the sidebar.
- Expander "Save": a folder path and a "Save" button. Save copies `unreal/` and `preview/`
  to the folder and writes `config.yaml` with the current parameters.

## 4. Helpers (`terrain/experiment.py`)

- `build_overrides(values: dict) -> dict`: maps flat UI values to the nested config dict.
- `generate(overrides: dict, out_dir, debug=True) -> ExperimentResult`: runs the pipeline and
  returns the config, the step records, the preview image paths, the timing, and the seeds used.
- `save_result(result, out_dir, target_dir) -> list[Path]`: copies the files and writes the YAML.

`run_pipeline` returns the step records in `PipelineResult.steps`, so the UI can show them.

## 5. Tests

- `build_overrides` maps every UI field to the right config key.
- `generate` at size 127 returns 30 or more steps and the 2 preview paths.
- `save_result` writes `config.yaml`, `unreal/heightmap.png`, and `preview/biomes_color.png`.
