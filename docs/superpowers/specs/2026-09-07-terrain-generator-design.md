# Terrain Generator Design

Date: 2026-09-07
Status: approved

## 1. Goal

The generator makes a set of black and white images for one game world. Unreal Engine reads
the images as a landscape heightmap and as landscape layer weight maps. The generator also
writes one debug image for each sub-step and a walkthrough document, so a person can see how
each image comes from the one before it.

## 2. Decisions

| Item | Value |
|---|---|
| Language | Python 3.12, numpy, Pillow, scipy |
| Engine | Unreal Engine |
| Resolution | 1009 x 1009 pixels (Unreal recommended size) |
| World shape | One circle. The diameter is a percentage of the image width. |
| Landmasses | Exactly 3 |
| Biome types | Sea Side (Neringa), Marshlands, Ancient Grove, Enchanted Forest, Mountain Range |
| Sub-types | 3 visual sub-types (A, B, C) for each biome type, 15 in total |
| Heightmap output | 16-bit grayscale PNG. Sea level is at value 32768. |
| Biome output | 8-bit grayscale PNG masks |
| Determinism | One seed controls all random numbers. The same seed gives the same bytes. |

## 3. Package layout

```
terrain/
  __init__.py
  __main__.py    python -m terrain
  cli.py         argument parser, runs the pipeline
  config.py      dataclasses, YAML load, defaults, validation
  noise.py       value noise, fractal noise, ridged noise, in numpy
  circle.py      stage 1
  landmass.py    stage 2
  biomes.py      stage 3
  heightmap.py   stage 4
  export.py      stage 5, Unreal files and previews
  debug.py       StepRecorder: writes step images and walkthrough.md
  imageio.py     save 8-bit and 16-bit grayscale PNG, save RGB preview
  pipeline.py    runs the stages in order
tests/
  test_noise.py
  test_circle.py
  test_landmass.py
  test_biomes.py
  test_heightmap.py
  test_export.py
  test_pipeline.py
config.yaml      default parameters
requirements.txt numpy, Pillow, scipy, PyYAML, pytest
README.md        how to run, how to import into Unreal
```

Each stage module has one public function. The function takes numpy arrays and a config
dataclass. The function returns a small result dataclass. The function receives a
`StepRecorder` and calls `recorder.step(...)` for each sub-step. The stage functions do not
read or write files. Only `imageio.py`, `debug.py`, and `export.py` write files.

## 4. Command line

```
python -m terrain --seed 42 --size 1009 --diameter 90 --out out --debug
python -m terrain --config my_config.yaml --out out
```

| Flag | Meaning | Default |
|---|---|---|
| `--config PATH` | YAML file with parameters | built-in defaults |
| `--seed INT` | random seed | 42 |
| `--size INT` | image width and height in pixels | 1009 |
| `--diameter FLOAT` | circle diameter as a percentage of the width | 90 |
| `--out PATH` | output folder | `out` |
| `--debug` | write sub-step images and `walkthrough.md` | off |

Command line flags override values from the YAML file.

## 5. Output folder

```
out/
  unreal/
    heightmap.png                 16-bit, 1009 x 1009
    weight_sea_side.png           8-bit, one file per biome type (5 files)
    weight_marshlands.png
    weight_ancient_grove.png
    weight_enchanted_forest.png
    weight_mountain_range.png
    subtype_sea_side_A.png        8-bit, one file per sub-type (15 files)
    ...
    params.json                   seed, parameters, Unreal import settings
  preview/
    height_shaded.png             8-bit hill shade for people
    biomes_color.png              RGB, one color per sub-type, for people
    biomes_type_color.png         RGB, one color per biome type, for people
    heightmap_8bit.png            8-bit copy of the heightmap, for image viewers and the UI
  steps/                          only with --debug
    01a_center_distance.png
    ...
  walkthrough.md                  only with --debug
```

## 6. Configuration

`config.yaml` holds all parameters. The values below are the defaults.

