"""Scenario resolution: turn a declarative scenario into explicit numeric schedules.

Every resolved quantity is an explicit array over months 0..N, so the simulator itself
contains no hidden defaults. Missing dataset values are handled explicitly (last
observation carried forward, flagged in ``warnings``) and never replaced with zero.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .config import templates
from .model import CompiledModel, compile_model
from .params import apply_overrides
from .schemas import ALL_VARS, CONTEXT_VARS, STATE_VARS, Scenario


@dataclass
class ResolvedScenario:
    horizon: int
    initial: dict[str, float]
    Q0: float
    flex0: Optional[float]  # None -> equilibrium initialisation
    modes: dict[str, str]
    overrides: dict[str, np.ndarray]
    Z_obs: np.ndarray  # (N+1, 7)
    U: np.ndarray      # (N+1, nu); row 0 unused
    D: np.ndarray      # (N+1, nd)
    warnings: list[str] = field(default_factory=list)
    data_class: str = "SYNTHETIC"
    calendar_start_month: int = 9


def series_from_spec(spec: Optional[dict], default: float, n: int) -> np.ndarray:
    """Expand {'value': x} or {'values': [...]} into an array of length n (months 0..n-1)."""
    out = np.full(n, float(default))
    if not spec:
        return out
    if spec.get("values"):
        vals = list(spec["values"])
        last = float(default)
        for t in range(n):
            if t < len(vals) and vals[t] is not None:
                last = float(vals[t])
            out[t] = last
        return out
    if spec.get("value") is not None:
        out[:] = float(spec["value"])
    return out


def intervention_matrix(interventions: list[dict], keys: list[str], horizon: int) -> np.ndarray:
    """U[t, k] for months t = 0..N. Month t >= start receives intensity·ramp(t); 0 after end."""
    U = np.zeros((horizon + 1, len(keys)))
    idx = {k: i for i, k in enumerate(keys)}
    for iv in interventions:
        if iv["key"] not in idx:
            raise ValueError(f"unknown intervention '{iv['key']}' (valid: {keys})")
        k = idx[iv["key"]]
        start, ramp, end = int(iv.get("start_month", 1)), int(iv.get("ramp_months", 0)), iv.get("end_month")
        for t in range(1, horizon + 1):
            if t < start or (end is not None and t > int(end)):
                continue
            r = 1.0 if ramp <= 0 else min(1.0, (t - start + 1) / ramp)
            U[t, k] += float(iv["intensity"]) * r
    return np.clip(U, 0.0, 1.0)


def scenario_hash(s: dict[str, Any]) -> str:
    keep = {k: v for k, v in s.items() if k not in ("id", "name", "description", "notes", "created_at", "updated_at")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


def baseline_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    t = next(x for x in templates() if x.get("is_baseline"))
    return instantiate_template(cfg, t["id"])


def instantiate_template(cfg: dict[str, Any], template_id: str, lang: str = "en") -> dict[str, Any]:
    t = next((x for x in templates() if x["id"] == template_id), None)
    if t is None:
        raise ValueError(f"unknown template {template_id}")
    init = {v["symbol"]: float(v["initial"]) for v in cfg["variables"]}
    sc = Scenario(
        name=t["labels"].get(lang, t["name"]), description=t["description"].get(lang, ""), template_id=t["id"],
        is_baseline=bool(t.get("is_baseline")), horizon_months=int(cfg["time"]["default_horizon"]),
        initial_state=init, initial_stock={"Q": float(cfg["initial_stock"].get("Q", 0.0))},
        interventions=copy.deepcopy(t["interventions"]),
        external={e["key"]: {"value": float(e["default"])} for e in cfg["external_conditions"]},
    )
    return json.loads(sc.model_dump_json())


def _dataset_series(dataset: dict[str, Any], sym: str) -> list[Optional[float]]:
    return list(dataset.get("variables", {}).get(sym, []))


def resolve(cfg: dict[str, Any], scenario: dict[str, Any], dataset: Optional[dict[str, Any]] = None) -> tuple[ResolvedScenario, dict[str, Any]]:
    """Validate a scenario and expand it. Returns (resolved, effective_config)."""
    sc = Scenario.model_validate(scenario)
    warnings: list[str] = []
    N = sc.horizon_months
    max_h = int(cfg["time"].get("max_horizon", 60))
    if N > max_h:
        raise ValueError(f"horizon {N} exceeds supported maximum {max_h}")
    eff_cfg = apply_overrides(cfg, sc.parameter_overrides) if sc.parameter_overrides else cfg

    initial = {v["symbol"]: float(v["initial"]) for v in cfg["variables"]}
    initial.update({k: float(v) for k, v in sc.initial_state.items()})
    Q0 = float(sc.initial_stock.get("Q", cfg["initial_stock"].get("Q", 0.0)))
    flex0 = sc.initial_stock.get("flex")
    if flex0 is None and cfg["initial_stock"].get("flex") not in (None, "equilibrium"):
        flex0 = float(cfg["initial_stock"]["flex"])

    data_class = "SYNTHETIC"
    Z_obs = np.zeros((N + 1, len(CONTEXT_VARS)))
    for j, sym in enumerate(CONTEXT_VARS):
        Z_obs[:, j] = initial[sym]

    if dataset is not None:
        data_class = dataset.get("data_class", "UNKNOWN")
        n_rows = len(dataset.get("periods", []))
        if n_rows == 0:
            raise ValueError("selected dataset contains no periods")
        if sc.dataset_anchor == "latest":
            for sym in ALL_VARS:
                ser = _dataset_series(dataset, sym)
                vals = [v for v in ser if v is not None]
                if vals:
                    initial[sym] = float(vals[-1])
                else:
                    warnings.append(f"dataset has no observations for {sym}; scenario initial value {initial[sym]:.3f} used")
            for j, sym in enumerate(CONTEXT_VARS):
                Z_obs[:, j] = initial[sym]
            q = [v for v in dataset.get("flows", {}).get("Q", []) if v is not None]
            if q:
                Q0 = float(q[-1])
        else:  # replay observed context from the first period
            for sym in ALL_VARS:
                ser = _dataset_series(dataset, sym)
                if ser and ser[0] is not None:
                    initial[sym] = float(ser[0])
                elif ser:
                    warnings.append(f"first dataset value of {sym} is missing; scenario initial value used")
            q = dataset.get("flows", {}).get("Q", [])
            if q and q[0] is not None:
                Q0 = float(q[0])
            for j, sym in enumerate(CONTEXT_VARS):
                ser = _dataset_series(dataset, sym)
                last = initial[sym]
                n_locf = 0
                for t in range(N + 1):
                    if t < len(ser) and ser[t] is not None:
                        last = float(ser[t])
                    elif t < len(ser):
                        n_locf += 1
                    Z_obs[t, j] = last
                if n_locf:
                    warnings.append(f"{sym}: {n_locf} missing observation(s) filled by last observation carried forward")
            if N + 1 > n_rows:
                warnings.append(f"horizon extends {N + 1 - n_rows} month(s) beyond the dataset; observed context held at last value")

    # Explicit context schedules override constant/dataset paths
    for sym, spec in sc.context_schedule.items():
        Z_obs[:, CONTEXT_VARS.index(sym)] = series_from_spec(spec.model_dump(), initial[sym], N + 1)

    modes = {sym: sc.variable_modes.get(sym, "model") for sym in ALL_VARS}
    overrides: dict[str, np.ndarray] = {}
    for sym, mode in modes.items():
        if mode == "manual":
            spec = sc.overrides.get(sym)
            overrides[sym] = series_from_spec(spec.model_dump() if spec else None, initial[sym], N + 1)
            if sym in CONTEXT_VARS:
                Z_obs[:, CONTEXT_VARS.index(sym)] = overrides[sym]
            warnings.append(f"manual override active for {sym}")

    keys = [i["key"] for i in cfg["interventions"]]
    U = intervention_matrix([iv.model_dump() for iv in sc.interventions], keys, N)
    ext_keys = [e["key"] for e in cfg["external_conditions"]]
    D = np.zeros((N + 1, len(ext_keys)))
    for i, e in enumerate(cfg["external_conditions"]):
        spec = sc.external.get(e["key"])
        D[:, i] = series_from_spec(spec.model_dump() if spec else None, float(e["default"]), N + 1)
    unknown_ext = set(sc.external) - set(ext_keys)
    if unknown_ext:
        raise ValueError(f"unknown external conditions {sorted(unknown_ext)}")

    rs = ResolvedScenario(
        horizon=N, initial=initial, Q0=Q0, flex0=None if flex0 is None else float(flex0), modes=modes,
        overrides=overrides, Z_obs=np.clip(Z_obs, 0, 1), U=U, D=D, warnings=warnings, data_class=data_class,
        calendar_start_month=int(cfg["time"].get("calendar_start_month", 9)),
    )
    return rs, eff_cfg


def comparability(baseline: dict[str, Any], other: dict[str, Any]) -> list[str]:
    """List every difference other than intervention inputs (Section 14: identical conditions)."""
    diffs: list[str] = []
    for key in ("horizon_months", "initial_state", "initial_stock", "external", "parameter_overrides",
                "context_schedule", "variable_modes", "overrides", "dataset_id", "dataset_anchor"):
        a, b = baseline.get(key), other.get(key)
        if json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str):
            if isinstance(a, dict) and isinstance(b, dict):
                ks = sorted(k for k in set(a) | set(b) if json.dumps(a.get(k), sort_keys=True) != json.dumps(b.get(k), sort_keys=True))
                diffs.append(f"{key}: {', '.join(ks)}")
            else:
                diffs.append(key)
    return diffs


def compiled_for(cfg: dict[str, Any], scenario: dict[str, Any], dataset: Optional[dict[str, Any]] = None) -> tuple[CompiledModel, ResolvedScenario]:
    rs, eff = resolve(cfg, scenario, dataset)
    return compile_model(eff), rs


__all__ = ["ResolvedScenario", "resolve", "compiled_for", "instantiate_template", "baseline_from_config",
           "intervention_matrix", "series_from_spec", "comparability", "scenario_hash", "STATE_VARS"]
