"""Small, removable wall-clock profiler for one synchronous analysis request."""
from __future__ import annotations

import logging
import os
from time import perf_counter
from typing import Any


logger = logging.getLogger("uvicorn.error")


class AnalysisProfile:
    def __init__(self) -> None:
        self.started = perf_counter()
        self.stages: list[tuple[str, float, int]] = []
        self.metadata: dict[str, Any] = {"os.cpu_count": os.cpu_count()}

    def log_start(self) -> None:
        logger.info(
            "DEEPTRACE PROFILE START os.cpu_count=%s torch=not-imported-in-API-process; "
            "runner thread counts will appear in the final summary",
            self.metadata["os.cpu_count"],
        )

    def add(self, name: str, elapsed: float, *, depth: int = 0) -> None:
        self.stages.append((name, elapsed, depth))

    def add_runner(self, detector: str, elapsed: float, payload: dict[str, Any] | None) -> None:
        self.add(detector, elapsed)
        if not payload:
            return
        for name, seconds in payload.get("profile", {}).items():
            self.add(f"{detector}: {name}", float(seconds), depth=1)
        for key, value in payload.get("workload", {}).items():
            self.metadata[f"{detector}.{key}"] = value

    def log(self) -> None:
        width = max([len(name) + depth * 2 for name, _, depth in self.stages] + [5])
        lines = ["DEEPTRACE PROFILE", "-" * (width + 13)]
        for name, seconds, depth in self.stages:
            label = f"{'  ' * depth}{name}"
            lines.append(f"{label:<{width}}  {seconds:9.3f} s")
        lines.extend([
            "-" * (width + 13),
            f"{'TOTAL':<{width}}  {perf_counter() - self.started:9.3f} s",
            "workload: " + ", ".join(f"{key}={value}" for key, value in self.metadata.items()),
            "Indented detector stages are children of detector wall time and are not additive to TOTAL.",
        ])
        logger.info("\n".join(lines))
