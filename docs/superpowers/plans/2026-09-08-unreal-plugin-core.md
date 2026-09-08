# TerrainGen plugin, phases 1 and 2: core library and stages. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A C++ Unreal 5.8 plugin module `TerrainGenCore` that generates the circular world with 3 lands, sand bars, biomes, a heightmap, and the export arrays, with automation tests, and a debug image writer to check the look.

**Architecture:** One runtime module, `TerrainGenCore`, of plain C++ with no UObjects. `TGrid<T>` holds square arrays. `TerrainAlgorithms` replaces SciPy: distance transform, labels, blur, closing, noise. Six stage functions port the Python modules one to one. `GenerateTerrain` runs them in order with a progress sink.

**Tech Stack:** Unreal Engine 5.8.2 at E:\Epic Games\UE_5.8, C++20 as Unreal builds it, UnrealBuildTool, the Unreal automation test framework, PowerShell scripts for build and test.

**Spec:** S:\python-terrain-generation\docs\superpowers\specs\2026-09-08-unreal-plugin-design.md. The Python reference code is in S:\python-terrain-generation\terrain\. Read the Python module named in each task before you port it.

## Global Constraints

- Engine: Unreal 5.8.2 at `E:\Epic Games\UE_5.8`. Project: `S:\WorldGenUE\WorldGenUE.uproject`. Plugin: `S:\WorldGenUE\Plugins\TerrainGen`.
- The term is **Land**, not Landmass, in every C++ name, file, and comment. `LandId`, `MakeLands`, "3 lands".
- `TerrainGenCore` depends on the `Core` module only. No UObjects, no Engine includes.
- Seed parity with Python is not required. Noise uses `FMath::PerlinNoise2D`.
- Sizes: 127, 253, 505, 1009, 2017, 4033, 8129. Tests use 253.
- Every source file starts with `#pragma once` in headers and `#include "TerrainGenCore.h"` style relative includes as shown. No copyright banner.
- Commits go into the git repo at `S:\WorldGenUE` (Task 1 creates it). Commit messages end with the two attribution lines from the session.
- Build command (PowerShell): `S:\WorldGenUE\Tools\Build.ps1`. Test command: `S:\WorldGenUE\Tools\RunTests.ps1 <TestFilter>`. Both are created in Task 1.
- Automation tests live in `Source/TerrainGenCore/Private/Tests/`, inside `#if WITH_DEV_AUTOMATION_TESTS`, named `TerrainGen.Core.<Topic>`.
- Line endings LF, UTF-8, tabs for indentation in C++ (Unreal style), `PascalCase` names, `b` prefix for bools, `Out` prefix for output parameters.

## File structure

```
S:\WorldGenUE\
  .gitignore
  Tools\Build.ps1                       builds WorldGenUEEditor Win64 Development
  Tools\RunTests.ps1                    runs automation tests headless, prints pass/fail lines
  Plugins\TerrainGen\
    TerrainGen.uplugin
    Source\TerrainGenCore\
      TerrainGenCore.Build.cs
      Public\
        TerrainGenCore.h                module interface, log category
        TerrainGrid.h                   TGrid<T>
        TerrainNoise.h                  Smoothstep, noise types, MakeNoise
        TerrainAlgorithms.h             DistanceToMask, LabelComponents, GaussianBlur, Closing, Gradient, Dilate
        TerrainConfig.h                 the config structs, defaults, ValidateTerrainConfig
        TerrainResults.h                FCircleResult, FLandResult, FBiomeResult, FHeightResult, FTerrainResult
        TerrainStages.h                 MakeCircle, MakeLands, MakeSpits, MakeBiomes, MakeHeightmap, MakeExportArrays
        TerrainGenerator.h              FTerrainProgressSink, GenerateTerrain
        TerrainDebugImages.h            WritePgm for a look at the grids
      Private\
        TerrainGenCore.cpp
        TerrainNoise.cpp
        TerrainAlgorithms.cpp
        TerrainConfig.cpp
        TerrainStageCircle.cpp
        TerrainStageLands.cpp
        TerrainStageSpits.cpp
        TerrainStageBiomes.cpp
        TerrainStageHeightmap.cpp
        TerrainStageExport.cpp
        TerrainGenerator.cpp
        TerrainDebugImages.cpp
        Tests\
          TerrainTestUtil.h             MakeTestWorld helpers shared by the stage tests
          GridTests.cpp
          NoiseTests.cpp
          AlgorithmTests.cpp
          ConfigTests.cpp
          CircleTests.cpp
          LandsTests.cpp
          SpitsTests.cpp
          BiomesTests.cpp
          HeightmapTests.cpp
          ExportTests.cpp
          GeneratorTests.cpp
```

---

### Task 1: Git repo, plugin skeleton, build and test scripts

**Files:**
- Create: `S:\WorldGenUE\.gitignore`
- Create: `S:\WorldGenUE\Tools\Build.ps1`
- Create: `S:\WorldGenUE\Tools\RunTests.ps1`
- Create: `S:\WorldGenUE\Plugins\TerrainGen\TerrainGen.uplugin`
- Create: `S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\TerrainGenCore.Build.cs`
- Create: `S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\Public\TerrainGenCore.h`
- Create: `S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\Private\TerrainGenCore.cpp`
- Create: `S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\Private\Tests\SmokeTests.cpp`
- Modify: `S:\WorldGenUE\WorldGenUE.uproject` (add the plugin to the `Plugins` list)

**Interfaces:**
- Produces: the module `TerrainGenCore`, the log category `LogTerrainGen`, the scripts every later task runs.

- [ ] **Step 1: Create the git repo and the ignore file**

`S:\WorldGenUE\.gitignore`:
```
Binaries/
Intermediate/
Saved/
DerivedDataCache/
.vs/
*.sln
*.slnx
.vsconfig
Plugins/**/Binaries/
Plugins/**/Intermediate/
```

Run in PowerShell:
```powershell
Set-Location S:\WorldGenUE
git init -b main
git add .gitignore WorldGenUE.uproject Config Source Content
git commit -m "Import the WorldGenUE third-person template project"
```
Expected: one commit. `Content` may be large; if `git add Content` takes minutes, add it anyway, the assets are the project.

- [ ] **Step 2: Write the build script**

`S:\WorldGenUE\Tools\Build.ps1`:
```powershell
# Builds the editor target with the plugin. Exit code 0 on success.
$engine = "E:\Epic Games\UE_5.8"
$project = "S:\WorldGenUE\WorldGenUE.uproject"
& "$engine\Engine\Build\BatchFiles\Build.bat" WorldGenUEEditor Win64 Development -Project="$project" -WaitMutex -NoHotReload
exit $LASTEXITCODE
```

- [ ] **Step 3: Write the test script**

`S:\WorldGenUE\Tools\RunTests.ps1`:
```powershell
# Runs automation tests headless. Usage: .\Tools\RunTests.ps1 TerrainGen.Core
# Prints one line per test with Passed or Failed, then the failure messages. Exit code 1 if any test failed.
param([string]$Filter = "TerrainGen")
$engine = "E:\Epic Games\UE_5.8"
$project = "S:\WorldGenUE\WorldGenUE.uproject"
$log = "S:\WorldGenUE\Saved\Logs\Automation.log"
& "$engine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "$project" `
    -ExecCmds="Automation RunTests $Filter; Quit" `
    -unattended -nopause -nullrhi -nosplash -NoSound -stdout -FullStdOutLogOutput `
    -log="$log" | Out-Null
$lines = Get-Content $log -ErrorAction Stop
$results = $lines | Select-String -Pattern "Test Completed\. Result=\{(Passed|Failed|Skipped)\} Name=\{([^}]*)\}"
foreach ($r in $results) { "$($r.Matches[0].Groups[1].Value)  $($r.Matches[0].Groups[2].Value)" }
$errors = $lines | Select-String -Pattern "LogAutomationController: Error|Error: .*Automation" | Select-Object -First 40
foreach ($e in $errors) { $e.Line }
if ($results.Count -eq 0) { "No test matched filter '$Filter'"; exit 1 }
if (($results | Where-Object { $_.Matches[0].Groups[1].Value -eq "Failed" }).Count -gt 0) { exit 1 }
exit 0
```

- [ ] **Step 4: Write the plugin descriptor**

`S:\WorldGenUE\Plugins\TerrainGen\TerrainGen.uplugin`:
```json
{
	"FileVersion": 3,
	"Version": 1,
	"VersionName": "0.1",
	"FriendlyName": "TerrainGen",
	"Description": "Generates a circular world with 3 lands, sand bars, 5 biomes, and a heightmap.",
	"Category": "Procedural",
	"CreatedBy": "Curonian Winds Studios",
	"CanContainContent": true,
	"IsBetaVersion": true,
	"Installed": false,
	"Modules": [
		{
			"Name": "TerrainGenCore",
			"Type": "Runtime",
			"LoadingPhase": "Default"
		}
	]
}
```

- [ ] **Step 5: Write the module build file**

`S:\WorldGenUE\Plugins\TerrainGen\Source\TerrainGenCore\TerrainGenCore.Build.cs`:
```csharp
using UnrealBuildTool;

public class TerrainGenCore : ModuleRules
{
	public TerrainGenCore(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core" });
		PrivateDependencyModuleNames.AddRange(new string[] { });
	}
}
```

- [ ] **Step 6: Write the module header and source**

`Public/TerrainGenCore.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"

TERRAINGENCORE_API DECLARE_LOG_CATEGORY_EXTERN(LogTerrainGen, Log, All);

class FTerrainGenCoreModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
```

`Private/TerrainGenCore.cpp`:
```cpp
#include "TerrainGenCore.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogTerrainGen);

void FTerrainGenCoreModule::StartupModule() {}
void FTerrainGenCoreModule::ShutdownModule() {}

IMPLEMENT_MODULE(FTerrainGenCoreModule, TerrainGenCore)
```

- [ ] **Step 7: Write the smoke test**

`Private/Tests/SmokeTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainGenCore.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainSmokeTest, "TerrainGen.Core.Smoke",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainSmokeTest::RunTest(const FString& Parameters)
{
	TestTrue(TEXT("the module is loaded"), FModuleManager::Get().IsModuleLoaded(TEXT("TerrainGenCore")));
	return true;
}

#endif
```
If the compiler rejects the flags expression, replace `EAutomationTestFlags::EditorContext` with `EAutomationTestFlags_ApplicationContextMask`. Use the same form in every later test.

- [ ] **Step 8: Enable the plugin in the project**

In `S:\WorldGenUE\WorldGenUE.uproject`, add to the `Plugins` array:
```json
		{
			"Name": "TerrainGen",
			"Enabled": true
		}
```

- [ ] **Step 9: Build**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: the last lines say the build succeeded, exit code 0. The first build of the project takes several minutes.

- [ ] **Step 10: Run the smoke test**

Run: `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Smoke`
Expected: `Passed  TerrainGen.Core.Smoke`, exit code 0.

- [ ] **Step 11: Commit**

```powershell
Set-Location S:\WorldGenUE
git add .gitignore Tools Plugins WorldGenUE.uproject
git commit -m "Add the TerrainGen plugin skeleton with build and test scripts"
```

---

### Task 2: TGrid

**Files:**
- Create: `Public/TerrainGrid.h`
- Test: `Private/Tests/GridTests.cpp`

**Interfaces:**
- Produces:
  - `template<typename T> struct TGrid { int32 Size; TArray<T> Data; }` with `Init(Size, Fill)`, `At(X, Y)`, `IsInside(X, Y)`, `Num()`, `Fill(Value)`, `Sample(float X, float Y)` (bilinear, clamped, float grids), `Index(X, Y)`.
  - Aliases `FGridF` (float), `FGridB` (uint8 mask, 0 or 1), `FGridI` (int32), `FGridU16` (uint16).

- [ ] **Step 1: Write the failing test**

`Private/Tests/GridTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainGrid.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainGridTest, "TerrainGen.Core.Grid",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainGridTest::RunTest(const FString& Parameters)
{
	FGridF Grid(4, 1.0f);
	TestEqual(TEXT("size"), Grid.Size, 4);
	TestEqual(TEXT("count"), Grid.Num(), 16);
	TestEqual(TEXT("fill"), Grid.At(3, 3), 1.0f);
	Grid.At(1, 2) = 5.0f;
	TestEqual(TEXT("row-major index"), Grid.Data[2 * 4 + 1], 5.0f);
	TestTrue(TEXT("inside"), Grid.IsInside(3, 0));
	TestFalse(TEXT("outside"), Grid.IsInside(4, 0));
	TestFalse(TEXT("negative"), Grid.IsInside(0, -1));

	FGridF Ramp(3, 0.0f);
	for (int32 Y = 0; Y < 3; ++Y)
		for (int32 X = 0; X < 3; ++X)
			Ramp.At(X, Y) = float(X);
	TestEqual(TEXT("bilinear between columns"), Ramp.Sample(0.5f, 1.0f), 0.5f);
	TestEqual(TEXT("bilinear clamps"), Ramp.Sample(10.0f, -3.0f), 2.0f);

	FGridB Mask(2, 0);
	Mask.Fill(1);
	TestEqual(TEXT("fill all"), int32(Mask.At(1, 1)), 1);
	return true;
}

#endif
```

- [ ] **Step 2: Build and run to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainGrid.h` not found.

- [ ] **Step 3: Write the grid**

`Public/TerrainGrid.h`:
```cpp
#pragma once

#include "CoreMinimal.h"

/** A square array with (X, Y) access. Row-major: index = Y * Size + X. */
template<typename T>
struct TGrid
{
	int32 Size = 0;
	TArray<T> Data;

	TGrid() = default;
	explicit TGrid(int32 InSize, T FillValue = T()) { Init(InSize, FillValue); }

	void Init(int32 InSize, T FillValue = T())
	{
		Size = InSize;
		Data.Init(FillValue, Size * Size);
	}

	void Fill(T Value) { for (T& V : Data) V = Value; }
	int32 Num() const { return Data.Num(); }
	int32 Index(int32 X, int32 Y) const { return Y * Size + X; }
	bool IsInside(int32 X, int32 Y) const { return X >= 0 && Y >= 0 && X < Size && Y < Size; }

	T& At(int32 X, int32 Y) { return Data[Y * Size + X]; }
	const T& At(int32 X, int32 Y) const { return Data[Y * Size + X]; }

	/** Bilinear sample at a float position, clamped to the grid. For float grids. */
	float Sample(float X, float Y) const
	{
		const float CX = FMath::Clamp(X, 0.0f, float(Size - 1));
		const float CY = FMath::Clamp(Y, 0.0f, float(Size - 1));
		const int32 X0 = FMath::Min(int32(CX), Size - 2 >= 0 ? Size - 2 : 0);
		const int32 Y0 = FMath::Min(int32(CY), Size - 2 >= 0 ? Size - 2 : 0);
		const int32 X1 = FMath::Min(X0 + 1, Size - 1);
		const int32 Y1 = FMath::Min(Y0 + 1, Size - 1);
		const float TX = CX - float(X0);
		const float TY = CY - float(Y0);
		const float Top = float(At(X0, Y0)) + (float(At(X1, Y0)) - float(At(X0, Y0))) * TX;
		const float Bottom = float(At(X0, Y1)) + (float(At(X1, Y1)) - float(At(X0, Y1))) * TX;
		return Top + (Bottom - Top) * TY;
	}
};

using FGridF = TGrid<float>;
using FGridB = TGrid<uint8>;   // a mask: 0 or 1
using FGridI = TGrid<int32>;
using FGridU16 = TGrid<uint16>;
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Grid`
Expected: `Passed  TerrainGen.Core.Grid`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add TGrid, the square array of the terrain core"
```

---

### Task 3: Noise

**Files:**
- Create: `Public/TerrainNoise.h`, `Private/TerrainNoise.cpp`
- Test: `Private/Tests/NoiseTests.cpp`

Python reference: S:\python-terrain-generation\terrain\noise.py. The C++ version uses Perlin noise instead of value noise; the octave sum, the ridged transform `1 - |2n - 1|`, and the billow transform `|2n - 1|` are the same.

**Interfaces:**
- Produces:
  - `float Smoothstep(float X)` = `X * X * (3 - 2 * X)`.
  - `enum class ETerrainNoise : uint8 { Fractal, Ridged, Billow }`.
  - `struct FNoiseParams { int32 Octaves = 6; float Frequency = 3.0f; float Lacunarity = 2.0f; float Persistence = 0.5f; }`.
  - `void MakeNoise(FGridF& Out, int32 Size, const FNoiseParams& Params, ETerrainNoise Type, FRandomStream& Rng)`: fills `Out` with values in [0, 1]. Frequency is cycles across the grid width for the first octave. Each call draws random offsets from `Rng`, so two calls give two fields.

- [ ] **Step 1: Write the failing test**

`Private/Tests/NoiseTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainNoise.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainNoiseTest, "TerrainGen.Core.Noise",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainNoiseTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("smoothstep 0"), Smoothstep(0.0f), 0.0f);
	TestEqual(TEXT("smoothstep 1"), Smoothstep(1.0f), 1.0f);
	TestEqual(TEXT("smoothstep half"), Smoothstep(0.5f), 0.5f);

	FNoiseParams Params;
	Params.Octaves = 5;
	Params.Frequency = 5.0f;
	for (ETerrainNoise Type : { ETerrainNoise::Fractal, ETerrainNoise::Ridged, ETerrainNoise::Billow })
	{
		FRandomStream Rng(7);
		FGridF Noise;
		MakeNoise(Noise, 128, Params, Type, Rng);
		TestEqual(TEXT("size"), Noise.Size, 128);
		float Min = 1.0f, Max = 0.0f, Sum = 0.0f;
		for (float V : Noise.Data) { Min = FMath::Min(Min, V); Max = FMath::Max(Max, V); Sum += V; }
		TestTrue(TEXT("min >= 0"), Min >= 0.0f);
		TestTrue(TEXT("max <= 1"), Max <= 1.0f);
		TestTrue(TEXT("has contrast"), Max - Min > 0.3f);
		const float Mean = Sum / Noise.Num();
		TestTrue(TEXT("mean is not at an edge"), Mean > 0.15f && Mean < 0.85f);
	}

	FRandomStream A(3), B(3), C(4);
	FGridF NA, NB, NC;
	MakeNoise(NA, 64, Params, ETerrainNoise::Fractal, A);
	MakeNoise(NB, 64, Params, ETerrainNoise::Fractal, B);
	MakeNoise(NC, 64, Params, ETerrainNoise::Fractal, C);
	TestTrue(TEXT("same seed same noise"), NA.Data == NB.Data);
	TestFalse(TEXT("other seed other noise"), NA.Data == NC.Data);

	FGridF Second;
	MakeNoise(Second, 64, Params, ETerrainNoise::Fractal, A);
	TestFalse(TEXT("a second call gives a new field"), NA.Data == Second.Data);
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainNoise.h` not found.

- [ ] **Step 3: Write the noise**

`Public/TerrainNoise.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "Math/RandomStream.h"
#include "TerrainGrid.h"

TERRAINGENCORE_API float Smoothstep(float X);

enum class ETerrainNoise : uint8
{
	Fractal,   // rolling hills
	Ridged,    // sharp crests
	Billow,    // round bulges
};

struct FNoiseParams
{
	int32 Octaves = 6;
	float Frequency = 3.0f;    // cycles across the grid width, first octave
	float Lacunarity = 2.0f;
	float Persistence = 0.5f;
};

/** Fills Out with noise in [0, 1]. Each octave uses a random offset from Rng. */
TERRAINGENCORE_API void MakeNoise(FGridF& Out, int32 Size, const FNoiseParams& Params, ETerrainNoise Type, FRandomStream& Rng);
```

`Private/TerrainNoise.cpp`:
```cpp
#include "TerrainNoise.h"
#include "Async/ParallelFor.h"

float Smoothstep(float X)
{
	return X * X * (3.0f - 2.0f * X);
}

void MakeNoise(FGridF& Out, int32 Size, const FNoiseParams& Params, ETerrainNoise Type, FRandomStream& Rng)
{
	Out.Init(Size, 0.0f);
	const int32 Octaves = FMath::Max(Params.Octaves, 1);
	TArray<FVector2D> Offsets;
	TArray<float> Amplitudes;
	TArray<float> Frequencies;
	float Amplitude = 1.0f;
	float Frequency = Params.Frequency;
	float AmplitudeSum = 0.0f;
	for (int32 O = 0; O < Octaves; ++O)
	{
		Offsets.Add(FVector2D(Rng.FRandRange(0.0f, 1000.0f), Rng.FRandRange(0.0f, 1000.0f)));
		Amplitudes.Add(Amplitude);
		Frequencies.Add(Frequency);
		AmplitudeSum += Amplitude;
		Amplitude *= Params.Persistence;
		Frequency *= Params.Lacunarity;
	}
	const float Scale = 1.0f / float(Size);
	ParallelFor(Size, [&](int32 Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			float Total = 0.0f;
			for (int32 O = 0; O < Octaves; ++O)
			{
				const FVector2D P(Offsets[O].X + X * Scale * Frequencies[O], Offsets[O].Y + Y * Scale * Frequencies[O]);
				const float N = 0.5f * (FMath::PerlinNoise2D(P) + 1.0f);   // [0, 1]
				float V = N;
				if (Type == ETerrainNoise::Ridged) V = 1.0f - FMath::Abs(2.0f * N - 1.0f);
				else if (Type == ETerrainNoise::Billow) V = FMath::Abs(2.0f * N - 1.0f);
				Total += Amplitudes[O] * V;
			}
			Out.At(X, Y) = FMath::Clamp(Total / AmplitudeSum, 0.0f, 1.0f);
		}
	});
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Noise`
Expected: `Passed  TerrainGen.Core.Noise`. If "has contrast" fails, Perlin at this scale is too smooth: raise nothing, check that the offsets and the frequency scale are applied per octave as written.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add fractal, ridged, and billow noise from Perlin octaves"
```

