"""StepRecorder: writes one image per sub-step and a walkthrough document."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from terrain.imageio import save_gray8, to_uint8


@dataclass
class StepRecord:
    step_id: str
    title: str
    filename: str | None
    description: str
    params: dict = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class StepRecorder:
    def __init__(self, out_dir: str | Path | None, enabled: bool):
        self.enabled = bool(enabled) and out_dir is not None
        self.out_dir = Path(out_dir) if out_dir is not None else None
        self.records: list[StepRecord] = []
        if self.enabled:
            (self.out_dir / "steps").mkdir(parents=True, exist_ok=True)

    def step(self, step_id: str, title: str, array: np.ndarray, description: str,
             params: dict | None = None) -> None:
        if not self.enabled:
            return
        filename = f"steps/{step_id}_{_slug(title)}.png"
        save_gray8(self.out_dir / filename, to_uint8(np.asarray(array)))
        self.records.append(StepRecord(step_id, title, filename, description, dict(params or {})))

    def note(self, step_id: str, title: str, description: str, params: dict | None = None) -> None:
        if not self.enabled:
            return
        self.records.append(StepRecord(step_id, title, None, description, dict(params or {})))

    def write_walkthrough(self) -> Path | None:
        if not self.enabled:
            return None
        lines = [
            "# Walkthrough",
            "",
            "This document shows each step of the generator.",
            "Each step shows the image it makes and the parameters that control it.",
            "",
        ]
        for r in self.records:
            lines += [f"## Step {r.step_id}: {r.title}", "", r.description, ""]
            if r.params:
                lines += ["| Parameter | Value |", "|---|---|"]
                lines += [f"| {k} | {v} |" for k, v in r.params.items()]
                lines.append("")
            if r.filename:
                lines += [f"![Step {r.step_id}]({r.filename})", ""]
        path = self.out_dir / "walkthrough.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
