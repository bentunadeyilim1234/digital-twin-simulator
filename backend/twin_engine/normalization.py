"""Normalisation engine.

Positive direction:  z = clip((x - L) / (U - L), 0, 1)
Negative direction:  z = clip((U - x) / (U - L), 0, 1)

Reference bounds (L, U) come from configuration and are NEVER re-estimated from the
data being normalised, so baseline and intervention scenarios share one scale.
Missing observations stay missing (NaN / None) and are never converted to zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np


@dataclass(frozen=True)
class NormSpec:
    lower: float
    upper: float
    direction: str = "positive"  # "positive" | "negative"

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lower) and math.isfinite(self.upper)):
            raise ValueError("reference bounds must be finite")
        if self.upper <= self.lower:
            raise ValueError(f"reference bounds require lower < upper (got {self.lower}, {self.upper})")
        if self.direction not in ("positive", "negative"):
            raise ValueError("direction must be 'positive' or 'negative'")


def _is_missing(x: object) -> bool:
    if x is None:
        return True
    try:
        return math.isnan(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True


def normalize(x: Optional[float], spec: NormSpec) -> float:
    """Normalise a single raw value. Returns NaN for missing input (never 0)."""
    if _is_missing(x):
        return float("nan")
    x = float(x)  # type: ignore[arg-type]
    span = spec.upper - spec.lower
    z = (x - spec.lower) / span if spec.direction == "positive" else (spec.upper - x) / span
    return float(min(1.0, max(0.0, z)))


def was_clipped(x: Optional[float], spec: NormSpec) -> bool:
    if _is_missing(x):
        return False
    return not (spec.lower <= float(x) <= spec.upper)  # type: ignore[arg-type]


def denormalize(z: Optional[float], spec: NormSpec) -> float:
    if _is_missing(z):
        return float("nan")
    z = float(z)  # type: ignore[arg-type]
    span = spec.upper - spec.lower
    return spec.lower + z * span if spec.direction == "positive" else spec.upper - z * span


def normalize_series(values: Iterable[Optional[float]], spec: NormSpec) -> np.ndarray:
    arr = np.array([float("nan") if _is_missing(v) else float(v) for v in values], dtype=float)
    span = spec.upper - spec.lower
    z = (arr - spec.lower) / span if spec.direction == "positive" else (spec.upper - arr) / span
    return np.clip(z, 0.0, 1.0)  # NaN propagates through clip unchanged


def spec_for_variable(var: dict) -> NormSpec:
    m = var["measurement"]
    return NormSpec(float(m["lower"]), float(m["upper"]), m["direction"])


def to_json_list(arr: np.ndarray) -> list[Optional[float]]:
    """Convert to a JSON-safe list, mapping NaN/inf to None."""
    return [None if not np.isfinite(v) else float(v) for v in np.asarray(arr, dtype=float).ravel()]
