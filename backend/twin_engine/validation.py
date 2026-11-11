"""Verification & validation (Section 13; cf. Barlas, 1996).

* Mathematical verification — automated structural and behavioural checks of the engine.
* Conceptual validation — evidence status of every modelled relationship.
* Historical validation — calibration / holdout split with MAE, RMSE, residuals and trends.
* Intervention validation — interrupted time series on observed aggregates versus the
  model-implied change. A simulated improvement does NOT prove a real causal effect.
* Validation envelope and exportable report.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from .analysis_common import nan_to_none
from .calibration import _metrics, _observed, calibrate_lsq, default_targets, replay_setup
from .config import ENGINE_VERSION, config_hash, references, validate_config
from .graph import declared_loops
from .model import compile_model, linear_stability
from .params import apply_overrides, get_bounds, list_parameters
from .scenarios import comparability, instantiate_template, resolve
from .schemas import ALL_VARS
from .simulator import run, simulate

FORBIDDEN_KEYS = ("student_id", "name", "ethnicity", "religion", "diagnosis", "risk_score", "dangerousness", "attack_probability")


def _check(cid: str, name: str, fn) -> dict[str, Any]:
    try:
        ok, detail = fn()
        return {"id": cid, "name": name, "status": "pass" if ok else "fail", "detail": detail}
    except Exception as exc:  # report, never crash the suite
        return {"id": cid, "name": name, "status": "fail", "detail": f"error: {exc}"}


def verification_suite(cfg: dict[str, Any]) -> dict[str, Any]:
    checks = []

    def schema():
        validate_config(copy.deepcopy(cfg))
        return True, "configuration validates against the schema (dimensions, references, bounds)"
    checks.append(_check("V01", "Configuration schema and references", schema))

    def dims():
        m = compile_model(cfg)
        return True, f"A{m.A.shape} Γ{m.Gamma.shape} Π{m.Pi.shape} B{m.B.shape} G{m.G.shape} Λ{m.Lam.shape} Ω{m.Omega.shape}"
    checks.append(_check("V02", "Matrix dimensions", dims))

    def determinism():
        sc = instantiate_template(cfg, "S4")
        a, b = simulate(cfg, sc), simulate(cfg, sc)
        same = a["variables"] == b["variables"] and a["flows"] == b["flows"]
        return same, "two runs of S4 are bit-identical" if same else "outputs differ between identical runs"
    checks.append(_check("V03", "Deterministic reproducibility", determinism))

    def bounds():
        sc = instantiate_template(cfg, "S4")
        sc["horizon_months"] = 36
        sc["interventions"] = [{"key": i["key"], "intensity": 1.0, "start_month": 1, "ramp_months": 0} for i in cfg["interventions"]]
        r = simulate(cfg, sc)
        lo, hi = r["diagnostics"]["min_state"], r["diagnostics"]["max_state"]
        return (lo >= 0 and hi <= 1), f"all 16 variables within [{lo:.3f}, {hi:.3f}] under maximal interventions for 36 months"
    checks.append(_check("V04", "State boundaries [0,1]", bounds))

    def mass():
        worst = 0.0
        for tid in ("S0", "S1", "S2", "S3", "S4"):
            worst = max(worst, simulate(cfg, instantiate_template(cfg, tid))["diagnostics"]["mass_balance_max_error"])
        return worst < 1e-9, f"max |Q(t)-Q(t-1)-I(t)+C_flow(t)| = {worst:.2e} across templates"
    checks.append(_check("V05", "Stock-flow mass balance", mass))

    def zero_inflow():
        r = simulate(apply_overrides(cfg, {"flow.I_base": 0.0}), instantiate_template(cfg, "S0"))
        I = [x for x in r["flows"]["I"] if x is not None]
        Q = r["flows"]["Q"]
        ok = all(x == 0 for x in I) and all(Q[t] <= Q[t - 1] + 1e-12 for t in range(1, len(Q)))
        return ok, "zero base demand produces no requests and a non-increasing backlog"
    checks.append(_check("V06", "Zero inflow creates no requests", zero_inflow))

    def capacity():
        worst = 0.0
        for tid in ("S0", "S1"):
            r = simulate(cfg, instantiate_template(cfg, tid))
            f = r["flows"]
            for t in range(1, r["horizon"] + 1):
                worst = max(worst, f["C_flow"][t] - min(f["Q"][t - 1] + f["I"][t], f["mu"][t]))
        return abs(worst) < 1e-9, "C_flow(t) = min(Q(t-1)+I(t), μ(t)) holds every month"
    checks.append(_check("V07", "Capacity constraint", capacity))

    def stability():
        st = linear_stability(compile_model(cfg))
        return st["stable"], f"spectral radius of linearised [X, Δz] map = {st['spectral_radius']:.4f}"
    checks.append(_check("V08", "Linear stability of transition", stability))

    def full_map():
        from .simulator import full_map_jacobian
        rs, eff = resolve(cfg, instantiate_template(cfg, "S0"))
        j = full_map_jacobian(compile_model(eff), rs)
        return j["stable"], (f"spectral radius of the full nonlinear one-step map at the baseline state = {j['spectral_radius']:.4f} "
                             f"(fixed-point residual {j['fixed_point_residual']:.1e})")
    checks.append(_check("V09", "Local asymptotic stability (full nonlinear map)", full_map))

    def bounded():
        sc = instantiate_template(cfg, "S0")
        sc["horizon_months"] = 60
        ref = simulate(cfg, sc)
        p = copy.deepcopy(sc)
        for s in ("E", "C", "T", "A", "K", "S", "P"):
            p["initial_state"][s] = min(1.0, p["initial_state"][s] + 0.05)
        pert = simulate(cfg, p)
        dev = [max(abs(pert["variables"][s][t] - ref["variables"][s][t]) for s in ALL_VARS) for t in range(61)]
        settle = max(dev[-12:]) - min(dev[-12:])
        ok = max(dev) <= 3 * dev[0] and settle < 1e-3
        return ok, (f"+0.05 initial perturbation: max deviation {max(dev):.3f}, settled (last-year drift {settle:.1e}). "
                    "The perturbed run settles at its own equilibrium because context responses are anchored to each run's X(0).")
    checks.append(_check("V13", "Bounded, settling response to perturbation", bounded))

    def comparable():
        base = instantiate_template(cfg, "S0")
        diffs = {tid: comparability(base, instantiate_template(cfg, tid)) for tid in ("S1", "S2", "S3", "S4")}
        bad = {k: v for k, v in diffs.items() if v}
        return not bad, "templates differ from the baseline only in interventions" if not bad else f"differences: {bad}"
    checks.append(_check("V10", "Reproducible scenario comparison", comparable))

    def param_bounds():
        issues = []
        for p in list_parameters(cfg):
            lo, hi = p.get("min", 0), p.get("max", 5)
            if p.get("range"):
                if p["range"][0] < lo - 1e-12 or p["range"][1] > hi + 1e-12:
                    issues.append(p["id"])
        return not issues, "all uncertainty ranges lie within hard bounds" if not issues else f"ranges outside bounds: {issues}"
    checks.append(_check("V11", "Parameter bounds", param_bounds))

    def privacy():
        blob = str([v["key"] for v in cfg["variables"]]).lower()
        hits = [k for k in FORBIDDEN_KEYS if k in blob]
        return not hits, "no person-level, identifying or dangerousness fields exist in the model" if not hits else f"found {hits}"
    checks.append(_check("V12", "No individual-level inputs or risk scores", privacy))

    n_pass = sum(c["status"] == "pass" for c in checks)
    return {"checks": checks, "passed": n_pass, "total": len(checks), "all_passed": n_pass == len(checks),
            "config_hash": config_hash(cfg), "engine_version": ENGINE_VERSION}


def conceptual_validation(cfg: dict[str, Any]) -> dict[str, Any]:
    ref_ids = {r["id"] for r in references()}
    rows = []
    counts = {"E1": 0, "E2": 0, "H": 0, "L": 0}
    for e in cfg["edges"]:
        if e["kind"] == "structural":
            continue
        flags = []
        if e["evidence"] in ("E1", "E2") and not e["references"]:
            flags.append("evidence class requires at least one reference")
        unknown = [r for r in e["references"] if r not in ref_ids]
        if unknown:
            flags.append(f"unknown reference ids {unknown}")
        if e["evidence"] == "H":
            flags.append("research hypothesis: requires empirical testing")
        if e.get("original") and e["original"]["coefficient"] != e["coefficient"]:
            flags.append("coefficient modified from original assumption")
        if not e["enabled"]:
            flags.append("relationship disabled")
        counts[e["evidence"]] += 1
        rows.append({"id": e["id"], "hypothesis": e.get("hypothesis"), "source": e["source"], "target": e["target"],
                     "sign": e["sign"], "coefficient": e["coefficient"], "evidence": e["evidence"],
                     "confidence": e["confidence"], "references": e["references"], "enabled": e["enabled"], "flags": flags})
    loops = declared_loops(cfg)
    return {"relationships": rows, "evidence_counts": counts, "loops": loops,
            "loop_issues": [l["id"] for l in loops if not (l["closed"] and l["polarity_consistent"])]}


def historical_validation(cfg: dict[str, Any], dataset: dict[str, Any], holdout: int = 6,
                          param_ids: Optional[list[str]] = None, calibrate: bool = True) -> dict[str, Any]:
    n = len(dataset["periods"])
    if not (1 <= holdout <= n - 4):
        raise ValueError(f"holdout must lie in [1, {n - 4}]")
    targets = default_targets(dataset, cfg)
    used_cfg = cfg
    cal = None
    if calibrate:
        cal = calibrate_lsq(cfg, dataset, param_ids=param_ids, targets=targets, holdout=holdout)
        used_cfg = apply_overrides(cfg, {p["id"]: p["estimate"] for p in cal["parameters"]})
    m, rs = replay_setup(used_cfg, dataset, n)
    raw = run(m, rs)
    Y, _ = _observed(dataset, targets, n, False)
    n_cal = n - holdout
    rows = {}
    for j, s in enumerate(targets):
        sim = raw["V"][:, ALL_VARS.index(s)]
        obs = Y[:, j]
        res = sim - obs
        hold = slice(n_cal, n)
        tt = np.arange(n)[hold]
        ok = np.isfinite(obs[hold])
        slope_obs = float(np.polyfit(tt[ok], obs[hold][ok], 1)[0]) if ok.sum() >= 3 else None
        slope_sim = float(np.polyfit(tt, sim[hold], 1)[0]) if holdout >= 3 else None
        r_cal = res[:n_cal][np.isfinite(res[:n_cal])]
        lag1 = float(np.corrcoef(r_cal[:-1], r_cal[1:])[0, 1]) if r_cal.size > 3 and np.std(r_cal) > 0 else None
        rows[s] = {"calibration": _metrics(obs[:n_cal], sim[:n_cal]), "holdout": _metrics(obs[hold], sim[hold]),
                   "residuals": res, "observed": obs, "simulated": sim,
                   "trend": {"observed_slope": slope_obs, "simulated_slope": slope_sim,
                             "direction_agrees": (np.sign(slope_obs) == np.sign(slope_sim)) if slope_obs is not None and slope_sim is not None else None},
                   "residual_lag1_autocorrelation": lag1}
    hold_rmse = [r["holdout"]["rmse"] for r in rows.values() if r["holdout"]["rmse"] is not None]
    return nan_to_none({"periods": dataset["periods"], "n_calibration": n_cal, "n_holdout": holdout, "targets": targets,
                        "calibrated": calibrate, "calibration": cal and {"parameters": cal["parameters"], "status": cal["status"]},
                        "variables": rows, "mean_holdout_rmse": float(np.mean(hold_rmse)) if hold_rmse else None,
                        "data_class": dataset.get("data_class"),
                        "note": "Validation on SYNTHETIC data only demonstrates the workflow; it does not validate the model for real schools."
                        if dataset.get("data_class") == "SYNTHETIC" else None})


def intervention_validation(cfg: dict[str, Any], dataset: dict[str, Any], variable: str,
                            intervention_period: int, intervention: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Interrupted time series (segmented regression with Newey-West errors) on the observed
    aggregate, compared with the model-implied change relative to a no-intervention replay."""
    import statsmodels.api as sm

    n = len(dataset["periods"])
    if variable not in ALL_VARS:
        raise ValueError(f"unknown variable {variable}")
    if not (3 <= intervention_period <= n - 3):
        raise ValueError("intervention period must leave at least 3 observations on each side")
    ser = dataset.get("variables", {}).get(variable)
    if not ser:
        raise ValueError(f"dataset has no observations of {variable}")
    y = np.array([np.nan if v is None else float(v) for v in ser[:n]])
    t = np.arange(n, dtype=float)
    post = (t >= intervention_period).astype(float)
    X = np.column_stack([np.ones(n), t, post, (t - intervention_period) * post])
    ok = np.isfinite(y)
    fit = sm.OLS(y[ok], X[ok]).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    ci = fit.conf_int(alpha=0.05)
    post_t = t[(t >= intervention_period)] - intervention_period
    observed_change = float(fit.params[2] + fit.params[3] * post_t.mean())

    # Model-implied change: replay with recorded interventions vs counterfactual without them
    m, rs = replay_setup(cfg, dataset, n)
    if intervention:
        from .scenarios import intervention_matrix
        U = intervention_matrix([intervention], m.interventions, n - 1)
        rs.U = U
    with_iv = run(m, rs)["V"][:, ALL_VARS.index(variable)]
    rs_cf = copy.copy(rs)
    rs_cf.U = np.zeros_like(rs.U)
    without = run(m, rs_cf)["V"][:, ALL_VARS.index(variable)]
    model_change = float(np.mean((with_iv - without)[intervention_period:]))
    had_iv = bool(np.any(rs.U > 0))
    return nan_to_none({
        "variable": variable, "intervention_period": intervention_period,
        "intervention_period_label": dataset["periods"][intervention_period],
        "its": {"level_change": float(fit.params[2]), "level_change_ci95": ci[2].tolist(), "level_change_p": float(fit.pvalues[2]),
                "slope_change": float(fit.params[3]), "slope_change_ci95": ci[3].tolist(), "slope_change_p": float(fit.pvalues[3]),
                "pre_slope": float(fit.params[1]), "n_pre": int(ok[: intervention_period].sum()), "n_post": int(ok[intervention_period:].sum()),
                "observed_mean_post_change": observed_change},
        "model": {"mean_post_change_vs_counterfactual": model_change, "intervention_inputs_present": had_iv},
        "agreement": {"same_direction": (np.sign(observed_change) == np.sign(model_change)) if had_iv else None,
                      "difference": observed_change - model_change},
        "series": {"observed": y, "model_with_intervention": with_iv, "model_counterfactual": without, "periods": dataset["periods"]},
        "assumptions": [
            "Segmented regression assumes the pre-intervention trend would have continued without the intervention.",
            "No concurrent events or measurement changes coincide with the intervention period.",
            "Newey-West (HAC, 2 lags) errors partially address autocorrelation; short series remain fragile.",
            "Agreement between observed and simulated changes is consistency evidence only; it does not prove a causal effect.",
        ],
    })


