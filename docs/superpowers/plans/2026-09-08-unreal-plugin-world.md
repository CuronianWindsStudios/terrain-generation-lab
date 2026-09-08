# TerrainGen plugin, phase 3: the world module with the Generate button. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Press Generate on an actor in the Unreal editor and see the generated world as a 3D preview mesh with biome colors, from a config asset that round-trips with the Python `config.json`.

**Architecture:** A memory pass on `TerrainGenCore` first. Then a second runtime module `TerrainGen` with the UObject layer: `UTerrainConfig` (a Data Asset with JSON load and save), `UTerrainWorldResult` (the result as a UObject with textures on demand), `UTerrainWorldGenerator` (async generation on a worker thread with progress and cancel), `UTerrainGenLibrary::GenerateWorld` (the entry point), and `ATerrainWorld` (the actor with a `CallInEditor` Generate button and a Procedural Mesh preview with vertex colors). Phase 4 replaces the preview with the tiled Dynamic Mesh, the material, collision, and water.

**Tech Stack:** Unreal Engine 5.8.2 at E:\Epic Games\UE_5.8, C++, UnrealBuildTool, the automation test framework with latent commands, the engine plugin ProceduralMeshComponent for the preview, Json and JsonUtilities for the config files.

**Spec:** S:\python-terrain-generation\docs\superpowers\specs\2026-09-08-unreal-plugin-design.md, sections 5, 9, 10, 11 (the button and the config asset), and the memory pass in section 6. The core module and its API are in S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\Public\. The Python config keys are in S:\python-terrain-generation\config.yaml.

## Global Constraints