---
### Task 4: Distance transform

**Files:**
- Create: `Public/TerrainAlgorithms.h`, `Private/TerrainAlgorithms.cpp`
- Test: `Private/Tests/AlgorithmTests.cpp`

Python reference: `scipy.ndimage.distance_transform_edt`. The Python code calls it as `edt(~mask)` for "distance to the nearest mask pixel" and as `edt(mask)` for "distance to the nearest non-mask pixel". The C++ function takes the target set directly.

**Interfaces:**
- Produces:
  - `void DistanceToMask(const FGridB& Target, FGridF& OutDistance, FGridI* OutNearest = nullptr)`: for each pixel, the Euclidean distance to the nearest pixel where `Target != 0`. 0 on target pixels. `OutNearest` gets the linear index (`Y * Size + X`) of that nearest target pixel. If the target is empty, the distance is `Size * 2` everywhere and the nearest index is -1.
  - `void InvertMask(const FGridB& In, FGridB& Out)`.

- [ ] **Step 1: Write the failing test**

`Private/Tests/AlgorithmTests.cpp` (this file grows in Tasks 5 and 6):
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainAlgorithms.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainDistanceTest, "TerrainGen.Core.Distance",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainDistanceTest::RunTest(const FString& Parameters)
{
	// a 64 px mask with a few random target pixels; compare with brute force
	const int32 Size = 64;
	FGridB Target(Size, 0);
	FRandomStream Rng(11);
	TArray<FIntPoint> Points;
	for (int32 I = 0; I < 12; ++I)
	{
		const FIntPoint P(Rng.RandRange(0, Size - 1), Rng.RandRange(0, Size - 1));
		Points.Add(P);
		Target.At(P.X, P.Y) = 1;
	}
	FGridF Dist;
	FGridI Nearest;
	DistanceToMask(Target, Dist, &Nearest);
	float MaxError = 0.0f;
	bool bNearestOk = true;
	for (int32 Y = 0; Y < Size; ++Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			float Best = 1e9f;
			for (const FIntPoint& P : Points)
				Best = FMath::Min(Best, FMath::Sqrt(float((X - P.X) * (X - P.X) + (Y - P.Y) * (Y - P.Y))));
			MaxError = FMath::Max(MaxError, FMath::Abs(Best - Dist.At(X, Y)));
			const int32 N = Nearest.At(X, Y);
			const int32 NX = N % Size, NY = N / Size;
			if (Target.At(NX, NY) == 0) bNearestOk = false;
			const float DN = FMath::Sqrt(float((X - NX) * (X - NX) + (Y - NY) * (Y - NY)));
			if (FMath::Abs(DN - Best) > 1e-3f) bNearestOk = false;
		}
	}
	TestTrue(TEXT("exact distance"), MaxError < 1e-3f);
	TestTrue(TEXT("nearest index points at a target pixel at the right distance"), bNearestOk);
	TestEqual(TEXT("zero on target"), Dist.At(Points[0].X, Points[0].Y), 0.0f);

	FGridB Empty(8, 0);
	FGridF DistEmpty;
	FGridI NearestEmpty;
	DistanceToMask(Empty, DistEmpty, &NearestEmpty);
	TestTrue(TEXT("empty target gives a large distance"), DistEmpty.At(3, 3) >= 16.0f);
	TestEqual(TEXT("empty target gives -1"), NearestEmpty.At(3, 3), -1);

	FGridB Inv;
	InvertMask(Empty, Inv);
	TestEqual(TEXT("invert"), int32(Inv.At(0, 0)), 1);
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainAlgorithms.h` not found.

- [ ] **Step 3: Write the distance transform**

`Public/TerrainAlgorithms.h` (this file grows in Tasks 5 and 6):
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainGrid.h"

/** Euclidean distance from each pixel to the nearest pixel where Target != 0. Exact, O(n). */
TERRAINGENCORE_API void DistanceToMask(const FGridB& Target, FGridF& OutDistance, FGridI* OutNearest = nullptr);

TERRAINGENCORE_API void InvertMask(const FGridB& In, FGridB& Out);
```

`Private/TerrainAlgorithms.cpp`:
```cpp
#include "TerrainAlgorithms.h"
#include "Async/ParallelFor.h"

namespace
{
	constexpr float BigDistance = 1e20f;

	/** One-dimensional squared distance transform (Felzenszwalb and Huttenlocher).
	 *  F: input costs. D: output. Src: the index of the source that gives the minimum. N: length.
	 *  V, Z: scratch arrays of size N and N + 1. */
	void Transform1D(const float* F, float* D, int32* Src, int32 N, int32* V, float* Z)
	{
		int32 K = 0;
		V[0] = 0;
		Z[0] = -BigDistance;
		Z[1] = BigDistance;
		for (int32 Q = 1; Q < N; ++Q)
		{
			float S;
			while (true)
			{
				const int32 P = V[K];
				S = ((F[Q] + float(Q) * Q) - (F[P] + float(P) * P)) / (2.0f * Q - 2.0f * P);
				if (S <= Z[K] && K > 0) { --K; continue; }
				if (S <= Z[K]) { S = Z[K]; }
				break;
			}
			++K;
			V[K] = Q;
			Z[K] = S;
			Z[K + 1] = BigDistance;
		}
		K = 0;
		for (int32 Q = 0; Q < N; ++Q)
		{
			while (Z[K + 1] < float(Q)) ++K;
			const int32 P = V[K];
			D[Q] = float(Q - P) * float(Q - P) + F[P];
			Src[Q] = P;
		}
	}
}

void DistanceToMask(const FGridB& Target, FGridF& OutDistance, FGridI* OutNearest)
{
	const int32 Size = Target.Size;
	OutDistance.Init(Size, 0.0f);
	FGridI ColumnSource(Size, -1);   // after pass 1: for (X, Y) the Y of the nearest target in column X
	FGridF Squared(Size, 0.0f);

	// pass 1: along each column
	ParallelFor(Size, [&](int32 X)
	{
		TArray<float> F, D, Z;
		TArray<int32> Src, V;
		F.SetNum(Size); D.SetNum(Size); Src.SetNum(Size); V.SetNum(Size); Z.SetNum(Size + 1);
		for (int32 Y = 0; Y < Size; ++Y) F[Y] = Target.At(X, Y) ? 0.0f : BigDistance;
		Transform1D(F.GetData(), D.GetData(), Src.GetData(), Size, V.GetData(), Z.GetData());
		for (int32 Y = 0; Y < Size; ++Y)
		{
			Squared.At(X, Y) = D[Y];
			ColumnSource.At(X, Y) = (D[Y] < BigDistance * 0.5f) ? Src[Y] : -1;
		}
	});

	// pass 2: along each row
	if (OutNearest) OutNearest->Init(Size, -1);
	ParallelFor(Size, [&](int32 Y)
	{
		TArray<float> F, D, Z;
		TArray<int32> Src, V;
		F.SetNum(Size); D.SetNum(Size); Src.SetNum(Size); V.SetNum(Size); Z.SetNum(Size + 1);
		for (int32 X = 0; X < Size; ++X) F[X] = Squared.At(X, Y);
		Transform1D(F.GetData(), D.GetData(), Src.GetData(), Size, V.GetData(), Z.GetData());
		for (int32 X = 0; X < Size; ++X)
		{
			const bool bFound = D[X] < BigDistance * 0.5f;
			OutDistance.At(X, Y) = bFound ? FMath::Sqrt(D[X]) : float(Size * 2);
			if (OutNearest)
			{
				const int32 SX = Src[X];
				const int32 SY = bFound ? ColumnSource.At(SX, Y) : -1;
				OutNearest->At(X, Y) = (bFound && SY >= 0) ? (SY * Size + SX) : -1;
			}
		}
	});
}

void InvertMask(const FGridB& In, FGridB& Out)
{
	Out.Init(In.Size, 0);
	for (int32 I = 0; I < In.Num(); ++I) Out.Data[I] = In.Data[I] ? 0 : 1;
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Distance`
Expected: `Passed  TerrainGen.Core.Distance`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the exact Euclidean distance transform with nearest indices"
```

---

### Task 5: Connected component labels

**Files:**
- Modify: `Public/TerrainAlgorithms.h`, `Private/TerrainAlgorithms.cpp`
- Test: `Private/Tests/AlgorithmTests.cpp` (add a second test)

Python reference: `scipy.ndimage.label` with the default 4-connectivity, and `structure=np.ones((3, 3))` for 8-connectivity.

**Interfaces:**
- Produces: `int32 LabelComponents(const FGridB& Mask, FGridI& OutLabels, TArray<int32>& OutAreas, bool bEightConnected = false)`: labels 1..N on mask pixels, 0 elsewhere. `OutAreas[I]` is the pixel count of label `I + 1`. Returns N.

- [ ] **Step 1: Write the failing test**

Append to `Private/Tests/AlgorithmTests.cpp` before the final `#endif`:
```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainLabelTest, "TerrainGen.Core.Labels",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainLabelTest::RunTest(const FString& Parameters)
{
	// two blocks that touch at one corner: 2 pieces with 4-connectivity, 1 piece with 8-connectivity
	FGridB Mask(8, 0);
	for (int32 Y = 0; Y < 3; ++Y) for (int32 X = 0; X < 3; ++X) Mask.At(X, Y) = 1;
	for (int32 Y = 3; Y < 6; ++Y) for (int32 X = 3; X < 6; ++X) Mask.At(X, Y) = 1;
	Mask.At(7, 7) = 1;

	FGridI Labels;
	TArray<int32> Areas;
	const int32 N4 = LabelComponents(Mask, Labels, Areas, false);
	TestEqual(TEXT("4-connected count"), N4, 3);
	TestEqual(TEXT("areas"), Areas.Num(), 3);
	TestEqual(TEXT("first area"), Areas[Labels.At(0, 0) - 1], 9);
	TestEqual(TEXT("corner pixel area"), Areas[Labels.At(7, 7) - 1], 1);
	TestEqual(TEXT("sea is 0"), Labels.At(6, 0), 0);
	TestNotEqual(TEXT("blocks differ"), Labels.At(0, 0), Labels.At(4, 4));

	const int32 N8 = LabelComponents(Mask, Labels, Areas, true);
	TestEqual(TEXT("8-connected count"), N8, 2);
	TestEqual(TEXT("blocks merge"), Labels.At(0, 0), Labels.At(4, 4));
	TestEqual(TEXT("merged area"), Areas[Labels.At(0, 0) - 1], 18);
	return true;
}
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `LabelComponents` undeclared.

- [ ] **Step 3: Write the labels**

Add to `Public/TerrainAlgorithms.h`:
```cpp
/** Labels the connected pieces of the mask 1..N, 0 elsewhere. OutAreas[I] is the pixel count of label I + 1. Returns N. */
TERRAINGENCORE_API int32 LabelComponents(const FGridB& Mask, FGridI& OutLabels, TArray<int32>& OutAreas, bool bEightConnected = false);
```

Add to `Private/TerrainAlgorithms.cpp`:
```cpp
namespace
{
	int32 FindRoot(TArray<int32>& Parent, int32 I)
	{
		while (Parent[I] != I) { Parent[I] = Parent[Parent[I]]; I = Parent[I]; }
		return I;
	}

	void Union(TArray<int32>& Parent, int32 A, int32 B)
	{
		A = FindRoot(Parent, A);
		B = FindRoot(Parent, B);
		if (A != B) Parent[FMath::Max(A, B)] = FMath::Min(A, B);
	}
}

int32 LabelComponents(const FGridB& Mask, FGridI& OutLabels, TArray<int32>& OutAreas, bool bEightConnected)
{
	const int32 Size = Mask.Size;
	OutLabels.Init(Size, 0);
	TArray<int32> Parent;
	Parent.Add(0);   // label 0 is the background
	// pass 1: provisional labels from the neighbors above and to the left
	for (int32 Y = 0; Y < Size; ++Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			if (!Mask.At(X, Y)) continue;
			int32 Label = 0;
			auto Consider = [&](int32 NX, int32 NY)
			{
				if (NX < 0 || NY < 0 || NX >= Size || NY >= Size) return;
				const int32 L = OutLabels.At(NX, NY);
				if (L == 0) return;
				if (Label == 0) Label = L;
				else Union(Parent, Label, L);
			};
			Consider(X - 1, Y);
			Consider(X, Y - 1);
			if (bEightConnected) { Consider(X - 1, Y - 1); Consider(X + 1, Y - 1); }
			if (Label == 0) { Label = Parent.Num(); Parent.Add(Label); }
			OutLabels.At(X, Y) = Label;
		}
	}
	// pass 2: compact the roots into 1..N
	TArray<int32> Compact;
	Compact.Init(0, Parent.Num());
	int32 Count = 0;
	for (int32 I = 1; I < Parent.Num(); ++I)
		if (FindRoot(Parent, I) == I) Compact[I] = ++Count;
	OutAreas.Init(0, Count);
	for (int32 I = 0; I < OutLabels.Num(); ++I)
	{
		const int32 L = OutLabels.Data[I];
		if (L == 0) continue;
		const int32 C = Compact[FindRoot(Parent, L)];
		OutLabels.Data[I] = C;
		OutAreas[C - 1] += 1;
	}
	return Count;
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Labels`
Expected: `Passed  TerrainGen.Core.Labels`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add connected component labels with 4 and 8 connectivity"
```

---

### Task 6: Blur, closing, gradient, dilation

**Files:**
- Modify: `Public/TerrainAlgorithms.h`, `Private/TerrainAlgorithms.cpp`
- Test: `Private/Tests/AlgorithmTests.cpp` (add a third test)

Python references: `scipy.ndimage.gaussian_filter` (reflect edges; the C++ version clamps, the difference is at the border only), `np.gradient` (central differences, one-sided at the edges), `scipy.ndimage.binary_dilation` with `structure=np.ones((3, 3))`, and `closing` in `spit.py`.

**Interfaces:**
- Produces:
  - `void GaussianBlur(const FGridF& In, FGridF& Out, float Sigma)`: separable, kernel radius `ceil(3 * Sigma)`, edge clamp. `Sigma <= 0` copies.
  - `void Gradient(const FGridF& In, FGridF& OutGx, FGridF& OutGy)`: `np.gradient` order, `Gy` along rows (Y), `Gx` along columns (X).
  - `void Dilate8(const FGridB& In, FGridB& Out, int32 Iterations)`.
  - `void Closing(const FGridB& Mask, float Radius, FGridB& Out)`: dilation then erosion by a disk. `Radius <= 0` copies.

- [ ] **Step 1: Write the failing test**

Append to `Private/Tests/AlgorithmTests.cpp` before the final `#endif`:
```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainFilterTest, "TerrainGen.Core.Filters",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainFilterTest::RunTest(const FString& Parameters)
{
	// blur keeps the sum of a single dot and spreads it
	FGridF Dot(33, 0.0f);
	Dot.At(16, 16) = 1.0f;
	FGridF Blurred;
	GaussianBlur(Dot, Blurred, 2.0f);
	float Sum = 0.0f;
	for (float V : Blurred.Data) Sum += V;
	TestTrue(TEXT("blur keeps the sum"), FMath::Abs(Sum - 1.0f) < 1e-3f);
	TestTrue(TEXT("blur spreads"), Blurred.At(16, 16) < 0.1f && Blurred.At(18, 16) > 0.0f);
	TestTrue(TEXT("blur is symmetric"), FMath::Abs(Blurred.At(14, 16) - Blurred.At(18, 16)) < 1e-6f);

	// gradient of a ramp
	FGridF Ramp(5, 0.0f);
	for (int32 Y = 0; Y < 5; ++Y) for (int32 X = 0; X < 5; ++X) Ramp.At(X, Y) = 2.0f * X + 3.0f * Y;
	FGridF Gx, Gy;
	Gradient(Ramp, Gx, Gy);
	TestTrue(TEXT("gx"), FMath::Abs(Gx.At(2, 2) - 2.0f) < 1e-5f && FMath::Abs(Gx.At(0, 0) - 2.0f) < 1e-5f);
	TestTrue(TEXT("gy"), FMath::Abs(Gy.At(2, 2) - 3.0f) < 1e-5f && FMath::Abs(Gy.At(4, 4) - 3.0f) < 1e-5f);

	// dilation grows a dot into a 5x5 block after 2 iterations
	FGridB DotMask(9, 0);
	DotMask.At(4, 4) = 1;
	FGridB Grown;
	Dilate8(DotMask, Grown, 2);
	int32 Count = 0;
	for (uint8 V : Grown.Data) Count += V;
	TestEqual(TEXT("dilated area"), Count, 25);

	// closing fills a bay that is open to the right
	FGridB Land(60, 0);
	for (int32 Y = 10; Y < 50; ++Y) for (int32 X = 10; X < 50; ++X) Land.At(X, Y) = 1;
	for (int32 Y = 25; Y < 35; ++Y) for (int32 X = 30; X < 60; ++X) Land.At(X, Y) = 0;
	FGridB Closed;
	Closing(Land, 12.0f, Closed);
	TestEqual(TEXT("the bay is filled"), int32(Closed.At(45, 30)), 1);
	TestEqual(TEXT("the land stays"), int32(Closed.At(20, 20)), 1);
	TestEqual(TEXT("the open sea stays"), int32(Closed.At(5, 5)), 0);
	return true;
}
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `GaussianBlur` undeclared.

- [ ] **Step 3: Write the filters**

Add to `Public/TerrainAlgorithms.h`:
```cpp
/** Separable Gaussian blur, kernel radius ceil(3 sigma), edge clamp. Sigma <= 0 copies. */
TERRAINGENCORE_API void GaussianBlur(const FGridF& In, FGridF& Out, float Sigma);

/** Central differences like np.gradient. Gx is the change along X, Gy along Y. */
TERRAINGENCORE_API void Gradient(const FGridF& In, FGridF& OutGx, FGridF& OutGy);

/** Grows the mask by one pixel in all 8 directions, Iterations times. */
TERRAINGENCORE_API void Dilate8(const FGridB& In, FGridB& Out, int32 Iterations);

/** Morphological closing with a disk: dilation, then erosion. Fills bays narrower than 2 * Radius. */
TERRAINGENCORE_API void Closing(const FGridB& Mask, float Radius, FGridB& Out);
```

Add to `Private/TerrainAlgorithms.cpp`:
```cpp
void GaussianBlur(const FGridF& In, FGridF& Out, float Sigma)
{
	const int32 Size = In.Size;
	if (Sigma <= 0.0f) { Out = In; return; }
	const int32 R = FMath::CeilToInt(3.0f * Sigma);
	TArray<float> Kernel;
	Kernel.SetNum(2 * R + 1);
	float KSum = 0.0f;
	for (int32 I = -R; I <= R; ++I) { Kernel[I + R] = FMath::Exp(-0.5f * I * I / (Sigma * Sigma)); KSum += Kernel[I + R]; }
	for (float& K : Kernel) K /= KSum;

	FGridF Temp(Size, 0.0f);
	ParallelFor(Size, [&](int32 Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			float Acc = 0.0f;
			for (int32 I = -R; I <= R; ++I) Acc += Kernel[I + R] * In.At(FMath::Clamp(X + I, 0, Size - 1), Y);
			Temp.At(X, Y) = Acc;
		}
	});
	Out.Init(Size, 0.0f);
	ParallelFor(Size, [&](int32 Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			float Acc = 0.0f;
			for (int32 I = -R; I <= R; ++I) Acc += Kernel[I + R] * Temp.At(X, FMath::Clamp(Y + I, 0, Size - 1));
			Out.At(X, Y) = Acc;
		}
	});
}

void Gradient(const FGridF& In, FGridF& OutGx, FGridF& OutGy)
{
	const int32 Size = In.Size;
	OutGx.Init(Size, 0.0f);
	OutGy.Init(Size, 0.0f);
	ParallelFor(Size, [&](int32 Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			const int32 X0 = FMath::Max(X - 1, 0), X1 = FMath::Min(X + 1, Size - 1);
			const int32 Y0 = FMath::Max(Y - 1, 0), Y1 = FMath::Min(Y + 1, Size - 1);
			OutGx.At(X, Y) = (In.At(X1, Y) - In.At(X0, Y)) / float(X1 - X0);
			OutGy.At(X, Y) = (In.At(X, Y1) - In.At(X, Y0)) / float(Y1 - Y0);
		}
	});
}

void Dilate8(const FGridB& In, FGridB& Out, int32 Iterations)
{
	const int32 Size = In.Size;
	FGridB Current = In;
	for (int32 It = 0; It < Iterations; ++It)
	{
		FGridB Next(Size, 0);
		for (int32 Y = 0; Y < Size; ++Y)
			for (int32 X = 0; X < Size; ++X)
			{
				if (!Current.At(X, Y)) continue;
				for (int32 DY = -1; DY <= 1; ++DY)
					for (int32 DX = -1; DX <= 1; ++DX)
						if (Current.IsInside(X + DX, Y + DY)) Next.At(X + DX, Y + DY) = 1;
			}
		Current = MoveTemp(Next);
	}
	Out = MoveTemp(Current);
}

