import hashlib
from pathlib import Path

from terrain.cli import main
from terrain.config import config_from_dict
from terrain.pipeline import run_pipeline


def _digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_same_seed_same_bytes(tmp_path):
    cfg = config_from_dict({"size": 253, "seed": 11})
    run_pipeline(cfg, tmp_path / "a", debug=True)
    run_pipeline(cfg, tmp_path / "b", debug=True)
    a, b = _digest(tmp_path / "a"), _digest(tmp_path / "b")
    assert a == b
    assert len(a) > 40


def test_debug_writes_steps_and_walkthrough(tmp_path):
    cfg = config_from_dict({"size": 253})
    res = run_pipeline(cfg, tmp_path, debug=True)
    steps = list((tmp_path / "steps").glob("*.png"))
    assert len(steps) >= 20
    assert res.walkthrough == tmp_path / "walkthrough.md"
    text = res.walkthrough.read_text(encoding="utf-8")
    assert "## Step 01a" in text and "## Step 04f" in text


def test_no_debug_writes_no_steps(tmp_path):
    cfg = config_from_dict({"size": 253})
    res = run_pipeline(cfg, tmp_path, debug=False)
    assert not (tmp_path / "steps").exists()
    assert res.walkthrough is None
    assert (tmp_path / "unreal" / "heightmap.png").exists()


def test_cli_runs_and_rejects_bad_size(tmp_path, capsys):
    assert main(["--size", "253", "--seed", "3", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "unreal" / "heightmap.png").exists()
    assert main(["--size", "1000", "--out", str(tmp_path / "p")]) == 1
    assert "127, 253, 505" in capsys.readouterr().err
