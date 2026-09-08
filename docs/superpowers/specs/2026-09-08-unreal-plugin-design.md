# Unreal runtime plugin: design

Date: 2026-09-08. Status: approved by the user in chat, spec under review.

## 1. Goal

Port the Python terrain generator to a C++ plugin for Unreal Engine 5.8, so a packaged game
generates one world at the start of a playthrough and shows it as a playable terrain. The plugin
is developed in the isolated project `S:\WorldGenUE` and moves to the final game project later.

## 2. Decisions

| Topic | Decision |
|---|---|
| Language | C++. No Python at run time. |
| Seed parity | Not required. The same seed may give a different world than the Python version. |
| Reference | The Python generator stays the reference for the look and for the rules, not for the bytes. |
| Engine | Unreal 5.8.2 at `E:\Epic Games\UE_5.8`. |
| Platform | PC, Windows, DirectX 12. |
| World | One world per playthrough, generated behind a loading screen on a worker thread with a progress bar. |
| Resolution | 4033 px default. 8129 px is an option. |
| World size | Diameter 9 km. Meters per pixel = diameter in meters / (size × diameter_pct / 100). About 2.48 m at 4033 px. |
| Height range | Plus or minus 256 m, a setting. |
| Terrain | A grid of tiles, each a Dynamic Mesh Component with LOD levels and async collision. |
| Later experiments | Virtual Heightfield Mesh, Nanite tessellation with displacement. Not in the first version. |
| Editor iteration | The terrain actor regenerates from a Generate button in its details panel, in the editor, with no play session. The config is a Data Asset. |
| Editor module | An optional editor-only module that writes PNG files of the steps and imports into a Landscape. |

## 3. Non-goals

- Byte-identical output to the Python version.
- Generation during gameplay, streaming, or tiles that generate on demand.
- Consoles and mobile.
- Nanite on the runtime mesh. The engine builds Nanite offline only.
- Rivers, roads, vegetation, and gameplay content. The plugin ends at the terrain and its layer data.

## 4. Plugin layout

Path: `S:\WorldGenUE\Plugins\TerrainGen`.

```
TerrainGen/
  TerrainGen.uplugin              modules: TerrainGenCore (Runtime), TerrainGen (Runtime),
                                  TerrainGenEditor (Editor)
  Source/
    TerrainGenCore/               plain C++, no UObjects, no rendering dependency
      Public/
        TerrainConfig.h           the settings structs, mirrors config.json
        TerrainGrid.h             TGrid<T>: a square array with width, height, and (x, y) access
        TerrainAlgorithms.h       noise, distance transform, labels, blur, closing, level march
        TerrainStages.h           circle, landmasses, sand bars, biomes, heightmap, export
        TerrainResult.h           the arrays and the region list the stages produce
        TerrainGenerator.h        runs the stages in order, reports progress, supports cancel
      Private/                    one .cpp per header
    TerrainGen/                   the UObject layer
      Public/
        TerrainConfigAsset.h      UTerrainConfig: a USTRUCT mirror of the config, JSON load and save
        TerrainWorldGenerator.h   UTerrainWorldGenerator: async generation, progress, result
        TerrainTextures.h         transient textures from the arrays
        TerrainActor.h            ATerrainWorld: the tiles, the material, the water, the collision
      Private/
      Content/                    the master material, the water material, a debug material
    TerrainGenEditor/             editor only, phase 4
      Public/
        TerrainEditorTools.h      run in editor, write PNG files, import into a Landscape
      Private/
  Tests/                          automation tests, in TerrainGenCore/Private/Tests
```

Module dependencies: `TerrainGenCore` depends on `Core` only. `TerrainGen` depends on
`TerrainGenCore`, `Engine`, `GeometryFramework`, `GeometryCore`, `DynamicMesh`, `Json`, and
`JsonUtilities`. `TerrainGenEditor` depends on `TerrainGen`, `UnrealEd`, `Landscape`, and
`LandscapeEditor`.

## 5. Config

