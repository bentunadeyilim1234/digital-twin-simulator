"""Global and local sensitivity analysis (Section 12B).

* Morris elementary-effects screening (Morris, 1991; Campolongo et al., 2007) via SALib.
* Sobol variance decomposition — first-order S1, total-order ST and second-order S2
  (Sobol', 2001; Saltelli sampling) via SALib.
* One-at-a-time tornado diagram (deterministic low/high swings).

Run counts are bounded by explicit safeguards; defaults are sized for an ordinary laptop.
"""

from __future__ import annotations

import importlib.util
import math
from typing import Any, Optional

import numpy as np

from .analysis_common import check_outputs, evaluate, guard_runs, nan_to_none
from .model import compile_model
from .params import get_range, get_value, uncertain_parameters
from .scenarios import resolve

SALIB_AVAILABLE = importlib.util.find_spec("SALib") is not None
DEFAULT_SA_OUTPUTS = ["TOTAL", "SOC", "ORG", "SUP", "Q"]


def _problem(cfg: dict[str, Any], param_ids: list[str], ranges: Optional[dict[str, list[float]]]) -> dict[str, Any]:
    bounds = []
    for pid in param_ids:
        r = (ranges or {}).get(pid) or get_range(cfg, pid)
        if r is None or r[1] <= r[0]:
            raise ValueError(f"parameter {pid} needs a non-degenerate range")
        bounds.append([float(r[0]), float(r[1])])
    return {"num_vars": len(param_ids), "names": list(param_ids), "bounds": bounds}


def _evaluator(cfg: dict[str, Any], scenario: dict[str, Any], outputs: list[str], month: Optional[int]):
    rs, eff = resolve(cfg, scenario)
    base = compile_model(eff)
    t = rs.horizon if month is None else int(month)
    if not (0 <= t <= rs.horizon):
        raise ValueError(f"evaluation month must lie in [0, {rs.horizon}]")

    def f(names: list[str], X: np.ndarray) -> np.ndarray:
        Y = np.zeros((X.shape[0], len(outputs)))
        for i in range(X.shape[0]):
            res = evaluate(base.with_params(dict(zip(names, X[i]))), rs, outputs)
            Y[i] = [res[k][t] for k in outputs]
        return Y
    return f, base, t