```yaml
seed: 42
size: 1009

circle:
  diameter_pct: 90          # circle diameter as % of image width
  edge_band_pct: 10         # soft band inside the circle edge, as % of the radius

landmass:
  count: 3
  seed_area_pct: 55         # seed points lie inside this % of the circle radius
  min_separation_pct: 75    # minimum distance between seed points, as % of the radius
  radius_pct: [100, 120]    # landmass falloff radius, random in this range, as % of the circle radius
  warp_pct: 15              # noise warp of all distances, as % of the radius
  channel_pct: 22           # width of the sea channel between landmasses, as % of the radius
  noise:
    octaves: 7
    frequency: 5.0          # cycles across the image width, first octave
    lacunarity: 2.0
    persistence: 0.5
  threshold: 0.28           # noise * shape_mask above this value is land
  min_lake_area_px: 200     # lakes and islands smaller than this are removed
  max_retries: 10           # tries with seed + 1 when the count is wrong

biomes:
  seeds_per_landmass: [5, 7]
  min_seed_separation_px: 60
  coast_band_px: 40         # "coast" seeds lie within this distance from the coast
  inland_fraction: 0.7      # "inland" seeds lie beyond this fraction of the max coast distance
  max_retries: 10
  warp:
    strength_px: 90
    frequency: 5.0
    octaves: 5
  types:
    - {name: sea_side,         label: "Sea Side (Neringa)", placement: spit}
    - {name: marshlands,       label: "Marshlands",         placement: low}
    - {name: ancient_grove,    label: "Ancient Grove",      placement: any}
    - {name: enchanted_forest, label: "Enchanted Forest",   placement: any}
    - {name: mountain_range,   label: "Mountain Range",     placement: inland}

heightmap:
  coast_distance_px: 80     # distance from the coast where the base curve reaches 1
  coast_blur_px: 12         # blur of the coast distance, removes creases
  profiles:                 # one height profile per biome type. height = base + amplitude * noise
    # base (lowest height of the biome, in -1..1; below 0 is under the sea level, so pools form),
    # amplitude (height of the hills above the base), frequency, octaves, lacunarity, persistence,
    # noise (fractal, ridged, or billow), blend_px (blur of this biome mask at its border)
    sea_side:         {base:  0.01, amplitude: 0.08, frequency: 12.0, octaves: 3, noise: fractal, blend_px: 25}
    marshlands:       {base: -0.03, amplitude: 0.12, frequency:  6.0, octaves: 2, noise: fractal, blend_px: 25}
    ancient_grove:    {base:  0.13, amplitude: 0.24, frequency:  5.0, octaves: 5, noise: fractal, blend_px: 25}
    enchanted_forest: {base:  0.15, amplitude: 0.30, frequency:  6.0, octaves: 5, noise: fractal, blend_px: 25}
    mountain_range:   {base:  0.20, amplitude: 0.80, frequency:  8.0, octaves: 6, noise: ridged,  blend_px: 25}
  seabed_depth: 0.30        # seabed floor as a fraction of the range below sea level
  seabed_distance_px: 150   # distance from the coast where the seabed reaches its floor
  seabed_blur_px: 10        # blur of the seabed, removes creases

export:
  sea_level_value: 32768
  weight_blur_px: 12
```

Config validation: `size` must be one of the Unreal recommended sizes
127, 253, 505, 1009, 2017, 4033, 8129. `diameter_pct` must be in `(0, 100]`.
`landmass.count` must be 3 in this version. `biomes.types` must have exactly 5 entries.

## 7. Noise (`noise.py`)

All noise is value noise on a lattice, with smoothstep interpolation, computed in numpy.
No external noise library is necessary.

- `value_noise(shape, frequency, rng) -> float32 array in [0, 1]`.
  The function draws a random lattice of `ceil(frequency) + 2` points per axis and
  interpolates it to `shape`.
- `fractal_noise(shape, octaves, frequency, lacunarity, persistence, rng) -> [0, 1]`.
  The function sums octaves and divides by the sum of the amplitudes.
- `ridged_noise(shape, octaves, frequency, lacunarity, persistence, rng) -> [0, 1]`.
  Each octave uses `1 - abs(2 * n - 1)`. Ridged noise makes sharp mountain crests.