The config mirrors `config.json` of the Python version key for key, so one JSON file drives both
versions. The sections are `seed`, `size`, `circle`, `landmass`, `biomes`, `spit`, `heightmap`,
and `export`. The plugin adds a `world` section:

```json
"world": {
  "diameter_m": 9000.0,
  "height_range_m": 256.0,
  "tile_px": 253,
  "lod_levels": 4
}
```

`FTerrainConfig` in `TerrainGenCore` is the plain struct the stages read. `UTerrainConfig` in
`TerrainGen` is a Data Asset with `UPROPERTY` fields for Blueprint and the details panel, plus
`CallInEditor` buttons `LoadJson` and `SaveJson` for round trips with the Python UI. A converter
copies between the two. Validation follows
the Python `validate` function: the size list, the diameter range, exactly 3 landmasses, 5 biome
types with a profile each, `seeds_per_landmass` with a minimum of 4, and the spit and profile
ranges. A bad config returns an error string, never an assert.

## 6. Core library

`TerrainGenCore` replaces NumPy and SciPy with these functions. All of them work on `TGrid<T>`.

| Function | Replaces | Method |
|---|---|---|
| `FractalNoise`, `RidgedNoise`, `BillowNoise` | `terrain.noise` | Octave sums of `FMath::PerlinNoise2D` on a seeded offset, output in [0, 1]. Value noise is not needed because seed parity is not required. |
| `DistanceTransform` | `scipy.ndimage.distance_transform_edt` | Felzenszwalb and Huttenlocher, separable, exact, O(n). An option returns the nearest-pixel indices. |
| `LabelComponents` | `scipy.ndimage.label` | Two-pass union-find with 4-connectivity, and an 8-connectivity option. Returns the labels and the areas. |
| `GaussianBlur` | `scipy.ndimage.gaussian_filter` | Separable kernel, 3 sigma wide, edge clamp. |
| `Closing` | the Python `closing` function | Two distance transforms, as in Python. |
| `MarchLevelLine` | `_march` in `spit.py` | The same loop: bilinear samples of the field and its gradient, the ramp up and down, the room and inside checks, the jump cap. |
| `RasterizeStrip` | `_rasterize` in `spit.py` | Distance from each pixel in the path's bounding box to the nearest path point. A uniform grid of path points replaces the k-d tree. |
| `Smoothstep`, `Quantile`, `LargestRemainder255` | the small NumPy helpers | Direct ports. |

Random numbers: one `FRandomStream` per stage and attempt, seeded from a hash of the world
seed, the stage number, and the attempt number, as in Python.

Memory at 4033 px: a float grid is 65 MB. The stages free their scratch grids when they finish.
The peak is about 8 float grids, under 600 MB. At 8129 px the peak is about 2.2 GB, and the
plugin logs a warning above 4033 px.

Threads inside the core: the separable passes of the distance transform and the blur split
their rows over `ParallelFor`. Everything else is single-threaded on the worker.

## 7. Stages

The stages follow the Python modules one to one. The rules do not change.

1. **Circle.** Center distance, circle mask, edge band. `circle.py`.
2. **Landmasses.** Seed points with rejection sampling, warp noise, radial falloff, the sea
   channel, fractal noise, threshold, keep the 3 largest areas, remove islands, fill lakes, label
   by area. Retry with the next attempt seed until the count is 3. `landmass.py`.
3. **Sand bars.** One per landmass. Closing of the landmass, distance field of the closed shape,
   start points on the outer coast with room, the level-line march in both directions from 8
   starts, the enclosed-water score, the strait taper, the join to the coast. A failed bar makes
   the landmass stage retry. `spit.py`.
4. **Biomes.** Coast distance, region seeds for the 4 non-spit types on the mainland with the
   placement rules, warp noise, nearest-seed growth, one region per bar, validation, retry. The
   sub-type rule: each landmass gets one sub-type of each biome type and no two landmasses share
   it, from a random order per biome type. `biomes.py`.
