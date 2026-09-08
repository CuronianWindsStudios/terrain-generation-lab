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
| `--config PATH` | YAML or JSON file with parameters, see `config.yaml` | built-in defaults |
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
sliders for the landmass, biome, sand bar, and heightmap parameters. Click Generate to run the pipeline.
The page shows the color biome map, the hill shade, and the heightmap. Open the Steps section to
see every sub-step image with its formula and its parameters. The Seed browser generates 6 seeds
at a small size, and a button under each thumbnail loads that seed.

The Save and export section has a "Download ZIP for Unreal" button. The ZIP holds the settings as
`config.json` and `config.yaml`, the Unreal files, the previews, and a `README.txt` with the import
steps. The section can also copy the same files to a folder you name. You can run a saved config
later with `python -m terrain --config <folder>/config.json`.

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
3. **Sand bars.** Each landmass gets one sand bar, like the Curonian Spit. The bar runs along
   the coast at the lagoon distance and joins the coast at both ends. Across a bay it runs over
   the bay mouth, so the bay becomes the lagoon. Along an open coast a narrow lagoon lies behind
   it. A strait at one end keeps the lagoon open to the sea, and the bar tapers to a point there.
   The width varies along the bar. If no bar encloses enough water, the landmass stage tries the
   next seed.
4. **Biomes.** The sand bars are the Sea Side biome. The generator scatters region seeds for the 4
   other biome types on the mainland of each landmass. Mountain Range seeds sit inland. Each
   mainland pixel goes to the nearest seed, with a noise warp for organic borders. The generator
   then tunes a distance scale per biome type in a few rounds, so the 4 mainland biomes share
   each landmass about equally and no biome dominates. Each landmass
   gets one sub-type of each biome type, and no two landmasses share it. Example: landmass 1 has
   Sea Side B, landmass 2 has Sea Side C, and landmass 3 has Sea Side A. The order is random for
   each biome type.
5. **Heightmap.** The height rises from 0 at the coast with a smooth curve. On a sand bar the
   curve is short, so the dunes reach their full height a few pixels from the water. Each biome type has
   its own height profile: a base height, a hill amplitude, the noise octaves, a noise type
   (fractal, ridged, or billow), and a blend width at its border. The base is the lowest
   height of the biome. The hills go up from the base. A base below 0 puts land under the sea
   level, so pools form. The generator mixes the profiles with blurred biome masks. The seabed
   goes down to a floor at the circle edge.
6. **Export.** The generator writes the 16-bit heightmap, the weight maps, and the sub-type masks.

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
