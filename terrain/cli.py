"""Command line interface."""
from __future__ import annotations

import argparse
import sys
import time

from terrain.config import ConfigError, GenerationError, load_config
from terrain.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="terrain", description="Generate a circular world for Unreal Engine.")
    p.add_argument("--config", help="YAML file with parameters")
    p.add_argument("--seed", type=int, help="random seed (default 42)")
    p.add_argument("--size", type=int, help="image width and height in pixels (default 1009)")
    p.add_argument("--diameter", type=float, help="circle diameter as a percentage of the width (default 90)")
    p.add_argument("--out", default="out", help="output folder (default out)")
    p.add_argument("--debug", action="store_true", help="write sub-step images and walkthrough.md")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.size is not None:
        overrides["size"] = args.size
    if args.diameter is not None:
        overrides["circle"] = {"diameter_pct": args.diameter}
    try:
        cfg = load_config(args.config, overrides)
        start = time.perf_counter()
        result = run_pipeline(cfg, args.out, debug=args.debug)
    except (ConfigError, GenerationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    seconds = time.perf_counter() - start
    print(f"Wrote {len(result.files)} files to {args.out} in {seconds:.1f} s.")
    if result.walkthrough is not None:
        print(f"Walkthrough: {result.walkthrough}")
    return 0