5. **Heightmap.** Signed coast distance, the coast curve with the short rise on the bars, the
   profile mix with the per-biome blend and the bar pixels on the Sea Side profile only, the
   land height, the seabed, the final height in [-1, 1]. `heightmap.py`.
6. **Export arrays.** The 16-bit height with sea level at 32768, the 5 weight maps that add up to
   255 with the sea shelf blend to the Sea Side biome, the 15 sub-type masks, the region list,
   and the sub-type order per biome type. `export.py`.

Each stage takes the config, the results of the earlier stages, a random stream, and a progress
sink. It returns a result struct or an error string. There is no step recorder in the first
version; the editor module writes the intermediate grids as PNG files in phase 4.

## 8. Result

```cpp
struct FTerrainResult
{
    int32 Size;
    float MetersPerPixel;
    TGrid<uint16> Height;              // 32768 is sea level
    TArray<TGrid<uint8>> Weights;      // 5 maps, sum 255
    TGrid<uint8> SubtypeId;            // 0 sea, 1..15
    TGrid<uint8> BiomeId;              // 0 sea, 1..5
    TGrid<uint8> LandmassId;           // 0 sea, 1..3
    TArray<FTerrainRegion> Regions;    // id, landmass, biome, subtype, seed x y
    TMap<FName, TArray<int32>> SubtypePerLandmass;
    int32 SeedUsedLandmass, SeedUsedBiomes;
};
```

## 9. Async generation and progress

`UTerrainWorldGenerator` is a Blueprint-callable UObject.

- `Generate(const UTerrainConfig* Config)` validates the config, then starts the stages with
  `Async(EAsyncExecution::Thread, ...)`. It returns at once.
- `GetProgress()` returns a struct with the stage name, the stage index of 6, and a fraction in
  [0, 1]. The worker writes it through an atomic; the game thread reads it every tick for the
  loading screen.
- `OnFinished` is a dynamic multicast delegate, called on the game thread with the result or the
  error string.
- `Cancel()` sets a flag; the worker checks it between stages and between attempts and stops.
- `GetResult()` holds the last result until the next `Generate` call.

Time budget at 4033 px: the stages take a few seconds on the worker. The tile build takes
longer and runs on the game thread in slices, one tile per tick, so the frame does not stall.

## 10. Textures

`TerrainTextures` makes transient `UTexture2D` objects from the result arrays:

- Height: `PF_G16`, one texture at full size.
- Weights: two `PF_B8G8R8A8` textures, 4 biomes in the first and the fifth in the second, at
  full size. The material reads them as layer weights.
- Sub-type masks: one `PF_R8` texture with the sub-type id, at full size. The material picks the
  variant from the id.

The textures use no mips and clamp addressing. They exist for the material only; the mesh
reads the arrays directly.

## 11. Terrain actor

`ATerrainWorld` builds the terrain from a result. It is the iteration tool: place it in a map,
set its config asset, and press the `Generate` button in the details panel. The button runs the
same async generator as the game and rebuilds the tiles in the editor viewport, with the progress
in a notification. With Live Coding, a C++ change in the core is one compile and one press away.
`Generate` also runs on `BeginPlay` when the `bGenerateOnBeginPlay` flag is set, for the game.

- **Tiles.** The world splits into square tiles of `tile_px` pixels, 16 by 16 tiles at 4033 px
  with 253 px per tile. Each tile is a `UDynamicMeshComponent`. The vertex spacing is the pixel
  spacing. The tile builder makes `lod_levels` meshes per tile by skipping pixels, 1, 2, 4, and
  8, and switches them by camera distance. The heights come from the array, scaled by the height
  range. The vertex normals come from the height differences. The UV is the world position over
  the world size, so all textures sample by world position.
- **Detail.** Below the pixel spacing the material adds a normal detail from a tiled noise
  texture. The heightmap holds no detail below 2.5 m.