- `smoothstep(x) = x * x * (3 - 2 * x)` for `x` in `[0, 1]`.

Each call takes a `numpy.random.Generator`. Each stage makes its own generator with
`numpy.random.default_rng([seed, stage_number, try_number])`. A retry changes only the
try number. This gives determinism, and a retry in one stage does not change the other stages.

## 8. Stage 1: circle (`circle.py`)

Input: size, circle config. Output: `CircleResult(mask, edge_band, center_distance, radius)`.

| Step | Image | Description |
|---|---|---|
| 1a | `01a_center_distance.png` | Distance of each pixel from the center, as a gray gradient. |
| 1b | `01b_circle_mask.png` | Pixels with `distance <= radius` are white. `radius = size * diameter_pct / 200`. |
| 1c | `01c_edge_band.png` | A soft band inside the edge. Value 1 at `radius * (1 - edge_band_pct / 100)`, value 0 at the radius, smoothstep between. Value 0 outside the circle. The seabed uses this band. |

## 9. Stage 2: landmasses (`landmass.py`)

Input: `CircleResult`, landmass config, seed. Output: `LandResult(land_mask, landmass_ids, seeds, seed_used)`.
`landmass_ids` is an int array. Value 0 is sea. Values 1 to 3 are the landmasses.

| Step | Image | Description |
|---|---|---|
| 2a | `02a_seed_points.png` | 3 seed points as white dots on black. The points lie inside `seed_area_pct` of the radius. Rejection sampling keeps the distance between points `>= min_separation_pct` of the radius. After 1000 rejections the separation is halved. |
| 2b | `02b_warp_noise.png` | Two fractal noise fields give each pixel an offset `(dx, dy)` of up to `warp_pct` of the radius. All distances below use the warped pixel position `pixel + offset`. The image shows `dx`. |
| 2c | `02c_radial_falloff.png` | For each seed: `falloff = clamp(1 - distance / landmass_radius, 0, 1)`. The image shows the maximum of the 3 fields. |
| 2d | `02d_shape_mask.png` | Each pixel belongs to its nearest seed. `channel = smoothstep((d2 - d1) / channel_px)` fades to 0 at the border between two seeds. `shape_mask = max_falloff * channel * edge_band`. This guarantees a sea channel between the landmasses and a ragged coast at the circle edge. |
| 2e | `02e_noise.png` | Fractal noise from `landmass.noise`. |
| 2f | `02f_land_field.png` | `field = noise * shape_mask`. Pixels with `field > threshold` and inside the circle mask are land. Near a seed the mask is 1, so most pixels are land. Near the coast only high noise values are land, so the coast is ragged. |
| 2g | `02g_land_mask.png` | Keep the 3 largest connected areas (`scipy.ndimage.label`). Remove islands and fill lakes smaller than `min_lake_area_px`. |
| 2h | `02h_landmass_ids.png` | Each landmass gets an ID from 1 to 3, ordered by area, largest first. The image shows 3 gray levels. |

Retry rule: if the count of connected areas after step 2g is not 3, the stage repeats
with `seed + 1`, up to `max_retries` times. Each try is recorded in the walkthrough.
After the last try, the stage raises `GenerationError` with the message:
`"Seed 42 gave 2 landmasses after 10 tries. Decrease landmass.threshold or increase landmass.channel_pct."`

Design note (2026-09-07): the first version had one height profile per biome type. For a short
time the profiles became one shared `heightmap.profile`. The user then asked for explicit control
of each biome, so each biome type has its own profile again, with more values: the noise octaves
(`lacunarity`, `persistence`), a `noise` type (`fractal`, `ridged`, or `billow`), and a per-biome
`blend_px`. The height rule is `base + amplitude * noise` with the noise in `[0, 1]`, so the base
is the lowest height of the biome and the hills go up from it. A negative base makes pools below
the sea level. Biome placement rules (coast, low, inland) still control where the regions sit.

Design note: an earlier version added the noise to the falloff, `falloff + strength * (noise - 0.5)`.
That version merged two landmasses in about one try of three, and the coast followed the circle.
The multiplicative field with the channel gives 3 landmasses on the first try for every seed tested.