def validation_envelope(cfg: dict[str, Any], datasets: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    env = copy.deepcopy(cfg.get("validation_envelope", {}))
    params = list_parameters(cfg)
    prov: dict[str, int] = {}
    for p in params:
        prov[p.get("provenance", "illustrative")] = prov.get(p.get("provenance", "illustrative"), 0) + 1
    observed_ranges = {}
    for ds in datasets or []:
        for s, ser in ds.get("variables", {}).items():
            vals = [v for v in ser if v is not None]
            if vals:
                lo, hi = observed_ranges.get(s, (1.0, 0.0))
                observed_ranges[s] = (min(lo, min(vals)), max(hi, max(vals)))
    unvalidated = [f"{e['id']}: {e['source']} → {e['target']}" for e in cfg["edges"] if e["evidence"] == "H" and e["enabled"]]
    return {
        **env,
        "parameter_provenance_counts": prov,
        "observed_variable_ranges": {k: list(v) for k, v in observed_ranges.items()},
        "datasets_considered": [{"name": d.get("name"), "data_class": d.get("data_class"), "n_periods": len(d.get("periods", []))}
                                for d in (datasets or [])],
        "unvalidated_assumptions": unvalidated,
        "outside_scope": [
            "Any individual-level prediction, profiling, or risk/dangerousness scoring (excluded by design).",
            "Prediction of incidents, attacks, dates or locations (excluded by design).",
            "Schools or time horizons not represented in calibration data.",
            "Variable values outside the observed ranges listed above.",
            "Weekly or daily dynamics (model time step is one month).",
            "Use of indices as probabilities of any event.",
        ],
    }


def build_report(cfg: dict[str, Any], datasets: Optional[list[dict[str, Any]]] = None,
                 historical: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    ver = verification_suite(cfg)
    con = conceptual_validation(cfg)
    env = validation_envelope(cfg, datasets)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "engine_version": ENGINE_VERSION,
              "config_hash": config_hash(cfg), "parameter_status": cfg.get("parameter_set", {}).get("status"),
              "verification": ver, "conceptual": con, "envelope": env, "historical": historical}
    report["markdown"] = report_markdown(report)
    return nan_to_none(report)


def report_markdown(r: dict[str, Any]) -> str:
    L = ["# Validation Report — School Safety & Resilience Digital Twin", "",
         f"Generated: {r['generated_at']}  ", f"Engine: {r['engine_version']}  ", f"Configuration hash: `{r['config_hash']}`  ",
         f"Parameter status: **{r['parameter_status']}**", "",
         "> Outputs are institutional readiness and process indicators. They are not probabilities of violence, attack or harm.", "",
         "## 1. Mathematical verification", "", "| ID | Check | Status | Detail |", "|---|---|---|---|"]
    for c in r["verification"]["checks"]:
        L.append(f"| {c['id']} | {c['name']} | {c['status'].upper()} | {c['detail']} |")
    L += ["", f"Passed {r['verification']['passed']} / {r['verification']['total']}.", "", "## 2. Conceptual validation", "",
          "Evidence classes: " + ", ".join(f"{k}: {v}" for k, v in r["conceptual"]["evidence_counts"].items()), "",
          "| Relationship | Source → Target | Sign | Coef. | Evidence | Flags |", "|---|---|---|---|---|---|"]
    for e in r["conceptual"]["relationships"]:
        L.append(f"| {e['id']} | {e['source']} → {e['target']} | {'+' if e['sign'] > 0 else '−'} | {e['coefficient']:.3f} | {e['evidence']} | {'; '.join(e['flags'])} |")
    L += ["", "## 3. Validation envelope", "", f"- Validated horizon (months): {r['envelope'].get('validated_horizon_months')}",
          f"- Data frequency: {r['envelope'].get('data_frequency')}",
          f"- Parameter provenance: {r['envelope'].get('parameter_provenance_counts')}", "", "Unvalidated assumptions:", ""]
    L += [f"- {x}" for x in r["envelope"]["unvalidated_assumptions"]]
    L += ["", "Outside the model's validated scope:", ""] + [f"- {x}" for x in r["envelope"]["outside_scope"]]
    h = r.get("historical")
    if h:
        L += ["", "## 4. Historical validation", "", f"Calibration periods: {h['n_calibration']}, holdout: {h['n_holdout']}", "",
              "| Variable | Cal. RMSE | Holdout RMSE | Holdout MAE | Trend agrees |", "|---|---|---|---|---|"]
        for s, v in h["variables"].items():
            def f(x):
                return "—" if x is None else f"{x:.4f}"
            L.append(f"| {s} | {f(v['calibration']['rmse'])} | {f(v['holdout']['rmse'])} | {f(v['holdout']['mae'])} | {v['trend']['direction_agrees']} |")
        if h.get("note"):
            L += ["", f"_{h['note']}_"]
    return "\n".join(L) + "\n"


__all__ = ["verification_suite", "conceptual_validation", "historical_validation", "intervention_validation",
           "validation_envelope", "build_report", "get_bounds", "resolve"]
