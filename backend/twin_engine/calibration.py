"""Parameter calibration against AGGREGATE institutional time series (Section 11).

1. Regularised (weighted) least squares
       θ̂ = argmin Σ_t (Y_t − Ŷ_t(θ))ᵀ W (Y_t − Ŷ_t(θ)) + λ ||(θ − θ₀) / s||²
   solved with SciPy's bounded trust-region reflective algorithm. Approximate standard
   errors come from the Gauss–Newton covariance s²(JᵀJ)⁻¹.

2. Bayesian calibration  P(θ | D) ∝ P(D | θ) P(θ)
   Scaled-Beta priors on bounded parameter intervals, Gaussian observation errors with
   unknown scale, sampled by an adaptive Metropolis algorithm (Haario et al., 2001)
   implemented in NumPy. Convergence is summarised by split-R̂ and effective sample size.
   PyMC is used only if installed AND explicitly requested.

Only institutional system parameters are calibrated. No individual-level data exist in
this model and no individual predictions are produced.
"""

from __future__ import annotations

import importlib.util
from typing import Any, Optional

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import beta as beta_dist

from .analysis_common import guard_runs, nan_to_none
from .model import CompiledModel, compile_model
from .params import get_bounds, get_range, get_value
from .scenarios import ResolvedScenario, baseline_from_config, resolve
from .schemas import ALL_VARS, CONTEXT_VARS, DERIVED_VARS, STATE_VARS
from .simulator import run

DEFAULT_CAL_PARAMS = ["lambda.T", "lambda.C", "lambda.K", "edge.H1", "edge.H2", "edge.H4", "edge.H7", "edge.H9", "edge.SOC-T-C"]
# H1 and H2 both act on trust and are jointly weakly identifiable from aggregate data (see LSQ
# correlation report); the Bayesian default therefore samples one of the pair.
DEFAULT_BAYES_PARAMS = ["lambda.T", "lambda.K", "edge.H1", "edge.H4", "edge.H7", "edge.H9", "edge.SOC-T-C"]
PYMC_AVAILABLE = importlib.util.find_spec("pymc") is not None


# --------------------------------------------------------------------------- replay setup
def replay_setup(cfg: dict[str, Any], dataset: dict[str, Any], n_periods: Optional[int] = None) -> tuple[CompiledModel, ResolvedScenario]:
    """Replay the dataset's observed context, external conditions and known interventions
    from its first period, so that simulated state trajectories are comparable with data."""
    n = len(dataset["periods"]) if n_periods is None else int(n_periods)
    if n < 4:
        raise ValueError("calibration requires at least 4 periods")
    sc = baseline_from_config(cfg)
    sc["horizon_months"] = n - 1
    sc["dataset_anchor"] = "replay"
    rs, eff = resolve(cfg, sc, dataset)
    m = compile_model(eff)
    # Responsive context indicators (targets of enabled context-response edges) are partly
    # endogenous: their observed path already contains the modelled response. Replaying it
    # as Z_obs would double-count the response, so they are anchored at their first
    # observation and treated as calibration targets instead.
    for sym in responsive_contexts(cfg):
        j = CONTEXT_VARS.index(sym)
        rs.Z_obs[:, j] = rs.Z_obs[0, j]
    for k, ser in (dataset.get("interventions") or {}).items():
        if k in m.interventions:
            arr = np.array([0.0 if v is None else float(v) for v in ser[: n]] + [0.0] * max(0, n - len(ser)))
            rs.U[:, m.interventions.index(k)] = np.clip(arr[: n], 0, 1)
    for k, ser in (dataset.get("external") or {}).items():
        if k in m.externals:
            vals = [v for v in ser[:n]]
            last = float(rs.D[0, m.externals.index(k)])
            for t in range(n):
                if t < len(vals) and vals[t] is not None:
                    last = float(vals[t])
                rs.D[t, m.externals.index(k)] = last
    return m, rs