- Engine: Unreal 5.8.2 at `E:\Epic Games\UE_5.8`. Project: `S:\WorldGenUE\WorldGenUE.uproject`. Plugin: `S:\WorldGenUE\Plugins\TerrainGen`. Repo: S:\WorldGenUE, branch `terrain-gen-core` (continue on it; origin is https://github.com/CuronianWindsStudios/WorldGenUE).
- The term is **Land**, not Landmass, in every name, file, comment, and UI label. `LandId`, "3 lands".
- `TerrainGenCore` keeps its `Core`-only dependency. `TerrainGen` depends on `Core`, `CoreUObject`, `Engine`, `TerrainGenCore`, `Json`, `JsonUtilities`, `ProceduralMeshComponent`. No editor modules in either.
- JSON keys are the Python keys, snake_case, exactly as in config.yaml: `seed`, `size`, `circle.diameter_pct`, `landmass.*` (the Python section name stays `landmass` in JSON so files round-trip; the C++ field is `Land`), `biomes.*`, `spit.*`, `heightmap.*`, `export.*`, and the new `world.*`.
- The sink callbacks run on the worker thread. The delegate and every UObject write happen on the game thread.
- Build: `pwsh -ExecutionPolicy Bypass -File S:\WorldGenUE\Tools\Build.ps1`. Tests: `pwsh -ExecutionPolicy Bypass -File S:\WorldGenUE\Tools\RunTests.ps1 <Filter>`. Both exist. Line endings LF, tabs, PascalCase, `b` prefix for bools. Line-ending checks with a Python byte count, not grep.
- Commits end with the session's two attribution lines.
- Automation tests of the new module live in `Source/TerrainGen/Private/Tests/`, named `TerrainGen.World.<Topic>`, flags `EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter`.

## File structure

```
Plugins/TerrainGen/
  TerrainGen.uplugin                          add the TerrainGen module and the ProceduralMeshComponent plugin dependency
  Source/TerrainGenCore/                      Task 1 touches: TerrainResults.h, TerrainStageCircle.cpp, TerrainStageHeightmap.cpp,
                                              TerrainStageLands.cpp, TerrainStageSpits.cpp, TerrainStageBiomes.cpp, TerrainStageExport.cpp,
                                              TerrainGenerator.cpp, the tests that read the id grids
  Source/TerrainGen/
    TerrainGen.Build.cs
    Public/
      TerrainGenModule.h                      module interface, log category LogTerrainGenWorld
      TerrainConfigAsset.h                    UTerrainConfig: the Data Asset, ToCore, FromCore, LoadJson, SaveJson, JSON helpers
      TerrainWorldResult.h                    UTerrainWorldResult: holds FTerrainResult, MakeTextures, height in meters
      TerrainWorldGenerator.h                 UTerrainWorldGenerator: Generate, GetProgress, Cancel, OnFinished
      TerrainWorldActor.h                     ATerrainWorld: config, Generate button, the preview mesh
      TerrainGenLibrary.h                     UTerrainGenLibrary::GenerateWorld and FTerrainGenerateParams
    Private/
      TerrainGenModule.cpp
      TerrainConfigAsset.cpp
      TerrainConfigJson.cpp                   the JSON read and write of the config, one function per section
      TerrainWorldResult.cpp
      TerrainWorldGenerator.cpp
      TerrainWorldActor.cpp
      TerrainGenLibrary.cpp
      Tests/
        WorldTestUtil.h                       a latent command that waits for a generator
        ConfigAssetTests.cpp
        WorldResultTests.cpp
        WorldGeneratorTests.cpp
        WorldActorTests.cpp
```

---

### Task 1: Memory pass in the core

**Files:**
- Modify: `Source/TerrainGenCore/Public/TerrainResults.h`, `Private/TerrainStageCircle.cpp`, `Private/TerrainStageLands.cpp`, `Private/TerrainStageSpits.cpp`, `Private/TerrainStageBiomes.cpp`, `Private/TerrainStageHeightmap.cpp`, `Private/TerrainStageExport.cpp`, `Private/TerrainGenerator.cpp`, and every test under `Private/Tests/` that reads `LandIds`, `SpitOwner`, `BiomeIds`, or `SubtypeIds`.
- Test: `Private/Tests/GeneratorTests.cpp` (add a memory test).

**Interfaces:**
- Produces: `FLandResult::LandIds` and `SpitOwner` become `TGrid<uint8>`; `FBiomeResult::BiomeIds` and `SubtypeIds` become `TGrid<uint8>`; `RegionIds` stays `FGridI`. `FCircleResult::CenterDistance` is removed. The heightmap stage holds one weight grid at a time. `GenerateTerrainWithDebug` gets the same grid types. The memory test logs the peak.

- [ ] **Step 1: Write the failing memory test**

Append to `Private/Tests/GeneratorTests.cpp` before the final `#endif`:
```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainGeneratorMemoryTest, "TerrainGen.Core.GeneratorMemory",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainGeneratorMemoryTest::RunTest(const FString& Parameters)
{
	// the id grids are one byte per pixel, so a 4033 px world stays inside the budget
	static_assert(sizeof(decltype(FLandResult::LandIds)::Data)::ElementType) == 1, "LandIds must be uint8");
	static_assert(sizeof(decltype(FBiomeResult::BiomeIds)::Data)::ElementType) == 1, "BiomeIds must be uint8");
	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	Cfg.Size = 1009;
	Cfg.Seed = 5;
	const FPlatformMemoryStats Before = FPlatformMemory::GetStats();
	FTerrainResult Result;
	FString Error;
	const double Start = FPlatformTime::Seconds();
	TestTrue(TEXT("1009 px generates"), GenerateTerrain(Cfg, Result, Error));
	const double Seconds = FPlatformTime::Seconds() - Start;
	const FPlatformMemoryStats After = FPlatformMemory::GetStats();
	const double PeakMB = double(After.PeakUsedPhysical) / (1024.0 * 1024.0);
	const double GrowthMB = double(int64(After.PeakUsedPhysical) - int64(Before.UsedPhysical)) / (1024.0 * 1024.0);
	AddInfo(FString::Printf(TEXT("1009 px in %.2f s, process peak %.0f MB, growth during the run %.0f MB"), Seconds, PeakMB, GrowthMB));
	// a 1009 px float grid is 4 MB; the budget is 8 float grids at 4033 px, so 40 MB here with margin for the allocator
	TestTrue(TEXT("growth under 120 MB at 1009 px"), GrowthMB < 120.0);
	TestTrue(TEXT("1009 px under 20 s"), Seconds < 20.0);
	return true;
}
```
If the `static_assert` lines do not compile as written, replace both with `static_assert(std::is_same_v<decltype(FLandResult::LandIds), TGrid<uint8>>, "LandIds must be uint8");` and the same for `BiomeIds`.

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL, the static assertion fails because the grids are `int32`.

- [ ] **Step 3: Narrow the id grids**

In `Public/TerrainResults.h`:
- `FCircleResult`: delete the `CenterDistance` member.
- `FLandResult`: `TGrid<uint8> LandIds;` and `TGrid<uint8> SpitOwner;` with the same comments.
- `FBiomeResult`: `TGrid<uint8> BiomeIds;` and `TGrid<uint8> SubtypeIds;`. `RegionIds` stays `FGridI`.

Then follow the compiler. The expected edits:
- `TerrainStageCircle.cpp`: remove the `CenterDistance` init and the store in the loop; keep `D` as a local for the mask and the band.
- `TerrainStageLands.cpp`: `LabelByArea` writes `uint8(Rank[...])` into a `TGrid<uint8>`; `Attempt` inits `SpitOwner` as `TGrid<uint8>`; comparisons like `Land.LandIds.Data[I] == LandId` compile as they are.
- `TerrainStageSpits.cpp`: `Land.LandIds.Data[I] = uint8(LandId)`, `Land.SpitOwner.Data[I] = uint8(LandId)`.
- `TerrainStageBiomes.cpp`: the LUTs write `uint8(...)`; `Out.BiomeIds.Init(Size, 0)` keeps working; `int32 LandCount` from a `uint8` max needs `int32(V)`.
- `TerrainStageHeightmap.cpp`: comparisons with `T + 1` compile; cast where the compiler warns.
- `TerrainStageExport.cpp`: the copies into `Out.BiomeId` and friends become plain copies of `uint8` grids (`Out.BiomeId = Biomes.BiomeIds;`).
- `TerrainGenerator.cpp`: `FTerrainDebugGrids::BiomeIds` and `SubtypeIds` become `TGrid<uint8>`; `WriteDebugImages` needs a `WritePgm(const FString&, const TGrid<uint8>&)` overload that maps 0..max to black..white — add it to `TerrainDebugImages.h` and `.cpp` (the `FGridB` overload maps 0 and nonzero only, so the new overload must be a separate function; give it the name `WritePgmIds`).
- Tests: `int32(...)` casts where a `TestEqual` compares a `uint8` with an `int32`.

- [ ] **Step 4: One weight grid at a time in the heightmap**

In `Private/TerrainStageHeightmap.cpp`, replace the block that builds `TArray<FGridF> Weights` and `Total` and then mixes the profiles with two passes over the types:
```cpp
	// pass 1: the sum of the blurred masks, for the normalization
	FGridF Total(Size, 0.0f);
	{
		FGridF Mask(Size, 0.0f), Blurred;
		for (int32 T = 0; T < Types; ++T)
		{
			for (int32 I = 0; I < N; ++I) Mask.Data[I] = Biomes.BiomeIds.Data[I] == T + 1 ? 1.0f : 0.0f;
			GaussianBlur(Mask, Blurred, Profiles[T]->BlendPx);
			for (int32 I = 0; I < N; ++I) Total.Data[I] += Blurred.Data[I];
		}
	}
	// pass 2: the profile mix, one blurred mask and one noise grid alive at a time
	FGridF Base(Size, 0.0f), Amp(Size, 0.0f), NoiseMix(Size, 0.0f);
	{
		FGridF Mask(Size, 0.0f), Blurred, Noise;
		for (int32 T = 0; T < Types; ++T)
		{
			for (int32 I = 0; I < N; ++I) Mask.Data[I] = Biomes.BiomeIds.Data[I] == T + 1 ? 1.0f : 0.0f;
			GaussianBlur(Mask, Blurred, Profiles[T]->BlendPx);
			FRandomStream Rng(HashSeed(Seed, StageNumber, T));
			const FNoiseParams P = { Profiles[T]->Octaves, Profiles[T]->Frequency, Profiles[T]->Lacunarity, Profiles[T]->Persistence };
			MakeNoise(Noise, Size, P, Profiles[T]->Noise, Rng);
			for (int32 I = 0; I < N; ++I)
			{
				float W;
				if (Land.SpitMask.Data[I]) W = (Biomes.BiomeIds.Data[I] == T + 1) ? 1.0f : 0.0f;
				else W = Blurred.Data[I] / FMath::Max(Total.Data[I], 1e-6f);
				Base.Data[I] += W * Profiles[T]->Base;
				Amp.Data[I] += W * Profiles[T]->Amplitude;
				NoiseMix.Data[I] += W * Noise.Data[I];
			}
		}
	}
```
The result is the same numbers as before, so the heightmap test keeps its assertions. Free `Total` right after pass 2 with `Total.Data.Empty();`. Free `Signed` and `Smooth` after the curve, and `Curve`, `Base`, `Amp`, `NoiseMix` after the land height, with `.Data.Empty()`.

- [ ] **Step 5: Release the stage results early in the generator**

In `Private/TerrainGenerator.cpp`, inside `GenerateTerrainImpl`, after `MakeHeightmap` returns, the circle mask is still needed by nothing (the export does not read it after the memory pass; check `MakeExportArrays` and remove the unused `Circle` parameter from it and from `TerrainStages.h` if it is still unused). Free `Circle.EdgeBand.Data.Empty()` after the heightmap. Keep `Land` and `Biomes` alive until the export and the debug copy.

- [ ] **Step 6: Build and run every core test**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core`
Expected: every test passes, including `GeneratorMemory`. Read the `AddInfo` line in the log (S:\WorldGenUE\Saved\Logs\Automation.log, search "1009 px in") and put the peak and growth figures in the commit message.

- [ ] **Step 7: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Core memory pass: byte id grids, one weight grid at a time, no center distance grid"
```

---

### Task 2: The TerrainGen module skeleton

**Files:**
- Modify: `Plugins/TerrainGen/TerrainGen.uplugin`
- Create: `Source/TerrainGen/TerrainGen.Build.cs`, `Public/TerrainGenModule.h`, `Private/TerrainGenModule.cpp`, `Private/Tests/WorldSmokeTests.cpp`

**Interfaces:**
- Produces: the module `TerrainGen`, the log category `LogTerrainGenWorld`, the plugin dependency on `ProceduralMeshComponent`.

- [ ] **Step 1: Write the failing smoke test**

`Private/Tests/WorldSmokeTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "Modules/ModuleManager.h"
#include "TerrainGenModule.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainWorldSmokeTest, "TerrainGen.World.Smoke",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainWorldSmokeTest::RunTest(const FString& Parameters)
{
	TestTrue(TEXT("TerrainGen is loaded"), FModuleManager::Get().IsModuleLoaded(TEXT("TerrainGen")));
	TestTrue(TEXT("TerrainGenCore is loaded"), FModuleManager::Get().IsModuleLoaded(TEXT("TerrainGenCore")));
	TestTrue(TEXT("ProceduralMeshComponent is loaded"), FModuleManager::Get().IsModuleLoaded(TEXT("ProceduralMeshComponent")));
	return true;
}

#endif
```

- [ ] **Step 2: Write the module**

`TerrainGen.Build.cs`:
```csharp
using UnrealBuildTool;

public class TerrainGen : ModuleRules
{
	public TerrainGen(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "TerrainGenCore" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Json", "JsonUtilities", "ProceduralMeshComponent", "RenderCore", "RHI" });
	}
}
```

`Public/TerrainGenModule.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"

TERRAINGEN_API DECLARE_LOG_CATEGORY_EXTERN(LogTerrainGenWorld, Log, All);

class FTerrainGenModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
```

`Private/TerrainGenModule.cpp`:
```cpp
#include "TerrainGenModule.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogTerrainGenWorld);

void FTerrainGenModule::StartupModule() {}
void FTerrainGenModule::ShutdownModule() {}

IMPLEMENT_MODULE(FTerrainGenModule, TerrainGen)
```

In `TerrainGen.uplugin`, the `Modules` array gets a second entry after `TerrainGenCore`:
```json
		{
			"Name": "TerrainGen",
			"Type": "Runtime",
			"LoadingPhase": "Default"
		}
```
and a top-level `Plugins` array:
```json
	"Plugins": [
		{
			"Name": "ProceduralMeshComponent",
			"Enabled": true
		}
	]
```

- [ ] **Step 3: Build and run**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.World.Smoke`
Expected: `Passed  TerrainGen.World.Smoke`. If the ProceduralMeshComponent assertion fails, the plugin is not enabled in the project: add `{ "Name": "ProceduralMeshComponent", "Enabled": true }` to the `Plugins` array of `WorldGenUE.uproject` too.

- [ ] **Step 4: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen WorldGenUE.uproject
git commit -m "Add the TerrainGen world module skeleton"
```

---
### Task 3: The config Data Asset with the JSON round trip

**Files:**
- Create: `Public/TerrainConfigAsset.h`, `Private/TerrainConfigAsset.cpp`, `Private/TerrainConfigJson.cpp`
- Test: `Private/Tests/ConfigAssetTests.cpp`

**Interfaces:**
- Consumes: `FTerrainConfig` and its sub-structs from `TerrainConfig.h`, `ValidateTerrainConfig`, `MakeDefaultTerrainConfig`, `ETerrainNoise`, `ETerrainPlacement`.
- Produces:
  - `USTRUCT(BlueprintType) FTerrainBiomeTypeAsset { FName Name; FString Label; ETerrainPlacementAsset Placement; }`, `FTerrainProfileAsset` (the profile fields with `UPROPERTY`), `UENUM ETerrainNoiseAsset { Fractal, Ridged, Billow }`, `UENUM ETerrainPlacementAsset { Spit, Coast, Low, Inland, Any }`.
  - `UCLASS(BlueprintType) UTerrainConfig : public UDataAsset` with one `UPROPERTY(EditAnywhere, BlueprintReadWrite, Category=...)` per config field, grouped by section, defaults equal to `MakeDefaultTerrainConfig()`.
  - `FTerrainConfig ToCore() const`, `void FromCore(const FTerrainConfig&)`, `bool Validate(FString& OutError) const`.
  - `bool LoadJsonString(const FString& Text, FString& OutError)`, `FString SaveJsonString() const`, and the `CallInEditor` buttons `LoadJson()` and `SaveJson()` that use `JsonPath` (a `UPROPERTY(EditAnywhere) FFilePath`), with `UE_LOG` results.
  - Free functions in `TerrainConfigJson.cpp`, declared in the header: `bool TerrainConfigFromJson(const FString& Text, FTerrainConfig& InOut, FString& OutError)` (keys that are absent keep their value, like the Python `_merge`) and `FString TerrainConfigToJson(const FTerrainConfig&)`.

- [ ] **Step 1: Write the failing test**

`Private/Tests/ConfigAssetTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainConfigAsset.h"
#include "TerrainConfig.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainConfigAssetTest, "TerrainGen.World.ConfigAsset",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainConfigAssetTest::RunTest(const FString& Parameters)
{
	UTerrainConfig* Asset = NewObject<UTerrainConfig>();
	FString Error;
	TestTrue(TEXT("asset defaults are valid"), Asset->Validate(Error));
	const FTerrainConfig Core = Asset->ToCore();
	const FTerrainConfig Defaults = MakeDefaultTerrainConfig();
	TestEqual(TEXT("size"), Core.Size, Defaults.Size);
	TestEqual(TEXT("seed"), Core.Seed, Defaults.Seed);
	TestEqual(TEXT("biome types"), Core.Biomes.Types.Num(), 5);
	TestEqual(TEXT("first type is the spit"), int32(Core.Biomes.Types[0].Placement), int32(ETerrainPlacement::Spit));
	TestEqual(TEXT("profiles"), Core.Heightmap.Profiles.Num(), 5);
	TestTrue(TEXT("mountain amplitude"), FMath::IsNearlyEqual(Core.Heightmap.Profiles[FName("mountain_range")].Amplitude, 0.8f));
	TestEqual(TEXT("world diameter"), Core.World.DiameterM, 9000.0f);
	TestEqual(TEXT("balance rounds"), Core.Biomes.BalanceIterations, 25);

	// a JSON file from the Python UI: only some keys, snake_case, the Python section name landmass
	const FString Python = TEXT(R"({
		"seed": 77, "size": 505,
		"circle": {"diameter_pct": 80.0},
		"landmass": {"threshold": 0.3, "noise": {"frequency": 4.0, "octaves": 6}, "radius_pct": [90.0, 110.0]},
		"biomes": {"seeds_per_landmass": [4, 5], "warp": {"strength_px": 80.0}, "balance_tolerance": 0.08,
			"types": [{"name": "sea_side", "label": "Sea Side (Neringa)", "placement": "spit"},
				{"name": "marshlands", "label": "Marshlands", "placement": "low"},
				{"name": "ancient_grove", "label": "Ancient Grove", "placement": "any"},
				{"name": "enchanted_forest", "label": "Enchanted Forest", "placement": "any"},
				{"name": "mountain_range", "label": "Mountain Range", "placement": "inland"}]},
		"spit": {"lagoon_pct": 6.0, "length_pct": [50.0, 80.0]},
		"heightmap": {"profiles": {"mountain_range": {"base": 0.3, "noise": "billow"}}},
		"export": {"sea_level_value": 32768},
		"world": {"diameter_m": 6000.0}
	})");
	TestTrue(TEXT("python json loads"), Asset->LoadJsonString(Python, Error));
	TestTrue(TEXT("no error"), Error.IsEmpty());
	const FTerrainConfig Loaded = Asset->ToCore();
	TestEqual(TEXT("seed loaded"), Loaded.Seed, 77);
	TestEqual(TEXT("size loaded"), Loaded.Size, 505);
	TestEqual(TEXT("diameter loaded"), Loaded.Circle.DiameterPct, 80.0f);
	TestEqual(TEXT("land threshold loaded"), Loaded.Land.Threshold, 0.3f);
	TestEqual(TEXT("land noise frequency loaded"), Loaded.Land.Noise.Frequency, 4.0f);
	TestEqual(TEXT("land radius loaded"), Loaded.Land.RadiusPctMax, 110.0f);
	TestEqual(TEXT("seeds loaded"), Loaded.Biomes.SeedsPerLandMax, 5);
	TestEqual(TEXT("warp loaded"), Loaded.Biomes.Warp.StrengthPx, 80.0f);
	TestEqual(TEXT("tolerance loaded"), Loaded.Biomes.BalanceTolerance, 0.08f);
	TestEqual(TEXT("absent key keeps its default"), Loaded.Biomes.BalanceIterations, 25);
	TestEqual(TEXT("spit lagoon loaded"), Loaded.Spit.LagoonPct, 6.0f);
	TestEqual(TEXT("spit length loaded"), Loaded.Spit.LengthPctMax, 80.0f);
	TestEqual(TEXT("profile base loaded"), Loaded.Heightmap.Profiles[FName("mountain_range")].Base, 0.3f);
	TestEqual(TEXT("profile noise loaded"), int32(Loaded.Heightmap.Profiles[FName("mountain_range")].Noise), int32(ETerrainNoise::Billow));
	TestTrue(TEXT("profile amplitude kept"), FMath::IsNearlyEqual(Loaded.Heightmap.Profiles[FName("mountain_range")].Amplitude, 0.8f));
	TestEqual(TEXT("world diameter loaded"), Loaded.World.DiameterM, 6000.0f);

	// save and load again gives the same core values
	const FString Saved = Asset->SaveJsonString();
	TestTrue(TEXT("saved json has the python section name"), Saved.Contains(TEXT("\"landmass\"")));
	TestTrue(TEXT("saved json has snake case keys"), Saved.Contains(TEXT("\"diameter_pct\"")) && Saved.Contains(TEXT("\"balance_iterations\"")));
	UTerrainConfig* Again = NewObject<UTerrainConfig>();
	TestTrue(TEXT("saved json loads"), Again->LoadJsonString(Saved, Error));
	const FTerrainConfig Round = Again->ToCore();
	TestEqual(TEXT("round trip seed"), Round.Seed, 77);
	TestEqual(TEXT("round trip threshold"), Round.Land.Threshold, 0.3f);
	TestEqual(TEXT("round trip profile"), Round.Heightmap.Profiles[FName("mountain_range")].Base, 0.3f);
	TestEqual(TEXT("round trip types"), Round.Biomes.Types.Num(), 5);

	// bad input
	TestFalse(TEXT("bad json fails"), Again->LoadJsonString(TEXT("{ not json"), Error));
	TestTrue(TEXT("bad json message"), !Error.IsEmpty());
	TestFalse(TEXT("bad value fails validation"), Again->LoadJsonString(TEXT("{\"size\": 1000}"), Error));
	TestTrue(TEXT("bad value message"), Error.Contains(TEXT("size must be")));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainConfigAsset.h` not found.

- [ ] **Step 3: Write the asset header**

`Public/TerrainConfigAsset.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "TerrainConfig.h"
#include "TerrainConfigAsset.generated.h"

UENUM(BlueprintType)
enum class ETerrainNoiseAsset : uint8 { Fractal, Ridged, Billow };

UENUM(BlueprintType)
enum class ETerrainPlacementAsset : uint8 { Spit, Coast, Low, Inland, Any };

USTRUCT(BlueprintType)
struct FTerrainBiomeTypeAsset
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Name;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString Label;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) ETerrainPlacementAsset Placement = ETerrainPlacementAsset::Any;
};

USTRUCT(BlueprintType)
struct FTerrainProfileAsset
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, meta = (ClampMin = "-1", ClampMax = "1")) float Base = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, meta = (ClampMin = "0")) float Amplitude = 0.1f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float Frequency = 6.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, meta = (ClampMin = "1")) int32 Octaves = 4;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float Lacunarity = 2.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float Persistence = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) ETerrainNoiseAsset Noise = ETerrainNoiseAsset::Fractal;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float BlendPx = 25.0f;
};

/** The settings of a world. Mirrors config.json of the Python generator, key for key. */
UCLASS(BlueprintType)
class TERRAINGEN_API UTerrainConfig : public UDataAsset
{
	GENERATED_BODY()
public:
	UTerrainConfig();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") int32 Seed = 42;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") int32 Size = 4033;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") float DiameterM = 9000.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") float HeightRangeM = 256.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") int32 TilePx = 253;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World") int32 LodLevels = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Circle") float DiameterPct = 90.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Circle") float EdgeBandPct = 10.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandSeedAreaPct = 55.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandMinSeparationPct = 75.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandRadiusPctMin = 100.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandRadiusPctMax = 120.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandWarpPct = 15.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandChannelPct = 22.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") int32 LandNoiseOctaves = 7;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandNoiseFrequency = 5.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandNoiseLacunarity = 2.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandNoisePersistence = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") float LandThreshold = 0.28f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") int32 LandMinLakeAreaPx = 200;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lands") int32 LandMaxRetries = 10;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") int32 SeedsPerLandMin = 4;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") int32 SeedsPerLandMax = 6;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float MinSeedSeparationPx = 60.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float CoastBandPx = 40.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float InlandFraction = 0.7f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") int32 BiomeMaxRetries = 10;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") int32 BalanceIterations = 25;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float BalanceTolerance = 0.05f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float WarpStrengthPx = 90.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") float WarpFrequency = 5.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") int32 WarpOctaves = 5;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Biomes") TArray<FTerrainBiomeTypeAsset> Types;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float BayPct = 15.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float LagoonPct = 5.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitLengthPctMin = 40.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitLengthPctMax = 90.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float MinLagoonPct = 3.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitWidthPct = 4.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitWidthVariation = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float StraitPct = 2.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitEdgeNoisePct = 1.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitGapPct = 6.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sand bar") float SpitRisePx = 6.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") float CoastDistancePx = 80.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") float CoastBlurPx = 12.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") TMap<FName, FTerrainProfileAsset> Profiles;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") float SeabedDepth = 0.3f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") float SeabedDistancePx = 150.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Heightmap") float SeabedBlurPx = 10.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Export") int32 SeaLevelValue = 32768;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Export") float WeightBlurPx = 12.0f;

	/** The JSON file for the Load JSON and Save JSON buttons. The Python UI writes this file. */
	UPROPERTY(EditAnywhere, Category = "JSON") FFilePath JsonPath;

	UFUNCTION(CallInEditor, Category = "JSON") void LoadJson();
	UFUNCTION(CallInEditor, Category = "JSON") void SaveJson();

	UFUNCTION(BlueprintCallable, Category = "TerrainGen") bool LoadJsonString(const FString& Text, FString& OutError);
	UFUNCTION(BlueprintCallable, Category = "TerrainGen") FString SaveJsonString() const;
	UFUNCTION(BlueprintCallable, Category = "TerrainGen") bool Validate(FString& OutError) const;

	FTerrainConfig ToCore() const;
	void FromCore(const FTerrainConfig& Core);
};

/** Reads the Python JSON into the core config. Keys that are absent keep their value. */
TERRAINGEN_API bool TerrainConfigFromJson(const FString& Text, FTerrainConfig& InOut, FString& OutError);
/** Writes the core config as the Python JSON, snake_case keys, the section name landmass. */
TERRAINGEN_API FString TerrainConfigToJson(const FTerrainConfig& Config);
```

- [ ] **Step 4: Write the asset source**

`Private/TerrainConfigAsset.cpp`:
```cpp
#include "TerrainConfigAsset.h"
#include "TerrainGenModule.h"
#include "Misc/FileHelper.h"

namespace
{
	ETerrainNoise ToCoreNoise(ETerrainNoiseAsset V) { return ETerrainNoise(uint8(V)); }
	ETerrainNoiseAsset FromCoreNoise(ETerrainNoise V) { return ETerrainNoiseAsset(uint8(V)); }
	ETerrainPlacement ToCorePlacement(ETerrainPlacementAsset V) { return ETerrainPlacement(uint8(V)); }
	ETerrainPlacementAsset FromCorePlacement(ETerrainPlacement V) { return ETerrainPlacementAsset(uint8(V)); }
}

UTerrainConfig::UTerrainConfig()
{
	FromCore(MakeDefaultTerrainConfig());
	Size = 4033;   // the runtime default of the spec; the core default of 1009 is the Python one
}

FTerrainConfig UTerrainConfig::ToCore() const
{
	FTerrainConfig C;
	C.Seed = Seed;
	C.Size = Size;
	C.World.DiameterM = DiameterM; C.World.HeightRangeM = HeightRangeM; C.World.TilePx = TilePx; C.World.LodLevels = LodLevels;
	C.Circle.DiameterPct = DiameterPct; C.Circle.EdgeBandPct = EdgeBandPct;
	C.Land.SeedAreaPct = LandSeedAreaPct; C.Land.MinSeparationPct = LandMinSeparationPct;
	C.Land.RadiusPctMin = LandRadiusPctMin; C.Land.RadiusPctMax = LandRadiusPctMax;
	C.Land.WarpPct = LandWarpPct; C.Land.ChannelPct = LandChannelPct;
	C.Land.Noise = { LandNoiseOctaves, LandNoiseFrequency, LandNoiseLacunarity, LandNoisePersistence };
	C.Land.Threshold = LandThreshold; C.Land.MinLakeAreaPx = LandMinLakeAreaPx; C.Land.MaxRetries = LandMaxRetries;
	C.Biomes.SeedsPerLandMin = SeedsPerLandMin; C.Biomes.SeedsPerLandMax = SeedsPerLandMax;
	C.Biomes.MinSeedSeparationPx = MinSeedSeparationPx; C.Biomes.CoastBandPx = CoastBandPx; C.Biomes.InlandFraction = InlandFraction;
	C.Biomes.MaxRetries = BiomeMaxRetries; C.Biomes.BalanceIterations = BalanceIterations; C.Biomes.BalanceTolerance = BalanceTolerance;
	C.Biomes.Warp.StrengthPx = WarpStrengthPx; C.Biomes.Warp.Frequency = WarpFrequency; C.Biomes.Warp.Octaves = WarpOctaves;
	C.Biomes.Types.Reset();
	for (const FTerrainBiomeTypeAsset& T : Types) C.Biomes.Types.Add({ T.Name, T.Label, ToCorePlacement(T.Placement) });
	C.Spit.BayPct = BayPct; C.Spit.LagoonPct = LagoonPct; C.Spit.LengthPctMin = SpitLengthPctMin; C.Spit.LengthPctMax = SpitLengthPctMax;
	C.Spit.MinLagoonPct = MinLagoonPct; C.Spit.WidthPct = SpitWidthPct; C.Spit.WidthVariation = SpitWidthVariation;
	C.Spit.StraitPct = StraitPct; C.Spit.EdgeNoisePct = SpitEdgeNoisePct; C.Spit.GapPct = SpitGapPct; C.Spit.RisePx = SpitRisePx;
	C.Heightmap.CoastDistancePx = CoastDistancePx; C.Heightmap.CoastBlurPx = CoastBlurPx;
	C.Heightmap.Profiles.Reset();
	for (const auto& Pair : Profiles)
	{
		FTerrainProfile P;
		P.Base = Pair.Value.Base; P.Amplitude = Pair.Value.Amplitude; P.Frequency = Pair.Value.Frequency; P.Octaves = Pair.Value.Octaves;
		P.Lacunarity = Pair.Value.Lacunarity; P.Persistence = Pair.Value.Persistence; P.Noise = ToCoreNoise(Pair.Value.Noise); P.BlendPx = Pair.Value.BlendPx;
		C.Heightmap.Profiles.Add(Pair.Key, P);
	}
	C.Heightmap.SeabedDepth = SeabedDepth; C.Heightmap.SeabedDistancePx = SeabedDistancePx; C.Heightmap.SeabedBlurPx = SeabedBlurPx;
	C.Export.SeaLevelValue = SeaLevelValue; C.Export.WeightBlurPx = WeightBlurPx;
	return C;
}

void UTerrainConfig::FromCore(const FTerrainConfig& C)
{
	Seed = C.Seed; Size = C.Size;
	DiameterM = C.World.DiameterM; HeightRangeM = C.World.HeightRangeM; TilePx = C.World.TilePx; LodLevels = C.World.LodLevels;
	DiameterPct = C.Circle.DiameterPct; EdgeBandPct = C.Circle.EdgeBandPct;
	LandSeedAreaPct = C.Land.SeedAreaPct; LandMinSeparationPct = C.Land.MinSeparationPct;
	LandRadiusPctMin = C.Land.RadiusPctMin; LandRadiusPctMax = C.Land.RadiusPctMax; LandWarpPct = C.Land.WarpPct; LandChannelPct = C.Land.ChannelPct;
	LandNoiseOctaves = C.Land.Noise.Octaves; LandNoiseFrequency = C.Land.Noise.Frequency; LandNoiseLacunarity = C.Land.Noise.Lacunarity; LandNoisePersistence = C.Land.Noise.Persistence;
	LandThreshold = C.Land.Threshold; LandMinLakeAreaPx = C.Land.MinLakeAreaPx; LandMaxRetries = C.Land.MaxRetries;
	SeedsPerLandMin = C.Biomes.SeedsPerLandMin; SeedsPerLandMax = C.Biomes.SeedsPerLandMax; MinSeedSeparationPx = C.Biomes.MinSeedSeparationPx;
	CoastBandPx = C.Biomes.CoastBandPx; InlandFraction = C.Biomes.InlandFraction; BiomeMaxRetries = C.Biomes.MaxRetries;
	BalanceIterations = C.Biomes.BalanceIterations; BalanceTolerance = C.Biomes.BalanceTolerance;
	WarpStrengthPx = C.Biomes.Warp.StrengthPx; WarpFrequency = C.Biomes.Warp.Frequency; WarpOctaves = C.Biomes.Warp.Octaves;
	Types.Reset();
	for (const FTerrainBiomeType& T : C.Biomes.Types) { FTerrainBiomeTypeAsset A; A.Name = T.Name; A.Label = T.Label; A.Placement = FromCorePlacement(T.Placement); Types.Add(A); }
	BayPct = C.Spit.BayPct; LagoonPct = C.Spit.LagoonPct; SpitLengthPctMin = C.Spit.LengthPctMin; SpitLengthPctMax = C.Spit.LengthPctMax;
	MinLagoonPct = C.Spit.MinLagoonPct; SpitWidthPct = C.Spit.WidthPct; SpitWidthVariation = C.Spit.WidthVariation; StraitPct = C.Spit.StraitPct;
	SpitEdgeNoisePct = C.Spit.EdgeNoisePct; SpitGapPct = C.Spit.GapPct; SpitRisePx = C.Spit.RisePx;
	CoastDistancePx = C.Heightmap.CoastDistancePx; CoastBlurPx = C.Heightmap.CoastBlurPx;
	Profiles.Reset();
	for (const auto& Pair : C.Heightmap.Profiles)
	{
		FTerrainProfileAsset A;
		A.Base = Pair.Value.Base; A.Amplitude = Pair.Value.Amplitude; A.Frequency = Pair.Value.Frequency; A.Octaves = Pair.Value.Octaves;
		A.Lacunarity = Pair.Value.Lacunarity; A.Persistence = Pair.Value.Persistence; A.Noise = FromCoreNoise(Pair.Value.Noise); A.BlendPx = Pair.Value.BlendPx;
		Profiles.Add(Pair.Key, A);
	}
	SeabedDepth = C.Heightmap.SeabedDepth; SeabedDistancePx = C.Heightmap.SeabedDistancePx; SeabedBlurPx = C.Heightmap.SeabedBlurPx;
	SeaLevelValue = C.Export.SeaLevelValue; WeightBlurPx = C.Export.WeightBlurPx;
}

bool UTerrainConfig::Validate(FString& OutError) const
{
	return ValidateTerrainConfig(ToCore(), OutError);
}

bool UTerrainConfig::LoadJsonString(const FString& Text, FString& OutError)
{
	FTerrainConfig Core = ToCore();
	if (!TerrainConfigFromJson(Text, Core, OutError)) return false;
	if (!ValidateTerrainConfig(Core, OutError)) return false;
	FromCore(Core);
	OutError.Empty();
	return true;
}

FString UTerrainConfig::SaveJsonString() const
{
	return TerrainConfigToJson(ToCore());
}

void UTerrainConfig::LoadJson()
{
	FString Text, Error;
	if (!FFileHelper::LoadFileToString(Text, *JsonPath.FilePath))
	{
		UE_LOG(LogTerrainGenWorld, Error, TEXT("Cannot read %s"), *JsonPath.FilePath);
		return;
	}
	if (!LoadJsonString(Text, Error)) { UE_LOG(LogTerrainGenWorld, Error, TEXT("Load JSON failed: %s"), *Error); return; }
	Modify();
	UE_LOG(LogTerrainGenWorld, Log, TEXT("Loaded %s"), *JsonPath.FilePath);
}

void UTerrainConfig::SaveJson()
{
	if (FFileHelper::SaveStringToFile(SaveJsonString(), *JsonPath.FilePath))
		UE_LOG(LogTerrainGenWorld, Log, TEXT("Saved %s"), *JsonPath.FilePath);
	else
		UE_LOG(LogTerrainGenWorld, Error, TEXT("Cannot write %s"), *JsonPath.FilePath);
}
```

- [ ] **Step 5: Write the JSON read and write**

`Private/TerrainConfigJson.cpp`:
```cpp
#include "TerrainConfigAsset.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	using FObj = TSharedPtr<FJsonObject>;

	void Num(const FObj& O, const TCHAR* Key, float& V) { double D; if (O.IsValid() && O->TryGetNumberField(Key, D)) V = float(D); }
	void Num(const FObj& O, const TCHAR* Key, int32& V) { double D; if (O.IsValid() && O->TryGetNumberField(Key, D)) V = int32(FMath::RoundToInt(D)); }
	void Pair(const FObj& O, const TCHAR* Key, float& A, float& B)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O.IsValid() && O->TryGetArrayField(Key, Arr) && Arr->Num() == 2) { A = float((*Arr)[0]->AsNumber()); B = float((*Arr)[1]->AsNumber()); }
	}
	void Pair(const FObj& O, const TCHAR* Key, int32& A, int32& B)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O.IsValid() && O->TryGetArrayField(Key, Arr) && Arr->Num() == 2) { A = int32((*Arr)[0]->AsNumber()); B = int32((*Arr)[1]->AsNumber()); }
	}
	FObj Sub(const FObj& O, const TCHAR* Key)
	{
		const FObj* S;
		return (O.IsValid() && O->TryGetObjectField(Key, S)) ? *S : nullptr;
	}
	const TCHAR* NoiseNames[] = { TEXT("fractal"), TEXT("ridged"), TEXT("billow") };
	const TCHAR* PlacementNames[] = { TEXT("spit"), TEXT("coast"), TEXT("low"), TEXT("inland"), TEXT("any") };

	template<typename E, int32 N>
	bool ParseEnum(const FString& Text, const TCHAR* (&Names)[N], E& Out)
	{
		for (int32 I = 0; I < N; ++I) if (Text.Equals(Names[I], ESearchCase::IgnoreCase)) { Out = E(I); return true; }
		return false;
	}

	void ReadNoise(const FObj& O, FNoiseParams& P)
	{
		Num(O, TEXT("octaves"), P.Octaves); Num(O, TEXT("frequency"), P.Frequency);
		Num(O, TEXT("lacunarity"), P.Lacunarity); Num(O, TEXT("persistence"), P.Persistence);
	}
}

bool TerrainConfigFromJson(const FString& Text, FTerrainConfig& C, FString& OutError)
{
	FObj Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		OutError = FString::Printf(TEXT("The text is not valid JSON: %s"), *Reader->GetErrorMessage());
		return false;
	}
	Num(Root, TEXT("seed"), C.Seed);
	Num(Root, TEXT("size"), C.Size);
	if (FObj O = Sub(Root, TEXT("circle")))
	{
		Num(O, TEXT("diameter_pct"), C.Circle.DiameterPct); Num(O, TEXT("edge_band_pct"), C.Circle.EdgeBandPct);
	}
	if (FObj O = Sub(Root, TEXT("landmass")))
	{
		Num(O, TEXT("count"), C.Land.Count); Num(O, TEXT("seed_area_pct"), C.Land.SeedAreaPct);
		Num(O, TEXT("min_separation_pct"), C.Land.MinSeparationPct); Pair(O, TEXT("radius_pct"), C.Land.RadiusPctMin, C.Land.RadiusPctMax);
		Num(O, TEXT("warp_pct"), C.Land.WarpPct); Num(O, TEXT("channel_pct"), C.Land.ChannelPct);
		ReadNoise(Sub(O, TEXT("noise")), C.Land.Noise);
		Num(O, TEXT("threshold"), C.Land.Threshold); Num(O, TEXT("min_lake_area_px"), C.Land.MinLakeAreaPx); Num(O, TEXT("max_retries"), C.Land.MaxRetries);
	}
	if (FObj O = Sub(Root, TEXT("biomes")))
	{
		Pair(O, TEXT("seeds_per_landmass"), C.Biomes.SeedsPerLandMin, C.Biomes.SeedsPerLandMax);
		Num(O, TEXT("min_seed_separation_px"), C.Biomes.MinSeedSeparationPx); Num(O, TEXT("coast_band_px"), C.Biomes.CoastBandPx);
		Num(O, TEXT("inland_fraction"), C.Biomes.InlandFraction); Num(O, TEXT("max_retries"), C.Biomes.MaxRetries);
		Num(O, TEXT("balance_iterations"), C.Biomes.BalanceIterations); Num(O, TEXT("balance_tolerance"), C.Biomes.BalanceTolerance);
		if (FObj W = Sub(O, TEXT("warp")))
		{
			Num(W, TEXT("strength_px"), C.Biomes.Warp.StrengthPx); Num(W, TEXT("frequency"), C.Biomes.Warp.Frequency); Num(W, TEXT("octaves"), C.Biomes.Warp.Octaves);
		}
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O->TryGetArrayField(TEXT("types"), Arr))
		{
			TArray<FTerrainBiomeType> Types;
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const FObj T = V->AsObject();
				if (!T.IsValid()) continue;
				FTerrainBiomeType B;
				B.Name = FName(*T->GetStringField(TEXT("name")));
				B.Label = T->GetStringField(TEXT("label"));
				FString P;
				if (!T->TryGetStringField(TEXT("placement"), P) || !ParseEnum(P, PlacementNames, B.Placement))
				{
					OutError = FString::Printf(TEXT("biome %s has an unknown placement '%s'"), *B.Name.ToString(), *P);
					return false;
				}
				Types.Add(B);
			}
			C.Biomes.Types = Types;
		}
	}
	if (FObj O = Sub(Root, TEXT("spit")))
	{
		Num(O, TEXT("bay_pct"), C.Spit.BayPct); Num(O, TEXT("lagoon_pct"), C.Spit.LagoonPct);
		Pair(O, TEXT("length_pct"), C.Spit.LengthPctMin, C.Spit.LengthPctMax); Num(O, TEXT("min_lagoon_pct"), C.Spit.MinLagoonPct);
		Num(O, TEXT("width_pct"), C.Spit.WidthPct); Num(O, TEXT("width_variation"), C.Spit.WidthVariation); Num(O, TEXT("strait_pct"), C.Spit.StraitPct);
		Num(O, TEXT("edge_noise_pct"), C.Spit.EdgeNoisePct); Num(O, TEXT("gap_pct"), C.Spit.GapPct); Num(O, TEXT("rise_px"), C.Spit.RisePx);
	}
	if (FObj O = Sub(Root, TEXT("heightmap")))
	{
		Num(O, TEXT("coast_distance_px"), C.Heightmap.CoastDistancePx); Num(O, TEXT("coast_blur_px"), C.Heightmap.CoastBlurPx);
		Num(O, TEXT("seabed_depth"), C.Heightmap.SeabedDepth); Num(O, TEXT("seabed_distance_px"), C.Heightmap.SeabedDistancePx); Num(O, TEXT("seabed_blur_px"), C.Heightmap.SeabedBlurPx);
		if (FObj Profiles = Sub(O, TEXT("profiles")))
		{
			for (const auto& Pair : Profiles->Values)
			{
				const FObj P = Pair.Value->AsObject();
				if (!P.IsValid()) continue;
				FTerrainProfile& Prof = C.Heightmap.Profiles.FindOrAdd(FName(*Pair.Key));
				Num(P, TEXT("base"), Prof.Base); Num(P, TEXT("amplitude"), Prof.Amplitude); Num(P, TEXT("frequency"), Prof.Frequency);
				Num(P, TEXT("octaves"), Prof.Octaves); Num(P, TEXT("lacunarity"), Prof.Lacunarity); Num(P, TEXT("persistence"), Prof.Persistence);
				Num(P, TEXT("blend_px"), Prof.BlendPx);
				FString NoiseText;
				if (P->TryGetStringField(TEXT("noise"), NoiseText) && !ParseEnum(NoiseText, NoiseNames, Prof.Noise))
				{
					OutError = FString::Printf(TEXT("heightmap.profiles.%s.noise '%s' is not fractal, ridged, or billow"), *Pair.Key, *NoiseText);
					return false;
				}
			}
		}
	}
	if (FObj O = Sub(Root, TEXT("export")))
	{
		Num(O, TEXT("sea_level_value"), C.Export.SeaLevelValue); Num(O, TEXT("weight_blur_px"), C.Export.WeightBlurPx);
	}
	if (FObj O = Sub(Root, TEXT("world")))
	{
		Num(O, TEXT("diameter_m"), C.World.DiameterM); Num(O, TEXT("height_range_m"), C.World.HeightRangeM);
		Num(O, TEXT("tile_px"), C.World.TilePx); Num(O, TEXT("lod_levels"), C.World.LodLevels);
	}
	OutError.Empty();
	return true;
}

FString TerrainConfigToJson(const FTerrainConfig& C)
{
	auto Obj = [] { return MakeShared<FJsonObject>(); };
	auto PairArr = [](double A, double B)
	{
		TArray<TSharedPtr<FJsonValue>> Arr;
		Arr.Add(MakeShared<FJsonValueNumber>(A)); Arr.Add(MakeShared<FJsonValueNumber>(B));
		return Arr;
	};
	TSharedRef<FJsonObject> Root = Obj();
	Root->SetNumberField(TEXT("seed"), C.Seed);
	Root->SetNumberField(TEXT("size"), C.Size);
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("diameter_pct"), C.Circle.DiameterPct); O->SetNumberField(TEXT("edge_band_pct"), C.Circle.EdgeBandPct);
		Root->SetObjectField(TEXT("circle"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("count"), C.Land.Count); O->SetNumberField(TEXT("seed_area_pct"), C.Land.SeedAreaPct);
		O->SetNumberField(TEXT("min_separation_pct"), C.Land.MinSeparationPct); O->SetArrayField(TEXT("radius_pct"), PairArr(C.Land.RadiusPctMin, C.Land.RadiusPctMax));
		O->SetNumberField(TEXT("warp_pct"), C.Land.WarpPct); O->SetNumberField(TEXT("channel_pct"), C.Land.ChannelPct);
		TSharedRef<FJsonObject> N = Obj();
		N->SetNumberField(TEXT("octaves"), C.Land.Noise.Octaves); N->SetNumberField(TEXT("frequency"), C.Land.Noise.Frequency);
		N->SetNumberField(TEXT("lacunarity"), C.Land.Noise.Lacunarity); N->SetNumberField(TEXT("persistence"), C.Land.Noise.Persistence);
		O->SetObjectField(TEXT("noise"), N);
		O->SetNumberField(TEXT("threshold"), C.Land.Threshold); O->SetNumberField(TEXT("min_lake_area_px"), C.Land.MinLakeAreaPx); O->SetNumberField(TEXT("max_retries"), C.Land.MaxRetries);
		Root->SetObjectField(TEXT("landmass"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetArrayField(TEXT("seeds_per_landmass"), PairArr(C.Biomes.SeedsPerLandMin, C.Biomes.SeedsPerLandMax));
		O->SetNumberField(TEXT("min_seed_separation_px"), C.Biomes.MinSeedSeparationPx); O->SetNumberField(TEXT("coast_band_px"), C.Biomes.CoastBandPx);
		O->SetNumberField(TEXT("inland_fraction"), C.Biomes.InlandFraction); O->SetNumberField(TEXT("max_retries"), C.Biomes.MaxRetries);
		O->SetNumberField(TEXT("balance_iterations"), C.Biomes.BalanceIterations); O->SetNumberField(TEXT("balance_tolerance"), C.Biomes.BalanceTolerance);
		TSharedRef<FJsonObject> W = Obj();
		W->SetNumberField(TEXT("strength_px"), C.Biomes.Warp.StrengthPx); W->SetNumberField(TEXT("frequency"), C.Biomes.Warp.Frequency); W->SetNumberField(TEXT("octaves"), C.Biomes.Warp.Octaves);
		O->SetObjectField(TEXT("warp"), W);
		TArray<TSharedPtr<FJsonValue>> Types;
		for (const FTerrainBiomeType& T : C.Biomes.Types)
		{
			TSharedRef<FJsonObject> B = Obj();
			B->SetStringField(TEXT("name"), T.Name.ToString()); B->SetStringField(TEXT("label"), T.Label);
			B->SetStringField(TEXT("placement"), PlacementNames[uint8(T.Placement)]);
			Types.Add(MakeShared<FJsonValueObject>(B));
		}
		O->SetArrayField(TEXT("types"), Types);
		Root->SetObjectField(TEXT("biomes"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("bay_pct"), C.Spit.BayPct); O->SetNumberField(TEXT("lagoon_pct"), C.Spit.LagoonPct);
		O->SetArrayField(TEXT("length_pct"), PairArr(C.Spit.LengthPctMin, C.Spit.LengthPctMax)); O->SetNumberField(TEXT("min_lagoon_pct"), C.Spit.MinLagoonPct);
		O->SetNumberField(TEXT("width_pct"), C.Spit.WidthPct); O->SetNumberField(TEXT("width_variation"), C.Spit.WidthVariation); O->SetNumberField(TEXT("strait_pct"), C.Spit.StraitPct);
		O->SetNumberField(TEXT("edge_noise_pct"), C.Spit.EdgeNoisePct); O->SetNumberField(TEXT("gap_pct"), C.Spit.GapPct); O->SetNumberField(TEXT("rise_px"), C.Spit.RisePx);
		Root->SetObjectField(TEXT("spit"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("coast_distance_px"), C.Heightmap.CoastDistancePx); O->SetNumberField(TEXT("coast_blur_px"), C.Heightmap.CoastBlurPx);
		TSharedRef<FJsonObject> Profiles = Obj();
		for (const auto& Pair : C.Heightmap.Profiles)
		{
			TSharedRef<FJsonObject> P = Obj();
			P->SetNumberField(TEXT("base"), Pair.Value.Base); P->SetNumberField(TEXT("amplitude"), Pair.Value.Amplitude); P->SetNumberField(TEXT("frequency"), Pair.Value.Frequency);
			P->SetNumberField(TEXT("octaves"), Pair.Value.Octaves); P->SetNumberField(TEXT("lacunarity"), Pair.Value.Lacunarity); P->SetNumberField(TEXT("persistence"), Pair.Value.Persistence);
			P->SetStringField(TEXT("noise"), NoiseNames[uint8(Pair.Value.Noise)]); P->SetNumberField(TEXT("blend_px"), Pair.Value.BlendPx);
			Profiles->SetObjectField(Pair.Key.ToString(), P);
		}
		O->SetObjectField(TEXT("profiles"), Profiles);
		O->SetNumberField(TEXT("seabed_depth"), C.Heightmap.SeabedDepth); O->SetNumberField(TEXT("seabed_distance_px"), C.Heightmap.SeabedDistancePx); O->SetNumberField(TEXT("seabed_blur_px"), C.Heightmap.SeabedBlurPx);
		Root->SetObjectField(TEXT("heightmap"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("sea_level_value"), C.Export.SeaLevelValue); O->SetNumberField(TEXT("weight_blur_px"), C.Export.WeightBlurPx);
		Root->SetObjectField(TEXT("export"), O);
	}
	{
		TSharedRef<FJsonObject> O = Obj();
		O->SetNumberField(TEXT("diameter_m"), C.World.DiameterM); O->SetNumberField(TEXT("height_range_m"), C.World.HeightRangeM);
		O->SetNumberField(TEXT("tile_px"), C.World.TilePx); O->SetNumberField(TEXT("lod_levels"), C.World.LodLevels);
		Root->SetObjectField(TEXT("world"), O);
	}
	FString Out;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
	FJsonSerializer::Serialize(Root, Writer);
	return Out;
}
```

- [ ] **Step 6: Build and run**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.World.ConfigAsset`
Expected: `Passed  TerrainGen.World.ConfigAsset`. If `TestEqual` on floats fails by rounding through the JSON double, compare with `FMath::IsNearlyEqual` inside `TestTrue`.

- [ ] **Step 7: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the terrain config Data Asset with the JSON round trip"
```

---
### Task 4: The result object and the async generator

**Files:**
- Create: `Public/TerrainWorldResult.h`, `Private/TerrainWorldResult.cpp`, `Public/TerrainWorldGenerator.h`, `Private/TerrainWorldGenerator.cpp`
- Create: `Private/Tests/WorldTestUtil.h`
- Test: `Private/Tests/WorldResultTests.cpp`, `Private/Tests/WorldGeneratorTests.cpp`

**Interfaces:**
- Consumes: `GenerateTerrain`, `FTerrainProgressSink`, `FTerrainResult`, `UTerrainConfig::ToCore`.
- Produces:
  - `UCLASS(BlueprintType) UTerrainWorldResult : public UObject` holding `FTerrainResult Result` (plain member, not a UPROPERTY) and `FTerrainConfig Config`, with `int32 GetSize() const`, `float GetMetersPerPixel() const`, `float GetHeightMeters(int32 X, int32 Y) const` (decodes the 16-bit value with the config's sea level and the world's height range), `uint8 GetBiomeId(int32 X, int32 Y) const`, `uint8 GetSubtypeId(int32 X, int32 Y) const`, `uint8 GetLandId(int32 X, int32 Y) const`, `FLinearColor GetBiomeColor(int32 X, int32 Y) const` (the Python palette, darker for sub-type A and lighter for C, sea blue), and `void MakeTextures()` that fills `UPROPERTY() TObjectPtr<UTexture2D> HeightTexture` (`PF_G16`) and `BiomeColorTexture` (`PF_B8G8R8A8`) on demand; a second call does nothing.
  - `UCLASS(BlueprintType) UTerrainWorldGenerator : public UObject`: `void Generate(const UTerrainConfig* Config)`, `FTerrainProgress GetProgress() const` (a USTRUCT with `int32 Stage`, `FString StageName`, `float Fraction`, `bool bRunning`, `bool bDone`, `bool bFailed`, `FString Error`), `void Cancel()`, `UTerrainWorldResult* GetResult() const`, and the dynamic multicast delegate `FOnTerrainGenerated` with `(UTerrainWorldResult* Result, const FString& Error)` exposed as `UPROPERTY(BlueprintAssignable) FOnTerrainGenerated OnFinished`. The worker thread writes progress into atomics; the delegate fires on the game thread. `Generate` while running is ignored with a warning.
  - Test helper `FWaitForTerrainGenerator` latent command.

- [ ] **Step 1: Write the failing tests**

`Private/Tests/WorldTestUtil.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "TerrainWorldGenerator.h"

/** Waits until the generator is done or failed, or the deadline passes. */
DEFINE_LATENT_AUTOMATION_COMMAND_TWO_PARAMETER(FWaitForTerrainGenerator, TWeakObjectPtr<UTerrainWorldGenerator>, Generator, double, Deadline);

inline bool FWaitForTerrainGenerator::Update()
{
	if (!Generator.IsValid()) return true;
	const FTerrainProgress P = Generator->GetProgress();
	return P.bDone || P.bFailed || FPlatformTime::Seconds() > Deadline;
}
```

`Private/Tests/WorldResultTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainWorldResult.h"
#include "TerrainConfig.h"
#include "TerrainGenerator.h"
#include "Engine/Texture2D.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainWorldResultTest, "TerrainGen.World.Result",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainWorldResultTest::RunTest(const FString& Parameters)
{
	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	Cfg.Size = 253;
	Cfg.Seed = 3;
	UTerrainWorldResult* R = NewObject<UTerrainWorldResult>();
	FString Error;
	TestTrue(TEXT("generate"), GenerateTerrain(Cfg, R->Result, Error));
	R->Config = Cfg;
	TestEqual(TEXT("size"), R->GetSize(), 253);
	TestTrue(TEXT("meters per pixel"), FMath::IsNearlyEqual(R->GetMetersPerPixel(), 9000.0f / (253.0f * 0.9f), 0.01f));
	TestTrue(TEXT("corner is the sea floor"), R->GetHeightMeters(0, 0) < -0.2f * Cfg.World.HeightRangeM);
	TestEqual(TEXT("corner is sea"), int32(R->GetLandId(0, 0)), 0);
	bool bSomeLand = false;
	float MaxHeight = -1e9f;
	for (int32 Y = 0; Y < 253; Y += 4)
		for (int32 X = 0; X < 253; X += 4)
		{
			if (R->GetLandId(X, Y) > 0) { bSomeLand = true; MaxHeight = FMath::Max(MaxHeight, R->GetHeightMeters(X, Y)); }
			if (R->GetLandId(X, Y) > 0) TestTrue(TEXT("land has a biome"), R->GetBiomeId(X, Y) >= 1 && R->GetBiomeId(X, Y) <= 5);
		}
	TestTrue(TEXT("some land"), bSomeLand);
	TestTrue(TEXT("land rises above sea level"), MaxHeight > 0.0f);
	TestTrue(TEXT("sea is blue"), R->GetBiomeColor(0, 0).B > R->GetBiomeColor(0, 0).R);

	TestNull(TEXT("no texture before the call"), R->HeightTexture.Get());
	R->MakeTextures();
	TestNotNull(TEXT("height texture"), R->HeightTexture.Get());
	TestNotNull(TEXT("biome color texture"), R->BiomeColorTexture.Get());
	TestEqual(TEXT("height texture size"), R->HeightTexture->GetSizeX(), 253);
	TestEqual(TEXT("height texture format"), int32(R->HeightTexture->GetPixelFormat()), int32(PF_G16));
	UTexture2D* First = R->HeightTexture;
	R->MakeTextures();
	TestEqual(TEXT("second call keeps the texture"), R->HeightTexture.Get(), First);
	return true;
}

#endif
```

`Private/Tests/WorldGeneratorTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainWorldGenerator.h"
#include "TerrainWorldResult.h"
#include "TerrainConfigAsset.h"
#include "WorldTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainWorldGeneratorTest, "TerrainGen.World.Generator",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainWorldGeneratorTest::RunTest(const FString& Parameters)
{
	UTerrainConfig* Config = NewObject<UTerrainConfig>();
	Config->AddToRoot();
	Config->Size = 253;
	Config->Seed = 9;
	UTerrainWorldGenerator* Gen = NewObject<UTerrainWorldGenerator>();
	Gen->AddToRoot();
	const FTerrainProgress Idle = Gen->GetProgress();
	TestFalse(TEXT("idle before generate"), Idle.bRunning);
	Gen->Generate(Config);
	TestTrue(TEXT("running after generate"), Gen->GetProgress().bRunning);

	ADD_LATENT_AUTOMATION_COMMAND(FWaitForTerrainGenerator(Gen, FPlatformTime::Seconds() + 60.0));
	ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this, Gen, Config]()
	{
		const FTerrainProgress P = Gen->GetProgress();
		TestTrue(TEXT("done"), P.bDone);
		TestFalse(TEXT("not failed"), P.bFailed);
		TestFalse(TEXT("not running"), P.bRunning);
		TestEqual(TEXT("last stage"), P.Stage, 6);
		TestEqual(TEXT("last fraction"), P.Fraction, 1.0f);
		UTerrainWorldResult* R = Gen->GetResult();
		TestNotNull(TEXT("result"), R);
		if (R)
		{
			TestEqual(TEXT("result size"), R->GetSize(), 253);
			TestEqual(TEXT("result config seed"), R->Config.Seed, 9);
		}
		Gen->RemoveFromRoot();
		Config->RemoveFromRoot();
		return true;
	}));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainWorldGeneratorCancelTest, "TerrainGen.World.GeneratorCancel",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainWorldGeneratorCancelTest::RunTest(const FString& Parameters)
{
	UTerrainConfig* Config = NewObject<UTerrainConfig>();
	Config->AddToRoot();
	Config->Size = 1009;
	Config->Seed = 4;
	UTerrainWorldGenerator* Gen = NewObject<UTerrainWorldGenerator>();
	Gen->AddToRoot();
	Gen->Generate(Config);
	Gen->Cancel();
	ADD_LATENT_AUTOMATION_COMMAND(FWaitForTerrainGenerator(Gen, FPlatformTime::Seconds() + 60.0));
	ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this, Gen, Config]()
	{
		const FTerrainProgress P = Gen->GetProgress();
		TestTrue(TEXT("failed after cancel"), P.bFailed);
		TestTrue(TEXT("error says cancelled"), P.Error.Contains(TEXT("cancelled")));
		TestNull(TEXT("no result after cancel"), Gen->GetResult());
		Gen->RemoveFromRoot();
		Config->RemoveFromRoot();
		return true;
	}));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainWorldResult.h` not found.

- [ ] **Step 3: Write the result object**

`Public/TerrainWorldResult.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "TerrainConfig.h"
#include "TerrainResults.h"
#include "TerrainWorldResult.generated.h"

class UTexture2D;

/** A generated world: the arrays of the core, the config that made them, and textures on demand. */
UCLASS(BlueprintType)
class TERRAINGEN_API UTerrainWorldResult : public UObject
{
	GENERATED_BODY()
public:
	FTerrainResult Result;
	FTerrainConfig Config;

	UPROPERTY(BlueprintReadOnly, Category = "TerrainGen") TObjectPtr<UTexture2D> HeightTexture;
	UPROPERTY(BlueprintReadOnly, Category = "TerrainGen") TObjectPtr<UTexture2D> BiomeColorTexture;

	UFUNCTION(BlueprintPure, Category = "TerrainGen") int32 GetSize() const { return Result.Size; }
	UFUNCTION(BlueprintPure, Category = "TerrainGen") float GetMetersPerPixel() const { return Result.MetersPerPixel; }
	/** Height above sea level in meters, negative under the sea. */
	UFUNCTION(BlueprintPure, Category = "TerrainGen") float GetHeightMeters(int32 X, int32 Y) const;
	UFUNCTION(BlueprintPure, Category = "TerrainGen") uint8 GetBiomeId(int32 X, int32 Y) const { return Result.BiomeId.At(X, Y); }
	UFUNCTION(BlueprintPure, Category = "TerrainGen") uint8 GetSubtypeId(int32 X, int32 Y) const { return Result.SubtypeId.At(X, Y); }
	UFUNCTION(BlueprintPure, Category = "TerrainGen") uint8 GetLandId(int32 X, int32 Y) const { return Result.LandId.At(X, Y); }
	/** The preview color: the Python palette per biome, darker for sub-type A and lighter for C, blue for sea. */
	UFUNCTION(BlueprintPure, Category = "TerrainGen") FLinearColor GetBiomeColor(int32 X, int32 Y) const;
	/** Makes the height and the biome color textures. A second call does nothing. */
	UFUNCTION(BlueprintCallable, Category = "TerrainGen") void MakeTextures();
};
```

`Private/TerrainWorldResult.cpp`:
```cpp
#include "TerrainWorldResult.h"
#include "Engine/Texture2D.h"

namespace
{
	const FLinearColor Palette[] = {
		FLinearColor(224 / 255.0f, 200 / 255.0f, 120 / 255.0f),   // sea_side: sand
		FLinearColor(107 / 255.0f, 142 / 255.0f, 35 / 255.0f),    // marshlands: olive
		FLinearColor(46 / 255.0f, 107 / 255.0f, 58 / 255.0f),     // ancient_grove: deep green
		FLinearColor(122 / 255.0f, 79 / 255.0f, 163 / 255.0f),    // enchanted_forest: violet
		FLinearColor(140 / 255.0f, 140 / 255.0f, 140 / 255.0f),   // mountain_range: gray
	};
	const FLinearColor SeaColor(26 / 255.0f, 58 / 255.0f, 107 / 255.0f);
	const float SubtypeLightness[] = { 0.75f, 1.0f, 1.25f };
}

float UTerrainWorldResult::GetHeightMeters(int32 X, int32 Y) const
{
	const float Sea = float(Config.Export.SeaLevelValue);
	const float V = float(Result.Height.At(X, Y));
	const float Unit = V >= Sea ? (V - Sea) / (65535.0f - Sea) : (V - Sea) / Sea;   // -1..1
	return Unit * Config.World.HeightRangeM;
}

FLinearColor UTerrainWorldResult::GetBiomeColor(int32 X, int32 Y) const
{
	const uint8 Biome = Result.BiomeId.At(X, Y);
	if (Biome == 0) return SeaColor;
	const int32 Index = FMath::Clamp(int32(Biome) - 1, 0, 4);
	const uint8 Subtype = Result.SubtypeId.At(X, Y);
	const int32 Variant = Subtype == 0 ? 1 : (int32(Subtype) - 1) % 3;
	FLinearColor C = Palette[Index] * SubtypeLightness[Variant];
	C.A = 1.0f;
	return C.GetClamped();
}

void UTerrainWorldResult::MakeTextures()
{
	if (HeightTexture && BiomeColorTexture) return;
	const int32 Size = Result.Size;
	if (Size <= 0) return;

	HeightTexture = UTexture2D::CreateTransient(Size, Size, PF_G16);
	HeightTexture->SRGB = false;
	HeightTexture->Filter = TF_Bilinear;
	HeightTexture->AddressX = TA_Clamp;
	HeightTexture->AddressY = TA_Clamp;
	{
		FTexture2DMipMap& Mip = HeightTexture->GetPlatformData()->Mips[0];
		void* Data = Mip.BulkData.Lock(LOCK_READ_WRITE);
		FMemory::Memcpy(Data, Result.Height.Data.GetData(), Size * Size * sizeof(uint16));
		Mip.BulkData.Unlock();
	}
	HeightTexture->UpdateResource();

	BiomeColorTexture = UTexture2D::CreateTransient(Size, Size, PF_B8G8R8A8);
	BiomeColorTexture->SRGB = true;
	BiomeColorTexture->Filter = TF_Nearest;
	BiomeColorTexture->AddressX = TA_Clamp;
	BiomeColorTexture->AddressY = TA_Clamp;
	{
		FTexture2DMipMap& Mip = BiomeColorTexture->GetPlatformData()->Mips[0];
		FColor* Data = static_cast<FColor*>(Mip.BulkData.Lock(LOCK_READ_WRITE));
		for (int32 Y = 0; Y < Size; ++Y)
			for (int32 X = 0; X < Size; ++X)
				Data[Y * Size + X] = GetBiomeColor(X, Y).ToFColor(true);
		Mip.BulkData.Unlock();
	}
	BiomeColorTexture->UpdateResource();
}
```

- [ ] **Step 4: Write the generator object**

`Public/TerrainWorldGenerator.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include <atomic>
#include "TerrainWorldGenerator.generated.h"

class UTerrainConfig;
class UTerrainWorldResult;

USTRUCT(BlueprintType)
struct FTerrainProgress
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly) int32 Stage = 0;          // 1..6
	UPROPERTY(BlueprintReadOnly) FString StageName;
	UPROPERTY(BlueprintReadOnly) float Fraction = 0.0f;    // 0..1 inside the stage
	UPROPERTY(BlueprintReadOnly) bool bRunning = false;
	UPROPERTY(BlueprintReadOnly) bool bDone = false;
	UPROPERTY(BlueprintReadOnly) bool bFailed = false;
	UPROPERTY(BlueprintReadOnly) FString Error;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnTerrainGenerated, UTerrainWorldResult*, Result, const FString&, Error);

/** Generates a world on a worker thread. Progress is readable every tick; OnFinished fires on the game thread. */
UCLASS(BlueprintType)
class TERRAINGEN_API UTerrainWorldGenerator : public UObject
{
	GENERATED_BODY()
public:
	/** Starts a run. Returns at once. A second call while a run is active is ignored with a warning. */
	UFUNCTION(BlueprintCallable, Category = "TerrainGen") void Generate(const UTerrainConfig* Config);
	UFUNCTION(BlueprintPure, Category = "TerrainGen") FTerrainProgress GetProgress() const;
	/** Asks the worker to stop between attempts and stages. The run ends with the error "cancelled". */
	UFUNCTION(BlueprintCallable, Category = "TerrainGen") void Cancel();
	/** The last result, or null. */
	UFUNCTION(BlueprintPure, Category = "TerrainGen") UTerrainWorldResult* GetResult() const { return Result; }

	UPROPERTY(BlueprintAssignable, Category = "TerrainGen") FOnTerrainGenerated OnFinished;

	virtual void BeginDestroy() override;

private:
	UPROPERTY() TObjectPtr<UTerrainWorldResult> Result;

	std::atomic<int32> Stage{ 0 };
	std::atomic<float> Fraction{ 0.0f };
	std::atomic<bool> bRunning{ false };
	std::atomic<bool> bDone{ false };
	std::atomic<bool> bFailed{ false };
	std::atomic<bool> bCancel{ false };
	mutable FCriticalSection TextLock;
	FString StageName;
	FString ErrorText;
	int32 RunSerial = 0;
};
```

`Private/TerrainWorldGenerator.cpp`:
```cpp
#include "TerrainWorldGenerator.h"
#include "TerrainWorldResult.h"
#include "TerrainConfigAsset.h"
#include "TerrainGenerator.h"
#include "TerrainGenModule.h"
#include "Async/Async.h"

void UTerrainWorldGenerator::Generate(const UTerrainConfig* ConfigAsset)
{
	if (bRunning)
	{
		UE_LOG(LogTerrainGenWorld, Warning, TEXT("Generate ignored: a run is active"));
		return;
	}
	if (!ConfigAsset)
	{
		UE_LOG(LogTerrainGenWorld, Error, TEXT("Generate needs a config"));
		return;
	}
	FString Error;
	if (!ConfigAsset->Validate(Error))
	{
		UE_LOG(LogTerrainGenWorld, Error, TEXT("Config is not valid: %s"), *Error);
		return;
	}
	const FTerrainConfig Config = ConfigAsset->ToCore();
	Result = nullptr;
	Stage = 0;
	Fraction = 0.0f;
	bDone = false;
	bFailed = false;
	bCancel = false;
	{
		FScopeLock Lock(&TextLock);
		StageName.Empty();
		ErrorText.Empty();
	}
	bRunning = true;
	const int32 Serial = ++RunSerial;
	TWeakObjectPtr<UTerrainWorldGenerator> WeakThis(this);

	Async(EAsyncExecution::Thread, [WeakThis, Config, Serial]()
	{
		// the worker: it touches this object only through the atomics and the lock
		TSharedPtr<FTerrainResult> Arrays = MakeShared<FTerrainResult>();
		FString RunError;
		FTerrainProgressSink Sink;
		Sink.IsCancelled = [WeakThis]() { UTerrainWorldGenerator* G = WeakThis.Get(); return !G || G->bCancel.load(); };
		Sink.Report = [WeakThis](int32 InStage, const FString& Name, float InFraction)
		{
			if (UTerrainWorldGenerator* G = WeakThis.Get())
			{
				G->Stage = InStage;
				G->Fraction = InFraction;
				FScopeLock Lock(&G->TextLock);
				G->StageName = Name;
			}
		};
		const bool bOk = GenerateTerrain(Config, *Arrays, RunError, &Sink);

		AsyncTask(ENamedThreads::GameThread, [WeakThis, Config, Serial, Arrays, bOk, RunError]()
		{
			UTerrainWorldGenerator* G = WeakThis.Get();
			if (!G || G->RunSerial != Serial) return;
			if (bOk)
			{
				UTerrainWorldResult* R = NewObject<UTerrainWorldResult>(G);
				R->Result = MoveTemp(*Arrays);
				R->Config = Config;
				G->Result = R;
				G->Stage = 6;
				G->Fraction = 1.0f;
				G->bDone = true;
			}
			else
			{
				FScopeLock Lock(&G->TextLock);
				G->ErrorText = RunError;
				G->bFailed = true;
			}
			G->bRunning = false;
			G->OnFinished.Broadcast(G->Result, bOk ? FString() : RunError);
		});
	});
}

FTerrainProgress UTerrainWorldGenerator::GetProgress() const
{
	FTerrainProgress P;
	P.Stage = Stage;
	P.Fraction = Fraction;
	P.bRunning = bRunning;
	P.bDone = bDone;
	P.bFailed = bFailed;
	FScopeLock Lock(&TextLock);
	P.StageName = StageName;
	P.Error = ErrorText;
	return P;
}

void UTerrainWorldGenerator::Cancel()
{
	bCancel = true;
}

void UTerrainWorldGenerator::BeginDestroy()
{
	bCancel = true;
	Super::BeginDestroy();
}
```
If `std::atomic<float>` does not compile with the engine's headers, store the fraction as `std::atomic<int32>` in thousandths and divide in `GetProgress`.

- [ ] **Step 5: Build and run**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.World`
Expected: `Passed` for `Result`, `Generator`, `GeneratorCancel`, `ConfigAsset`, `Smoke`. The latent tests need the automation controller to tick; the headless run in `RunTests.ps1` does tick. If `GeneratorCancel` finishes with a full result instead of a cancel because the run at 1009 px ended before the cancel flag was read, raise its size to 2017.

- [ ] **Step 6: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the world result object and the async world generator"
```

---
### Task 5: The terrain actor with the Generate button, the preview mesh, and GenerateWorld

**Files:**
- Create: `Public/TerrainWorldActor.h`, `Private/TerrainWorldActor.cpp`, `Public/TerrainGenLibrary.h`, `Private/TerrainGenLibrary.cpp`
- Test: `Private/Tests/WorldActorTests.cpp`

**Interfaces:**
- Consumes: `UTerrainConfig`, `UTerrainWorldGenerator`, `UTerrainWorldResult`, `UProceduralMeshComponent`.
- Produces:
  - `UCLASS() ATerrainWorld : public AActor` with `UPROPERTY(EditAnywhere) TObjectPtr<UTerrainConfig> Config` (null means "the defaults"), `UPROPERTY(EditAnywhere) bool bGenerateOnBeginPlay = false`, `UPROPERTY(EditAnywhere, meta=(ClampMin=1)) int32 PreviewStep = 0` (0 means "pick the step that keeps the preview under 250 000 vertices"), `UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> PreviewMesh`, `UPROPERTY(VisibleAnywhere, Transient) TObjectPtr<UTerrainWorldGenerator> Generator`, `UFUNCTION(CallInEditor, BlueprintCallable) void Generate()`, `UFUNCTION(CallInEditor, BlueprintCallable) void CancelGeneration()`, `UFUNCTION(BlueprintPure) FTerrainProgress GetProgress() const`, `UFUNCTION(BlueprintPure) UTerrainWorldResult* GetResult() const`, the delegate `UPROPERTY(BlueprintAssignable) FOnTerrainWorldBuilt OnBuilt` with `(ATerrainWorld* World, const FString& Error)`, and `void BuildPreview(const UTerrainWorldResult* Result)` (public, so a test can call it with a result made on the game thread).
  - The preview: a grid over the whole square, every `Step` pixels, vertices at `(X * MetersPerPixel * 100, Y * MetersPerPixel * 100, Height * 100)` in cm relative to the actor, centered on the actor (the world center is the actor location), vertex colors from `GetBiomeColor`, normals from the height differences, one section, no collision. The material is the engine's vertex color debug material `/Engine/EngineDebugMaterials/VertexColorMaterial`, with a fallback to the default material if the load fails.
  - `UCLASS() UTerrainGenLibrary : public UBlueprintFunctionLibrary` with `USTRUCT(BlueprintType) FTerrainGenerateParams { FVector Origin; FRotator Rotation; TObjectPtr<UTerrainConfig> Config; int32 SeedOverride = -1; bool bBuildCollision = true; bool bBuildWater = true; bool bBuildInEditor = false; }` and `static ATerrainWorld* GenerateWorld(UObject* WorldContextObject, const FTerrainGenerateParams& Params, ATerrainWorld* Existing = nullptr)`: spawns an `ATerrainWorld` at the origin and rotation, or reuses `Existing`, applies the seed override to a copy of the config, calls `Generate`, and returns the actor. Callers bind `OnBuilt` on the returned actor. `bBuildCollision` and `bBuildWater` are stored on the actor for phase 4 and do nothing yet.

- [ ] **Step 1: Write the failing test**

`Private/Tests/WorldActorTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "ProceduralMeshComponent.h"
#include "TerrainWorldActor.h"
#include "TerrainWorldResult.h"
#include "TerrainConfigAsset.h"
#include "TerrainGenLibrary.h"
#include "TerrainGenerator.h"
#include "WorldTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainWorldActorPreviewTest, "TerrainGen.World.ActorPreview",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainWorldActorPreviewTest::RunTest(const FString& Parameters)
{
	UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
	FWorldContext& Context = GEngine->CreateNewWorldContext(EWorldType::Game);
	Context.SetCurrentWorld(World);
	World->InitializeActorsForPlay(FURL());

	ATerrainWorld* Actor = World->SpawnActor<ATerrainWorld>(FVector(1000.0f, 2000.0f, 0.0f), FRotator::ZeroRotator);
	TestNotNull(TEXT("actor spawned"), Actor);

	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	Cfg.Size = 253;
	Cfg.Seed = 3;
	UTerrainWorldResult* R = NewObject<UTerrainWorldResult>(Actor);
	FString Error;
	TestTrue(TEXT("generate"), GenerateTerrain(Cfg, R->Result, Error));
	R->Config = Cfg;

	Actor->PreviewStep = 4;
	Actor->BuildPreview(R);
	UProceduralMeshComponent* Mesh = Actor->PreviewMesh;
	TestNotNull(TEXT("preview mesh"), Mesh);
	TestEqual(TEXT("one section"), Mesh->GetNumSections(), 1);
	const FProcMeshSection* Section = Mesh->GetProcMeshSection(0);
	TestNotNull(TEXT("section"), Section);
	if (Section)
	{
		const int32 Side = (253 + 3) / 4;   // ceil(253 / 4)
		TestEqual(TEXT("vertex count"), Section->ProcVertexBuffer.Num(), Side * Side);
		TestEqual(TEXT("triangle count"), Section->ProcIndexBuffer.Num(), (Side - 1) * (Side - 1) * 6);
		const float MetersPerPixel = R->GetMetersPerPixel();
		const float ExpectedExtent = 0.5f * 252.0f * MetersPerPixel * 100.0f;
		const FVector First = Section->ProcVertexBuffer[0].Position;
		TestTrue(TEXT("preview is centered on the actor"), FMath::IsNearlyEqual(First.X, -ExpectedExtent, 1.0f) && FMath::IsNearlyEqual(First.Y, -ExpectedExtent, 1.0f));
		TestTrue(TEXT("corner is the sea floor in cm"), First.Z < -0.2f * Cfg.World.HeightRangeM * 100.0f);
		bool bColorVaries = false;
		for (const FProcMeshVertex& V : Section->ProcVertexBuffer) if (V.Color != Section->ProcVertexBuffer[0].Color) { bColorVaries = true; break; }
		TestTrue(TEXT("vertex colors vary"), bColorVaries);
	}
	TestTrue(TEXT("bounds cover the world"), Mesh->Bounds.BoxExtent.X > 1000.0f);

	// the automatic step keeps the preview small
	Actor->PreviewStep = 0;
	Cfg.Size = 1009;
	UTerrainWorldResult* Big = NewObject<UTerrainWorldResult>(Actor);
	TestTrue(TEXT("generate 1009"), GenerateTerrain(Cfg, Big->Result, Error));
	Big->Config = Cfg;
	Actor->BuildPreview(Big);
	const FProcMeshSection* BigSection = Actor->PreviewMesh->GetProcMeshSection(0);
	TestTrue(TEXT("automatic step stays under 250k vertices"), BigSection && BigSection->ProcVertexBuffer.Num() <= 250000);

	GEngine->DestroyWorldContext(World);
	World->DestroyWorld(false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainGenerateWorldTest, "TerrainGen.World.GenerateWorld",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainGenerateWorldTest::RunTest(const FString& Parameters)
{
	UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
	FWorldContext& Context = GEngine->CreateNewWorldContext(EWorldType::Game);
	Context.SetCurrentWorld(World);
	World->InitializeActorsForPlay(FURL());

	UTerrainConfig* Config = NewObject<UTerrainConfig>();
	Config->AddToRoot();
	Config->Size = 253;
	Config->Seed = 1;
	FTerrainGenerateParams Params;
	Params.Origin = FVector(500.0f, 0.0f, 100.0f);
	Params.Config = Config;
	Params.SeedOverride = 21;
	ATerrainWorld* Actor = UTerrainGenLibrary::GenerateWorld(World, Params);
	TestNotNull(TEXT("actor"), Actor);
	if (!Actor) return false;
	TestTrue(TEXT("actor at the origin"), Actor->GetActorLocation().Equals(Params.Origin));
	TestTrue(TEXT("running"), Actor->GetProgress().bRunning);

	ADD_LATENT_AUTOMATION_COMMAND(FWaitForTerrainGenerator(Actor->Generator, FPlatformTime::Seconds() + 60.0));
	ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([this, Actor, Config, World]()
	{
		// the preview is built on the game thread in the finished callback, which ran before this command
		TestTrue(TEXT("done"), Actor->GetProgress().bDone);
		UTerrainWorldResult* R = Actor->GetResult();
		TestNotNull(TEXT("result"), R);
		if (R) TestEqual(TEXT("seed override used"), R->Config.Seed, 21);
		TestTrue(TEXT("preview built"), Actor->PreviewMesh->GetNumSections() == 1);
		Config->RemoveFromRoot();
		GEngine->DestroyWorldContext(World);
		World->DestroyWorld(false);
		return true;
	}));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainWorldActor.h` not found.

- [ ] **Step 3: Write the actor**

`Public/TerrainWorldActor.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TerrainWorldGenerator.h"
#include "TerrainWorldActor.generated.h"

class UTerrainConfig;
class UTerrainWorldResult;
class UProceduralMeshComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnTerrainWorldBuilt, ATerrainWorld*, World, const FString&, Error);

/** The generated world in a level. Press Generate in the details panel to build it in the editor. */
UCLASS(BlueprintType, Blueprintable)
class TERRAINGEN_API ATerrainWorld : public AActor
{
	GENERATED_BODY()
public:
	ATerrainWorld();

	/** The settings. Null uses the defaults. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TerrainGen") TObjectPtr<UTerrainConfig> Config;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TerrainGen") bool bGenerateOnBeginPlay = false;
	/** Pixels per preview vertex. 0 picks a step that keeps the preview under 250 000 vertices. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TerrainGen", meta = (ClampMin = "0")) int32 PreviewStep = 0;
	/** Stored for phase 4. They do nothing yet. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TerrainGen") bool bBuildCollision = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TerrainGen") bool bBuildWater = true;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "TerrainGen") TObjectPtr<UProceduralMeshComponent> PreviewMesh;
	UPROPERTY(VisibleAnywhere, Transient, BlueprintReadOnly, Category = "TerrainGen") TObjectPtr<UTerrainWorldGenerator> Generator;

	UPROPERTY(BlueprintAssignable, Category = "TerrainGen") FOnTerrainWorldBuilt OnBuilt;

	/** Generates the world with the config on a worker thread and rebuilds the preview when done. */
	UFUNCTION(CallInEditor, BlueprintCallable, Category = "TerrainGen") void Generate();
	UFUNCTION(CallInEditor, BlueprintCallable, Category = "TerrainGen") void CancelGeneration();
	UFUNCTION(BlueprintPure, Category = "TerrainGen") FTerrainProgress GetProgress() const;
	UFUNCTION(BlueprintPure, Category = "TerrainGen") UTerrainWorldResult* GetResult() const;

	/** Rebuilds the preview mesh from a result. Game thread only. */
	void BuildPreview(const UTerrainWorldResult* Result);

	virtual void BeginPlay() override;

private:
	UFUNCTION() void HandleFinished(UTerrainWorldResult* Result, const FString& Error);
	int32 PickStep(int32 Size) const;
};
```

`Private/TerrainWorldActor.cpp`:
```cpp
#include "TerrainWorldActor.h"
#include "TerrainWorldResult.h"
#include "TerrainConfigAsset.h"
#include "TerrainGenModule.h"
#include "ProceduralMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

ATerrainWorld::ATerrainWorld()
{
	PrimaryActorTick.bCanEverTick = false;
	PreviewMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("PreviewMesh"));
	SetRootComponent(PreviewMesh);
	PreviewMesh->bUseAsyncCooking = true;
	PreviewMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void ATerrainWorld::BeginPlay()
{
	Super::BeginPlay();
	if (bGenerateOnBeginPlay) Generate();
}

void ATerrainWorld::Generate()
{
	if (!Generator)
	{
		Generator = NewObject<UTerrainWorldGenerator>(this);
		Generator->OnFinished.AddDynamic(this, &ATerrainWorld::HandleFinished);
	}
	if (Generator->GetProgress().bRunning)
	{
		UE_LOG(LogTerrainGenWorld, Warning, TEXT("%s: a run is active"), *GetName());
		return;
	}
	UTerrainConfig* Used = Config ? Config.Get() : NewObject<UTerrainConfig>(this);
	UE_LOG(LogTerrainGenWorld, Log, TEXT("%s: generating a %d px world, seed %d"), *GetName(), Used->Size, Used->Seed);
	Generator->Generate(Used);
}

void ATerrainWorld::CancelGeneration()
{
	if (Generator) Generator->Cancel();
}

FTerrainProgress ATerrainWorld::GetProgress() const
{
	return Generator ? Generator->GetProgress() : FTerrainProgress();
}

UTerrainWorldResult* ATerrainWorld::GetResult() const
{
	return Generator ? Generator->GetResult() : nullptr;
}

void ATerrainWorld::HandleFinished(UTerrainWorldResult* Result, const FString& Error)
{
	if (Result)
	{
		BuildPreview(Result);
		UE_LOG(LogTerrainGenWorld, Log, TEXT("%s: world built, %d px, %.2f m per pixel"), *GetName(), Result->GetSize(), Result->GetMetersPerPixel());
	}
	else
	{
		UE_LOG(LogTerrainGenWorld, Error, TEXT("%s: generation failed: %s"), *GetName(), *Error);
	}
	OnBuilt.Broadcast(this, Error);
}

int32 ATerrainWorld::PickStep(int32 Size) const
{
	if (PreviewStep > 0) return PreviewStep;
	int32 Step = 1;
	while ((Size + Step - 1) / Step * ((Size + Step - 1) / Step) > 250000) ++Step;
	return Step;
}

void ATerrainWorld::BuildPreview(const UTerrainWorldResult* Result)
{
	if (!Result || Result->GetSize() <= 0) return;
	const int32 Size = Result->GetSize();
	const int32 Step = PickStep(Size);
	const int32 Side = (Size + Step - 1) / Step;
	const float Spacing = Result->GetMetersPerPixel() * 100.0f;   // cm per pixel
	const float Extent = 0.5f * float(Size - 1) * Spacing;

	TArray<FVector> Vertices;
	TArray<int32> Triangles;
	TArray<FVector> Normals;
	TArray<FVector2D> UV0;
	TArray<FLinearColor> Colors;
	TArray<FProcMeshTangent> Tangents;
	Vertices.Reserve(Side * Side);
	Colors.Reserve(Side * Side);
	UV0.Reserve(Side * Side);
	Normals.Reserve(Side * Side);
	Triangles.Reserve((Side - 1) * (Side - 1) * 6);

	auto Px = [&](int32 I) { return FMath::Min(I * Step, Size - 1); };
	for (int32 J = 0; J < Side; ++J)
	{
		for (int32 I = 0; I < Side; ++I)
		{
			const int32 X = Px(I), Y = Px(J);
			const float H = Result->GetHeightMeters(X, Y) * 100.0f;
			Vertices.Add(FVector(X * Spacing - Extent, Y * Spacing - Extent, H));
			Colors.Add(Result->GetBiomeColor(X, Y));
			UV0.Add(FVector2D(float(X) / float(Size - 1), float(Y) / float(Size - 1)));
			const int32 XL = FMath::Max(X - Step, 0), XR = FMath::Min(X + Step, Size - 1);
			const int32 YU = FMath::Max(Y - Step, 0), YD = FMath::Min(Y + Step, Size - 1);
			const float DX = (Result->GetHeightMeters(XR, Y) - Result->GetHeightMeters(XL, Y)) * 100.0f / (float(XR - XL) * Spacing);
			const float DY = (Result->GetHeightMeters(X, YD) - Result->GetHeightMeters(X, YU)) * 100.0f / (float(YD - YU) * Spacing);
			Normals.Add(FVector(-DX, -DY, 1.0f).GetSafeNormal());
		}
	}
	for (int32 J = 0; J < Side - 1; ++J)
	{
		for (int32 I = 0; I < Side - 1; ++I)
		{
			const int32 A = J * Side + I, B = A + 1, C = A + Side, D = C + 1;
			Triangles.Append({ A, C, B, B, C, D });
		}
	}
	PreviewMesh->ClearAllMeshSections();
	PreviewMesh->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, UV0, Colors, Tangents, false);
	UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineDebugMaterials/VertexColorMaterial.VertexColorMaterial"));
	if (Material) PreviewMesh->SetMaterial(0, Material);
}
```
If the triangle winding shows the mesh from below only, swap `B` and `C` in the append.

- [ ] **Step 4: Write the library**

`Public/TerrainGenLibrary.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "TerrainGenLibrary.generated.h"

class UTerrainConfig;
class ATerrainWorld;

USTRUCT(BlueprintType)
struct FTerrainGenerateParams
{
	GENERATED_BODY()
	/** World position of the circle center. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FVector Origin = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FRotator Rotation = FRotator::ZeroRotator;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UTerrainConfig> Config;
	/** -1 keeps the seed of the config. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 SeedOverride = -1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bBuildCollision = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bBuildWater = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bBuildInEditor = false;
};

UCLASS()
class TERRAINGEN_API UTerrainGenLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** Spawns a terrain world at the origin, or reuses Existing, and starts the generation. Bind OnBuilt on the returned actor. */
	UFUNCTION(BlueprintCallable, Category = "TerrainGen", meta = (WorldContext = "WorldContextObject"))
	static ATerrainWorld* GenerateWorld(UObject* WorldContextObject, const FTerrainGenerateParams& Params, ATerrainWorld* Existing = nullptr);
};
```

`Private/TerrainGenLibrary.cpp`:
```cpp
#include "TerrainGenLibrary.h"
#include "TerrainWorldActor.h"
#include "TerrainConfigAsset.h"
#include "TerrainGenModule.h"
#include "Engine/World.h"
#include "Engine/Engine.h"

ATerrainWorld* UTerrainGenLibrary::GenerateWorld(UObject* WorldContextObject, const FTerrainGenerateParams& Params, ATerrainWorld* Existing)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World) return nullptr;
	ATerrainWorld* Actor = Existing;
	if (!Actor)
	{
		FActorSpawnParameters Spawn;
		Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Actor = World->SpawnActor<ATerrainWorld>(Params.Origin, Params.Rotation, Spawn);
		if (!Actor) return nullptr;
	}
	else
	{
		Actor->SetActorLocationAndRotation(Params.Origin, Params.Rotation);
	}
	UTerrainConfig* Config = Params.Config ? DuplicateObject<UTerrainConfig>(Params.Config, Actor) : NewObject<UTerrainConfig>(Actor);
	if (Params.SeedOverride >= 0) Config->Seed = Params.SeedOverride;
	Actor->Config = Config;
	Actor->bBuildCollision = Params.bBuildCollision;
	Actor->bBuildWater = Params.bBuildWater;
	Actor->Generate();
	return Actor;
}
```

- [ ] **Step 5: Build and run**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.World`
Expected: every `TerrainGen.World.*` test passes. If `UWorld::CreateWorld` in the test asserts under `-nullrhi`, keep the world creation but pass `EWorldType::Game` and skip `InitializeActorsForPlay`; if the actor spawn still fails, report it and stop.

- [ ] **Step 6: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the terrain world actor with the Generate button, the preview mesh, and GenerateWorld"
```

---

### Task 6: Try it in the editor

**Files:** none in the repo; a manual check by the person, plus a short section in the plugin README.

- Create: `Plugins/TerrainGen/README.md`

- [ ] **Step 1: Write the README**

`Plugins/TerrainGen/README.md`:
```markdown
# TerrainGen

Generates a circular world with 3 lands, sand bars, 5 biomes, and a heightmap. A C++ port of the
Python generator in the terrain-generation-lab repo.

## Try it in the editor

1. Open the project. The plugin is enabled in the project file.
2. Make a config: right-click in the Content Browser, Miscellaneous, Data Asset, pick TerrainConfig.
   Set Size to 1009 for a quick look, or leave 4033 for the real world. Load JSON reads a file from the
   Python UI; Save JSON writes one.
3. Open a level. Place a Terrain World actor from the Place Actors panel (search "Terrain World").
4. In its details, set Config to the asset and press Generate. The output log shows the progress
   and the world appears as a colored preview mesh centered on the actor, one color per biome,
   heights in meters times the world's height range. A 1009 px world takes a few seconds, a 4033 px
   world a few tens of seconds.
5. Generate On Begin Play makes the actor generate when the game starts.

## From code

`UTerrainGenLibrary::GenerateWorld(WorldContext, Params)` spawns the actor at `Params.Origin` and
starts the generation. Bind `OnBuilt` on the returned actor. `Params.SeedOverride` replaces the
seed of the config.

## Tests

`Tools\Build.ps1` then `Tools\RunTests.ps1 TerrainGen` runs every automation test.
```

- [ ] **Step 2: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen/README.md
git commit -m "Add the plugin README with the editor steps"
```

---

## Self-review notes

- Spec sections 5 (config asset with Load JSON and Save JSON), 9 (`GenerateWorld`, the async generator with progress and cancel), 10 (textures on demand only), and the editor iteration loop of 11 (the Generate button) are covered by Tasks 3, 4, and 5. The tiles, LOD, master material, collision, and water of section 11 are phase 4. The memory pass of section 6 is Task 1.
- Names used across tasks: `UTerrainConfig::ToCore`, `Validate`, `LoadJsonString`, `SaveJsonString`; `UTerrainWorldResult::Result`, `Config`, `GetSize`, `GetMetersPerPixel`, `GetHeightMeters`, `GetBiomeColor`, `MakeTextures`, `HeightTexture`, `BiomeColorTexture`; `UTerrainWorldGenerator::Generate`, `GetProgress`, `Cancel`, `GetResult`, `OnFinished`; `FTerrainProgress`; `ATerrainWorld::Config`, `PreviewStep`, `PreviewMesh`, `Generator`, `Generate`, `BuildPreview`, `GetProgress`, `GetResult`, `OnBuilt`; `UTerrainGenLibrary::GenerateWorld`, `FTerrainGenerateParams`. All consistent between the tests and the code.
- The preview uses the engine debug vertex-color material, so no content asset is needed to see the world; phase 4 brings the master material.