## 10. Stage 3: biomes (`biomes.py`)

Input: `LandResult`, biomes config, seed. Output:
`BiomeResult(coast_distance, regions, region_ids, biome_ids, subtype_ids)`.

- `coast_distance`: float array. Distance from each land pixel to the nearest sea pixel. 0 on sea.
- `region_ids`: int array. 0 is sea. 1..N is the region.
- `biome_ids`: int array. 0 is sea. 1..5 is the biome type in the order of `biomes.types`.
- `subtype_ids`: int array. 0 is sea. 1..15 is `(biome_id - 1) * 3 + subtype_index + 1`.
- `regions`: list of `Region(id, landmass_id, seed_xy, biome_index, subtype_index)`.

| Step | Image | Description |
|---|---|---|
| 3a | `03a_coast_distance.png` | Distance from each land pixel to the nearest sea pixel (`distance_transform_edt`). |
| 3b | `03b_region_seeds.png` | Region seed points. See the assignment rule below. One gray level per biome type. |
| 3c | `03c_warp_noise.png` | Two fractal noise fields make an offset `(dx, dy)` for each pixel. `offset = warp.strength_px * (noise - 0.5) * 2`. The image shows `dx`. |
| 3d | `03d_region_ids.png` | Each land pixel goes to the nearest seed on the same landmass, with the warped pixel position. `region = argmin(distance(pixel + offset, seed))`. |
| 3e | `03e_biome_ids.png` | Each region maps to its biome type. 6 gray levels. |
| 3f | `03f_subtype_ids.png` | Each region gets a sub-type. 16 gray levels. |
| 3g | `03g_mask_<biome>.png` | One white mask per biome type, 5 images. |

Seed assignment rule:

1. Each landmass gets `n` seeds, `n` random in `seeds_per_landmass`.
2. The first 5 seeds on each landmass get one biome type each, in the order of `biomes.types`.
   This guarantees that every landmass has every biome type, and that every biome type
   has at least 3 regions in the world.
3. The remaining seeds on each landmass get a random biome type.
4. Each seed position obeys the placement rule of its biome type:
   - `coast`: `0 < coast_distance <= coast_band_px`
   - `low`: `coast_band_px < coast_distance <= 2 * coast_band_px`
   - `inland`: `coast_distance >= inland_fraction * max(coast_distance on this landmass)`
   - `any`: `coast_distance > 10`
   If a rule gives no candidate pixels on a landmass, the rule falls back to `any`.
   Rejection sampling keeps the distance between seeds on one landmass
   `>= min_seed_separation_px`. After 200 rejections the separation is halved.
5. Sub-types: for each biome type, sort its regions by region ID. Give them A, B, C, A, B, C, ...
   in that order. Because every biome type has at least 3 regions, every sub-type appears.

Validation rule: after step 3d, every region must have at least 1 pixel, and every region
with placement `coast` must have at least 1 pixel with `coast_distance <= coast_band_px`.
If the validation fails, the stage repeats with `seed + 1`, up to `biomes.max_retries` times,
then raises `GenerationError`.

## 11. Stage 4: heightmap (`heightmap.py`)

Input: `CircleResult`, `LandResult`, `BiomeResult`, heightmap config, seed.
Output: `HeightResult(height)`. `height` is a float32 array. Land is in `[min(base, 0), 1]`,
where `base` is the lowest profile base. Sea is in `[-seabed_depth, 0]`.

