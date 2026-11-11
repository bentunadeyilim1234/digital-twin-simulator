"""Parameter-uncertainty propagation (Section 12A).

Each sample is ONE deterministic simulation. The outer Latin-hypercube sampling layer
represents uncertainty about parameter values only. All compared scenarios use the
same parameter samples (common random numbers), so paired differences to the baseline
isolate the scenario effect under each plausible parameter set.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.stats import qmc, spearmanr

from .analysis_common import OUTPUT_KEYS, check_outputs, evaluate, guard_runs, nan_to_none
from .model import compile_model
from .params import get_range, get_value, uncertain_parameters
from .scenarios import resolve

DEFAULT_OUTPUTS = ["TOTAL", "ENV", "SOC", "ORG", "SUP", "MIN_DOMAIN", "Q", "T", "L", "P"]


def sample_parameters(cfg: dict[str, Any], param_ids: list[str], n: int, seed: int,
                      ranges: Optional[dict[str, list[float]]] = None) -> tuple[np.ndarray, list[tuple[float, float]]]:
    bounds = []
    for pid in param_ids:
        r = (ranges or {}).get(pid) or get_range(cfg, pid)
        if r is None:
            raise ValueError(f"parameter {pid} has no uncertainty range; define one before sampling")
        lo, hi = float(r[0]), float(r[1])
        if hi < lo:
            raise ValueError(f"range for {pid} is inverted")
        bounds.append((lo, hi))
    sampler = qmc.LatinHypercube(d=len(param_ids), seed=seed)
    u = sampler.random(n)
    lo = np.array([b[0] for b in bounds]); hi = np.array([b[1] for b in bounds])
    return lo + u * (hi - lo), bounds


def run_uncertainty(
    cfg: dict[str, Any],
    scenarios: list[dict[str, Any]],
    param_ids: Optional[list[str]] = None,
    n_samples: int = 200,
    seed: int = 7,
    outputs: Optional[list[str]] = None,
    ranges: Optional[dict[str, list[float]]] = None,
    baseline_index: int = 0,
    datasets: Optional[list[Optional[dict]]] = None,
) -> dict[str, Any]:
    if not scenarios:
        raise ValueError("at least one scenario is required")
    if not (10 <= n_samples <= 2000):
        raise ValueError("n_samples must lie between 10 and 2000")
    outputs = outputs or DEFAULT_OUTPUTS
    check_outputs(outputs)
    param_ids = param_ids or [p["id"] for p in uncertain_parameters(cfg)]
    if not param_ids:
        raise ValueError("no uncertain parameters selected")
    guard_runs(n_samples * len(scenarios))
    X, bounds = sample_parameters(cfg, param_ids, n_samples, seed, ranges)

    per_scenario = []
    stores: list[dict[str, np.ndarray]] = []
    for si, sc in enumerate(scenarios):
        ds = datasets[si] if datasets else None
        rs, eff = resolve(cfg, sc, ds)
        base = compile_model(eff)
        missing = [p for p in param_ids if p not in base.param_slots]
        if missing:
            raise ValueError(f"parameters {missing} are not active (disabled relationships?)")
        nominal = evaluate(base, rs, outputs)
        store = {k: np.zeros((n_samples, rs.horizon + 1)) for k in outputs}
        for i in range(n_samples):
            res = evaluate(base.with_params(dict(zip(param_ids, X[i]))), rs, outputs)
            for k in outputs:
                store[k][i] = res[k]
        stores.append(store)
        bands = {}
        for k in outputs:
            p5, p50, p95 = np.nanpercentile(store[k], [5, 50, 95], axis=0)
            bands[k] = {"p5": p5, "p50": p50, "p95": p95, "nominal": nominal[k], "mean": np.nanmean(store[k], axis=0)}
        per_scenario.append({"scenario_id": sc.get("id"), "scenario_name": sc.get("name"), "bands": bands})

    # Paired differences to the baseline under common parameter samples
    if len(scenarios) > 1:
        b = stores[baseline_index]
        for si, store in enumerate(stores):
            if si == baseline_index:
                continue
            diff = {}
            for k in outputs:
                d = store[k] - b[k]
                p5, p50, p95 = np.nanpercentile(d, [5, 50, 95], axis=0)
                diff[k] = {"p5": p5, "p50": p50, "p95": p95,
                           "prob_positive_end": float(np.mean(d[:, -1] > 0))}
            per_scenario[si]["difference_to_baseline"] = diff

    # Parameter summaries: rank correlation with end-of-horizon TOTAL of the first scenario
    target_key = "TOTAL" if "TOTAL" in outputs else outputs[0]
    y_end = stores[0][target_key][:, -1]
    psum = []
    for j, pid in enumerate(param_ids):
        rho = spearmanr(X[:, j], y_end).statistic if np.ptp(y_end) > 0 else 0.0
        psum.append({"id": pid, "nominal": get_value(cfg, pid), "range": list(bounds[j]),
                     "sample_mean": float(X[:, j].mean()), "sample_sd": float(X[:, j].std(ddof=1)),
                     f"spearman_with_{target_key}_end": float(rho) if np.isfinite(rho) else None})
    psum.sort(key=lambda r: -abs(r.get(f"spearman_with_{target_key}_end") or 0))
    return nan_to_none({
        "method": "Latin hypercube sampling over parameter ranges; deterministic simulation per sample",
        "n_samples": n_samples, "seed": seed, "parameters": param_ids, "outputs": outputs,
        "horizon": len(per_scenario[0]["bands"][outputs[0]]["p50"]) - 1,
        "scenarios": per_scenario, "parameter_summary": psum,
        "baseline_index": baseline_index,
        "note": "Bands are P5-P95 across parameter samples. They express parameter uncertainty under the model structure, not forecast error or real-world probability.",
    })


__all__ = ["run_uncertainty", "sample_parameters", "OUTPUT_KEYS"]
