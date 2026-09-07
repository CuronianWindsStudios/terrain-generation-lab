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