| Step | Image | Description |
|---|---|---|
| 4a | `04a_signed_coast_distance.png` | Distance to the coast. Land is positive. Sea is negative. |
| 4b | `04b_coast_curve.png` | The distance is blurred with a Gaussian of `coast_blur_px` first, so the curve has no creases on the medial axis. `curve = smoothstep(clamp(blurred_distance / coast_distance_px, 0, 1))` on land, 0 on sea. |
| 4c | `04c_profile_base.png` | Each biome mask is blurred with the `blend_px` of that biome, and the masks are normalized to sum 1. The base heights of the profiles are mixed with these weights. |
| 4c-2 | `04c-2_profile_amplitude.png` | The amplitudes of the profiles, mixed with the same weights. |
| 4d | `04d_biome_noise.png` | One noise field per biome type from its `noise` type, `frequency`, `octaves`, `lacunarity`, and `persistence`, mixed with the same weights. |
| 4e | `04e_land_height.png` | `land = clamp(curve * (base + amplitude * noise), -1, 1)`. The noise is in `[0, 1]`, so the hills go up from the base. The whole sum is multiplied by `curve`, so the coast stays at 0. |
| 4f | `04f_seabed.png` | `seabed = -seabed_depth * smoothstep(clamp(-distance / seabed_distance_px, 0, 1))`. The seabed is then blended to `-seabed_depth` with `(1 - edge_band)` outside the band, blurred with a Gaussian of `seabed_blur_px` to remove creases, and blended with the edge band again, so the circle edge and the outside of the circle sit exactly at the floor. |
| 4g | `04g_height.png` | `height = land` where land, `seabed` where sea. The image maps `[-seabed_depth, 1]` to `[0, 255]`. |

## 12. Stage 5: Unreal export (`export.py`)

| File | Rule |
|---|---|
| `heightmap.png` | `uint16 = round(32768 + height * 32767)` for `height >= 0`. `uint16 = round(32768 + height * 32768)` for `height < 0`. Sea level is exactly 32768. |
| `weight_<biome>.png` | Start with the one-hot biome mask. Sea pixels take the biome of the nearest land pixel (`distance_transform_edt` with `return_indices`). Further out the sea blends to the seabed biome, the first biome type with placement `coast`, over `4 * weight_blur_px` from the coast. Blur with a Gaussian of `weight_blur_px`. Normalize with the largest remainder method, so the 5 values add up to exactly 255 at each pixel. |
| `subtype_<biome>_<A,B,C>.png` | One-hot mask of the sub-type, 0 or 255, no blur. |
| `params.json` | The full resolved config, the seed, the seeds used after retries, and `unreal_import: {resolution: 1009, section_size: "63x63", sections_per_component: "2x2", components: "8x8", z_scale: 100, sea_level_value: 32768}`. |

Preview files:

- `preview/height_shaded.png`: hill shade from the height gradient, light from the north-west, blended with the height.
- `preview/biomes_color.png`: RGB. One hue per biome type. Three lightness levels per sub-type. Sea is dark blue.

## 13. Debug recorder and walkthrough (`debug.py`)

`StepRecorder(out_dir, enabled)` has two methods:

- `step(step_id, title, array, description, params: dict)`.
  If `enabled` is false, the method returns at once.
  The method normalizes the array to 8-bit grayscale and writes `steps/<step_id>_<slug>.png`.
  The method appends a record.
- `write_walkthrough()` writes `walkthrough.md` from the records:

```
## Step 2d: Land field

field = max_falloff + noise_strength * (noise - 0.5)
Pixels with field > threshold inside the circle are land.

| Parameter | Value |
|---|---|
| noise_strength | 0.45 |
| threshold | 0.5 |

![Step 2d](steps/02d_land_field.png)
```

The description text is written in Simplified Technical English.

## 14. Tests

Tests use pytest and a small size (127 or 253) for speed, except where the size matters.

| Test file | Checks |
|---|---|
| `test_noise.py` | Output shape and range `[0, 1]`. Same rng seed gives the same array. |
| `test_circle.py` | Mask width along the center row is within 1 pixel of `size * diameter_pct / 100`. Edge band is 1 inside and 0 at the edge. |
| `test_landmass.py` | Exactly 3 connected areas. All land is inside the circle. IDs are 1..3. No lakes below `min_lake_area_px`. `GenerationError` is raised with an impossible config. |
| `test_biomes.py` | Every biome type appears on every landmass. Every sub-type 1..15 appears. Every `coast` region touches the coast band. `region_ids` is 0 exactly on sea. |
| `test_heightmap.py` | Land height is in `[min(base, 0), 1]`. A negative base puts inland land below 0. The noise only adds height above the base. Sea height is in `[-seabed_depth, 0]`. Coast pixels are near 0. Each biome uses its own profile: Mountain Range inland is higher than Marshlands inland. A higher base gives higher land. A wider blend gives a lower maximum slope inland. |
| `test_export.py` | Heightmap is `uint16`, shape `(size, size)`, sea pixels are 32768. Weight maps sum to 255 (+/- 1) at each pixel. 21 PNG files plus `params.json` exist. |
| `test_pipeline.py` | Two runs with the same seed give identical bytes for every output file. `--debug` writes 20+ step images and `walkthrough.md`. |

