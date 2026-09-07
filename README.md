# Terrain generator

The generator makes a circular world with 3 landmasses and 5 biome types for Unreal Engine.
All output images are grayscale PNG files. The design is in
`docs/superpowers/specs/2026-09-07-terrain-generator-design.md`.

## Install

```
pip install -r requirements.txt
```

## Run

```
python -m terrain --seed 42 --size 1009 --diameter 90 --out out --debug
```

| Flag | Meaning | Default |
|---|---|---|
| `--config PATH` | YAML file with parameters, see `config.yaml` | built-in defaults |
| `--seed INT` | random seed | 42 |
| `--size INT` | image size: 127, 253, 505, 1009, 2017, 4033, or 8129 | 1009 |
| `--diameter FLOAT` | circle diameter as a percentage of the width | 90 |
| `--out PATH` | output folder | `out` |
| `--debug` | write one image per sub-step and `walkthrough.md` | off |

The same seed always gives the same images.

## Experiment UI

```
streamlit run ui.py
```

The command opens a page in the browser. The sidebar has the seed, the size, the diameter, and
sliders for the landmass, biome, and heightmap parameters. Click Generate to run the pipeline.
The page shows the color biome map, the hill shade, and the heightmap. Open the Steps section to
see every sub-step image with its formula and its parameters. The Seed browser generates 6 seeds
at a small size, and a button under each thumbnail loads that seed. The Save section copies the
Unreal files and writes a `config.yaml` with the current settings to a folder you name. You can
run that config later with `python -m terrain --config <folder>/config.yaml`.

## Output

- `out/unreal/heightmap.png`: 16-bit heightmap. Sea level is at value 32768.
- `out/unreal/weight_<biome>.png`: 5 layer weight maps. They add up to 255 at each pixel.
- `out/unreal/subtype_<biome>_<A|B|C>.png`: 15 sub-type masks, one per visual variant.
- `out/unreal/params.json`: the seed, the parameters, the region list, and the Unreal import settings.
- `out/preview/height_shaded.png`: a hill shade of the heightmap, for people.
- `out/preview/biomes_color.png`: a color map of the 15 sub-types, for people.
- `out/preview/biomes_type_color.png`: the same map with one color per biome type.
- `out/preview/heightmap_8bit.png`: an 8-bit copy of the heightmap, for image viewers.
- `out/steps/` and `out/walkthrough.md`: one image per sub-step, with `--debug`.

## How the generator works

1. **Circle.** The generator computes the distance from the center and makes a circle mask.
   The diameter is a percentage of the image width.
2. **Landmasses.** The generator places 3 seed points. Each seed point gets a radial falloff.
   A sea channel between the seed points keeps the landmasses apart. A noise warp bends the
   shapes. Fractal noise multiplies the shape mask, so the coast is ragged. The generator keeps
   the 3 largest areas, removes small islands, and fills small lakes.
3. **Biomes.** The generator scatters region seeds on each landmass. The first 5 seeds on each
   landmass get one biome type each. Sea Side seeds sit at the coast. Mountain Range seeds sit
   inland. Each land pixel goes to the nearest seed, with a noise warp for organic borders.
   Each biome type cycles its regions through the sub-types A, B, and C.
4. **Heightmap.** The height rises from 0 at the coast with a smooth curve. Each biome type has
   its own height profile: a base height, a hill amplitude, the noise octaves, a noise type
   (fractal, ridged, or billow), and a blend width at its border. The base is the lowest
   height of the biome. The hills go up from the base. A base below 0 puts land under the sea
   level, so pools form. The generator mixes the profiles with blurred biome masks. The seabed
   goes down to a floor at the circle edge.
5. **Export.** The generator writes the 16-bit heightmap, the weight maps, and the sub-type masks.

Run with `--debug` and open `out/walkthrough.md` to see the image of each sub-step.

## Import into Unreal

1. Open the Landscape mode and select Import from File.
2. Select `out/unreal/heightmap.png` as the heightmap file.
3. Set the section size to 63x63 quads and the sections per component to 2x2.
4. Set the component count to the value in `params.json`, for example 8x8 for 1009.
5. Set the Z scale to 100. Value 32768 is then 0 m, and 65535 is 256 m.
6. Add 5 layers in the landscape material, one per biome type.
7. Select each `weight_<biome>.png` as the layer file for its layer.

## Tests

```
python -m pytest
```