- **Material.** One master material with 5 layer slots. Each slot has 3 sub-type variants of
  albedo, normal, and roughness. The material reads the weight textures for the layer blend and
  the sub-type texture for the variant. The plugin content holds the master material with flat
  placeholder colors per biome, the same palette as the Python previews. The game replaces the
  slots with its own textures.
- **Collision.** Each tile cooks a simple collision mesh from its LOD 1 mesh on a worker,
  through the Dynamic Mesh async collision path.
- **Water.** One flat plane at sea level over the whole circle, with a translucent placeholder
  material.
- **Sea floor outside the circle.** The tiles cover the whole square. The seabed reaches the
  floor at the circle edge, as in Python, so the outside is a flat floor under the water.
- **Origin.** The world center is the actor location. The circle radius in meters is half the
  diameter setting.

## 12. Editor module, phase 4

`TerrainGenEditor` adds an Editor Utility Widget with:

- Run the generator with a chosen config JSON, on the worker with the same progress.
- Write the PNG files of the Python contract to a folder: `heightmap.png`, `weight_*.png`,
  `subtype_*.png`, `params.json`, and the two color previews.
- Import the height and the weights into a Landscape actor with the Landscape edit interface,
  with the component layout from `unreal_import_settings` in Python.

## 13. Testing

Automation tests in `TerrainGenCore`, run with the Session Frontend or the command line
`-ExecCmds="Automation RunTests TerrainGen"`. They use 253 px worlds, like the Python tests.

- Algorithms: the distance transform against a brute-force check on a 64 px grid, the labels
  on a known picture, the blur against a known kernel sum, the closing fills a bay.
- Landmasses: exactly 3 areas, all inside the circle, ids ordered by area, no small lakes,
  an impossible config returns an error after the retries, same seed same output.
- Sand bars: one bar joined to each landmass, a gap from other land, water behind the middle
  of the bar, a lagoon without the strait, one contact with the strait, inside the circle.
- Biomes: every biome on every landmass, Sea Side exactly on the bars, one sub-type per biome
  per landmass and no two landmasses share it, regions stay on their landmass.
- Heightmap: the coast at sea level, the bar reaches its profile base, a higher base gives
  higher land, a negative base makes pools.
- Export: weights add up to 255 at every pixel, the height encoding, the far sea takes the
  Sea Side weight.
- Config: JSON round trip, the validation errors.

Visual check: the editor module writes the PNG files, and the person compares them to the
Python previews by eye. There is no automatic image comparison.

## 14. Phases

1. Plugin skeleton, `TerrainGenCore` with the config, the grid, the algorithms, and their tests.
2. The six stages with their tests. A commandlet that runs a config and writes the height as a
   raw file, for a first look.
3. `TerrainGen`: the config Data Asset, the async generator, the textures, and `ATerrainWorld`
   with the `Generate` button and a debug quad that shows the height and the biome colors in the
   editor viewport. From here on every change is visible in the editor without a play session.
4. `ATerrainWorld` tiles, LOD, material, collision, water. A test map in the isolated project
   with a loading screen widget that shows the progress and drops the player on the terrain.
5. `TerrainGenEditor`: the utility widget, the PNG writer of the steps, the Landscape import.
6. Experiments: Virtual Heightfield Mesh, Nanite tessellation with displacement.

Each phase ends with the tests green and a commit.

## 15. Risks

- **Performance at 8129 px.** The memory peak is about 2.2 GB and the tile build takes minutes.
  The default stays 4033 px. If the game needs more detail, add it in the material, not in the
  heightmap.
- **Dynamic Mesh at 256 tiles.** Each tile is one draw call per LOD. 256 components with 4 LOD
  meshes each is fine for PC. If the draw calls hurt, merge tiles at the far LOD levels.
- **Collision cook time.** 256 cooks on workers take seconds. The loading screen waits for
  them.
- **Perlin instead of value noise.** The coasts and the hills will look a little different from
  the Python version. The user accepted this.
- **Level march edge cases.** The bar march is the most delicate code. Its tests port the
  Python tests one to one, and the retry loop catches the rest.
