import pytest

from terrain.config import (
    Config,
    ConfigError,
    config_from_dict,
    config_to_dict,
    load_config,
)


def test_defaults_are_valid():
    cfg = config_from_dict({})
    assert cfg.size == 1009
    assert cfg.landmass.count == 3
    assert len(cfg.biomes.types) == 5
    assert set(cfg.heightmap.profiles) == {t.name for t in cfg.biomes.types}
    assert cfg.heightmap.profiles["mountain_range"].noise == "ridged"
    assert cfg.heightmap.profiles["marshlands"].noise == "fractal"
    assert cfg.heightmap.profiles["marshlands"].base < 0
    assert not hasattr(cfg.heightmap.profiles["marshlands"], "floor")


def test_override_merges_nested_values():
    cfg = config_from_dict({"size": 253, "landmass": {"threshold": 0.3}})
    assert cfg.size == 253
    assert cfg.landmass.threshold == 0.3
    assert cfg.landmass.count == 3


def test_invalid_size_raises():
    with pytest.raises(ConfigError, match="127, 253, 505, 1009"):
        config_from_dict({"size": 1000})


def test_bad_placement_raises():
    types = config_to_dict(Config())["biomes"]["types"]
    types[0]["placement"] = "sky"
    with pytest.raises(ConfigError, match="sky"):
        config_from_dict({"biomes": {"types": types}})


def test_bad_profile_octaves_raises():
    with pytest.raises(ConfigError, match="octaves"):
        config_from_dict({"heightmap": {"profiles": {"marshlands": {"octaves": 0}}}})


def test_bad_profile_noise_type_raises():
    with pytest.raises(ConfigError, match="noise"):
        config_from_dict({"heightmap": {"profiles": {"marshlands": {"noise": "spiky"}}}})


def test_bad_profile_blend_raises():
    with pytest.raises(ConfigError, match="blend_px"):
        config_from_dict({"heightmap": {"profiles": {"marshlands": {"blend_px": 0}}}})


def test_bad_profile_base_raises():
    with pytest.raises(ConfigError, match="base"):
        config_from_dict({"heightmap": {"profiles": {"marshlands": {"base": 1.5}}}})


def test_bad_profile_amplitude_raises():
    with pytest.raises(ConfigError, match="amplitude"):
        config_from_dict({"heightmap": {"profiles": {"marshlands": {"amplitude": -0.1}}}})


def test_missing_profile_raises():
    types = config_to_dict(Config())["biomes"]["types"]
    types[0]["name"] = "dunes"
    with pytest.raises(ConfigError, match="dunes"):
        config_from_dict({"biomes": {"types": types}})


def test_load_yaml_and_cli_override(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("size: 505\nseed: 7\n", encoding="utf-8")
    cfg = load_config(path, {"seed": 9})
    assert cfg.size == 505
    assert cfg.seed == 9


def test_round_trip_dict():
    cfg = Config()
    again = config_from_dict(config_to_dict(cfg))
    assert config_to_dict(again) == config_to_dict(cfg)


def test_spit_defaults():
    cfg = config_from_dict({})
    assert cfg.spit.length_pct[0] <= cfg.spit.length_pct[1]
    assert cfg.spit.bay_pct >= 0
    assert cfg.spit.lagoon_pct > 0
    assert cfg.spit.min_lagoon_pct > 0
    assert cfg.spit.width_pct > 0
    assert 0 <= cfg.spit.width_variation < 1
    assert cfg.spit.strait_pct >= 0
    assert cfg.spit.rise_px > 0
    assert cfg.biomes.types[0].placement == "spit"


def test_spit_placement_is_valid_and_seeds_count_the_other_types():
    # 4 biome types get seeds, so 4 seeds per landmass is enough
    cfg = config_from_dict({"biomes": {"seeds_per_landmass": [4, 6]}})
    assert cfg.biomes.seeds_per_landmass == (4, 6)
    with pytest.raises(ConfigError, match="lo >= 4"):
        config_from_dict({"biomes": {"seeds_per_landmass": [3, 6]}})


def test_bad_spit_values_raise():
    with pytest.raises(ConfigError, match="spit.length_pct"):
        config_from_dict({"spit": {"length_pct": [80, 30]}})
    with pytest.raises(ConfigError, match="spit.lagoon_pct"):
        config_from_dict({"spit": {"lagoon_pct": 0}})
    with pytest.raises(ConfigError, match="spit.width_pct"):
        config_from_dict({"spit": {"width_pct": 0}})
    with pytest.raises(ConfigError, match="spit.width_variation"):
        config_from_dict({"spit": {"width_variation": 1.0}})


def test_load_json_config(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"size": 505, "seed": 7, "spit": {"length_pct": [20, 60]}}', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.size == 505 and cfg.seed == 7
    assert cfg.spit.length_pct == (20.0, 60.0)