def run_sensitivity(
    cfg: dict[str, Any],
    scenario: dict[str, Any],
    method: str = "morris",
    param_ids: Optional[list[str]] = None,
    outputs: Optional[list[str]] = None,
    month: Optional[int] = None,
    n: Optional[int] = None,
    seed: int = 3,
    ranges: Optional[dict[str, list[float]]] = None,
    second_order: bool = False,
    max_runs: int = 20000,
) -> dict[str, Any]:
    outputs = outputs or DEFAULT_SA_OUTPUTS
    check_outputs(outputs)
    param_ids = param_ids or [p["id"] for p in uncertain_parameters(cfg)]
    if len(param_ids) < 2:
        raise ValueError("select at least two parameters")
    problem = _problem(cfg, param_ids, ranges)
    f, base, t = _evaluator(cfg, scenario, outputs, month)
    D = len(param_ids)
    nominal = f(param_ids, np.array([[get_value(cfg, p) for p in param_ids]]))[0]
    common = {"method": method, "parameters": param_ids, "outputs": outputs, "month": t, "seed": seed,
              "nominal_outputs": dict(zip(outputs, nominal.tolist())),
              "scenario_name": scenario.get("name")}

    if method == "tornado":
        guard_runs(2 * D, max_runs)
        rows = []
        for j, pid in enumerate(param_ids):
            lo, hi = problem["bounds"][j]
            nom = [get_value(cfg, p) for p in param_ids]
            xl, xh = list(nom), list(nom)
            xl[j], xh[j] = lo, hi
            yl, yh = f(param_ids, np.array([xl, xh]))
            rows.append({"id": pid, "low": lo, "high": hi, "nominal_value": nom[j],
                         "output_low": dict(zip(outputs, yl.tolist())), "output_high": dict(zip(outputs, yh.tolist())),
                         "swing": dict(zip(outputs, np.abs(yh - yl).tolist()))})
        rows.sort(key=lambda r: -r["swing"][outputs[0]])
        return nan_to_none({**common, "n_runs": 2 * D + 1, "tornado": rows})

    if not SALIB_AVAILABLE:
        raise RuntimeError("SALib is not installed; Morris and Sobol analyses are unavailable (tornado still works)")

    if method == "morris":
        from SALib.analyze import morris as morris_analyze
        from SALib.sample import morris as morris_sample
        r = int(n or 20)
        if not (4 <= r <= 200):
            raise ValueError("Morris trajectories must lie in [4, 200]")
        guard_runs(r * (D + 1), max_runs)
        X = morris_sample.sample(problem, N=r, num_levels=4, seed=seed)
        Y = f(param_ids, X)
        res_out = {}
        heat = np.zeros((D, len(outputs)))
        for k, key in enumerate(outputs):
            Si = morris_analyze.analyze(problem, X, Y[:, k], num_levels=4, seed=seed, print_to_console=False)
            mu_star = np.asarray(Si["mu_star"], dtype=float)
            res_out[key] = [{"id": pid, "mu": float(Si["mu"][j]), "mu_star": float(mu_star[j]),
                             "sigma": float(Si["sigma"][j]), "mu_star_conf": float(Si["mu_star_conf"][j])}
                            for j, pid in enumerate(param_ids)]
            res_out[key].sort(key=lambda x: -x["mu_star"])
            heat[:, k] = mu_star / mu_star.max() if mu_star.max() > 0 else 0
        return nan_to_none({**common, "n_runs": int(X.shape[0]), "trajectories": r, "levels": 4,
                            "indices": res_out, "heatmap": {"rows": param_ids, "cols": outputs, "values": heat,
                                                            "metric": "mu_star normalised per output"}})

    if method == "sobol":
        from SALib.analyze import sobol as sobol_analyze
        from SALib.sample import sobol as sobol_sample
        base_n = int(n or 128)
        if base_n < 16 or (base_n & (base_n - 1)) != 0:
            raise ValueError("Sobol base sample size must be a power of two >= 16")
        runs = base_n * (2 * D + 2 if second_order else D + 2)
        guard_runs(runs, max_runs)
        X = sobol_sample.sample(problem, base_n, calc_second_order=second_order, seed=seed)
        Y = f(param_ids, X)
        res_out = {}
        heat = np.zeros((D, len(outputs)))
        interactions = None
        for k, key in enumerate(outputs):
            if np.ptp(Y[:, k]) < 1e-14:
                res_out[key] = [{"id": pid, "S1": 0.0, "S1_conf": 0.0, "ST": 0.0, "ST_conf": 0.0} for pid in param_ids]
                continue
            Si = sobol_analyze.analyze(problem, Y[:, k], calc_second_order=second_order, seed=seed, print_to_console=False)
            res_out[key] = [{"id": pid, "S1": float(Si["S1"][j]), "S1_conf": float(Si["S1_conf"][j]),
                             "ST": float(Si["ST"][j]), "ST_conf": float(Si["ST_conf"][j])} for j, pid in enumerate(param_ids)]
            res_out[key].sort(key=lambda x: -x["ST"])
            heat[:, k] = np.clip(np.asarray(Si["ST"], dtype=float), 0, None)
            if second_order and k == 0:
                S2 = np.asarray(Si["S2"], dtype=float)
                interactions = {"output": key, "rows": param_ids, "values": np.where(np.isfinite(S2), S2, np.nan)}
        return nan_to_none({**common, "n_runs": int(X.shape[0]), "base_samples": base_n, "second_order": second_order,
                            "indices": res_out, "interactions": interactions,
                            "heatmap": {"rows": param_ids, "cols": outputs, "values": heat, "metric": "total-order ST"},
                            "note": "Sobol estimates with small base samples have wide confidence intervals; inspect S1_conf/ST_conf."})

    raise ValueError("method must be 'morris', 'sobol' or 'tornado'")


def estimate_runs(method: str, n_params: int, n: Optional[int] = None, second_order: bool = False) -> int:
    if method == "tornado":
        return 2 * n_params + 1
    if method == "morris":
        return int(n or 20) * (n_params + 1)
    base_n = int(n or 128)
    return base_n * (2 * n_params + 2 if second_order else n_params + 2)


__all__ = ["run_sensitivity", "estimate_runs", "SALIB_AVAILABLE", "math"]
