"""Shared helpers for the outer analysis layers (uncertainty, sensitivity, calibration).

Each individual model evaluation is the same deterministic simulator; analysis layers
only vary parameter values around it.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .indices import domain_indices
from .model import CompiledModel
from .scenarios import ResolvedScenario
from .schemas import ALL_VARS
from .simulator import run

INDEX_KEYS = ["TOTAL", "ENV", "SOC", "ORG", "SUP", "MIN_DOMAIN"]
FLOW_KEYS = ["Q", "I", "C_flow", "mu", "Qp"]
OUTPUT_KEYS = INDEX_KEYS + FLOW_KEYS + list(ALL_VARS)
MAX_RUNS = 40000


def evaluate(m: CompiledModel, rs: ResolvedScenario, keys: list[str]) -> dict[str, np.ndarray]:
    raw = run(m, rs, record_targets=False)
    idx = domain_indices(raw["V"], m)
    out: dict[str, np.ndarray] = {}
    for k in keys:
        if k in idx:
            out[k] = idx[k]
        elif k in FLOW_KEYS:
            out[k] = raw[k]
        elif k in ALL_VARS:
            out[k] = raw["V"][:, ALL_VARS.index(k)]
        else:
            raise ValueError(f"unknown output '{k}' (valid: {OUTPUT_KEYS})")
    return out


def check_outputs(keys: list[str]) -> None:
    bad = [k for k in keys if k not in OUTPUT_KEYS]
    if bad:
        raise ValueError(f"unknown outputs {bad}; valid outputs: {OUTPUT_KEYS}")


def guard_runs(n_runs: int, limit: Optional[int] = None) -> None:
    lim = limit or MAX_RUNS
    if n_runs > lim:
        raise ValueError(f"requested {n_runs} model evaluations exceeds the safeguard of {lim}; reduce the sample count")


def nan_to_none(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: nan_to_none(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nan_to_none(v) for v in x]
    if isinstance(x, np.ndarray):
        return nan_to_none(x.tolist())
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x