def _observed(dataset: dict[str, Any], targets: list[str], n: int, include_Q: bool) -> tuple[np.ndarray, Optional[np.ndarray]]:
    Y = np.full((n, len(targets)), np.nan)
    for j, s in enumerate(targets):
        ser = dataset.get("variables", {}).get(s, [])
        for t in range(min(n, len(ser))):
            if ser[t] is not None:
                Y[t, j] = float(ser[t])
    Q = None
    if include_Q and dataset.get("flows", {}).get("Q"):
        ser = dataset["flows"]["Q"]
        Q = np.array([np.nan if (t >= len(ser) or ser[t] is None) else float(ser[t]) for t in range(n)])
    return Y, Q


def responsive_contexts(cfg: dict[str, Any]) -> list[str]:
    return sorted({e["target"] for e in cfg["edges"]
                   if e["kind"] == "context_response" and e["enabled"] and e["coefficient"] > 0},
                  key=CONTEXT_VARS.index)


def default_targets(dataset: dict[str, Any], cfg: Optional[dict[str, Any]] = None) -> list[str]:
    present = set(dataset.get("variables", {}).keys())
    endo = list(STATE_VARS) + list(DERIVED_VARS) + (responsive_contexts(cfg) if cfg else [])
    return [s for s in endo if s in present]


def _sim(m: CompiledModel, rs: ResolvedScenario, targets: list[str]) -> tuple[np.ndarray, np.ndarray]:
    raw = run(m, rs, record_targets=False)
    return raw["V"][:, [ALL_VARS.index(s) for s in targets]], raw["Q"]


def _metrics(obs: np.ndarray, sim: np.ndarray) -> dict[str, Optional[float]]:
    mask = np.isfinite(obs)
    if mask.sum() == 0:
        return {"n": 0, "rmse": None, "mae": None, "r2": None, "bias": None}
    e = sim[mask] - obs[mask]
    ss_tot = float(np.sum((obs[mask] - obs[mask].mean()) ** 2))
    return {"n": int(mask.sum()), "rmse": float(np.sqrt(np.mean(e ** 2))), "mae": float(np.mean(np.abs(e))),
            "r2": (1 - float(np.sum(e ** 2)) / ss_tot) if ss_tot > 1e-12 else None, "bias": float(np.mean(e))}


def _search_bounds(cfg: dict[str, Any], pid: str) -> tuple[float, float]:
    hlo, hhi = get_bounds(cfg, pid)
    r = get_range(cfg, pid)
    if r:
        w = r[1] - r[0]
        return max(hlo, r[0] - w), min(hhi, r[1] + w)
    return hlo, hhi


def prior_spec(cfg: dict[str, Any], pid: str, source: str = "config") -> dict[str, Any]:
    """Prior centre and support. 'expert' / 'literature' use recorded elicitation if present."""
    from .params import _find
    _, obj = _find(cfg, pid)
    centre = get_value(cfg, pid)
    lo, hi = _search_bounds(cfg, pid)
    used = "config value and uncertainty range"
    if source == "expert" and obj.get("expert_range"):
        er = obj["expert_range"]
        lo, hi, centre, used = float(er["low"]), float(er["high"]), float(er["mode"]), "expert elicitation"
    elif source == "literature" and obj.get("literature_ranges"):
        lr = obj["literature_ranges"]
        lo, hi = min(float(x["low"]) for x in lr), max(float(x["high"]) for x in lr)
        centre, used = 0.5 * (lo + hi), "recorded literature ranges"
    hlo, hhi = get_bounds(cfg, pid)
    lo, hi = max(lo, hlo), min(hi, hhi)
    if hi <= lo:
        hi = lo + 1e-6
    centre = float(np.clip(centre, lo, hi))
    return {"low": lo, "high": hi, "centre": centre, "source": used}