## 15. Errors

- `GenerationError(message)`: the pipeline cannot satisfy a rule after the retries.
  The message names the seed, the count, and the parameter to change.
- `ConfigError(message)`: a config value is out of range. The message lists the valid values.
- The CLI catches both errors, prints the message, and exits with code 1.

## 16. Out of scope for this version

- Rivers and lakes as features.
- Erosion.
- More than one circle or more than 3 landmasses.
- Unreal World Partition tiles.

## Sand bars (added 2026-09-08, revised the same day)

Each landmass gets one sand bar, like the Curonian Spit. The bar is the Sea Side biome. The first
version was a thin ribbon that hung off the coast into open water. The user rejected that look, so
the bar now joins the coast at both ends and encloses water.

- The bar runs along the coast at the lagoon distance and joins the coast at both ends. Across a
  bay it runs over the bay mouth, so the bay becomes the lagoon. Along an open coast a narrow
  lagoon lies behind it, like a barrier island.
- The path follows a level line of the distance field of the closed land shape. A morphological
  closing with a disk of `bay_pct` fills the bays, so the level line crosses the bay mouths. The
  level ramps up from 0 at the start and back down to 0 at the end, so the bar leaves and rejoins
  the coast at a tangent. Both ends extend onto the nearest coast pixel.
- The generator tries several start points on the outer coast, in both directions, and keeps the
  path that encloses the most water. A path that stops early, near other land or the circle edge,
  or that encloses less than `min_lagoon_pct` of the landmass area, does not count. If no path
  counts, the landmass stage retries with the next seed.
- The strip around the path has a width that varies with low-frequency noise by
  `width_variation`, plus edge noise. At the strait end the path stops `strait_pct` short of the
  coast and the width tapers to a point. `strait_pct` 0 closes the lagoon.
- All sizes are a percentage of the circle radius, except `min_lagoon_pct` (of the landmass area)
  and `rise_px`. Config section `spit`: `bay_pct`, `lagoon_pct`, `length_pct`, `min_lagoon_pct`,
  `width_pct`, `width_variation`, `strait_pct`, `edge_noise_pct`, `gap_pct`, `rise_px`.
- Biomes: the placement `spit` marks the biome type that covers the bars. It gets no region
  seeds. Each bar is one region. The 4 other biome types get seeds on the mainland only.
  `seeds_per_landmass` counts the mainland regions, so its minimum is 4.
- Biome areas (decided 2026-09-08): the 4 mainland biome types share each landmass about
  equally, within `biomes.balance_tolerance`. The region growth multiplies the distance to each
  seed by a scale per biome type, and the generator tunes the scales in `biomes.balance_iterations`
  damped rounds. A seed is always nearest to itself, so a biome never vanishes; a duplicate seed
  of a type that shrinks to nothing is dropped. This rule applies to the Unreal plugin too.
- Sub-types: each landmass gets one sub-type of each biome type, and no two landmasses share it.
  For each biome type the generator draws a random order of A, B, C over the landmasses 1, 2, 3.
  Every region of that biome on a landmass gets the sub-type of that landmass.
- Heightmap: on the bar the coast curve reaches 1 at `spit.rise_px` from the water, and the bar
  pixels use the Sea Side profile only, so the mainland profiles do not blend into the bar.
- Export: the experiment UI has a "Download ZIP for Unreal" button. The ZIP holds `config.json`,
  `config.yaml`, `README.txt`, the `unreal/` files, and the `preview/` files. The CLI `--config`
  flag accepts a JSON file.