void Closing(const FGridB& Mask, float Radius, FGridB& Out)
{
	const int32 Size = Mask.Size;
	if (Radius <= 0.0f) { Out = Mask; return; }
	FGridF Dist;
	DistanceToMask(Mask, Dist);
	FGridB Dilated(Size, 0);
	for (int32 I = 0; I < Size * Size; ++I) Dilated.Data[I] = Dist.Data[I] <= Radius ? 1 : 0;
	FGridB NotDilated;
	InvertMask(Dilated, NotDilated);
	FGridF Inner;
	DistanceToMask(NotDilated, Inner);   // distance to the nearest pixel outside the dilation
	Out.Init(Size, 0);
	for (int32 I = 0; I < Size * Size; ++I) Out.Data[I] = Inner.Data[I] > Radius - 0.5f ? 1 : 0;
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Filters`
Expected: `Passed  TerrainGen.Core.Filters`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add Gaussian blur, gradient, dilation, and closing"
```

---
### Task 7: Config structs and validation

**Files:**
- Create: `Public/TerrainConfig.h`, `Private/TerrainConfig.cpp`
- Test: `Private/Tests/ConfigTests.cpp`

Python reference: S:\python-terrain-generation\terrain\config.py and S:\python-terrain-generation\config.yaml. Every field and default matches the Python `Config` dataclasses. JSON load is not in this module; it comes with the UObject layer in a later plan.

**Interfaces:**
- Produces: the structs below, `TerrainUnrealSizes`, `MakeDefaultTerrainConfig()`, `ValidateTerrainConfig(const FTerrainConfig&, FString& OutError)`, `HashSeed(int32 Seed, int32 Stage, int32 Attempt)`.

- [ ] **Step 1: Write the failing test**

`Private/Tests/ConfigTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainConfig.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainConfigTest, "TerrainGen.Core.Config",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainConfigTest::RunTest(const FString& Parameters)
{
	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	FString Error;
	TestTrue(TEXT("defaults are valid"), ValidateTerrainConfig(Cfg, Error));
	TestEqual(TEXT("size"), Cfg.Size, 1009);
	TestEqual(TEXT("3 lands"), Cfg.Land.Count, 3);
	TestEqual(TEXT("5 biome types"), Cfg.Biomes.Types.Num(), 5);
	TestEqual(TEXT("sea side is the spit type"), Cfg.Biomes.Types[0].Placement, ETerrainPlacement::Spit);
	TestEqual(TEXT("profiles"), Cfg.Heightmap.Profiles.Num(), 5);
	TestEqual(TEXT("mountain noise"), Cfg.Heightmap.Profiles[FName("mountain_range")].Noise, ETerrainNoise::Ridged);
	TestTrue(TEXT("marsh base below 0"), Cfg.Heightmap.Profiles[FName("marshlands")].Base < 0.0f);
	TestEqual(TEXT("world diameter"), Cfg.World.DiameterM, 9000.0f);

	FTerrainConfig Bad = Cfg;
	Bad.Size = 1000;
	TestFalse(TEXT("bad size"), ValidateTerrainConfig(Bad, Error));
	TestTrue(TEXT("size message"), Error.Contains(TEXT("127, 253, 505, 1009")));

	Bad = Cfg; Bad.Biomes.SeedsPerLandMin = 3;
	TestFalse(TEXT("too few seeds"), ValidateTerrainConfig(Bad, Error));
	TestTrue(TEXT("seeds message"), Error.Contains(TEXT("lo >= 4")));

	Bad = Cfg; Bad.Heightmap.Profiles[FName("marshlands")].Octaves = 0;
	TestFalse(TEXT("bad octaves"), ValidateTerrainConfig(Bad, Error));

	Bad = Cfg; Bad.Spit.WidthVariation = 1.0f;
	TestFalse(TEXT("bad width variation"), ValidateTerrainConfig(Bad, Error));
	TestTrue(TEXT("width variation message"), Error.Contains(TEXT("spit.width_variation")));

	Bad = Cfg; Bad.Heightmap.Profiles.Remove(FName("ancient_grove"));
	TestFalse(TEXT("missing profile"), ValidateTerrainConfig(Bad, Error));
	TestTrue(TEXT("missing profile message"), Error.Contains(TEXT("ancient_grove")));

	TestNotEqual(TEXT("seed hash differs by stage"), HashSeed(42, 2, 0), HashSeed(42, 3, 0));
	TestNotEqual(TEXT("seed hash differs by attempt"), HashSeed(42, 2, 0), HashSeed(42, 2, 1));
	TestEqual(TEXT("seed hash is stable"), HashSeed(42, 2, 0), HashSeed(42, 2, 0));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainConfig.h` not found.

- [ ] **Step 3: Write the config**

`Public/TerrainConfig.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainNoise.h"

static const int32 TerrainUnrealSizes[] = { 127, 253, 505, 1009, 2017, 4033, 8129 };

enum class ETerrainPlacement : uint8 { Spit, Coast, Low, Inland, Any };

struct FTerrainCircleConfig
{
	float DiameterPct = 90.0f;     // circle diameter as % of the image width
	float EdgeBandPct = 10.0f;     // soft band inside the circle edge, as % of the radius
};

struct FTerrainLandConfig
{
	int32 Count = 3;
	float SeedAreaPct = 55.0f;     // seed points lie inside this % of the circle radius
	float MinSeparationPct = 75.0f;
	float RadiusPctMin = 100.0f;   // land falloff radius, random in this range, as % of the circle radius
	float RadiusPctMax = 120.0f;
	float WarpPct = 15.0f;
	float ChannelPct = 22.0f;      // width of the sea channel between lands, as % of the radius
	FNoiseParams Noise = { 7, 5.0f, 2.0f, 0.5f };
	float Threshold = 0.28f;
	int32 MinLakeAreaPx = 200;
	int32 MaxRetries = 10;
};

struct FTerrainWarpConfig
{
	float StrengthPx = 90.0f;
	float Frequency = 5.0f;
	int32 Octaves = 5;
};

struct FTerrainBiomeType
{
	FName Name;
	FString Label;
	ETerrainPlacement Placement = ETerrainPlacement::Any;
};

struct FTerrainBiomesConfig
{
	int32 SeedsPerLandMin = 4;     // mainland regions per land; the spit adds one region
	int32 SeedsPerLandMax = 6;
	float MinSeedSeparationPx = 60.0f;
	float CoastBandPx = 40.0f;
	float InlandFraction = 0.7f;
	int32 MaxRetries = 10;
	FTerrainWarpConfig Warp;
	TArray<FTerrainBiomeType> Types;
};

struct FTerrainSpitConfig
{
	float BayPct = 15.0f;          // bay search disk, % of the radius. The bar crosses bays narrower than 2x this
	float LagoonPct = 5.0f;        // width of the water behind the bar, % of the radius
	float LengthPctMin = 40.0f;    // bar length, random in this range, % of the radius
	float LengthPctMax = 90.0f;
	float MinLagoonPct = 3.0f;     // smallest lagoon area, % of the land area
	float WidthPct = 4.0f;
	float WidthVariation = 0.5f;
	float StraitPct = 2.5f;        // opening near one end, % of the radius. 0 closes the lagoon
	float EdgeNoisePct = 1.0f;
	float GapPct = 6.0f;           // smallest distance to other land, % of the radius
	float RisePx = 6.0f;           // distance from the bar coast where the dunes reach full height
};

struct FTerrainProfile
{
	float Base = 0.0f;             // lowest height of the biome, -1..1
	float Amplitude = 0.1f;        // height of the hills above the base
	float Frequency = 6.0f;
	int32 Octaves = 4;
	float Lacunarity = 2.0f;
	float Persistence = 0.5f;
	ETerrainNoise Noise = ETerrainNoise::Fractal;
	float BlendPx = 25.0f;
};

struct FTerrainHeightmapConfig
{
	float CoastDistancePx = 80.0f;
	float CoastBlurPx = 12.0f;
	TMap<FName, FTerrainProfile> Profiles;
	float SeabedDepth = 0.3f;
	float SeabedDistancePx = 150.0f;
	float SeabedBlurPx = 10.0f;
};

struct FTerrainExportConfig
{
	int32 SeaLevelValue = 32768;
	float WeightBlurPx = 12.0f;
};

struct FTerrainWorldConfig
{
	float DiameterM = 9000.0f;
	float HeightRangeM = 256.0f;
	int32 TilePx = 253;
	int32 LodLevels = 4;
};

struct FTerrainConfig
{
	int32 Seed = 42;
	int32 Size = 1009;
	FTerrainCircleConfig Circle;
	FTerrainLandConfig Land;
	FTerrainBiomesConfig Biomes;
	FTerrainSpitConfig Spit;
	FTerrainHeightmapConfig Heightmap;
	FTerrainExportConfig Export;
	FTerrainWorldConfig World;
};

/** The defaults of config.yaml: the 5 biome types and their height profiles. */
TERRAINGENCORE_API FTerrainConfig MakeDefaultTerrainConfig();

/** False with a message when a value is out of range. The messages name the config key, like the Python version. */
TERRAINGENCORE_API bool ValidateTerrainConfig(const FTerrainConfig& Config, FString& OutError);

/** One random stream seed per world seed, stage, and attempt. */
TERRAINGENCORE_API int32 HashSeed(int32 Seed, int32 Stage, int32 Attempt);
```

`Private/TerrainConfig.cpp`:
```cpp
#include "TerrainConfig.h"

FTerrainConfig MakeDefaultTerrainConfig()
{
	FTerrainConfig C;
	C.Biomes.Types = {
		{ FName("sea_side"), TEXT("Sea Side (Neringa)"), ETerrainPlacement::Spit },
		{ FName("marshlands"), TEXT("Marshlands"), ETerrainPlacement::Low },
		{ FName("ancient_grove"), TEXT("Ancient Grove"), ETerrainPlacement::Any },
		{ FName("enchanted_forest"), TEXT("Enchanted Forest"), ETerrainPlacement::Any },
		{ FName("mountain_range"), TEXT("Mountain Range"), ETerrainPlacement::Inland },
	};
	auto Profile = [](float Base, float Amplitude, float Frequency, int32 Octaves, ETerrainNoise Noise)
	{
		FTerrainProfile P;
		P.Base = Base; P.Amplitude = Amplitude; P.Frequency = Frequency; P.Octaves = Octaves; P.Noise = Noise;
		return P;
	};
	C.Heightmap.Profiles.Add(FName("sea_side"), Profile(0.01f, 0.08f, 12.0f, 3, ETerrainNoise::Fractal));
	C.Heightmap.Profiles.Add(FName("marshlands"), Profile(-0.03f, 0.12f, 6.0f, 2, ETerrainNoise::Fractal));
	C.Heightmap.Profiles.Add(FName("ancient_grove"), Profile(0.13f, 0.24f, 5.0f, 5, ETerrainNoise::Fractal));
	C.Heightmap.Profiles.Add(FName("enchanted_forest"), Profile(0.15f, 0.30f, 6.0f, 5, ETerrainNoise::Fractal));
	C.Heightmap.Profiles.Add(FName("mountain_range"), Profile(0.20f, 0.80f, 8.0f, 6, ETerrainNoise::Ridged));
	return C;
}

bool ValidateTerrainConfig(const FTerrainConfig& Cfg, FString& OutError)
{
	bool bSizeOk = false;
	for (int32 S : TerrainUnrealSizes) bSizeOk |= (S == Cfg.Size);
	if (!bSizeOk)
	{
		OutError = FString::Printf(TEXT("size must be one of 127, 253, 505, 1009, 2017, 4033, 8129. Got %d."), Cfg.Size);
		return false;
	}
	if (!(Cfg.Circle.DiameterPct > 0.0f && Cfg.Circle.DiameterPct <= 100.0f))
	{
		OutError = FString::Printf(TEXT("circle.diameter_pct must be in (0, 100]. Got %g."), Cfg.Circle.DiameterPct);
		return false;
	}
	if (Cfg.Land.Count != 3)
	{
		OutError = FString::Printf(TEXT("land.count must be 3 in this version. Got %d."), Cfg.Land.Count);
		return false;
	}
	if (Cfg.Biomes.Types.Num() != 5)
	{
		OutError = FString::Printf(TEXT("biomes.types must have 5 entries. Got %d."), Cfg.Biomes.Types.Num());
		return false;
	}
	int32 SeededTypes = 0;
	for (const FTerrainBiomeType& T : Cfg.Biomes.Types)
	{
		if (T.Placement != ETerrainPlacement::Spit) ++SeededTypes;
		if (!Cfg.Heightmap.Profiles.Contains(T.Name))
		{
			OutError = FString::Printf(TEXT("heightmap.profiles has no entry for biome %s."), *T.Name.ToString());
			return false;
		}
	}
	if (Cfg.Biomes.SeedsPerLandMin < SeededTypes || Cfg.Biomes.SeedsPerLandMax < Cfg.Biomes.SeedsPerLandMin)
	{
		OutError = FString::Printf(TEXT("biomes.seeds_per_land must be [lo, hi] with lo >= %d and hi >= lo. Got %d, %d."),
			SeededTypes, Cfg.Biomes.SeedsPerLandMin, Cfg.Biomes.SeedsPerLandMax);
		return false;
	}
	for (const auto& Pair : Cfg.Heightmap.Profiles)
	{
		const FString Prefix = FString::Printf(TEXT("heightmap.profiles.%s"), *Pair.Key.ToString());
		const FTerrainProfile& P = Pair.Value;
		if (P.Base < -1.0f || P.Base > 1.0f) { OutError = Prefix + TEXT(".base must be in [-1, 1]."); return false; }
		if (P.Amplitude < 0.0f) { OutError = Prefix + TEXT(".amplitude must be >= 0."); return false; }
		if (P.Octaves < 1) { OutError = Prefix + TEXT(".octaves must be >= 1."); return false; }
		if (P.BlendPx <= 0.0f) { OutError = Prefix + TEXT(".blend_px must be > 0."); return false; }
		if (P.Lacunarity <= 0.0f) { OutError = Prefix + TEXT(".lacunarity must be > 0."); return false; }
		if (P.Persistence <= 0.0f || P.Persistence > 1.0f) { OutError = Prefix + TEXT(".persistence must be in (0, 1]."); return false; }
	}
	if (Cfg.Heightmap.SeabedDepth <= 0.0f || Cfg.Heightmap.SeabedDepth > 1.0f)
	{
		OutError = TEXT("heightmap.seabed_depth must be in (0, 1].");
		return false;
	}
	const FTerrainSpitConfig& S = Cfg.Spit;
	if (!(S.LengthPctMin > 0.0f && S.LengthPctMin <= S.LengthPctMax)) { OutError = TEXT("spit.length_pct must be [lo, hi] with 0 < lo <= hi."); return false; }
	if (S.BayPct < 0.0f) { OutError = TEXT("spit.bay_pct must be >= 0."); return false; }
	if (S.LagoonPct <= 0.0f) { OutError = TEXT("spit.lagoon_pct must be > 0."); return false; }
	if (S.MinLagoonPct <= 0.0f) { OutError = TEXT("spit.min_lagoon_pct must be > 0."); return false; }
	if (S.WidthPct <= 0.0f) { OutError = TEXT("spit.width_pct must be > 0."); return false; }
	if (S.WidthVariation < 0.0f || S.WidthVariation >= 1.0f) { OutError = TEXT("spit.width_variation must be in [0, 1)."); return false; }
	if (S.RisePx <= 0.0f) { OutError = TEXT("spit.rise_px must be > 0."); return false; }
	if (S.StraitPct < 0.0f || S.GapPct < 0.0f || S.EdgeNoisePct < 0.0f) { OutError = TEXT("spit.strait_pct, spit.gap_pct, and spit.edge_noise_pct must be >= 0."); return false; }
	if (Cfg.World.DiameterM <= 0.0f || Cfg.World.HeightRangeM <= 0.0f) { OutError = TEXT("world.diameter_m and world.height_range_m must be > 0."); return false; }
	OutError.Empty();
	return true;
}

int32 HashSeed(int32 Seed, int32 Stage, int32 Attempt)
{
	uint32 H = HashCombine(GetTypeHash(Seed), GetTypeHash(Stage));
	H = HashCombine(H, GetTypeHash(Attempt));
	return int32(H & 0x7fffffff);
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Config`
Expected: `Passed  TerrainGen.Core.Config`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the terrain config structs, the defaults, and the validation"
```

---

### Task 8: Results, the circle stage, and the debug image writer

**Files:**
- Create: `Public/TerrainResults.h`
- Create: `Public/TerrainStages.h` (grows in Tasks 9 to 13)
- Create: `Private/TerrainStageCircle.cpp`
- Create: `Public/TerrainDebugImages.h`, `Private/TerrainDebugImages.cpp`
- Test: `Private/Tests/CircleTests.cpp`

Python reference: S:\python-terrain-generation\terrain\circle.py.

**Interfaces:**
- Produces:
  - `struct FCircleResult { FGridB Mask; FGridF EdgeBand; FGridF CenterDistance; float Radius; }`
  - `struct FTerrainRegion { int32 Id; int32 LandId; FVector2f SeedXY; int32 BiomeIndex; int32 SubtypeIndex; }`
  - `struct FLandResult { FGridB LandMask; FGridI LandIds; TArray<FVector2f> Seeds; int32 SeedUsed; FGridB SpitMask; FGridI SpitOwner; TArray<float> SpitLengthsPx; }`
  - `struct FBiomeResult { FGridF CoastDistance; TArray<FTerrainRegion> Regions; FGridI RegionIds; FGridI BiomeIds; FGridI SubtypeIds; TArray<FName> TypeNames; int32 SeedUsed; TMap<FName, TArray<int32>> SubtypePerLand; }`
  - `struct FHeightResult { FGridF Height; }`
  - `struct FTerrainResult { int32 Size; float MetersPerPixel; FGridU16 Height; TArray<TGrid<uint8>> Weights; TGrid<uint8> SubtypeId; TGrid<uint8> BiomeId; TGrid<uint8> LandId; TArray<FTerrainRegion> Regions; TMap<FName, TArray<int32>> SubtypePerLand; int32 SeedUsedLand; int32 SeedUsedBiomes; }`
  - `void MakeCircle(int32 Size, const FTerrainCircleConfig& Config, FCircleResult& Out)`
  - `bool WritePgm(const FString& Path, const FGridF& Grid, float Min, float Max)`, `bool WritePgm(const FString& Path, const FGridB& Mask)`, `bool WritePgm(const FString& Path, const FGridI& Ids)`. Binary PGM (P5), 8-bit. Any image viewer opens it.

- [ ] **Step 1: Write the failing test**

`Private/Tests/CircleTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "TerrainStages.h"
#include "TerrainDebugImages.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainCircleTest, "TerrainGen.Core.Circle",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainCircleTest::RunTest(const FString& Parameters)
{
	FTerrainCircleConfig Cfg;
	FCircleResult Circle;
	MakeCircle(253, Cfg, Circle);
	TestEqual(TEXT("radius"), Circle.Radius, 253.0f * 90.0f / 200.0f);
	TestEqual(TEXT("center is inside"), int32(Circle.Mask.At(126, 126)), 1);
	TestEqual(TEXT("corner is outside"), int32(Circle.Mask.At(0, 0)), 0);
	TestEqual(TEXT("center distance at the center"), Circle.CenterDistance.At(126, 126), 0.0f);
	TestEqual(TEXT("edge band is 1 at the center"), Circle.EdgeBand.At(126, 126), 1.0f);
	TestEqual(TEXT("edge band is 0 outside"), Circle.EdgeBand.At(0, 0), 0.0f);
	const int32 EdgeX = 126 + int32(Circle.Radius) - 2;
	TestTrue(TEXT("edge band is between 0 and 1 near the edge"), Circle.EdgeBand.At(EdgeX, 126) > 0.0f && Circle.EdgeBand.At(EdgeX, 126) < 0.5f);
	int32 Inside = 0;
	for (uint8 V : Circle.Mask.Data) Inside += V;
	const float Expected = PI * Circle.Radius * Circle.Radius;
	TestTrue(TEXT("area is close to pi r squared"), FMath::Abs(Inside - Expected) / Expected < 0.02f);

	const FString Path = FPaths::ProjectSavedDir() / TEXT("TerrainGenTests") / TEXT("circle_mask.pgm");
	TestTrue(TEXT("pgm written"), WritePgm(Path, Circle.Mask));
	TestTrue(TEXT("pgm exists"), FPaths::FileExists(Path));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainStages.h` not found.

- [ ] **Step 3: Write the results header**

`Public/TerrainResults.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainGrid.h"

struct FCircleResult
{
	FGridB Mask;
	FGridF EdgeBand;
	FGridF CenterDistance;
	float Radius = 0.0f;
};

struct FTerrainRegion
{
	int32 Id = 0;
	int32 LandId = 0;
	FVector2f SeedXY = FVector2f::ZeroVector;
	int32 BiomeIndex = 0;
	int32 SubtypeIndex = 0;
};

struct FLandResult
{
	FGridB LandMask;               // land and sand bars
	FGridI LandIds;                // 0 sea, 1..3 by area, the bars carry the id of their land
	TArray<FVector2f> Seeds;
	int32 SeedUsed = 0;
	FGridB SpitMask;               // the sand bars
	FGridI SpitOwner;              // land id of each bar pixel
	TArray<float> SpitLengthsPx;
};

struct FBiomeResult
{
	FGridF CoastDistance;          // distance to the sea, 0 on sea
	TArray<FTerrainRegion> Regions;
	FGridI RegionIds;              // 0 sea
	FGridI BiomeIds;               // 0 sea, 1..5
	FGridI SubtypeIds;             // 0 sea, 1..15 = biome index * 3 + subtype index + 1
	TArray<FName> TypeNames;
	int32 SeedUsed = 0;
	TMap<FName, TArray<int32>> SubtypePerLand;   // biome name -> subtype index per land, index 0 = land 1
};

struct FHeightResult
{
	FGridF Height;                 // -1..1, 0 is sea level
};

struct FTerrainResult
{
	int32 Size = 0;
	float MetersPerPixel = 1.0f;
	FGridU16 Height;               // sea level at the export sea level value
	TArray<TGrid<uint8>> Weights;  // one per biome type, sum 255
	TGrid<uint8> SubtypeId;        // 0 sea, 1..15
	TGrid<uint8> BiomeId;          // 0 sea, 1..5
	TGrid<uint8> LandId;           // 0 sea, 1..3
	TArray<FTerrainRegion> Regions;
	TMap<FName, TArray<int32>> SubtypePerLand;
	int32 SeedUsedLand = 0;
	int32 SeedUsedBiomes = 0;
};
```

- [ ] **Step 4: Write the stages header and the circle stage**

`Public/TerrainStages.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainConfig.h"
#include "TerrainResults.h"

/** Stage 1: the circle mask, the edge band, and the center distance. */
TERRAINGENCORE_API void MakeCircle(int32 Size, const FTerrainCircleConfig& Config, FCircleResult& Out);
```

`Private/TerrainStageCircle.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainNoise.h"

void MakeCircle(int32 Size, const FTerrainCircleConfig& Config, FCircleResult& Out)
{
	const float Center = (Size - 1) / 2.0f;
	Out.Radius = Size * Config.DiameterPct / 200.0f;
	Out.Mask.Init(Size, 0);
	Out.EdgeBand.Init(Size, 0.0f);
	Out.CenterDistance.Init(Size, 0.0f);
	const float Inner = Out.Radius * (1.0f - Config.EdgeBandPct / 100.0f);
	const float BandWidth = FMath::Max(Out.Radius - Inner, 1e-6f);
	for (int32 Y = 0; Y < Size; ++Y)
	{
		for (int32 X = 0; X < Size; ++X)
		{
			const float D = FMath::Sqrt((X - Center) * (X - Center) + (Y - Center) * (Y - Center));
			Out.CenterDistance.At(X, Y) = D;
			const bool bInside = D <= Out.Radius;
			Out.Mask.At(X, Y) = bInside ? 1 : 0;
			const float T = FMath::Clamp((Out.Radius - D) / BandWidth, 0.0f, 1.0f);
			Out.EdgeBand.At(X, Y) = bInside ? Smoothstep(T) : 0.0f;
		}
	}
}
```

- [ ] **Step 5: Write the debug image writer**

`Public/TerrainDebugImages.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainGrid.h"

/** Writes an 8-bit binary PGM. Min maps to black, Max to white. Creates the folder. */
TERRAINGENCORE_API bool WritePgm(const FString& Path, const FGridF& Grid, float Min, float Max);
TERRAINGENCORE_API bool WritePgm(const FString& Path, const FGridB& Mask);
/** Ids: 0 is black, the largest id is white. */
TERRAINGENCORE_API bool WritePgm(const FString& Path, const FGridI& Ids);
```

`Private/TerrainDebugImages.cpp`:
```cpp
#include "TerrainDebugImages.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"

static bool WritePgmBytes(const FString& Path, int32 Size, const TArray<uint8>& Pixels)
{
	FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*FPaths::GetPath(Path));
	const FString Header = FString::Printf(TEXT("P5\n%d %d\n255\n"), Size, Size);
	TArray<uint8> Bytes;
	const FTCHARToUTF8 Utf8(*Header);
	Bytes.Append(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length());
	Bytes.Append(Pixels);
	return FFileHelper::SaveArrayToFile(Bytes, *Path);
}

bool WritePgm(const FString& Path, const FGridF& Grid, float Min, float Max)
{
	TArray<uint8> Pixels;
	Pixels.SetNum(Grid.Num());
	const float Range = FMath::Max(Max - Min, 1e-6f);
	for (int32 I = 0; I < Grid.Num(); ++I)
		Pixels[I] = uint8(FMath::Clamp(FMath::RoundToInt((Grid.Data[I] - Min) / Range * 255.0f), 0, 255));
	return WritePgmBytes(Path, Grid.Size, Pixels);
}

bool WritePgm(const FString& Path, const FGridB& Mask)
{
	TArray<uint8> Pixels;
	Pixels.SetNum(Mask.Num());
	for (int32 I = 0; I < Mask.Num(); ++I) Pixels[I] = Mask.Data[I] ? 255 : 0;
	return WritePgmBytes(Path, Mask.Size, Pixels);
}

bool WritePgm(const FString& Path, const FGridI& Ids)
{
	int32 MaxId = 1;
	for (int32 V : Ids.Data) MaxId = FMath::Max(MaxId, V);
	TArray<uint8> Pixels;
	Pixels.SetNum(Ids.Num());
	for (int32 I = 0; I < Ids.Num(); ++I) Pixels[I] = uint8(FMath::Clamp(Ids.Data[I] * 255 / MaxId, 0, 255));
	return WritePgmBytes(Path, Ids.Size, Pixels);
}
```

- [ ] **Step 6: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Circle`
Expected: `Passed  TerrainGen.Core.Circle`. Open S:\WorldGenUE\Saved\TerrainGenTests\circle_mask.pgm in an image viewer: a white disk on black.

- [ ] **Step 7: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the result structs, the circle stage, and the PGM debug writer"
```

---
### Task 9: Lands stage

**Files:**
- Modify: `Public/TerrainStages.h`
- Create: `Private/TerrainStageLands.cpp`
- Create: `Private/Tests/TerrainTestUtil.h`
- Test: `Private/Tests/LandsTests.cpp`

Python reference: S:\python-terrain-generation\terrain\landmass.py. Read it first. The C++ port keeps every rule and constant. The sand bars come in Task 10; this task leaves the spit grids empty and takes an optional spit config pointer that is `nullptr` here.

**Interfaces:**
- Consumes: `MakeCircle`, `MakeNoise`, `Smoothstep`, `DistanceToMask`, `LabelComponents`, `HashSeed`.
- Produces:
  - `bool MakeLands(const FCircleResult& Circle, const FTerrainLandConfig& Config, const FTerrainSpitConfig* SpitConfig, int32 Seed, FLandResult& Out, FString& OutError)`. Stage number 2. Retries `MaxRetries` attempts. False with a message after the retries.
  - `bool MakeSpits(const FCircleResult& Circle, FLandResult& InOutLand, const FTerrainSpitConfig& Config, FRandomStream& Rng, FString& OutProblem)` is declared here and defined in Task 10. In this task, `MakeLands` calls it only when `SpitConfig` is not null, and no test passes a spit config yet. Give it a stub body in `TerrainStageLands.cpp` that sets `OutProblem = TEXT("not implemented")` and returns false; Task 10 moves the real one into its own file and deletes the stub.
  - Test helper `MakeTestCircle(int32 Size)` and `MakeTestLands(int32 Seed, bool bWithSpits)` in `TerrainTestUtil.h`.

- [ ] **Step 1: Write the test helper and the failing tests**

`Private/Tests/TerrainTestUtil.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainStages.h"

namespace TerrainTest
{
	constexpr int32 Size = 253;

	inline FCircleResult MakeTestCircle()
	{
		FCircleResult Circle;
		MakeCircle(Size, FTerrainCircleConfig(), Circle);
		return Circle;
	}

	/** Lands at 253 px with the default config. bWithSpits adds the default sand bars. */
	inline bool MakeTestLands(int32 Seed, bool bWithSpits, FCircleResult& OutCircle, FLandResult& OutLand, FString& OutError)
	{
		OutCircle = MakeTestCircle();
		const FTerrainSpitConfig SpitConfig;
		return MakeLands(OutCircle, FTerrainLandConfig(), bWithSpits ? &SpitConfig : nullptr, Seed, OutLand, OutError);
	}
}
```

`Private/Tests/LandsTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainAlgorithms.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainLandsTest, "TerrainGen.Core.Lands",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainLandsTest::RunTest(const FString& Parameters)
{
	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TestTrue(TEXT("lands generate"), TerrainTest::MakeTestLands(42, false, Circle, Land, Error));

	FGridI Labels;
	TArray<int32> Areas;
	TestEqual(TEXT("exactly 3 lands"), LabelComponents(Land.LandMask, Labels, Areas), 3);
	int32 MaxId = 0;
	bool bAllInside = true;
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
	{
		MaxId = FMath::Max(MaxId, Land.LandIds.Data[I]);
		if (Land.LandMask.Data[I] && !Circle.Mask.Data[I]) bAllInside = false;
		if ((Land.LandIds.Data[I] > 0) != (Land.LandMask.Data[I] != 0)) bAllInside = false;
	}
	TestEqual(TEXT("ids go to 3"), MaxId, 3);
	TestTrue(TEXT("all land inside the circle, ids match the mask"), bAllInside);

	int32 AreaById[4] = { 0, 0, 0, 0 };
	for (int32 V : Land.LandIds.Data) if (V > 0) AreaById[V] += 1;
	TestTrue(TEXT("ids ordered by area"), AreaById[1] >= AreaById[2] && AreaById[2] >= AreaById[3]);

	FGridB Sea;
	InvertMask(Land.LandMask, Sea);
	FGridI SeaLabels;
	TArray<int32> SeaAreas;
	LabelComponents(Sea, SeaLabels, SeaAreas);
	bool bNoSmallLakes = true;
	for (int32 A : SeaAreas) if (A < 200) bNoSmallLakes = false;
	TestTrue(TEXT("no small lakes"), bNoSmallLakes);
	TestTrue(TEXT("no spits without a spit config"), !Land.SpitMask.Num() || Land.SpitMask.Data.Contains(1) == false);

	FLandResult Again;
	TerrainTest::MakeTestLands(42, false, Circle, Again, Error);
	TestTrue(TEXT("deterministic"), Again.LandIds.Data == Land.LandIds.Data);

	FTerrainLandConfig Impossible;
	Impossible.Threshold = 5.0f;
	Impossible.MaxRetries = 2;
	FLandResult Bad;
	TestFalse(TEXT("impossible config fails"), MakeLands(Circle, Impossible, nullptr, 42, Bad, Error));
	TestTrue(TEXT("failure message names the tries"), Error.Contains(TEXT("after 2 tries")));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `MakeLands` undeclared.

- [ ] **Step 3: Declare the stage functions**

Add to `Public/TerrainStages.h`:
```cpp
/** Stage 2: 3 lands inside the circle. With a spit config, one sand bar per land. Retries with the next attempt seed. */
TERRAINGENCORE_API bool MakeLands(const FCircleResult& Circle, const FTerrainLandConfig& Config,
	const FTerrainSpitConfig* SpitConfig, int32 Seed, FLandResult& Out, FString& OutError);

/** Stage 2, second part: one sand bar per land, added to the land result. False with a problem when a bar does not fit. */
TERRAINGENCORE_API bool MakeSpits(const FCircleResult& Circle, FLandResult& InOutLand, const FTerrainSpitConfig& Config,
	FRandomStream& Rng, FString& OutProblem);
```

- [ ] **Step 4: Write the lands stage**

`Private/TerrainStageLands.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainAlgorithms.h"
#include "TerrainNoise.h"
#include "TerrainGenCore.h"

namespace
{
	constexpr int32 StageNumber = 2;

	TArray<FVector2f> PlaceSeeds(FRandomStream& Rng, int32 Count, float AreaRadius, float Separation, float Center)
	{
		TArray<FVector2f> Seeds;
		int32 Rejections = 0;
		while (Seeds.Num() < Count)
		{
			const float R = AreaRadius * FMath::Sqrt(Rng.FRand());
			const float A = Rng.FRand() * 2.0f * PI;
			const FVector2f P(Center + R * FMath::Cos(A), Center + R * FMath::Sin(A));
			bool bFar = true;
			for (const FVector2f& Q : Seeds) if (FVector2f::Distance(P, Q) < Separation) { bFar = false; break; }
			if (bFar) { Seeds.Add(P); continue; }
			if (++Rejections >= 1000) { Separation /= 2.0f; Rejections = 0; }
		}
		return Seeds;
	}

	/** Keeps the Keep largest pieces with at least MinArea pixels. */
	void KeepComponents(FGridB& Mask, int32 Keep, int32 MinArea)
	{
		FGridI Labels;
		TArray<int32> Areas;
		const int32 N = LabelComponents(Mask, Labels, Areas);
		if (N == 0) return;
		TArray<int32> Order;
		for (int32 I = 0; I < N; ++I) Order.Add(I);
		Order.Sort([&](int32 A, int32 B) { return Areas[A] > Areas[B]; });
		TSet<int32> Chosen;
		for (int32 I = 0; I < FMath::Min(Keep, N); ++I) if (Areas[Order[I]] >= MinArea) Chosen.Add(Order[I] + 1);
		for (int32 I = 0; I < Mask.Num(); ++I) Mask.Data[I] = Chosen.Contains(Labels.Data[I]) ? 1 : 0;
	}

	/** Turns sea pieces smaller than MinArea into land. */
	void FillLakes(FGridB& Land, int32 MinArea)
	{
		FGridB Sea;
		InvertMask(Land, Sea);
		FGridI Labels;
		TArray<int32> Areas;
		const int32 N = LabelComponents(Sea, Labels, Areas);
		if (N == 0) return;
		for (int32 I = 0; I < Land.Num(); ++I)
		{
			const int32 L = Labels.Data[I];
			if (L > 0 && Areas[L - 1] < MinArea) Land.Data[I] = 1;
		}
	}

	/** Ids 1..N by area, largest first. Returns N. */
	int32 LabelByArea(const FGridB& Land, FGridI& OutIds)
	{
		FGridI Labels;
		TArray<int32> Areas;
		const int32 N = LabelComponents(Land, Labels, Areas);
		OutIds.Init(Land.Size, 0);
		if (N == 0) return 0;
		TArray<int32> Order;
		for (int32 I = 0; I < N; ++I) Order.Add(I);
		Order.Sort([&](int32 A, int32 B) { return Areas[A] > Areas[B]; });
		TArray<int32> Rank;
		Rank.Init(0, N + 1);
		for (int32 R = 0; R < N; ++R) Rank[Order[R] + 1] = R + 1;
		for (int32 I = 0; I < Land.Num(); ++I) OutIds.Data[I] = Rank[Labels.Data[I]];
		return N;
	}

	/** One attempt. Returns the land count it got. */
	int32 Attempt(const FCircleResult& Circle, const FTerrainLandConfig& Cfg, FRandomStream& Rng, FLandResult& Out)
	{
		const int32 Size = Circle.Mask.Size;
		const float Center = (Size - 1) / 2.0f;
		const float Radius = Circle.Radius;

		Out.Seeds = PlaceSeeds(Rng, Cfg.Count, Radius * Cfg.SeedAreaPct / 100.0f, Radius * Cfg.MinSeparationPct / 100.0f, Center);

		const float WarpPx = Radius * Cfg.WarpPct / 100.0f;
		FNoiseParams WarpParams = { 4, 3.0f, 2.0f, 0.5f };
		FGridF NX, NY;
		MakeNoise(NX, Size, WarpParams, ETerrainNoise::Fractal, Rng);
		MakeNoise(NY, Size, WarpParams, ETerrainNoise::Fractal, Rng);

		TArray<float> Radii;
		for (int32 I = 0; I < Out.Seeds.Num(); ++I)
			Radii.Add(Rng.FRandRange(Cfg.RadiusPctMin, Cfg.RadiusPctMax) / 100.0f * Radius);

		const float ChannelPx = FMath::Max(Radius * Cfg.ChannelPct / 100.0f, 1e-6f);
		FGridF Noise;
		MakeNoise(Noise, Size, Cfg.Noise, ETerrainNoise::Fractal, Rng);

		FGridB RawLand(Size, 0);
		for (int32 Y = 0; Y < Size; ++Y)
		{
			for (int32 X = 0; X < Size; ++X)
			{
				const float PX = X + WarpPx * (NX.At(X, Y) - 0.5f) * 2.0f;
				const float PY = Y + WarpPx * (NY.At(X, Y) - 0.5f) * 2.0f;
				float Falloff = 0.0f;
				float D0 = 1e30f, D1 = 1e30f;   // the two smallest seed distances
				for (int32 I = 0; I < Out.Seeds.Num(); ++I)
				{
					const float D = FVector2f::Distance(FVector2f(PX, PY), Out.Seeds[I]);
					Falloff = FMath::Max(Falloff, FMath::Clamp(1.0f - D / Radii[I], 0.0f, 1.0f));
					if (D < D0) { D1 = D0; D0 = D; } else if (D < D1) { D1 = D; }
				}
				const float Channel = Smoothstep(FMath::Clamp((D1 - D0) / ChannelPx, 0.0f, 1.0f));
				const float Shape = Falloff * Channel * Circle.EdgeBand.At(X, Y);
				RawLand.At(X, Y) = (Noise.At(X, Y) * Shape > Cfg.Threshold && Circle.Mask.At(X, Y)) ? 1 : 0;
			}
		}
		KeepComponents(RawLand, Cfg.Count, Cfg.MinLakeAreaPx);
		FillLakes(RawLand, Cfg.MinLakeAreaPx);
		Out.LandMask = RawLand;
		const int32 Count = LabelByArea(Out.LandMask, Out.LandIds);
		Out.SpitMask.Init(Size, 0);
		Out.SpitOwner.Init(Size, 0);
		Out.SpitLengthsPx.Reset();
		return Count;
	}
}

bool MakeLands(const FCircleResult& Circle, const FTerrainLandConfig& Config, const FTerrainSpitConfig* SpitConfig,
	int32 Seed, FLandResult& Out, FString& OutError)
{
	FString Problem;
	int32 Count = 0;
	for (int32 AttemptIndex = 0; AttemptIndex < Config.MaxRetries; ++AttemptIndex)
	{
		FRandomStream Rng(HashSeed(Seed, StageNumber, AttemptIndex));
		Count = Attempt(Circle, Config, Rng, Out);
		if (Count == Config.Count)
		{
			FString SpitProblem;
			if (SpitConfig == nullptr || MakeSpits(Circle, Out, *SpitConfig, Rng, SpitProblem))
			{
				Out.SeedUsed = Seed + AttemptIndex;
				return true;
			}
			Problem = FString::Printf(TEXT("Try %d could not fit a sand bar: %s."), AttemptIndex + 1, *SpitProblem);
		}
		else
		{
			Problem = FString::Printf(TEXT("Try %d gave %d lands, not %d."), AttemptIndex + 1, Count, Config.Count);
		}
		UE_LOG(LogTerrainGen, Log, TEXT("%s The stage tries again with the next seed."), *Problem);
	}
	OutError = FString::Printf(TEXT("Seed %d failed after %d tries. %s Decrease land.threshold, increase land.channel_pct, or decrease spit.min_lagoon_pct."),
		Seed, Config.MaxRetries, *Problem);
	return false;
}

// Task 10 replaces this stub with the real sand bars in TerrainStageSpits.cpp.
bool MakeSpits(const FCircleResult& Circle, FLandResult& InOutLand, const FTerrainSpitConfig& Config, FRandomStream& Rng, FString& OutProblem)
{
	OutProblem = TEXT("not implemented");
	return false;
}
```

- [ ] **Step 5: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Lands`
Expected: `Passed  TerrainGen.Core.Lands`. If "exactly 3 lands" fails, the Perlin noise differs from the Python value noise in contrast: check the noise test passed, then lower `Threshold` in the test config to 0.25 and note it in the commit message. The default config in `config.yaml` may need the same tune after a visual check in Task 14.

- [ ] **Step 6: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the lands stage: 3 lands with a sea channel, retries on failure"
```

---
### Task 10: Sand bars

**Files:**
- Create: `Private/TerrainStageSpits.cpp`
- Modify: `Private/TerrainStageLands.cpp` (delete the `MakeSpits` stub)
- Test: `Private/Tests/SpitsTests.cpp`

Python reference: S:\python-terrain-generation\terrain\spit.py. Read the whole file first. The port keeps the level-line march, the ramp, the enclosed-water score, the strait taper, and the join to the coast. The k-d tree of the Python strip becomes a stamp: each path point marks the pixels within its reach with the distance and its index.

**Interfaces:**
- Consumes: `Closing`, `DistanceToMask`, `GaussianBlur`, `Gradient`, `Dilate8`, `LabelComponents`, `MakeNoise`, `Smoothstep`, `FGridF::Sample`.
- Produces: the real `MakeSpits` declared in Task 9. It fills `SpitMask`, `SpitOwner`, `SpitLengthsPx`, adds the bars to `LandMask`, and sets `LandIds` on the bar pixels.

- [ ] **Step 1: Write the failing test**

`Private/Tests/SpitsTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainAlgorithms.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainSpitsTest, "TerrainGen.Core.Spits",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

/** The number of coast pieces the bar of one land touches. */
static int32 CountContacts(const FLandResult& Land, int32 LandId)
{
	FGridB Bar(Land.SpitMask.Size, 0);
	for (int32 I = 0; I < Bar.Num(); ++I) Bar.Data[I] = (Land.SpitMask.Data[I] && Land.SpitOwner.Data[I] == LandId) ? 1 : 0;
	FGridB Grown;
	Dilate8(Bar, Grown, 2);
	FGridB Touch(Bar.Size, 0);
	for (int32 I = 0; I < Bar.Num(); ++I)
		Touch.Data[I] = (Grown.Data[I] && !Land.SpitMask.Data[I] && Land.LandIds.Data[I] == LandId) ? 1 : 0;
	FGridI Labels;
	TArray<int32> Areas;
	return LabelComponents(Touch, Labels, Areas, true);
}

bool FTerrainSpitsTest::RunTest(const FString& Parameters)
{
	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TestTrue(TEXT("lands with bars generate"), TerrainTest::MakeTestLands(42, true, Circle, Land, Error));
	const FTerrainSpitConfig Cfg;

	// one bar per land, joined to its land
	FGridI Labels;
	TArray<int32> Areas;
	TestEqual(TEXT("still 3 lands"), LabelComponents(Land.LandMask, Labels, Areas), 3);
	TestEqual(TEXT("3 bar lengths"), Land.SpitLengthsPx.Num(), 3);
	bool bOwnersOk = true;
	int32 BarPixels[4] = { 0, 0, 0, 0 };
	for (int32 I = 0; I < Land.SpitMask.Num(); ++I)
	{
		if (!Land.SpitMask.Data[I]) continue;
		const int32 Owner = Land.SpitOwner.Data[I];
		if (Owner < 1 || Owner > 3 || Land.LandIds.Data[I] != Owner || !Land.LandMask.Data[I]) bOwnersOk = false;
		else BarPixels[Owner] += 1;
	}
	TestTrue(TEXT("bar pixels carry their land id and are land"), bOwnersOk);
	TestTrue(TEXT("every land has a bar"), BarPixels[1] > 0 && BarPixels[2] > 0 && BarPixels[3] > 0);

	// a gap from other land
	const float Gap = Cfg.GapPct / 100.0f * Circle.Radius;
	for (int32 LandId = 1; LandId <= 3; ++LandId)
	{
		FGridB Other(Land.LandMask.Size, 0);
		for (int32 I = 0; I < Other.Num(); ++I) Other.Data[I] = (Land.LandMask.Data[I] && Land.LandIds.Data[I] != LandId) ? 1 : 0;
		FGridF Dist;
		DistanceToMask(Other, Dist);
		float MinDist = 1e9f;
		for (int32 I = 0; I < Other.Num(); ++I)
			if (Land.SpitMask.Data[I] && Land.SpitOwner.Data[I] == LandId) MinDist = FMath::Min(MinDist, Dist.Data[I]);
		TestTrue(TEXT("gap from other land"), MinDist >= 0.5f * Gap);
	}

	// with the default strait the bar touches the coast on one side only, and it is long and thin
	const float Width = Cfg.WidthPct / 100.0f * Circle.Radius;
	for (int32 LandId = 1; LandId <= 3; ++LandId)
	{
		TestEqual(TEXT("one contact with the strait"), CountContacts(Land, LandId), 1);
		const float Length = Land.SpitLengthsPx[LandId - 1];
		TestTrue(TEXT("long"), Length >= 0.6f * Cfg.LengthPctMin / 100.0f * Circle.Radius);
		TestTrue(TEXT("thin"), float(BarPixels[LandId]) / Length <= Width * (1.0f + Cfg.WidthVariation) * 2.0f);
	}

	// without the strait the bar joins two sides of the coast and encloses a lagoon
	FTerrainSpitConfig Closed;
	Closed.StraitPct = 0.0f;
	FLandResult LandClosed;
	TestTrue(TEXT("closed bars generate"), MakeLands(Circle, FTerrainLandConfig(), &Closed, 42, LandClosed, Error));
	FGridB Sea;
	InvertMask(LandClosed.LandMask, Sea);
	FGridI SeaLabels;
	TArray<int32> SeaAreas;
	LabelComponents(Sea, SeaLabels, SeaAreas);
	const int32 OpenSea = SeaLabels.At(0, 0);
	for (int32 LandId = 1; LandId <= 3; ++LandId)
	{
		TestTrue(TEXT("two contacts without the strait"), CountContacts(LandClosed, LandId) >= 2);
		FGridB Bar(Sea.Size, 0);
		int32 LandArea = 0;
		for (int32 I = 0; I < Bar.Num(); ++I)
		{
			Bar.Data[I] = (LandClosed.SpitMask.Data[I] && LandClosed.SpitOwner.Data[I] == LandId) ? 1 : 0;
			if (LandClosed.LandIds.Data[I] == LandId) ++LandArea;
		}
		FGridB Beside;
		Dilate8(Bar, Beside, 2);
		TSet<int32> Enclosed;
		for (int32 I = 0; I < Bar.Num(); ++I)
			if (Beside.Data[I] && Sea.Data[I] && SeaLabels.Data[I] != OpenSea) Enclosed.Add(SeaLabels.Data[I]);
		int32 Lagoon = 0;
		for (int32 L : Enclosed) Lagoon += SeaAreas[L - 1];
		TestTrue(TEXT("a lagoon lies behind the bar"), Lagoon >= 0.5f * Closed.MinLagoonPct / 100.0f * LandArea);
	}

	// inside the circle, deterministic, impossible config
	bool bInside = true;
	for (int32 I = 0; I < Land.SpitMask.Num(); ++I) if (Land.SpitMask.Data[I] && !Circle.Mask.Data[I]) bInside = false;
	TestTrue(TEXT("bars stay inside the circle"), bInside);
	FLandResult Again;
	TerrainTest::MakeTestLands(42, true, Circle, Again, Error);
	TestTrue(TEXT("deterministic"), Again.SpitMask.Data == Land.SpitMask.Data);
	FTerrainSpitConfig Impossible;
	Impossible.GapPct = 150.0f;
	FTerrainLandConfig LandCfg;
	LandCfg.MaxRetries = 2;
	FLandResult Bad;
	TestFalse(TEXT("impossible bar fails after the retries"), MakeLands(Circle, LandCfg, &Impossible, 42, Bad, Error));
	TestTrue(TEXT("message names the sand bar"), Error.Contains(TEXT("sand bar")));
	return true;
}

#endif
```

- [ ] **Step 2: Build and run to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Spits`
Expected: `Failed  TerrainGen.Core.Spits`, "lands with bars generate" fails because the stub returns false.

- [ ] **Step 3: Delete the stub and write the sand bars**

Delete the `MakeSpits` stub at the end of `Private/TerrainStageLands.cpp`.

`Private/TerrainStageSpits.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainAlgorithms.h"
#include "TerrainNoise.h"

namespace
{
	constexpr float StepPx = 2.0f;
	constexpr int32 Starts = 8;
	constexpr float Taper = 5.0f;   // taper length at the strait tip, in bar widths

	struct FSizes { float Bay, Lagoon, LengthMin, LengthMax, Width, Strait, EdgeNoise, Gap; };

	FSizes MakeSizes(const FTerrainSpitConfig& Cfg, float Radius)
	{
		const float R = Radius / 100.0f;
		return { Cfg.BayPct * R, Cfg.LagoonPct * R, Cfg.LengthPctMin * R, Cfg.LengthPctMax * R,
			Cfg.WidthPct * R, Cfg.StraitPct * R, Cfg.EdgeNoisePct * R, Cfg.GapPct * R };
	}

	float PathLength(const TArray<FVector2f>& Path)
	{
		float L = 0.0f;
		for (int32 I = 1; I < Path.Num(); ++I) L += FVector2f::Distance(Path[I - 1], Path[I]);
		return L;
	}

	/** Follows the level line of Dist at the lagoon level from Start for Length px, with a ramp up and down. */
	TArray<FVector2f> March(const FVector2f& Start, float Sign, const FGridF& Dist, const FGridF& Gx, const FGridF& Gy,
		const FGridF& DMain, const FGridF& Room, const FGridF& Inside, float Lagoon, float Length, float MinRoom)
	{
		const int32 Size = Dist.Size;
		const float Ramp = FMath::Min(3.0f * Lagoon, Length / 4.0f);
		TArray<FVector2f> Points;
		Points.Add(Start);
		FVector2f P = Start;
		float Travelled = 0.0f;
		while (Travelled < Length + 3.0f * Ramp)
		{
			FVector2f G(Gx.Sample(P.X, P.Y), Gy.Sample(P.X, P.Y));
			const float Norm = G.Size();
			if (Norm < 1e-6f) break;
			G /= Norm;
			const FVector2f Tangent = FVector2f(-G.Y, G.X) * Sign;
			const float S = Travelled + StepPx;
			const float Up = Smoothstep(FMath::Min(S / Ramp, 1.0f));
			const float Down = Smoothstep(FMath::Clamp((Length - S) / Ramp, 0.0f, 1.0f));
			const float Level = Lagoon * Up * Down;
			FVector2f Q = P + StepPx * Tangent;
			Q = Q + (Level - Dist.Sample(Q.X, Q.Y)) * G;
			const float Jump = FVector2f::Distance(Q, P);
			if (Jump > 1.5f * StepPx) Q = P + (Q - P) * (1.5f * StepPx / Jump);
			if (!(Q.X >= 1.0f && Q.X < Size - 2 && Q.Y >= 1.0f && Q.Y < Size - 2)) break;
			if (Room.Sample(Q.X, Q.Y) < MinRoom || Inside.Sample(Q.X, Q.Y) < 0.5f) break;
			Travelled += FVector2f::Distance(Q, P);
			P = Q;
			Points.Add(P);
			if (S > Length && DMain.Sample(Q.X, Q.Y) <= 1.5f) break;
		}
		return Points;
	}

	/** The strip around the path. Width is the full width per pixel; Factor scales it per path point. */
	void Rasterize(const TArray<FVector2f>& Path, const FGridF& Width, const FGridF& EdgeNoise, const TArray<float>* Factor, FGridB& Out)
	{
		const int32 Size = Width.Size;
		float MaxWidth = 0.0f, MaxNoise = 0.0f;
		for (float V : Width.Data) MaxWidth = FMath::Max(MaxWidth, V);
		for (float V : EdgeNoise.Data) MaxNoise = FMath::Max(MaxNoise, FMath::Abs(V));
		const int32 Reach = FMath::CeilToInt(MaxWidth / 2.0f + MaxNoise + 2.0f);
		FGridF Nearest(Size, 1e9f);
		FGridI NearestIndex(Size, -1);
		for (int32 I = 0; I < Path.Num(); ++I)
		{
			const int32 CX = FMath::RoundToInt(Path[I].X), CY = FMath::RoundToInt(Path[I].Y);
			for (int32 Y = FMath::Max(CY - Reach, 0); Y <= FMath::Min(CY + Reach, Size - 1); ++Y)
				for (int32 X = FMath::Max(CX - Reach, 0); X <= FMath::Min(CX + Reach, Size - 1); ++X)
				{
					const float D = FVector2f::Distance(FVector2f(float(X), float(Y)), Path[I]);
					if (D < Nearest.At(X, Y)) { Nearest.At(X, Y) = D; NearestIndex.At(X, Y) = I; }
				}
		}
		Out.Init(Size, 0);
		for (int32 I = 0; I < Size * Size; ++I)
		{
			const int32 Idx = NearestIndex.Data[I];
			if (Idx < 0) continue;
			float Half = Width.Data[I] / 2.0f;
			if (Factor) Half *= (*Factor)[Idx];
			const float Limit = FMath::Max(Half + EdgeNoise.Data[I], 0.5f * Half);
			Out.Data[I] = Nearest.Data[I] <= Limit ? 1 : 0;
		}
	}

	/** The sea area the bar encloses: sea pieces beside the bar that do not reach the image corner. */
	int32 LagoonArea(const FGridB& Bar, const FGridB& AllLand)
	{
		const int32 Size = Bar.Size;
		FGridB Sea(Size, 0);
		for (int32 I = 0; I < Size * Size; ++I) Sea.Data[I] = (AllLand.Data[I] || Bar.Data[I]) ? 0 : 1;
		FGridI Labels;
		TArray<int32> Areas;
		LabelComponents(Sea, Labels, Areas);
		const int32 OpenSea = Labels.At(0, 0);
		FGridB Beside;
		Dilate8(Bar, Beside, 2);
		TSet<int32> Enclosed;
		for (int32 I = 0; I < Size * Size; ++I)
			if (Beside.Data[I] && Sea.Data[I] && Labels.Data[I] != 0 && Labels.Data[I] != OpenSea) Enclosed.Add(Labels.Data[I]);
		int32 Area = 0;
		for (int32 L : Enclosed) Area += Areas[L - 1];
		return Area;
	}

	/** Cuts the path short of the coast at the given end and tapers the width to a point there. */
	void Strait(TArray<FVector2f>& Path, int32 End, const FSizes& Px, TArray<float>& OutFactor)
	{
		if (End == 0) Algo::Reverse(Path);
		TArray<float> FromTip;   // path distance to the cut end
		FromTip.SetNum(Path.Num());
		FromTip[Path.Num() - 1] = 0.0f;
		for (int32 I = Path.Num() - 2; I >= 0; --I) FromTip[I] = FromTip[I + 1] + FVector2f::Distance(Path[I], Path[I + 1]);
		const float Cut = Px.Strait + Px.Width / 2.0f;
		TArray<FVector2f> Kept;
		OutFactor.Reset();
		for (int32 I = 0; I < Path.Num(); ++I)
		{
			if (FromTip[I] <= Cut) continue;
			Kept.Add(Path[I]);
			OutFactor.Add(0.15f + 0.85f * Smoothstep(FMath::Clamp((FromTip[I] - Cut) / (Taper * Px.Width), 0.0f, 1.0f)));
		}
		Path = MoveTemp(Kept);
	}

	/** Extends both ends of the path onto the nearest mainland pixel. */
	void JoinEnds(TArray<FVector2f>& Path, const FGridI& NearestMainland, int32 Size)
	{
		for (int32 End : { 0, 1 })
		{
			const FVector2f P = End == 0 ? Path[0] : Path.Last();
			const int32 X = FMath::Clamp(FMath::RoundToInt(P.X), 0, Size - 1), Y = FMath::Clamp(FMath::RoundToInt(P.Y), 0, Size - 1);
			const int32 N = NearestMainland.At(X, Y);
			if (N < 0) continue;
			const FVector2f Target(float(N % Size), float(N / Size));
			const int32 Steps = FMath::Max(FMath::CeilToInt(FVector2f::Distance(Target, P) / StepPx), 1);
			TArray<FVector2f> Segment;
			for (int32 I = 1; I <= Steps; ++I) Segment.Add(P + (Target - P) * (float(I) / Steps));
			if (End == 0) { Algo::Reverse(Segment); Segment.Append(Path); Path = MoveTemp(Segment); }
			else Path.Append(Segment);
		}
	}

	/** One bar for one land. Returns false with a problem. */
	bool OneBar(int32 LandId, FLandResult& Land, const FCircleResult& Circle, const FSizes& Px, const FTerrainSpitConfig& Cfg,
		FRandomStream& Rng, const FGridF& EdgeNoise, const FGridF& Width, FGridB& OutBar, float& OutLength, FString& OutProblem)
	{
		const int32 Size = Land.LandMask.Size;
		FGridB Mainland(Size, 0);
		FGridB Other(Size, 0);
		FGridB AllLand(Size, 0);
		int32 MainlandArea = 0;
		for (int32 I = 0; I < Size * Size; ++I)
		{
			const bool bMain = Land.LandIds.Data[I] == LandId && !Land.SpitMask.Data[I];
			Mainland.Data[I] = bMain ? 1 : 0;
			MainlandArea += bMain ? 1 : 0;
			Other.Data[I] = (Land.LandMask.Data[I] && !bMain) ? 1 : 0;   // other lands and earlier bars
			AllLand.Data[I] = Land.LandMask.Data[I];
		}
		FGridF DMain;
		FGridI NearestMainland;
		DistanceToMask(Mainland, DMain, &NearestMainland);
		FGridB Closed;
		Closing(Mainland, Px.Bay, Closed);
		FGridF DistRaw, Dist;
		DistanceToMask(Closed, DistRaw);
		GaussianBlur(DistRaw, Dist, 2.0f);
		FGridF Gx, Gy;
		Gradient(Dist, Gx, Gy);
		FGridF Room;
		DistanceToMask(Other, Room);
		FGridF Inside(Size, 0.0f);
		for (int32 I = 0; I < Size * Size; ++I) Inside.Data[I] = Circle.EdgeBand.Data[I] > 0.5f ? 1.0f : 0.0f;
		const float MinRoom = Px.Gap + Px.Width;
		const float MinLagoon = Cfg.MinLagoonPct / 100.0f * float(MainlandArea);

		// start points: outer coast pixels on the boundary of the closed shape, with room around them
		FGridB NotClosed;
		InvertMask(Closed, NotClosed);
		FGridF DistOutside;
		DistanceToMask(NotClosed, DistOutside);
		TArray<FVector2f> Coast;
		for (int32 Y = 0; Y < Size; ++Y)
			for (int32 X = 0; X < Size; ++X)
				if (Mainland.At(X, Y) && DistOutside.At(X, Y) <= 2.5f && Room.At(X, Y) >= MinRoom && Inside.At(X, Y) > 0.5f)
					Coast.Add(FVector2f(float(X), float(Y)));
		if (Coast.Num() == 0) { OutProblem = FString::Printf(TEXT("land %d has no coast with room for a sand bar"), LandId); return false; }

		TArray<FVector2f> BestPath;
		int32 BestArea = -1;
		int32 Short = 0, Small = 0;
		for (int32 S = 0; S < Starts; ++S)
		{
			const FVector2f Start = Coast[Rng.RandRange(0, Coast.Num() - 1)];
			const float Length = Rng.FRandRange(Px.LengthMin, Px.LengthMax);
			for (float Sign : { 1.0f, -1.0f })
			{
				TArray<FVector2f> Path = March(Start, Sign, Dist, Gx, Gy, DMain, Room, Inside, Px.Lagoon, Length, MinRoom);
				const float Got = PathLength(Path);
				if (Got < 0.6f * Length || DMain.Sample(Path.Last().X, Path.Last().Y) > 3.0f) { ++Short; continue; }
				FGridB Bar;
				Rasterize(Path, Width, EdgeNoise, nullptr, Bar);
				for (int32 I = 0; I < Size * Size; ++I) if (!Circle.Mask.Data[I] || AllLand.Data[I]) Bar.Data[I] = 0;
				const int32 Area = LagoonArea(Bar, AllLand);
				if (Area < MinLagoon) { ++Small; continue; }
				if (Area > BestArea) { BestArea = Area; BestPath = MoveTemp(Path); }
			}
		}
		if (BestArea < 0)
		{
			OutProblem = FString::Printf(TEXT("land %d: no sand bar fits. %d paths tried, %d stopped early, %d enclosed fewer than %d px"),
				LandId, 2 * Starts, Short, Small, int32(MinLagoon));
			return false;
		}
		JoinEnds(BestPath, NearestMainland, Size);
		OutLength = PathLength(BestPath);
		TArray<float> Factor;
		const TArray<float>* FactorPtr = nullptr;
		if (Px.Strait > 0.0f) { Strait(BestPath, Rng.RandRange(0, 1), Px, Factor); FactorPtr = &Factor; }
		Rasterize(BestPath, Width, EdgeNoise, FactorPtr, OutBar);
		for (int32 I = 0; I < Size * Size; ++I) if (!Circle.Mask.Data[I] || AllLand.Data[I]) OutBar.Data[I] = 0;
		// keep the pieces joined to the mainland, 4-connected like the rest of the pipeline
		FGridB Joined(Size, 0);
		for (int32 I = 0; I < Size * Size; ++I) Joined.Data[I] = (OutBar.Data[I] || Mainland.Data[I]) ? 1 : 0;
		FGridI Labels;
		TArray<int32> Areas;
		LabelComponents(Joined, Labels, Areas);
		TSet<int32> MainLabels;
		for (int32 I = 0; I < Size * Size; ++I) if (Mainland.Data[I]) MainLabels.Add(Labels.Data[I]);
		int32 Kept = 0;
		for (int32 I = 0; I < Size * Size; ++I)
		{
			if (OutBar.Data[I] && !MainLabels.Contains(Labels.Data[I])) OutBar.Data[I] = 0;
			Kept += OutBar.Data[I];
		}
		if (Kept == 0) { OutProblem = FString::Printf(TEXT("land %d: the strait removed the whole bar"), LandId); return false; }
		return true;
	}
}

bool MakeSpits(const FCircleResult& Circle, FLandResult& Land, const FTerrainSpitConfig& Config, FRandomStream& Rng, FString& OutProblem)
{
	const int32 Size = Land.LandMask.Size;
	const FSizes Px = MakeSizes(Config, Circle.Radius);
	FGridF EdgeNoise, WidthNoise, Width(Size, 0.0f);
	MakeNoise(EdgeNoise, Size, { 3, 24.0f, 2.0f, 0.5f }, ETerrainNoise::Fractal, Rng);
	MakeNoise(WidthNoise, Size, { 2, 6.0f, 2.0f, 0.5f }, ETerrainNoise::Fractal, Rng);
	for (int32 I = 0; I < Size * Size; ++I)
	{
		EdgeNoise.Data[I] = Px.EdgeNoise * (EdgeNoise.Data[I] - 0.5f) * 2.0f;
		Width.Data[I] = Px.Width * (1.0f + Config.WidthVariation * (WidthNoise.Data[I] - 0.5f) * 2.0f);
	}
	Land.SpitMask.Init(Size, 0);
	Land.SpitOwner.Init(Size, 0);
	Land.SpitLengthsPx.Reset();
	int32 MaxId = 0;
	for (int32 V : Land.LandIds.Data) MaxId = FMath::Max(MaxId, V);
	for (int32 LandId = 1; LandId <= MaxId; ++LandId)
	{
		FGridB Bar;
		float Length = 0.0f;
		if (!OneBar(LandId, Land, Circle, Px, Config, Rng, EdgeNoise, Width, Bar, Length, OutProblem)) return false;
		for (int32 I = 0; I < Size * Size; ++I)
		{
			if (!Bar.Data[I]) continue;
			Land.SpitMask.Data[I] = 1;
			Land.SpitOwner.Data[I] = LandId;
			Land.LandMask.Data[I] = 1;
			Land.LandIds.Data[I] = LandId;
		}
		Land.SpitLengthsPx.Add(Length);
	}
	return true;
}
```
Add `#include "Algo/Reverse.h"` at the top of the file.

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Spits`
Expected: `Passed  TerrainGen.Core.Spits`. If "one contact with the strait" fails with 2, the taper tip still touches the coast: raise the cut in `Strait` by adding `Px.Width` once more and rerun. If it fails with 0, `JoinEnds` did not reach the coast: check that `NearestMainland` comes from the `Mainland` transform, not the closed shape.

- [ ] **Step 5: Run the lands test again and commit**

Run: `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Lands`
Expected: `Passed  TerrainGen.Core.Lands`.

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the sand bars: a level-line path along the coast with a lagoon behind it"
```

---
### Task 11: Biomes stage

**Files:**
- Modify: `Public/TerrainStages.h`
- Create: `Private/TerrainStageBiomes.cpp`
- Test: `Private/Tests/BiomesTests.cpp`

Python reference: S:\python-terrain-generation\terrain\biomes.py. Read it first. The rules: region seeds for the non-spit types on the mainland with the placement rules, the warp, nearest-seed growth per land, one region per bar, validation, retry, and the sub-type rule: each land gets one sub-type of each biome type and no two lands share it.

**Interfaces:**
- Consumes: `FLandResult` from Task 9 and 10, `DistanceToMask`, `MakeNoise`, `HashSeed`.
- Produces: `bool MakeBiomes(const FLandResult& Land, const FTerrainBiomesConfig& Config, int32 Seed, FBiomeResult& Out, FString& OutError)`. Stage number 3. `SubtypeId(BiomeIndex, SubtypeIndex) = BiomeIndex * 3 + SubtypeIndex + 1`. Constant `TerrainSubtypeCount = 3`.

- [ ] **Step 1: Write the failing test**

`Private/Tests/BiomesTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainBiomesTest, "TerrainGen.Core.Biomes",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainBiomesTest::RunTest(const FString& Parameters)
{
	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TestTrue(TEXT("lands"), TerrainTest::MakeTestLands(42, true, Circle, Land, Error));
	const FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	FBiomeResult Biomes;
	TestTrue(TEXT("biomes generate"), MakeBiomes(Land, Cfg.Biomes, 42, Biomes, Error));

	TestEqual(TEXT("subtype id formula"), SubtypeId(0, 0), 1);
	TestEqual(TEXT("subtype id formula end"), SubtypeId(4, 2), 15);
	TestEqual(TEXT("type names follow the config"), Biomes.TypeNames[4], FName("mountain_range"));

	// every biome on every land, sea side exactly on the bars, ids 0 exactly on sea
	bool bZeroOnSea = true, bSeaSideOnBars = true;
	TSet<int32> Present[4];
	TSet<int32> Subtypes;
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
	{
		const int32 LandId = Land.LandIds.Data[I];
		if ((Biomes.RegionIds.Data[I] == 0) != (LandId == 0)) bZeroOnSea = false;
		if ((Biomes.BiomeIds.Data[I] == 1) != (Land.SpitMask.Data[I] != 0)) bSeaSideOnBars = false;
		if (LandId > 0) Present[LandId].Add(Biomes.BiomeIds.Data[I]);
		Subtypes.Add(Biomes.SubtypeIds.Data[I]);
	}
	TestTrue(TEXT("region ids are 0 exactly on sea"), bZeroOnSea);
	TestTrue(TEXT("sea side covers exactly the bars"), bSeaSideOnBars);
	for (int32 LandId = 1; LandId <= 3; ++LandId) TestEqual(TEXT("every biome on every land"), Present[LandId].Num(), 5);
	TestEqual(TEXT("all 15 sub-types plus sea appear"), Subtypes.Num(), 16);

	// one sub-type per biome per land, and no two lands share it
	for (int32 T = 0; T < 5; ++T)
	{
		TSet<int32> Letters;
		for (int32 LandId = 1; LandId <= 3; ++LandId)
		{
			TSet<int32> OnLand;
			for (const FTerrainRegion& R : Biomes.Regions)
				if (R.BiomeIndex == T && R.LandId == LandId) OnLand.Add(R.SubtypeIndex);
			TestEqual(TEXT("one sub-type of each biome per land"), OnLand.Num(), 1);
			if (OnLand.Num() == 1) Letters.Add(*OnLand.CreateConstIterator());
		}
		TestEqual(TEXT("the 3 lands use A, B, and C"), Letters.Num(), 3);
		const TArray<int32>* Order = Biomes.SubtypePerLand.Find(Biomes.TypeNames[T]);
		TestTrue(TEXT("sub-type order recorded"), Order != nullptr && Order->Num() == 3);
	}

	// regions stay on their land, and each bar is one region
	bool bOnLand = true;
	for (const FTerrainRegion& R : Biomes.Regions)
	{
		bool bAny = false;
		for (int32 I = 0; I < Land.LandMask.Num(); ++I)
			if (Biomes.RegionIds.Data[I] == R.Id) { bAny = true; if (Land.LandIds.Data[I] != R.LandId) bOnLand = false; }
		if (!bAny) bOnLand = false;
	}
	TestTrue(TEXT("regions stay on their land"), bOnLand);
	int32 BarRegions = 0;
	for (const FTerrainRegion& R : Biomes.Regions) if (R.BiomeIndex == 0) ++BarRegions;
	TestEqual(TEXT("one bar region per land"), BarRegions, 3);

	FBiomeResult Again;
	MakeBiomes(Land, Cfg.Biomes, 42, Again, Error);
	TestTrue(TEXT("deterministic"), Again.SubtypeIds.Data == Biomes.SubtypeIds.Data);
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `MakeBiomes` undeclared.

- [ ] **Step 3: Declare and write the biomes stage**

Add to `Public/TerrainStages.h`:
```cpp
constexpr int32 TerrainSubtypeCount = 3;
inline int32 SubtypeId(int32 BiomeIndex, int32 SubtypeIndex) { return BiomeIndex * TerrainSubtypeCount + SubtypeIndex + 1; }

/** Stage 3: biome regions and sub-types. Retries with the next attempt seed. */
TERRAINGENCORE_API bool MakeBiomes(const FLandResult& Land, const FTerrainBiomesConfig& Config, int32 Seed,
	FBiomeResult& Out, FString& OutError);
```

`Private/TerrainStageBiomes.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainAlgorithms.h"
#include "TerrainNoise.h"
#include "TerrainGenCore.h"

namespace
{
	constexpr int32 StageNumber = 3;

	TArray<int32> SeededTypes(const FTerrainBiomesConfig& Cfg)
	{
		TArray<int32> Out;
		for (int32 I = 0; I < Cfg.Types.Num(); ++I) if (Cfg.Types[I].Placement != ETerrainPlacement::Spit) Out.Add(I);
		return Out;
	}

	/** Candidate seed pixels of one land for a placement rule, with the Python fallbacks. */
	TArray<int32> Candidates(const FLandResult& Land, int32 LandId, const FGridF& Coast, ETerrainPlacement Placement, const FTerrainBiomesConfig& Cfg)
	{
		const int32 Size = Coast.Size;
		float MaxCoast = 0.0f;
		for (int32 I = 0; I < Size * Size; ++I)
			if (Land.LandIds.Data[I] == LandId && !Land.SpitMask.Data[I]) MaxCoast = FMath::Max(MaxCoast, Coast.Data[I]);
		auto Select = [&](TFunctionRef<bool(float)> Rule)
		{
			TArray<int32> Out;
			for (int32 I = 0; I < Size * Size; ++I)
				if (Land.LandIds.Data[I] == LandId && !Land.SpitMask.Data[I] && Rule(Coast.Data[I])) Out.Add(I);
			return Out;
		};
		const float Band = Cfg.CoastBandPx;
		TArray<int32> Out;
		switch (Placement)
		{
		case ETerrainPlacement::Coast: Out = Select([&](float C) { return C > 0.0f && C <= Band; }); break;
		case ETerrainPlacement::Low: Out = Select([&](float C) { return C > Band && C <= 2.0f * Band; }); break;
		case ETerrainPlacement::Inland: Out = Select([&](float C) { return C >= Cfg.InlandFraction * MaxCoast; }); break;
		default: Out = Select([&](float C) { return C > 10.0f; }); break;
		}
		if (Out.Num() == 0) Out = Select([&](float C) { return C > 10.0f; });
		if (Out.Num() == 0) Out = Select([&](float) { return true; });
		return Out;
	}

	TArray<FTerrainRegion> PlaceRegionSeeds(const FLandResult& Land, const FGridF& Coast, const FTerrainBiomesConfig& Cfg, FRandomStream& Rng, int32 LandCount)
	{
		const int32 Size = Coast.Size;
		TArray<FTerrainRegion> Regions;
		const TArray<int32> Seeded = SeededTypes(Cfg);
		for (int32 LandId = 1; LandId <= LandCount; ++LandId)
		{
			const int32 N = Rng.RandRange(Cfg.SeedsPerLandMin, Cfg.SeedsPerLandMax);
			TArray<int32> Types = Seeded;
			for (int32 I = Seeded.Num(); I < N; ++I) Types.Add(Seeded[Rng.RandRange(0, Seeded.Num() - 1)]);
			TArray<FVector2f> Placed;
			float Separation = Cfg.MinSeedSeparationPx;
			int32 Rejections = 0;
			for (int32 T : Types)
			{
				const TArray<int32> Pool = Candidates(Land, LandId, Coast, Cfg.Types[T].Placement, Cfg);
				FVector2f P;
				while (true)
				{
					const int32 K = Pool[Rng.RandRange(0, Pool.Num() - 1)];
					P = FVector2f(float(K % Size), float(K / Size));
					bool bFar = true;
					for (const FVector2f& Q : Placed) if (FVector2f::Distance(P, Q) < Separation) { bFar = false; break; }
					if (bFar) break;
					if (++Rejections >= 200) { Separation /= 2.0f; Rejections = 0; }
				}
				Placed.Add(P);
				FTerrainRegion R;
				R.Id = Regions.Num() + 1;
				R.LandId = LandId;
				R.SeedXY = P;
				R.BiomeIndex = T;
				Regions.Add(R);
			}
		}
		return Regions;
	}

	void GrowRegions(const FLandResult& Land, const TArray<FTerrainRegion>& Regions, const FGridF& Dx, const FGridF& Dy, FGridI& OutRegionIds)
	{
		const int32 Size = Dx.Size;
		OutRegionIds.Init(Size, 0);
		for (int32 Y = 0; Y < Size; ++Y)
		{
			for (int32 X = 0; X < Size; ++X)
			{
				const int32 LandId = Land.LandIds.At(X, Y);
				if (LandId == 0 || Land.SpitMask.At(X, Y)) continue;
				const FVector2f Warped(X + Dx.At(X, Y), Y + Dy.At(X, Y));
				float Best = 1e30f;
				int32 BestId = 0;
				for (const FTerrainRegion& R : Regions)
				{
					if (R.LandId != LandId) continue;
					const float D = FVector2f::DistSquared(Warped, R.SeedXY);
					if (D < Best) { Best = D; BestId = R.Id; }
				}
				OutRegionIds.At(X, Y) = BestId;
			}
		}
	}

	/** One region per bar, appended to the list and drawn into the region ids. */
	void SpitRegions(const FLandResult& Land, TArray<FTerrainRegion>& Regions, FGridI& RegionIds, const FTerrainBiomesConfig& Cfg, int32 LandCount)
	{
		int32 BiomeIndex = -1;
		for (int32 I = 0; I < Cfg.Types.Num(); ++I) if (Cfg.Types[I].Placement == ETerrainPlacement::Spit) { BiomeIndex = I; break; }
		if (BiomeIndex < 0) return;
		const int32 Size = RegionIds.Size;
		for (int32 LandId = 1; LandId <= LandCount; ++LandId)
		{
			double SumX = 0.0, SumY = 0.0;
			int32 Count = 0;
			for (int32 Y = 0; Y < Size; ++Y)
				for (int32 X = 0; X < Size; ++X)
					if (Land.SpitMask.At(X, Y) && Land.SpitOwner.At(X, Y) == LandId) { SumX += X; SumY += Y; ++Count; }
			if (Count == 0) continue;
			FTerrainRegion R;
			R.Id = Regions.Num() + 1;
			R.LandId = LandId;
			R.SeedXY = FVector2f(float(SumX / Count), float(SumY / Count));
			R.BiomeIndex = BiomeIndex;
			Regions.Add(R);
			for (int32 I = 0; I < Size * Size; ++I)
				if (Land.SpitMask.Data[I] && Land.SpitOwner.Data[I] == LandId) RegionIds.Data[I] = R.Id;
		}
	}

	/** Each land gets one sub-type of each biome type, and no two lands share it. */
	TMap<FName, TArray<int32>> AssignSubtypes(TArray<FTerrainRegion>& Regions, const FTerrainBiomesConfig& Cfg, int32 LandCount, FRandomStream& Rng)
	{
		TMap<FName, TArray<int32>> Orders;
		TArray<TArray<int32>> ByType;
		for (int32 T = 0; T < Cfg.Types.Num(); ++T)
		{
			TArray<int32> Order = { 0, 1, 2 };
			for (int32 I = Order.Num() - 1; I > 0; --I) Order.Swap(I, Rng.RandRange(0, I));
			while (Order.Num() < LandCount) Order.Add(Order[Order.Num() % TerrainSubtypeCount]);
			Orders.Add(Cfg.Types[T].Name, Order);
			ByType.Add(Order);
		}
		for (FTerrainRegion& R : Regions) R.SubtypeIndex = ByType[R.BiomeIndex][R.LandId - 1];
		return Orders;
	}

	bool AttemptBiomes(const FLandResult& Land, const FGridF& Coast, const FTerrainBiomesConfig& Cfg, FRandomStream& Rng, FBiomeResult& Out, FString& OutProblem)
	{
		const int32 Size = Coast.Size;
		int32 LandCount = 0;
		for (int32 V : Land.LandIds.Data) LandCount = FMath::Max(LandCount, V);
		TArray<FTerrainRegion> Regions = PlaceRegionSeeds(Land, Coast, Cfg, Rng, LandCount);

		FGridF Dx, Dy;
		const FNoiseParams WarpParams = { Cfg.Warp.Octaves, Cfg.Warp.Frequency, 2.0f, 0.5f };
		MakeNoise(Dx, Size, WarpParams, ETerrainNoise::Fractal, Rng);
		MakeNoise(Dy, Size, WarpParams, ETerrainNoise::Fractal, Rng);
		for (int32 I = 0; I < Size * Size; ++I)
		{
			Dx.Data[I] = Cfg.Warp.StrengthPx * (Dx.Data[I] - 0.5f) * 2.0f;
			Dy.Data[I] = Cfg.Warp.StrengthPx * (Dy.Data[I] - 0.5f) * 2.0f;
		}
		FGridI RegionIds;
		GrowRegions(Land, Regions, Dx, Dy, RegionIds);
		SpitRegions(Land, Regions, RegionIds, Cfg, LandCount);

		TArray<int32> Pixels;
		Pixels.Init(0, Regions.Num() + 1);
		for (int32 V : RegionIds.Data) if (V > 0) Pixels[V] += 1;
		for (const FTerrainRegion& R : Regions)
			if (Pixels[R.Id] == 0) { OutProblem = FString::Printf(TEXT("region %d has no pixels"), R.Id); return false; }

		Out.SubtypePerLand = AssignSubtypes(Regions, Cfg, LandCount, Rng);
		Out.RegionIds = RegionIds;
		Out.BiomeIds.Init(Size, 0);
		Out.SubtypeIds.Init(Size, 0);
		TArray<int32> BiomeLut, SubtypeLut;
		BiomeLut.Init(0, Regions.Num() + 1);
		SubtypeLut.Init(0, Regions.Num() + 1);
		for (const FTerrainRegion& R : Regions)
		{
			BiomeLut[R.Id] = R.BiomeIndex + 1;
			SubtypeLut[R.Id] = SubtypeId(R.BiomeIndex, R.SubtypeIndex);
		}
		for (int32 I = 0; I < Size * Size; ++I)
		{
			Out.BiomeIds.Data[I] = BiomeLut[RegionIds.Data[I]];
			Out.SubtypeIds.Data[I] = SubtypeLut[RegionIds.Data[I]];
		}
		Out.Regions = MoveTemp(Regions);
		Out.TypeNames.Reset();
		for (const FTerrainBiomeType& T : Cfg.Types) Out.TypeNames.Add(T.Name);
		return true;
	}
}

bool MakeBiomes(const FLandResult& Land, const FTerrainBiomesConfig& Config, int32 Seed, FBiomeResult& Out, FString& OutError)
{
	FGridB Sea;
	InvertMask(Land.LandMask, Sea);
	DistanceToMask(Sea, Out.CoastDistance);   // distance to the sea, 0 on sea
	FString Problem;
	for (int32 AttemptIndex = 0; AttemptIndex < Config.MaxRetries; ++AttemptIndex)
	{
		FRandomStream Rng(HashSeed(Seed, StageNumber, AttemptIndex));
		if (AttemptBiomes(Land, Out.CoastDistance, Config, Rng, Out, Problem))
		{
			Out.SeedUsed = Seed + AttemptIndex;
			return true;
		}
		UE_LOG(LogTerrainGen, Log, TEXT("Biomes try %d failed: %s. The stage tries again with the next seed."), AttemptIndex + 1, *Problem);
	}
	OutError = FString::Printf(TEXT("Seed %d could not place biome regions after %d tries: %s. Decrease biomes.warp.strength_px or biomes.min_seed_separation_px."),
		Seed, Config.MaxRetries, *Problem);
	return false;
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Biomes`
Expected: `Passed  TerrainGen.Core.Biomes`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the biomes stage with one sub-type per biome per land"
```

---
### Task 12: Heightmap stage

**Files:**
- Modify: `Public/TerrainStages.h`
- Create: `Private/TerrainStageHeightmap.cpp`
- Test: `Private/Tests/HeightmapTests.cpp`

Python reference: S:\python-terrain-generation\terrain\heightmap.py. Read it first.

**Interfaces:**
- Consumes: `FLandResult`, `FBiomeResult`, `DistanceToMask`, `GaussianBlur`, `MakeNoise`, `Smoothstep`.
- Produces: `void MakeHeightmap(const FCircleResult& Circle, const FLandResult& Land, const FBiomeResult& Biomes, const FTerrainHeightmapConfig& Config, int32 Seed, float SpitRisePx, FHeightResult& Out)`. Stage number 4. Height in [-1, 1], 0 at sea level.

- [ ] **Step 1: Write the failing test**

`Private/Tests/HeightmapTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainHeightmapTest, "TerrainGen.Core.Heightmap",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainHeightmapTest::RunTest(const FString& Parameters)
{
	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TestTrue(TEXT("lands"), TerrainTest::MakeTestLands(42, true, Circle, Land, Error));
	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	FBiomeResult Biomes;
	TestTrue(TEXT("biomes"), MakeBiomes(Land, Cfg.Biomes, 42, Biomes, Error));

	// a small world: a short coast rise and a narrow blend, like the Python tests
	FTerrainHeightmapConfig Hm = Cfg.Heightmap;
	Hm.CoastDistancePx = 15.0f;
	Hm.CoastBlurPx = 3.0f;
	for (auto& Pair : Hm.Profiles) Pair.Value.BlendPx = 5.0f;
	FHeightResult Height;
	MakeHeightmap(Circle, Land, Biomes, Hm, 42, Cfg.Spit.RisePx, Height);

	float LandMin = 1.0f, LandMax = -1.0f, SeaMax = -1.0f, SeaMin = 1.0f, CoastMax = -1.0f;
	float MinBase = 0.0f;
	for (const auto& Pair : Hm.Profiles) MinBase = FMath::Min(MinBase, Pair.Value.Base);
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
	{
		const float H = Height.Height.Data[I];
		if (Land.LandMask.Data[I])
		{
			LandMin = FMath::Min(LandMin, H); LandMax = FMath::Max(LandMax, H);
			if (Biomes.CoastDistance.Data[I] <= 1.5f && !Land.SpitMask.Data[I]) CoastMax = FMath::Max(CoastMax, H);
		}
		else { SeaMax = FMath::Max(SeaMax, H); SeaMin = FMath::Min(SeaMin, H); }
	}
	TestTrue(TEXT("land range"), LandMin >= MinBase - 1e-5f && LandMax <= 1.0f);
	TestTrue(TEXT("sea is below or at 0"), SeaMax <= 0.0f);
	TestTrue(TEXT("sea floor"), SeaMin >= -Hm.SeabedDepth - 1e-5f);
	TestTrue(TEXT("coast is near 0"), CoastMax < 0.02f);
	TestTrue(TEXT("outside the circle is the floor"), FMath::Abs(Height.Height.At(0, 0) + Hm.SeabedDepth) < 1e-4f);

	// mountains are higher than marshes inland
	auto InlandMean = [&](FName Name)
	{
		const int32 Index = Biomes.TypeNames.IndexOfByKey(Name) + 1;
		double Sum = 0.0; int32 N = 0;
		for (int32 I = 0; I < Land.LandMask.Num(); ++I)
			if (Biomes.CoastDistance.Data[I] > Hm.CoastDistancePx && Biomes.BiomeIds.Data[I] == Index) { Sum += Height.Height.Data[I]; ++N; }
		return N > 50 ? float(Sum / N) : -99.0f;
	};
	TestTrue(TEXT("mountains higher than marshes"), InlandMean(FName("mountain_range")) > InlandMean(FName("marshlands")) + 0.2f);

	// the bar reaches its profile base within the rise distance, and its coast stays low
	FTerrainProfile Bar = Hm.Profiles[FName("sea_side")];
	Bar.Base = 0.05f; Bar.Amplitude = 0.1f; Bar.BlendPx = 2.0f;
	Hm.Profiles[FName("sea_side")] = Bar;
	FHeightResult H2;
	MakeHeightmap(Circle, Land, Biomes, Hm, 42, 2.0f, H2);
	float InnerMin = 1.0f, EdgeMax = -1.0f; int32 Inner = 0;
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
	{
		if (!Land.SpitMask.Data[I]) continue;
		if (Biomes.CoastDistance.Data[I] >= 2.0f) { InnerMin = FMath::Min(InnerMin, H2.Height.Data[I]); ++Inner; }
		if (Biomes.CoastDistance.Data[I] <= 1.0f) EdgeMax = FMath::Max(EdgeMax, H2.Height.Data[I]);
	}
	TestTrue(TEXT("bar has inner pixels"), Inner > 20);
	TestTrue(TEXT("bar reaches its base"), InnerMin >= 0.05f - 0.01f);
	TestTrue(TEXT("bar edge stays low"), EdgeMax <= 0.5f * (0.05f + 0.1f) + 1e-4f);
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `MakeHeightmap` undeclared.

- [ ] **Step 3: Declare and write the heightmap stage**

Add to `Public/TerrainStages.h`:
```cpp
/** Stage 4: the height in [-1, 1]. 0 is sea level. SpitRisePx is the short coast rise on the sand bars. */
TERRAINGENCORE_API void MakeHeightmap(const FCircleResult& Circle, const FLandResult& Land, const FBiomeResult& Biomes,
	const FTerrainHeightmapConfig& Config, int32 Seed, float SpitRisePx, FHeightResult& Out);
```

`Private/TerrainStageHeightmap.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainAlgorithms.h"
#include "TerrainNoise.h"

namespace
{
	constexpr int32 StageNumber = 4;
}

void MakeHeightmap(const FCircleResult& Circle, const FLandResult& Land, const FBiomeResult& Biomes,
	const FTerrainHeightmapConfig& Cfg, int32 Seed, float SpitRisePx, FHeightResult& Out)
{
	const int32 Size = Land.LandMask.Size;
	const int32 N = Size * Size;
	const int32 Types = Biomes.TypeNames.Num();
	TArray<const FTerrainProfile*> Profiles;
	for (const FName& Name : Biomes.TypeNames) Profiles.Add(&Cfg.Profiles[Name]);

	// signed coast distance: land positive, sea negative
	FGridF SeaDistance;
	DistanceToMask(Land.LandMask, SeaDistance);
	FGridF Signed(Size, 0.0f);
	for (int32 I = 0; I < N; ++I) Signed.Data[I] = Land.LandMask.Data[I] ? Biomes.CoastDistance.Data[I] : -SeaDistance.Data[I];

	// the coast curve, with the short rise on the bars
	FGridF Smooth;
	GaussianBlur(Signed, Smooth, Cfg.CoastBlurPx);
	FGridF Curve(Size, 0.0f);
	for (int32 I = 0; I < N; ++I)
	{
		if (!Land.LandMask.Data[I]) continue;
		if (Land.SpitMask.Data[I]) Curve.Data[I] = Smoothstep(FMath::Clamp(Biomes.CoastDistance.Data[I] / SpitRisePx, 0.0f, 1.0f));
		else Curve.Data[I] = Smoothstep(FMath::Clamp(Smooth.Data[I] / Cfg.CoastDistancePx, 0.0f, 1.0f));
	}

	// blurred biome masks, one blend per biome, normalized. Bar pixels keep the bar profile only.
	TArray<FGridF> Weights;
	Weights.SetNum(Types);
	FGridF Total(Size, 0.0f);
	for (int32 T = 0; T < Types; ++T)
	{
		FGridF Mask(Size, 0.0f);
		for (int32 I = 0; I < N; ++I) Mask.Data[I] = Biomes.BiomeIds.Data[I] == T + 1 ? 1.0f : 0.0f;
		GaussianBlur(Mask, Weights[T], Profiles[T]->BlendPx);
		for (int32 I = 0; I < N; ++I) Total.Data[I] += Weights[T].Data[I];
	}
	for (int32 T = 0; T < Types; ++T)
		for (int32 I = 0; I < N; ++I)
		{
			if (Land.SpitMask.Data[I]) Weights[T].Data[I] = (Biomes.BiomeIds.Data[I] == T + 1) ? 1.0f : 0.0f;
			else Weights[T].Data[I] /= FMath::Max(Total.Data[I], 1e-6f);
		}

	// the profile mix
	FGridF Base(Size, 0.0f), Amp(Size, 0.0f), NoiseMix(Size, 0.0f);
	for (int32 T = 0; T < Types; ++T)
	{
		FRandomStream Rng(HashSeed(Seed, StageNumber, T));
		FGridF Noise;
		const FNoiseParams P = { Profiles[T]->Octaves, Profiles[T]->Frequency, Profiles[T]->Lacunarity, Profiles[T]->Persistence };
		MakeNoise(Noise, Size, P, Profiles[T]->Noise, Rng);
		for (int32 I = 0; I < N; ++I)
		{
			const float W = Weights[T].Data[I];
			Base.Data[I] += W * Profiles[T]->Base;
			Amp.Data[I] += W * Profiles[T]->Amplitude;
			NoiseMix.Data[I] += W * Noise.Data[I];
		}
	}

	// the seabed: 0 at the coast down to the floor, the floor at the circle edge and outside
	const float Depth = Cfg.SeabedDepth;
	FGridF Seabed(Size, 0.0f);
	for (int32 I = 0; I < N; ++I)
	{
		const float Band = Circle.EdgeBand.Data[I];
		const float S = -Depth * Smoothstep(FMath::Clamp(-Signed.Data[I] / Cfg.SeabedDistancePx, 0.0f, 1.0f));
		Seabed.Data[I] = S * Band + (-Depth) * (1.0f - Band);
	}
	FGridF SeabedBlur;
	GaussianBlur(Seabed, SeabedBlur, Cfg.SeabedBlurPx);
	for (int32 I = 0; I < N; ++I)
	{
		const float Band = Circle.EdgeBand.Data[I];
		SeabedBlur.Data[I] = FMath::Min(SeabedBlur.Data[I] * Band + (-Depth) * (1.0f - Band), 0.0f);
	}

	Out.Height.Init(Size, 0.0f);
	for (int32 I = 0; I < N; ++I)
	{
		if (Land.LandMask.Data[I])
			Out.Height.Data[I] = FMath::Clamp(Curve.Data[I] * (Base.Data[I] + Amp.Data[I] * NoiseMix.Data[I]), -1.0f, 1.0f);
		else
			Out.Height.Data[I] = SeabedBlur.Data[I];
	}
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Heightmap`
Expected: `Passed  TerrainGen.Core.Heightmap`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the heightmap stage with per-biome profiles and the bar rise"
```

---

### Task 13: Export arrays

**Files:**
- Modify: `Public/TerrainStages.h`
- Create: `Private/TerrainStageExport.cpp`
- Test: `Private/Tests/ExportTests.cpp`

Python reference: S:\python-terrain-generation\terrain\export.py, the functions `encode_height16`, `largest_remainder_255`, `make_weight_maps`, `seabed_biome_index`, and the id arrays in `export_unreal`. No files are written here; the arrays go into `FTerrainResult`.

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `uint16 EncodeHeight16(float Height, int32 SeaLevelValue)`.
  - `void LargestRemainder255(const TArray<float>& Weights, TArray<uint8>& Out)`: quantizes weights that add up to 1 into bytes that add up to exactly 255.
  - `int32 SeabedBiomeIndex(const FTerrainBiomesConfig& Config)`: the first spit or coast type, else 0.
  - `void MakeExportArrays(const FTerrainConfig& Config, const FCircleResult& Circle, const FLandResult& Land, const FBiomeResult& Biomes, const FHeightResult& Height, FTerrainResult& Out)`. Fills every field of `FTerrainResult` except `SeedUsedLand` and `SeedUsedBiomes`, which the generator sets.

- [ ] **Step 1: Write the failing test**

`Private/Tests/ExportTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "TerrainAlgorithms.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainExportTest, "TerrainGen.Core.Export",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainExportTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("encode -1"), int32(EncodeHeight16(-1.0f, 32768)), 0);
	TestEqual(TEXT("encode -0.5"), int32(EncodeHeight16(-0.5f, 32768)), 16384);
	TestEqual(TEXT("encode 0"), int32(EncodeHeight16(0.0f, 32768)), 32768);
	TestEqual(TEXT("encode 0.5"), int32(EncodeHeight16(0.5f, 32768)), 49152);
	TestEqual(TEXT("encode 1"), int32(EncodeHeight16(1.0f, 32768)), 65535);

	FRandomStream Rng(0);
	for (int32 Trial = 0; Trial < 50; ++Trial)
	{
		TArray<float> W = { Rng.FRand(), Rng.FRand(), Rng.FRand(), Rng.FRand(), Rng.FRand() };
		float Sum = 0.0f; for (float V : W) Sum += V;
		for (float& V : W) V /= Sum;
		TArray<uint8> Q;
		LargestRemainder255(W, Q);
		int32 QSum = 0; for (uint8 V : Q) QSum += V;
		if (QSum != 255) { TestEqual(TEXT("quantized weights add up to 255"), QSum, 255); break; }
	}

	const FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	TestEqual(TEXT("seabed biome is sea side"), SeabedBiomeIndex(Cfg.Biomes), 0);

	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TestTrue(TEXT("lands"), TerrainTest::MakeTestLands(42, true, Circle, Land, Error));
	FBiomeResult Biomes;
	TestTrue(TEXT("biomes"), MakeBiomes(Land, Cfg.Biomes, 42, Biomes, Error));
	FHeightResult Height;
	MakeHeightmap(Circle, Land, Biomes, Cfg.Heightmap, 42, Cfg.Spit.RisePx, Height);
	FTerrainConfig Small = Cfg;
	Small.Size = TerrainTest::Size;
	FTerrainResult Result;
	MakeExportArrays(Small, Circle, Land, Biomes, Height, Result);

	TestEqual(TEXT("size"), Result.Size, TerrainTest::Size);
	const float ExpectedMpp = 9000.0f / (TerrainTest::Size * 0.9f);
	TestTrue(TEXT("meters per pixel from the world diameter"), FMath::Abs(Result.MetersPerPixel - ExpectedMpp) < 1e-3f);
	TestEqual(TEXT("5 weight maps"), Result.Weights.Num(), 5);
	bool bSum255 = true, bIdsOk = true, bCoastNearSea = true;
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
	{
		int32 S = 0;
		for (int32 T = 0; T < 5; ++T) S += Result.Weights[T].Data[I];
		if (S != 255) bSum255 = false;
		if (Result.BiomeId.Data[I] != Biomes.BiomeIds.Data[I] || Result.SubtypeId.Data[I] != Biomes.SubtypeIds.Data[I]
			|| Result.LandId.Data[I] != Land.LandIds.Data[I]) bIdsOk = false;
		if (Land.LandMask.Data[I] && Biomes.CoastDistance.Data[I] <= 1.0f && !Land.SpitMask.Data[I]
			&& FMath::Abs(int32(Result.Height.Data[I]) - 32768) >= 700) bCoastNearSea = false;
	}
	TestTrue(TEXT("weights add up to 255 everywhere"), bSum255);
	TestTrue(TEXT("id arrays copy the stages"), bIdsOk);
	TestTrue(TEXT("the coast is near the sea level value"), bCoastNearSea);

	// the far sea takes the sea side weight
	FGridF SeaDist;
	DistanceToMask(Land.LandMask, SeaDist);
	bool bFarIsSand = true; int32 Far = 0;
	for (int32 I = 0; I < Land.LandMask.Num(); ++I)
		if (SeaDist.Data[I] > 6.0f * Cfg.Export.WeightBlurPx) { ++Far; if (Result.Weights[0].Data[I] != 255) bFarIsSand = false; }
	TestTrue(TEXT("far sea pixels exist"), Far > 100);
	TestTrue(TEXT("far sea is sea side"), bFarIsSand);
	TestEqual(TEXT("regions copied"), Result.Regions.Num(), Biomes.Regions.Num());
	TestEqual(TEXT("sub-type orders copied"), Result.SubtypePerLand.Num(), 5);
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `EncodeHeight16` undeclared.

- [ ] **Step 3: Declare and write the export stage**

Add to `Public/TerrainStages.h`:
```cpp
/** Stage 5: the export arrays. */
TERRAINGENCORE_API uint16 EncodeHeight16(float Height, int32 SeaLevelValue);
TERRAINGENCORE_API void LargestRemainder255(const TArray<float>& Weights, TArray<uint8>& Out);
TERRAINGENCORE_API int32 SeabedBiomeIndex(const FTerrainBiomesConfig& Config);
TERRAINGENCORE_API void MakeExportArrays(const FTerrainConfig& Config, const FCircleResult& Circle, const FLandResult& Land,
	const FBiomeResult& Biomes, const FHeightResult& Height, FTerrainResult& Out);
```

`Private/TerrainStageExport.cpp`:
```cpp
#include "TerrainStages.h"
#include "TerrainAlgorithms.h"
#include "TerrainNoise.h"

uint16 EncodeHeight16(float Height, int32 SeaLevelValue)
{
	const float Sea = float(SeaLevelValue);
	const float V = Height >= 0.0f ? Sea + Height * (65535.0f - Sea) : Sea + Height * Sea;
	return uint16(FMath::Clamp(FMath::RoundToInt(V), 0, 65535));
}

void LargestRemainder255(const TArray<float>& Weights, TArray<uint8>& Out)
{
	const int32 N = Weights.Num();
	TArray<int32> Base;
	TArray<float> Frac;
	int32 Sum = 0;
	for (int32 I = 0; I < N; ++I)
	{
		const float Scaled = Weights[I] * 255.0f;
		const int32 B = FMath::FloorToInt(Scaled);
		Base.Add(B);
		Frac.Add(Scaled - B);
		Sum += B;
	}
	TArray<int32> Order;
	for (int32 I = 0; I < N; ++I) Order.Add(I);
	Order.StableSort([&](int32 A, int32 B) { return Frac[A] > Frac[B]; });
	for (int32 K = 0; K < 255 - Sum && K < N; ++K) Base[Order[K]] += 1;
	Out.SetNum(N);
	for (int32 I = 0; I < N; ++I) Out[I] = uint8(FMath::Clamp(Base[I], 0, 255));
}

int32 SeabedBiomeIndex(const FTerrainBiomesConfig& Config)
{
	for (int32 I = 0; I < Config.Types.Num(); ++I)
		if (Config.Types[I].Placement == ETerrainPlacement::Spit || Config.Types[I].Placement == ETerrainPlacement::Coast) return I;
	return 0;
}

void MakeExportArrays(const FTerrainConfig& Config, const FCircleResult& Circle, const FLandResult& Land,
	const FBiomeResult& Biomes, const FHeightResult& Height, FTerrainResult& Out)
{
	const int32 Size = Land.LandMask.Size;
	const int32 N = Size * Size;
	const int32 Types = Biomes.TypeNames.Num();
	Out.Size = Size;
	Out.MetersPerPixel = Config.World.DiameterM / (Size * Config.Circle.DiameterPct / 100.0f);

	Out.Height.Init(Size, 0);
	for (int32 I = 0; I < N; ++I) Out.Height.Data[I] = EncodeHeight16(Height.Height.Data[I], Config.Export.SeaLevelValue);

	// weight maps: sea pixels near the coast take the nearest land biome, further out the seabed biome
	FGridF SeaDistance;
	FGridI NearestLand;
	DistanceToMask(Land.LandMask, SeaDistance, &NearestLand);
	const int32 Seabed = SeabedBiomeIndex(Config.Biomes);
	const float ShelfPx = FMath::Max(4.0f * Config.Export.WeightBlurPx, 1.0f);
	TArray<FGridF> Blurred;
	Blurred.SetNum(Types);
	for (int32 T = 0; T < Types; ++T)
	{
		FGridF OneHot(Size, 0.0f);
		for (int32 I = 0; I < N; ++I)
		{
			const int32 Filled = Land.LandMask.Data[I] ? Biomes.BiomeIds.Data[I] : Biomes.BiomeIds.Data[NearestLand.Data[I]];
			const float Tt = Smoothstep(FMath::Clamp(SeaDistance.Data[I] / ShelfPx, 0.0f, 1.0f));
			const float Hot = Filled == T + 1 ? 1.0f : 0.0f;
			const float Sea = T == Seabed ? 1.0f : 0.0f;
			OneHot.Data[I] = Hot * (1.0f - Tt) + Sea * Tt;
		}
		GaussianBlur(OneHot, Blurred[T], Config.Export.WeightBlurPx);
	}
	Out.Weights.SetNum(Types);
	for (int32 T = 0; T < Types; ++T) Out.Weights[T].Init(Size, 0);
	TArray<float> W;
	TArray<uint8> Q;
	for (int32 I = 0; I < N; ++I)
	{
		float Total = 0.0f;
		W.SetNum(Types);
		for (int32 T = 0; T < Types; ++T) { W[T] = Blurred[T].Data[I]; Total += W[T]; }
		for (int32 T = 0; T < Types; ++T) W[T] /= FMath::Max(Total, 1e-6f);
		LargestRemainder255(W, Q);
		for (int32 T = 0; T < Types; ++T) Out.Weights[T].Data[I] = Q[T];
	}

	Out.SubtypeId.Init(Size, 0);
	Out.BiomeId.Init(Size, 0);
	Out.LandId.Init(Size, 0);
	for (int32 I = 0; I < N; ++I)
	{
		Out.SubtypeId.Data[I] = uint8(Biomes.SubtypeIds.Data[I]);
		Out.BiomeId.Data[I] = uint8(Biomes.BiomeIds.Data[I]);
		Out.LandId.Data[I] = uint8(Land.LandIds.Data[I]);
	}
	Out.Regions = Biomes.Regions;
	Out.SubtypePerLand = Biomes.SubtypePerLand;
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Export`
Expected: `Passed  TerrainGen.Core.Export`.

- [ ] **Step 5: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the export arrays: 16-bit height, weight maps, id maps"
```

---
### Task 14: The generator, progress, cancel, and the debug image set

**Files:**
- Create: `Public/TerrainGenerator.h`, `Private/TerrainGenerator.cpp`
- Test: `Private/Tests/GeneratorTests.cpp`

**Interfaces:**
- Consumes: every stage function, `ValidateTerrainConfig`, `WritePgm`.
- Produces:
  - `struct FTerrainProgressSink { TFunction<void(int32 Stage, const FString& Name, float Fraction)> Report; TFunction<bool()> IsCancelled; }`. Both members may be empty.
  - `bool GenerateTerrain(const FTerrainConfig& Config, FTerrainResult& Out, FString& OutError, const FTerrainProgressSink* Sink = nullptr)`. Validates, runs the six stages, reports stage 1 to 6 with the names "Circle", "Lands", "Sand bars", "Biomes", "Heightmap", "Export", fraction 0 at the start and 1 at the end of each stage. Returns false with the error, or with "cancelled" when the sink asked for it between stages.
  - `struct FTerrainDebugGrids { FGridB LandMask; FGridB SpitMask; FGridI BiomeIds; FGridI SubtypeIds; FGridF Height; }` and `bool GenerateTerrainWithDebug(const FTerrainConfig& Config, FTerrainResult& Out, FTerrainDebugGrids& OutDebug, FString& OutError, const FTerrainProgressSink* Sink = nullptr)`, the same run that also keeps the stage grids for images.
  - `void WriteDebugImages(const FString& Folder, const FTerrainDebugGrids& Debug)`: writes `land_mask.pgm`, `spit_mask.pgm`, `biome_ids.pgm`, `subtype_ids.pgm`, `height.pgm`.

- [ ] **Step 1: Write the failing test**

`Private/Tests/GeneratorTests.cpp`:
```cpp
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "TerrainGenerator.h"
#include "TerrainTestUtil.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainGeneratorTest, "TerrainGen.Core.Generator",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainGeneratorTest::RunTest(const FString& Parameters)
{
	FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	Cfg.Size = TerrainTest::Size;
	Cfg.Seed = 11;

	TArray<int32> Stages;
	TArray<float> Fractions;
	FTerrainProgressSink Sink;
	Sink.Report = [&](int32 Stage, const FString& Name, float Fraction) { Stages.Add(Stage); Fractions.Add(Fraction); };
	Sink.IsCancelled = []() { return false; };

	FTerrainResult Result;
	FTerrainDebugGrids Debug;
	FString Error;
	const double Start = FPlatformTime::Seconds();
	TestTrue(TEXT("generation succeeds"), GenerateTerrainWithDebug(Cfg, Result, Debug, Error, &Sink));
	const double Seconds = FPlatformTime::Seconds() - Start;
	TestTrue(TEXT("253 px runs in under 10 s"), Seconds < 10.0);
	TestEqual(TEXT("size"), Result.Size, TerrainTest::Size);
	TestTrue(TEXT("seeds used recorded"), Result.SeedUsedLand >= 11 && Result.SeedUsedBiomes >= 11);
	TestEqual(TEXT("progress reached stage 6"), Stages.Last(), 6);
	TestEqual(TEXT("progress ends at 1"), Fractions.Last(), 1.0f);
	TestEqual(TEXT("progress starts at stage 1"), Stages[0], 1);

	const FString Folder = FPaths::ProjectSavedDir() / TEXT("TerrainGenTests") / TEXT("seed_11");
	WriteDebugImages(Folder, Debug);
	TestTrue(TEXT("height image written"), FPaths::FileExists(Folder / TEXT("height.pgm")));
	TestTrue(TEXT("biome image written"), FPaths::FileExists(Folder / TEXT("biome_ids.pgm")));

	// the same seed gives the same arrays
	FTerrainResult Again;
	TestTrue(TEXT("second run"), GenerateTerrain(Cfg, Again, Error));
	TestTrue(TEXT("deterministic height"), Again.Height.Data == Result.Height.Data);
	TestTrue(TEXT("deterministic sub-types"), Again.SubtypeId.Data == Result.SubtypeId.Data);

	// a bad config fails before any stage
	FTerrainConfig Bad = Cfg;
	Bad.Size = 100;
	FTerrainResult BadResult;
	TestFalse(TEXT("bad config fails"), GenerateTerrain(Bad, BadResult, Error));
	TestTrue(TEXT("bad config message"), Error.Contains(TEXT("size must be")));

	// cancel between stages
	FTerrainProgressSink CancelSink;
	int32 Calls = 0;
	CancelSink.IsCancelled = [&]() { return ++Calls >= 2; };
	FTerrainResult Cancelled;
	TestFalse(TEXT("cancel stops the run"), GenerateTerrain(Cfg, Cancelled, Error, &CancelSink));
	TestTrue(TEXT("cancel message"), Error.Contains(TEXT("cancelled")));
	return true;
}

#endif
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `TerrainGenerator.h` not found.

- [ ] **Step 3: Write the generator**

`Public/TerrainGenerator.h`:
```cpp
#pragma once

#include "CoreMinimal.h"
#include "TerrainConfig.h"
#include "TerrainResults.h"

/** Progress and cancel callbacks. Both may be empty. Called on the thread that runs the generator. */
struct FTerrainProgressSink
{
	TFunction<void(int32 Stage, const FString& Name, float Fraction)> Report;
	TFunction<bool()> IsCancelled;
};

/** The intermediate grids, kept for debug images. */
struct FTerrainDebugGrids
{
	FGridB LandMask;
	FGridB SpitMask;
	FGridI BiomeIds;
	FGridI SubtypeIds;
	FGridF Height;
};

/** Runs the six stages. False with an error message, or with "cancelled". */
TERRAINGENCORE_API bool GenerateTerrain(const FTerrainConfig& Config, FTerrainResult& Out, FString& OutError,
	const FTerrainProgressSink* Sink = nullptr);

TERRAINGENCORE_API bool GenerateTerrainWithDebug(const FTerrainConfig& Config, FTerrainResult& Out, FTerrainDebugGrids& OutDebug,
	FString& OutError, const FTerrainProgressSink* Sink = nullptr);

/** Writes land_mask.pgm, spit_mask.pgm, biome_ids.pgm, subtype_ids.pgm, and height.pgm into the folder. */
TERRAINGENCORE_API void WriteDebugImages(const FString& Folder, const FTerrainDebugGrids& Debug);
```

`Private/TerrainGenerator.cpp`:
```cpp
#include "TerrainGenerator.h"
#include "TerrainStages.h"
#include "TerrainDebugImages.h"
#include "TerrainGenCore.h"

namespace
{
	const TCHAR* StageNames[] = { TEXT("Circle"), TEXT("Lands"), TEXT("Sand bars"), TEXT("Biomes"), TEXT("Heightmap"), TEXT("Export") };

	bool Step(const FTerrainProgressSink* Sink, int32 Stage, float Fraction, FString& OutError)
	{
		if (Sink && Sink->IsCancelled && Sink->IsCancelled()) { OutError = TEXT("cancelled"); return false; }
		if (Sink && Sink->Report) Sink->Report(Stage, StageNames[Stage - 1], Fraction);
		return true;
	}
}

bool GenerateTerrainWithDebug(const FTerrainConfig& Config, FTerrainResult& Out, FTerrainDebugGrids& OutDebug,
	FString& OutError, const FTerrainProgressSink* Sink)
{
	if (!ValidateTerrainConfig(Config, OutError)) return false;
	const double Start = FPlatformTime::Seconds();

	if (!Step(Sink, 1, 0.0f, OutError)) return false;
	FCircleResult Circle;
	MakeCircle(Config.Size, Config.Circle, Circle);
	if (!Step(Sink, 1, 1.0f, OutError)) return false;

	// stages 2 and 3 run together: the lands stage retries when a sand bar does not fit
	if (!Step(Sink, 2, 0.0f, OutError)) return false;
	FLandResult Land;
	if (!MakeLands(Circle, Config.Land, &Config.Spit, Config.Seed, Land, OutError)) return false;
	if (!Step(Sink, 3, 1.0f, OutError)) return false;

	if (!Step(Sink, 4, 0.0f, OutError)) return false;
	FBiomeResult Biomes;
	if (!MakeBiomes(Land, Config.Biomes, Config.Seed, Biomes, OutError)) return false;
	if (!Step(Sink, 4, 1.0f, OutError)) return false;

	if (!Step(Sink, 5, 0.0f, OutError)) return false;
	FHeightResult Height;
	MakeHeightmap(Circle, Land, Biomes, Config.Heightmap, Config.Seed, Config.Spit.RisePx, Height);
	if (!Step(Sink, 5, 1.0f, OutError)) return false;

	if (!Step(Sink, 6, 0.0f, OutError)) return false;
	MakeExportArrays(Config, Circle, Land, Biomes, Height, Out);
	Out.SeedUsedLand = Land.SeedUsed;
	Out.SeedUsedBiomes = Biomes.SeedUsed;
	if (!Step(Sink, 6, 1.0f, OutError)) return false;

	OutDebug.LandMask = Land.LandMask;
	OutDebug.SpitMask = Land.SpitMask;
	OutDebug.BiomeIds = Biomes.BiomeIds;
	OutDebug.SubtypeIds = Biomes.SubtypeIds;
	OutDebug.Height = Height.Height;
	UE_LOG(LogTerrainGen, Log, TEXT("Generated a %d px world for seed %d in %.2f s."), Config.Size, Config.Seed, FPlatformTime::Seconds() - Start);
	OutError.Empty();
	return true;
}

bool GenerateTerrain(const FTerrainConfig& Config, FTerrainResult& Out, FString& OutError, const FTerrainProgressSink* Sink)
{
	FTerrainDebugGrids Unused;
	return GenerateTerrainWithDebug(Config, Out, Unused, OutError, Sink);
}

void WriteDebugImages(const FString& Folder, const FTerrainDebugGrids& Debug)
{
	WritePgm(Folder / TEXT("land_mask.pgm"), Debug.LandMask);
	WritePgm(Folder / TEXT("spit_mask.pgm"), Debug.SpitMask);
	WritePgm(Folder / TEXT("biome_ids.pgm"), Debug.BiomeIds);
	WritePgm(Folder / TEXT("subtype_ids.pgm"), Debug.SubtypeIds);
	WritePgm(Folder / TEXT("height.pgm"), Debug.Height, -0.3f, 1.0f);
}
```

- [ ] **Step 4: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.Generator`
Expected: `Passed  TerrainGen.Core.Generator`.

- [ ] **Step 5: Run every test and look at the images**

Run: `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core`
Expected: every line `Passed`, exit code 0.

Open S:\WorldGenUE\Saved\TerrainGenTests\seed_11\biome_ids.pgm and height.pgm in an image viewer and compare them with the Python previews in S:\python-terrain-generation\out\preview\. The 3 lands, the sand bars with water behind them, and the height shading must read the same way. If the lands look too small or too ragged, tune `FTerrainLandConfig::Threshold` in `TerrainConfig.h` by steps of 0.02, rerun the tests, and commit the value with a note.

- [ ] **Step 6: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Add the generator with progress, cancel, and debug images"
```

---

## Self-review notes

- Spec sections 4 to 8 and 13 are covered by Tasks 1 to 14. Sections 9 to 12 (the UObject layer, `GenerateWorld`, the actor, the editor module) belong to the next plans.
- The spec lists `TerrainAlgorithms.h` as one header; this plan also has `TerrainNoise.h`, `TerrainDebugImages.h`, and `TerrainGenerator.h`, which the spec names in its file list.
- Every function name used across tasks matches its definition: `DistanceToMask`, `LabelComponents`, `GaussianBlur`, `Gradient`, `Dilate8`, `Closing`, `MakeNoise`, `Smoothstep`, `HashSeed`, `MakeCircle`, `MakeLands`, `MakeSpits`, `MakeBiomes`, `SubtypeId`, `MakeHeightmap`, `EncodeHeight16`, `LargestRemainder255`, `SeabedBiomeIndex`, `MakeExportArrays`, `GenerateTerrain`, `GenerateTerrainWithDebug`, `WriteDebugImages`, `WritePgm`.

---

### Task 15: Biome area balance

**Files:**
- Modify: `Public/TerrainConfig.h` (two fields in `FTerrainBiomesConfig`), `Private/TerrainConfig.cpp` (two validation checks)
- Modify: `Private/TerrainStageBiomes.cpp` (`GrowRegions` takes a scale, new `BalanceRegions` and `DropEmptyRegions`, a per-type validation, `AttemptBiomes` uses them)
- Test: `Private/Tests/BiomesTests.cpp` (add a second test), `Private/Tests/ConfigTests.cpp` (add two assertions)

Python reference: S:\python-terrain-generation\terrain\biomes.py, the functions `_grow_regions`, `_balance_regions`, `_drop_empty_regions`, and `_validate`, plus the fields `balance_iterations` and `balance_tolerance` in `terrain/config.py`. Read them first. The rule: the 4 mainland biome types share each land about equally. The region growth multiplies the distance to each seed by a scale per region, and the generator tunes the scales per biome type and land in damped rounds until the worst share error is within the tolerance. A seed is always nearest to itself, so a type never vanishes; a duplicate seed of a type that shrinks to nothing is dropped and the region ids are made dense again.

**Interfaces:**
- Consumes: everything Task 11 produced.
- Produces: `FTerrainBiomesConfig::BalanceIterations` (default 25) and `BalanceTolerance` (default 0.05f). `MakeBiomes` keeps its signature. Region ids stay dense 1..N after dropping.

- [ ] **Step 1: Write the failing tests**

Append to `Private/Tests/BiomesTests.cpp` before the final `#endif`:
```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTerrainBiomeBalanceTest, "TerrainGen.Core.BiomeBalance",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FTerrainBiomeBalanceTest::RunTest(const FString& Parameters)
{
	const FTerrainConfig Cfg = MakeDefaultTerrainConfig();
	TArray<int32> Seeded;
	for (int32 T = 0; T < Cfg.Biomes.Types.Num(); ++T)
		if (Cfg.Biomes.Types[T].Placement != ETerrainPlacement::Spit) Seeded.Add(T);
	const float Target = 1.0f / Seeded.Num();

	for (int32 Seed : { 42, 7, 3 })
	{
		FCircleResult Circle;
		FLandResult Land;
		FString Error;
		TestTrue(TEXT("lands"), TerrainTest::MakeTestLands(Seed, true, Circle, Land, Error));
		FBiomeResult Biomes;
		TestTrue(TEXT("biomes"), MakeBiomes(Land, Cfg.Biomes, Seed, Biomes, Error));
		for (int32 LandId = 1; LandId <= 3; ++LandId)
		{
			int32 Total = 0;
			TArray<int32> Count;
			Count.Init(0, Cfg.Biomes.Types.Num());
			for (int32 I = 0; I < Land.LandMask.Num(); ++I)
			{
				if (Land.LandIds.Data[I] != LandId || Land.SpitMask.Data[I]) continue;
				++Total;
				Count[Biomes.BiomeIds.Data[I] - 1] += 1;
			}
			for (int32 T : Seeded)
			{
				const float Share = float(Count[T]) / float(Total);
				TestTrue(FString::Printf(TEXT("seed %d land %d biome %d share %.2f near %.2f"), Seed, LandId, T, Share, Target),
					FMath::Abs(Share - Target) <= Cfg.Biomes.BalanceTolerance + 0.03f);
			}
		}
		// the region ids stay dense after a dropped duplicate seed
		int32 MaxId = 0;
		for (int32 V : Biomes.RegionIds.Data) MaxId = FMath::Max(MaxId, V);
		TestEqual(TEXT("dense region ids"), MaxId, Biomes.Regions.Num());
		for (int32 I = 0; I < Biomes.Regions.Num(); ++I) TestEqual(TEXT("region id order"), Biomes.Regions[I].Id, I + 1);
	}

	// the balance can be switched off
	FCircleResult Circle;
	FLandResult Land;
	FString Error;
	TerrainTest::MakeTestLands(42, true, Circle, Land, Error);
	FTerrainBiomesConfig Off = Cfg.Biomes;
	Off.BalanceIterations = 0;
	FBiomeResult Plain;
	TestTrue(TEXT("biomes without balance"), MakeBiomes(Land, Off, 42, Plain, Error));
	int32 MaxBiome = 0;
	for (int32 V : Plain.BiomeIds.Data) MaxBiome = FMath::Max(MaxBiome, V);
	TestEqual(TEXT("all biomes present without balance"), MaxBiome, 5);
	return true;
}
```

Append to the config test in `Private/Tests/ConfigTests.cpp`, before `TestNotEqual(TEXT("seed hash differs by stage")...`:
```cpp
	TestEqual(TEXT("balance rounds"), Cfg.Biomes.BalanceIterations, 25);
	TestTrue(TEXT("balance tolerance"), FMath::IsNearlyEqual(Cfg.Biomes.BalanceTolerance, 0.05f));
	Bad = Cfg; Bad.Biomes.BalanceTolerance = 1.0f;
	TestFalse(TEXT("bad balance tolerance"), ValidateTerrainConfig(Bad, Error));
	TestTrue(TEXT("balance tolerance message"), Error.Contains(TEXT("biomes.balance_tolerance")));
```

- [ ] **Step 2: Build to verify it fails**

Run: `S:\WorldGenUE\Tools\Build.ps1`
Expected: FAIL to compile, `BalanceIterations` is not a member.

- [ ] **Step 3: Add the config fields and their validation**

In `Public/TerrainConfig.h`, inside `FTerrainBiomesConfig`, after `int32 MaxRetries = 10;`:
```cpp
	int32 BalanceIterations = 25;    // rounds that tune the biome sizes, so the mainland biomes share each land equally. 0 turns it off
	float BalanceTolerance = 0.05f;  // allowed difference from the equal share, as a fraction of the land
```

In `Private/TerrainConfig.cpp`, in `ValidateTerrainConfig`, after the `seeds_per_land` check and before the profiles loop:
```cpp
	if (Cfg.Biomes.BalanceIterations < 0)
	{
		OutError = FString::Printf(TEXT("biomes.balance_iterations must be >= 0. Got %d."), Cfg.Biomes.BalanceIterations);
		return false;
	}
	if (Cfg.Biomes.BalanceTolerance <= 0.0f || Cfg.Biomes.BalanceTolerance >= 1.0f)
	{
		OutError = FString::Printf(TEXT("biomes.balance_tolerance must be in (0, 1). Got %g."), Cfg.Biomes.BalanceTolerance);
		return false;
	}
```

- [ ] **Step 4: Change the biomes stage**

In `Private/TerrainStageBiomes.cpp`, replace the whole `GrowRegions` function with:
```cpp
	/** Each mainland pixel goes to the nearest seed on its land. The scale multiplies the distance per
	 *  region id, so a biome with a scale above 1 gives up pixels at its borders. A seed is always
	 *  nearest to itself, so no biome type can lose every pixel. */
	void GrowRegions(const FLandResult& Land, const TArray<FTerrainRegion>& Regions, const FGridF& Dx, const FGridF& Dy,
		const TArray<float>& Scale, FGridI& OutRegionIds)
	{
		const int32 Size = Dx.Size;
		OutRegionIds.Init(Size, 0);
		for (int32 Y = 0; Y < Size; ++Y)
		{
			for (int32 X = 0; X < Size; ++X)
			{
				const int32 LandId = Land.LandIds.At(X, Y);
				if (LandId == 0 || Land.SpitMask.At(X, Y)) continue;
				const FVector2f Warped(X + Dx.At(X, Y), Y + Dy.At(X, Y));
				float Best = 1e30f;
				int32 BestId = 0;
				for (const FTerrainRegion& R : Regions)
				{
					if (R.LandId != LandId) continue;
					const float D = FVector2f::Distance(Warped, R.SeedXY) * Scale[R.Id];
					if (D < Best) { Best = D; BestId = R.Id; }
				}
				OutRegionIds.At(X, Y) = BestId;
			}
		}
	}

	/** Tunes one distance scale per biome type and land until the seeded biome types share each land
	 *  about equally. Scale is indexed by region id, so it has Regions.Num() + 1 entries. */
	void BalanceRegions(const FLandResult& Land, const TArray<FTerrainRegion>& Regions, const FGridF& Dx, const FGridF& Dy,
		const FTerrainBiomesConfig& Cfg, int32 LandCount, FGridI& OutRegionIds, TArray<float>& OutScale)
	{
		const TArray<int32> Seeded = SeededTypes(Cfg);
		const float Target = 1.0f / FMath::Max(Seeded.Num(), 1);
		OutScale.Init(1.0f, Regions.Num() + 1);
		GrowRegions(Land, Regions, Dx, Dy, OutScale, OutRegionIds);
		TArray<int32> Total;
		TArray<int32> Count;
		for (int32 It = 0; It < Cfg.BalanceIterations; ++It)
		{
			// the step shrinks each round, so two neighbors cannot trade the same strip back and forth
			const float Exponent = 0.35f * FMath::Pow(0.8f, float(It));
			Total.Init(0, LandCount + 1);
			Count.Init(0, Regions.Num() + 1);
			for (int32 I = 0; I < OutRegionIds.Num(); ++I)
			{
				const int32 LandId = Land.LandIds.Data[I];
				if (LandId == 0 || Land.SpitMask.Data[I]) continue;
				Total[LandId] += 1;
				Count[OutRegionIds.Data[I]] += 1;
			}
			float Worst = 0.0f;
			for (int32 LandId = 1; LandId <= LandCount; ++LandId)
			{
				if (Total[LandId] == 0) continue;
				for (int32 T : Seeded)
				{
					int32 Pixels = 0;
					for (const FTerrainRegion& R : Regions) if (R.LandId == LandId && R.BiomeIndex == T) Pixels += Count[R.Id];
					const float Share = float(Pixels) / float(Total[LandId]);
					Worst = FMath::Max(Worst, FMath::Abs(Share - Target));
					const float Factor = FMath::Clamp(FMath::Pow(FMath::Max(Share, 1e-3f) / Target, Exponent), 0.75f, 1.33f);
					for (const FTerrainRegion& R : Regions)
						if (R.LandId == LandId && R.BiomeIndex == T) OutScale[R.Id] = FMath::Clamp(OutScale[R.Id] * Factor, 0.05f, 20.0f);
				}
			}
			if (Worst <= Cfg.BalanceTolerance) break;
			GrowRegions(Land, Regions, Dx, Dy, OutScale, OutRegionIds);
		}
	}

	/** The balance can shrink an extra seed of a biome type to nothing. Such a region goes away, and the
	 *  ids of the others stay dense 1..N. */
	void DropEmptyRegions(TArray<FTerrainRegion>& Regions, FGridI& RegionIds)
	{
		TArray<int32> Count;
		Count.Init(0, Regions.Num() + 1);
		for (int32 V : RegionIds.Data) if (V > 0) Count[V] += 1;
		TArray<int32> Remap;
		Remap.Init(0, Regions.Num() + 1);
		TArray<FTerrainRegion> Kept;
		for (FTerrainRegion& R : Regions)
		{
			if (Count[R.Id] == 0) continue;
			Remap[R.Id] = Kept.Num() + 1;
			R.Id = Kept.Num() + 1;
			Kept.Add(R);
		}
		for (int32& V : RegionIds.Data) V = Remap[V];
		Regions = MoveTemp(Kept);
	}
```

In `AttemptBiomes`, replace the block from `FGridI RegionIds;` through the empty-region check with:
```cpp
		FGridI RegionIds;
		TArray<float> Scale;
		BalanceRegions(Land, Regions, Dx, Dy, Cfg, LandCount, RegionIds, Scale);
		DropEmptyRegions(Regions, RegionIds);
		SpitRegions(Land, Regions, RegionIds, Cfg, LandCount);

		for (int32 LandId = 1; LandId <= LandCount; ++LandId)
			for (int32 T = 0; T < Cfg.Types.Num(); ++T)
			{
				if (Cfg.Types[T].Placement == ETerrainPlacement::Spit) continue;
				bool bAny = false;
				for (const FTerrainRegion& R : Regions) if (R.LandId == LandId && R.BiomeIndex == T) { bAny = true; break; }
				if (!bAny) { OutProblem = FString::Printf(TEXT("land %d lost every region of biome %s"), LandId, *Cfg.Types[T].Name.ToString()); return false; }
			}
		TArray<int32> Pixels;
		Pixels.Init(0, Regions.Num() + 1);
		for (int32 V : RegionIds.Data) if (V > 0) Pixels[V] += 1;
		for (const FTerrainRegion& R : Regions)
			if (Pixels[R.Id] == 0) { OutProblem = FString::Printf(TEXT("region %d has no pixels"), R.Id); return false; }
```
The old call `GrowRegions(Land, Regions, Dx, Dy, RegionIds);` and the old `SpitRegions` call go away; `SpitRegions` is now called after `DropEmptyRegions`, as shown, so the bar regions get ids after the kept mainland regions.

- [ ] **Step 5: Build and run to verify it passes**

Run: `S:\WorldGenUE\Tools\Build.ps1` then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core.BiomeBalance`, then `S:\WorldGenUE\Tools\RunTests.ps1 TerrainGen.Core`
Expected: `Passed  TerrainGen.Core.BiomeBalance` and every other test passes. If a share assertion fails by a little (the Perlin warp differs from Python), report the values first; the tolerance of the test is the config tolerance plus 0.03.

- [ ] **Step 6: Commit**

```powershell
Set-Location S:\WorldGenUE
git add Plugins/TerrainGen
git commit -m "Balance the biome areas: the mainland biomes share each land equally"
```