# --------------------------------------------------------------------------- least squares
def calibrate_lsq(
    cfg: dict[str, Any], dataset: dict[str, Any], param_ids: Optional[list[str]] = None,
    targets: Optional[list[str]] = None, reg_lambda: float = 0.05, holdout: int = 0, include_Q: bool = True,
    q_weight: float = 0.5, max_nfev: int = 300, prior_source: str = "config",
) -> dict[str, Any]:
    param_ids = param_ids or [p for p in DEFAULT_CAL_PARAMS]
    targets = targets or default_targets(dataset, cfg)
    if not targets:
        raise ValueError("dataset contains no state or derived variables to calibrate against")
    n_all = len(dataset["periods"])
    if holdout < 0 or holdout > n_all - 4:
        raise ValueError(f"holdout must lie in [0, {n_all - 4}]")
    n_cal = n_all - holdout
    m_cal, rs_cal = replay_setup(cfg, dataset, n_cal)
    m_all, rs_all = replay_setup(cfg, dataset, n_all)
    missing = [p for p in param_ids if p not in m_cal.param_slots]
    if missing:
        raise ValueError(f"parameters {missing} are not active in the model")
    Y, Qobs = _observed(dataset, targets, n_all, include_Q)
    Ycal, Qcal = Y[:n_cal], (Qobs[:n_cal] if Qobs is not None else None)
    q_scale = float(np.nanmean(Qcal)) if Qcal is not None and np.isfinite(Qcal).any() and np.nanmean(Qcal) > 0 else 1.0
    priors = [prior_spec(cfg, p, prior_source) for p in param_ids]
    theta0 = np.array([p["centre"] for p in priors])
    start = np.array([get_value(cfg, p) for p in param_ids])
    lo = np.array([_search_bounds(cfg, p)[0] for p in param_ids])
    hi = np.array([_search_bounds(cfg, p)[1] for p in param_ids])
    start = np.clip(start, lo + 1e-9, hi - 1e-9)
    scale = np.maximum(np.array([p["high"] - p["low"] for p in priors]), 1e-6)
    mask = np.isfinite(Ycal)
    qmask = np.isfinite(Qcal) if Qcal is not None else None
    n_data = int(mask.sum() + (qmask.sum() if qmask is not None else 0))
    if n_data <= len(param_ids):
        raise ValueError(f"only {n_data} observations for {len(param_ids)} parameters: not identifiable")
    guard_runs(max_nfev * (len(param_ids) + 1))

    def data_resid(theta: np.ndarray) -> np.ndarray:
        sim, Qs = _sim(m_cal.with_params(dict(zip(param_ids, theta))), rs_cal, targets)
        r = np.where(mask, sim - np.nan_to_num(Ycal), 0.0)[mask]
        if qmask is not None:
            r = np.concatenate([r, np.sqrt(q_weight) * (Qs - np.nan_to_num(Qcal))[qmask] / q_scale])
        return r

    def resid(theta: np.ndarray) -> np.ndarray:
        return np.concatenate([data_resid(theta), np.sqrt(reg_lambda) * (theta - theta0) / scale])

    r0 = data_resid(start)
    sol = least_squares(resid, start, bounds=(lo, hi), method="trf", x_scale="jac", max_nfev=max_nfev)
    theta = sol.x
    rd = data_resid(theta)
    k = len(param_ids)
    dof = max(1, rd.size - k)
    s2 = float(np.sum(rd ** 2) / dof)
    J = sol.jac
    Jd = J[: rd.size]
    cov = s2 * np.linalg.pinv(J.T @ J)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    sv = np.linalg.svd(Jd, compute_uv=False) if Jd.size else np.array([0.0])
    cond = float(sv.max() / sv.min()) if sv.min() > 0 else float("inf")
    col_norm = np.linalg.norm(Jd, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = cov / np.outer(se, se)
    rows = []
    for j, pid in enumerate(param_ids):
        rel = se[j] / scale[j]
        reasons = []
        if col_norm[j] < 1e-6 * max(1e-12, col_norm.max()):
            reasons.append("output insensitive to this parameter")
        if rel > 0.5:
            reasons.append("standard error exceeds half the plausible range")
        hc = [param_ids[i] for i in range(k) if i != j and np.isfinite(corr[j, i]) and abs(corr[j, i]) > 0.95]
        if hc:
            reasons.append(f"estimate strongly correlated with {hc}")
        rows.append({"id": pid, "initial": float(start[j]), "prior_centre": float(theta0[j]), "estimate": float(theta[j]),
                     "se": float(se[j]), "ci95": [float(max(lo[j], theta[j] - 1.96 * se[j])), float(min(hi[j], theta[j] + 1.96 * se[j]))],
                     "at_bound": bool(np.isclose(theta[j], lo[j]) or np.isclose(theta[j], hi[j])),
                     "identifiable": not reasons, "identifiability_notes": reasons, "prior_source": priors[j]["source"]})

    sim_init, Q_init = _sim(m_all.with_params(dict(zip(param_ids, start))), rs_all, targets)
    sim_fit, Q_fit = _sim(m_all.with_params(dict(zip(param_ids, theta))), rs_all, targets)
    fit = {}
    for j, s in enumerate(targets):
        fit[s] = {"calibration_initial": _metrics(Y[:n_cal, j], sim_init[:n_cal, j]),
                  "calibration_fitted": _metrics(Y[:n_cal, j], sim_fit[:n_cal, j]),
                  "holdout_fitted": _metrics(Y[n_cal:, j], sim_fit[n_cal:, j]) if holdout else None}
    traj = {s: {"observed": Y[:, j], "initial": sim_init[:, j], "fitted": sim_fit[:, j]} for j, s in enumerate(targets)}
    if Qobs is not None:
        traj["Q"] = {"observed": Qobs, "initial": Q_init, "fitted": Q_fit}
    truth = dataset.get("truth") or {}
    return nan_to_none({
        "method": "regularised weighted least squares (trust-region reflective)",
        "status": "converged" if sol.success else f"not converged: {sol.message}",
        "message": sol.message, "n_function_evals": int(sol.nfev),
        "periods": dataset["periods"], "n_calibration": n_cal, "n_holdout": holdout,
        "targets": targets, "reg_lambda": reg_lambda, "n_observations": n_data,
        "objective_initial": float(np.sum(r0 ** 2)), "objective_fitted": float(np.sum(rd ** 2)),
        "residual_sd": float(np.sqrt(s2)), "jacobian_condition_number": cond,
        "parameters": rows, "fit": fit, "trajectories": traj,
        "correlation": {"ids": param_ids, "values": corr},
        "truth": truth if dataset.get("data_class") == "SYNTHETIC" else None,
        "data_class": dataset.get("data_class"),
        "assumptions": [
            "Observation errors are independent across months and variables (autocorrelated errors understate uncertainty).",
            "Model structure is assumed correct; estimates are conditional on the causal graph.",
            "Observed context indicators, external conditions and recorded interventions are replayed as inputs.",
            "Standard errors use a local Gauss-Newton approximation and are unreliable near bounds.",
        ],
    })


# --------------------------------------------------------------------------- Bayesian (adaptive Metropolis)
def _split_rhat(chains: np.ndarray) -> float:
    """chains: (m, n). Split-R̂ (Gelman & Rubin, 1992; split-chain variant)."""
    m, n = chains.shape
    half = n // 2
    if half < 2:
        return float("nan")
    sp = np.concatenate([chains[:, :half], chains[:, half: 2 * half]], axis=0)
    w = sp.var(axis=1, ddof=1).mean()
    b = half * sp.mean(axis=1).var(ddof=1)
    var = (half - 1) / half * w + b / half
    return float(np.sqrt(var / w)) if w > 0 else float("nan")


def _ess(chains: np.ndarray) -> float:
    """Effective sample size from summed autocorrelations (initial positive sequence)."""
    total = 0.0
    for x in chains:
        n = x.size
        x = x - x.mean()
        v = x.var()
        if v <= 0:
            continue
        f = np.fft.rfft(x, n=2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n] / (v * n)
        s = 0.0
        for lag in range(1, n - 1, 2):
            pair = ac[lag] + ac[lag + 1]
            if pair < 0:
                break
            s += pair
        total += n / (1 + 2 * s)
    return float(total)


def calibrate_bayes(
    cfg: dict[str, Any], dataset: dict[str, Any], param_ids: Optional[list[str]] = None,
    targets: Optional[list[str]] = None, n_chains: int = 3, n_iter: int = 3000, burn: int = 1000, seed: int = 11,
    holdout: int = 0, concentration: float = 6.0, prior_source: str = "config", backend: str = "numpy",
    n_predictive: int = 60,
) -> dict[str, Any]:
    if backend == "pymc":
        if not PYMC_AVAILABLE:
            raise RuntimeError("PyMC is not installed in this environment. Use backend='numpy' (built-in adaptive Metropolis) "
                               "or install PyMC to enable the optional backend.")
        raise RuntimeError("The PyMC backend is not enabled in this build; the built-in adaptive Metropolis sampler is used instead.")
    param_ids = param_ids or [p for p in DEFAULT_BAYES_PARAMS]
    targets = targets or default_targets(dataset, cfg)
    if not targets:
        raise ValueError("dataset contains no state or derived variables to calibrate against")
    if not (1 <= n_chains <= 6) or not (200 <= n_iter <= 20000) or not (0 <= burn < n_iter):
        raise ValueError("require 1<=chains<=6, 200<=iterations<=20000 and 0<=burn<iterations")
    guard_runs(n_chains * n_iter)
    n_all = len(dataset["periods"])
    n_cal = n_all - holdout
    if n_cal < 4:
        raise ValueError("calibration window too short")
    m_cal, rs_cal = replay_setup(cfg, dataset, n_cal)
    m_all, rs_all = replay_setup(cfg, dataset, n_all)
    Y, _ = _observed(dataset, targets, n_all, False)
    Ycal = Y[:n_cal]
    mask = np.isfinite(Ycal)
    n_obs = int(mask.sum())
    if n_obs <= len(param_ids) + 1:
        raise ValueError("insufficient observations for Bayesian calibration")
    pri = [prior_spec(cfg, p, prior_source) for p in param_ids]
    a = np.array([p["low"] for p in pri]); b = np.array([p["high"] for p in pri])
    mode_u = np.clip((np.array([p["centre"] for p in pri]) - a) / (b - a), 0.05, 0.95)
    # Beta with given mode and concentration κ = α+β (κ > 2)
    kappa = max(2.5, float(concentration))
    alpha = 1 + mode_u * (kappa - 2); beta_ = 1 + (1 - mode_u) * (kappa - 2)
    k = len(param_ids)
    d = k + 1  # + log sigma
    log_sigma_mu, log_sigma_sd = np.log(0.03), 1.0

    # Sampling space: η = logit((θ - a)/(b - a)), so bounded parameters have no hard walls.
    # Beta(α, β) prior on u = sigmoid(η) plus the Jacobian du/dη = u(1-u) gives
    # log p(η) = α·log u + β·log(1-u) (up to a constant).
    def to_theta(eta: np.ndarray) -> np.ndarray:
        return a + (b - a) / (1.0 + np.exp(-eta))

    def log_post(phi: np.ndarray) -> float:
        eta, ls = phi[:k], phi[k]
        if not np.all(np.isfinite(phi)) or np.any(np.abs(eta) > 30) or abs(ls) > 20:
            return -np.inf
        u = 1.0 / (1.0 + np.exp(-eta))
        lp = float(np.sum(alpha * np.log(u) + beta_ * np.log1p(-u)))
        lp += -0.5 * ((ls - log_sigma_mu) / log_sigma_sd) ** 2
        sim, _ = _sim(m_cal.with_params(dict(zip(param_ids, to_theta(eta)))), rs_cal, targets)
        r = (sim - np.nan_to_num(Ycal))[mask]
        sig = np.exp(ls)
        return lp - 0.5 * float(np.sum(r ** 2)) / sig ** 2 - n_obs * ls

    # 1) Posterior mode (MAP) and Laplace approximation as the initial proposal covariance
    from scipy.optimize import minimize
    eta_mode = np.log(mode_u / (1 - mode_u))
    phi0 = np.concatenate([eta_mode, [log_sigma_mu]])
    opt = minimize(lambda p: -log_post(p) if np.isfinite(log_post(p)) else 1e12, phi0, method="BFGS",
                   options={"maxiter": 200, "gtol": 1e-4})
    phi_map = opt.x if np.isfinite(log_post(opt.x)) else phi0
    H_inv = np.asarray(opt.hess_inv) if hasattr(opt, "hess_inv") else np.eye(d)
    H_inv = 0.5 * (H_inv + H_inv.T)
    w, V = np.linalg.eigh(H_inv)
    C_laplace = (V * np.clip(w, 1e-6, 4.0)) @ V.T

    rng = np.random.default_rng(seed)
    sd = 2.38 ** 2 / d
    chains = np.zeros((n_chains, n_iter, d))
    acc_post = np.zeros(n_chains)
    adapt_from = max(100, burn // 4)  # discard the initial transient from the covariance estimate
    L_lap = np.linalg.cholesky(C_laplace)
    for c in range(n_chains):
        # Overdispersed start around the mode (1.5x Laplace scale) so that R-hat is meaningful
        x = phi_map + 1.5 * (L_lap @ rng.standard_normal(d))
        lp = log_post(x)
        if not np.isfinite(lp):
            x, lp = phi_map.copy(), log_post(phi_map)
        mean = np.zeros(d); M2 = np.zeros((d, d)); n_seen = 0
        log_scale = 0.0
        L_chol = np.linalg.cholesky(sd * C_laplace)
        start_am = adapt_from + 2 * d
        for i in range(n_iter):
            # Adaptive Metropolis during burn-in (Haario et al., 2001) with Robbins-Monro scale
            # tuning toward 0.234 acceptance; the proposal is frozen after burn-in.
            if start_am <= i < burn and i % 10 == 0:
                C = np.exp(log_scale) * sd * (M2 / max(1, n_seen - 1) + 1e-8 * np.eye(d))
                try:
                    L_chol = np.linalg.cholesky(C)
                except np.linalg.LinAlgError:
                    pass
            elif i < start_am and i % 10 == 0:
                L_chol = np.linalg.cholesky(np.exp(log_scale) * sd * C_laplace)
            prop = x + L_chol @ rng.standard_normal(d)
            lpp = log_post(prop)
            accepted = bool(np.log(rng.random()) < lpp - lp)
            if accepted:
                x, lp = prop, lpp
                if i >= burn:
                    acc_post[c] += 1
            if i < burn:
                log_scale = float(np.clip(log_scale + 0.5 * (float(accepted) - 0.234) / (i + 1.0) ** 0.6, -4.0, 2.0))
            chains[c, i] = x
            if adapt_from <= i < burn:
                n_seen += 1
                delta = x - mean
                mean = mean + delta / n_seen
                M2 = M2 + np.outer(delta, x - mean)
    acc = acc_post / max(1, n_iter - burn)
    post_eta = chains[:, burn:, :]
    post = post_eta.copy()
    post[:, :, :k] = to_theta(post_eta[:, :, :k])
    flat = post.reshape(-1, d)
    theta_map = to_theta(phi_map[:k])
    rows = []
    for j, pid in enumerate(param_ids):
        s = flat[:, j]
        prior_q = a[j] + (b[j] - a[j]) * beta_dist.ppf([0.05, 0.5, 0.95], alpha[j], beta_[j])
        prior_sd = (b[j] - a[j]) * float(beta_dist.std(alpha[j], beta_[j]))
        shrink = float(s.std(ddof=1) / prior_sd) if prior_sd > 0 else None
        rhat = _split_rhat(post[:, :, j])
        ess = _ess(post[:, :, j])
        notes = []
        if shrink is not None and shrink > 0.8:
            notes.append("posterior barely narrower than prior: data weakly informative")
        if np.isfinite(rhat) and rhat > 1.1:
            notes.append("R-hat > 1.1: chains not converged; increase iterations")
        elif np.isfinite(rhat) and rhat > 1.05:
            notes.append("R-hat between 1.05 and 1.1: marginal convergence")
        if ess < 100:
            notes.append("effective sample size < 100")
        rows.append({"id": pid, "map": float(theta_map[j]), "prior": {"low": float(a[j]), "high": float(b[j]), "mode": float(pri[j]["centre"]),
                                         "q05": float(prior_q[0]), "q50": float(prior_q[1]), "q95": float(prior_q[2]), "source": pri[j]["source"]},
                     "posterior": {"mean": float(s.mean()), "sd": float(s.std(ddof=1)), "q05": float(np.quantile(s, 0.05)),
                                   "q50": float(np.quantile(s, 0.5)), "q95": float(np.quantile(s, 0.95))},
                     "rhat": rhat, "ess": ess, "posterior_to_prior_sd": shrink, "identifiable": not notes, "notes": notes,
                     "trace": post[:, :: max(1, post.shape[1] // 150), j]})
    sig = np.exp(flat[:, k])
    # Posterior predictive bands for the targets (thinned draws)
    draws = flat[rng.choice(flat.shape[0], size=min(n_predictive, flat.shape[0]), replace=False)]
    preds = np.array([_sim(m_all.with_params(dict(zip(param_ids, dr[:k]))), rs_all, targets)[0] for dr in draws])
    bands = {s: {"observed": Y[:, j], "p5": np.percentile(preds[:, :, j], 5, axis=0),
                 "p50": np.percentile(preds[:, :, j], 50, axis=0), "p95": np.percentile(preds[:, :, j], 95, axis=0)}
             for j, s in enumerate(targets)}
    truth = dataset.get("truth") or {}
    return nan_to_none({
        "method": "Bayesian calibration: scaled-Beta priors, Gaussian likelihood, adaptive Metropolis (Haario et al., 2001)",
        "backend": "numpy-adaptive-metropolis", "pymc_available": PYMC_AVAILABLE,
        "n_chains": n_chains, "n_iter": n_iter, "burn": burn, "seed": seed, "targets": targets,
        "acceptance_rate": acc.tolist(), "parameters": rows,
        "sigma": {"mean": float(sig.mean()), "q05": float(np.quantile(sig, 0.05)), "q95": float(np.quantile(sig, 0.95))},
        "predictive": bands, "periods": dataset["periods"], "n_calibration": n_cal, "n_holdout": holdout,
        "converged": all((r["rhat"] is None or not np.isfinite(r["rhat"]) or r["rhat"] <= 1.1) for r in rows),
        "convergence_rule": "all split-R-hat <= 1.1 (values 1.05-1.1 flagged as marginal)",
        "truth": truth if dataset.get("data_class") == "SYNTHETIC" else None,
        "assumptions": [
            "Priors are scaled Beta distributions on bounded plausible intervals; they encode modelling assumptions, not evidence.",
            "A single Gaussian error scale is shared by all normalised targets; errors are assumed independent.",
            "Posteriors are conditional on the model structure and on replayed context/intervention inputs.",
            "Short or noisy series yield posteriors close to the prior; this is reported per parameter.",
        ],
    })


def apply_calibration(cfg: dict[str, Any], estimates: dict[str, float], method: str, dataset_name: str) -> dict[str, Any]:
    """Write estimates into a configuration copy, marking provenance as calibrated."""
    import copy
    from datetime import datetime, timezone

    from .params import _find, set_value
    new = copy.deepcopy(cfg)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for pid, v in estimates.items():
        set_value(new, pid, float(v))
        kind, obj = _find(new, pid)
        obj["calibration"] = {"method": method, "dataset": dataset_name, "applied_at": stamp}
        if kind == "param":
            obj["provenance"] = "calibrated"
        else:
            obj["evidence_note"] = "coefficient calibrated to local aggregate data; evidence class unchanged until reviewed"
    return new
