"""Deterministic monthly simulator (single authoritative implementation).

Timing convention (documented in MATHEMATICAL_EQUATIONS.md):

* Month 0 holds the initial (observed) conditions, including the initial R(0), L(0).
* For month t = 1..N the target state X*(t-1) is formed from information available at
  the end of month t-1 (X, Z, R, L, Qp at t-1) plus the interventions U(t) and external
  conditions D(t) acting in month t. Derived operational indicators therefore feed back
  with a one-month information delay.
* The state is updated, context deviations and reallocated hours are updated, and the
  month-t stock-flow block (I, μ, C_flow, Q) is evaluated with the updated state.

Identical inputs always produce identical outputs: there is no randomness here.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .config import ENGINE_VERSION, config_hash
from .indices import domain_indices
from .model import CompiledModel, NS, SRC_CONTEXT, SRC_EXTERNAL, SRC_STATE, compile_model
from .normalization import to_json_list
from .scenarios import ResolvedScenario, resolve, scenario_hash
from .schemas import ALL_VARS, CONTEXT_VARS, STATE_VARS

MU_FLOOR = 1e-9
EFF_FLOOR = 0.1


def _term_product(terms: np.ndarray, X: np.ndarray, Z: np.ndarray, D: np.ndarray) -> float:
    """Π max(0, 1 + c·(x_src - ref)) over multiplicative flow terms."""
    out = 1.0
    for st, si, c, ref in terms:
        src = X if st == SRC_STATE else Z if st == SRC_CONTEXT else D
        out *= max(0.0, 1.0 + c * (src[int(si)] - ref))
    return out


def capacity(m: CompiledModel, X: np.ndarray, Z: np.ndarray, D: np.ndarray, flex: float) -> tuple[float, float, float]:
    """Processing capacity μ [processes/month], support hours [h/month], efficiency factor."""
    hours = m.hours_from_S(float(X[STATE_VARS.index("S")]))
    eff = max(EFF_FLOOR, _term_product(m.eff_terms, X, Z, D))
    mu = (hours * m.alloc_share + flex) * eff / m.h_proc
    return max(0.0, mu), hours, eff


def pressure(Q: float, mu: float, w_half: float) -> tuple[float, float]:
    """Expected waiting time W = Q/μ (Little's law) and saturating backlog pressure W/(W + w½)."""
    W = Q / max(mu, MU_FLOOR)
    return W, W / (W + w_half)


def equilibrium_flex(m: CompiledModel, X: np.ndarray, Z: np.ndarray, D: np.ndarray, Q: float) -> float:
    """Fixed point flex = β·Qp(Q, μ(flex))·H_flex. The map is a contraction (Qp decreases in flex)."""
    f = 0.0
    for _ in range(100):
        mu, _, _ = capacity(m, X, Z, D, f)
        _, qp = pressure(Q, mu, m.w_half)
        nf = max(0.0, m.b1_gain * qp * m.flex_max)
        if abs(nf - f) < 1e-10:
            return nf
        f = 0.5 * (f + nf)
    return f


def run(m: CompiledModel, rs: ResolvedScenario, record_targets: bool = True) -> dict[str, np.ndarray]:
    N = rs.horizon
    X = np.zeros((N + 1, NS)); Z = np.zeros((N + 1, len(CONTEXT_VARS))); dz = np.zeros_like(Z)
    Rv = np.zeros(N + 1); Lv = np.zeros(N + 1); Q = np.zeros(N + 1); Qp = np.zeros(N + 1); W = np.zeros(N + 1)
    flex = np.zeros(N + 1); mu = np.zeros(N + 1); hours = np.zeros(N + 1); eff = np.zeros(N + 1)
    I = np.full(N + 1, np.nan); Cf = np.full(N + 1, np.nan); rho = np.full(N + 1, np.nan)
    Xstar = np.full((N + 1, NS), np.nan); clipped_targets = 0

    manual = {s: rs.overrides[s] for s, mode in rs.modes.items() if mode == "manual"}
    s_manual = [(STATE_VARS.index(s), arr) for s, arr in manual.items() if s in STATE_VARS]
    z_manual = [(CONTEXT_VARS.index(s), arr) for s, arr in manual.items() if s in CONTEXT_VARS]

    X[0] = [rs.initial[s] for s in STATE_VARS]
    for i, arr in s_manual:
        X[0, i] = arr[0]
    Z[0] = rs.Z_obs[0]
    Q[0] = rs.Q0
    # Reallocated hours at t = 0: explicit value, or equilibrium of the B1 adjustment for the initial backlog
    if rs.flex0 is not None:
        flex[0] = rs.flex0
    else:
        flex[0] = equilibrium_flex(m, X[0], Z[0], rs.D[0], Q[0])
    mu[0], hours[0], eff[0] = capacity(m, X[0], Z[0], rs.D[0], flex[0])
    W[0], Qp[0] = pressure(Q[0], mu[0], m.w_half)
    Rv[0] = rs.overrides["R"][0] if "R" in manual else rs.initial["R"]
    Lv[0] = rs.overrides["L"][0] if "L" in manual else rs.initial["L"]

    X0 = X[0].copy()
    for t in range(1, N + 1):
        u, d = rs.U[t], rs.D[t]
        y = np.array([Rv[t - 1], Lv[t - 1], Qp[t - 1]])
        raw = m.b + m.A @ X[t - 1] + m.Gamma @ Z[t - 1] + m.Pi @ y + m.B @ u + m.G @ d
        xs = np.clip(raw, 0.0, 1.0)
        clipped_targets += int(np.sum(np.abs(raw - xs) > 1e-12))
        if record_targets:
            Xstar[t] = xs
        X[t] = np.clip(X[t - 1] + m.Lam @ (xs - X[t - 1]), 0.0, 1.0)
        for i, arr in s_manual:
            X[t, i] = arr[t]
        dz[t] = dz[t - 1] + m.lambda_z * (m.Omega @ (X[t - 1] - X0) + m.Bz @ u + m.Gz @ d - dz[t - 1])
        Z[t] = np.clip(rs.Z_obs[t] + dz[t], 0.0, 1.0)
        for j, arr in z_manual:
            Z[t, j] = arr[t]
        flex[t] = max(0.0, flex[t - 1] + m.lambda_flex * (m.b1_gain * Qp[t - 1] * m.flex_max - flex[t - 1]))

        # --- stock-flow block for month t -------------------------------------------
        I[t] = max(0.0, m.I_base * _term_product(m.inflow_terms, X[t], Z[t], d))
        mu[t], hours[t], eff[t] = capacity(m, X[t], Z[t], d, flex[t])
        avail = Q[t - 1] + I[t]
        Cf[t] = min(avail, mu[t])
        Q[t] = max(0.0, Q[t - 1] + I[t] - Cf[t])
        rho[t] = Cf[t] / avail if avail > 0 else 1.0
        W[t], Qp[t] = pressure(Q[t], mu[t], m.w_half)

        Rv[t] = manual["R"][t] if "R" in manual else rho[t]
        if "L" in manual:
            Lv[t] = manual["L"][t]
        else:
            Lv[t] = float(np.clip(m.L_base + m.L_state @ X[t] + m.L_ctx @ Z[t] + m.L_qp * Qp[t] + m.L_ext @ d, 0.0, 1.0))

    # Assemble the 16-variable matrix in canonical order
    V = np.zeros((N + 1, len(ALL_VARS)))
    for k, s in enumerate(ALL_VARS):
        if s in STATE_VARS:
            V[:, k] = X[:, STATE_VARS.index(s)]
        elif s in CONTEXT_VARS:
            V[:, k] = Z[:, CONTEXT_VARS.index(s)]
        elif s == "R":
            V[:, k] = Rv
        else:
            V[:, k] = Lv
    return {
        "V": V, "X": X, "Z": Z, "dz": dz, "Xstar": Xstar, "Q": Q, "I": I, "C_flow": Cf, "mu": mu, "rho": rho,
        "W": W, "Qp": Qp, "flex": flex, "hours": hours, "eff": eff, "U": rs.U, "D": rs.D,
        "clipped_targets": np.array([clipped_targets]),
    }


def calendar_labels(start_month: int, n: int) -> list[str]:
    return [f"M{t}" for t in range(n)]


def package(cfg: dict[str, Any], m: CompiledModel, rs: ResolvedScenario, raw: dict[str, np.ndarray],
            scenario: dict[str, Any]) -> dict[str, Any]:
    """JSON-serialisable result with provenance and diagnostics."""
    N = rs.horizon
    V = raw["V"]
    idx = domain_indices(V, m)
    program = raw["U"] * m.costs[None, :]
    support_hours = raw["hours"] * m.alloc_share + raw["flex"]
    mass_err = float(np.nanmax(np.abs(raw["Q"][1:] - raw["Q"][:-1] - (raw["I"][1:] - raw["C_flow"][1:])))) if N > 0 else 0.0
    targets = {s: to_json_list(raw["Xstar"][:, i]) for i, s in enumerate(STATE_VARS)}
    warnings = list(rs.warnings)
    if int(raw["clipped_targets"][0]) > 0:
        warnings.append(f"target state X* was clipped to [0,1] {int(raw['clipped_targets'][0])} time(s)")
    return {
        "scenario_id": scenario.get("id"),
        "scenario_name": scenario.get("name"),
        "horizon": N,
        "months": list(range(N + 1)),
        "variables": {s: to_json_list(V[:, k]) for k, s in enumerate(ALL_VARS)},
        "targets": targets,
        "context_deviation": {s: to_json_list(raw["dz"][:, j]) for j, s in enumerate(CONTEXT_VARS)},
        "indices": {k: to_json_list(v) for k, v in idx.items()},
        "flows": {
            "Q": to_json_list(raw["Q"]), "I": to_json_list(raw["I"]), "C_flow": to_json_list(raw["C_flow"]),
            "mu": to_json_list(raw["mu"]), "completion_ratio": to_json_list(raw["rho"]),
            "waiting_time": to_json_list(raw["W"]), "backlog_pressure": to_json_list(raw["Qp"]),
            "flex_hours": to_json_list(raw["flex"]), "support_hours": to_json_list(support_hours),
            "efficiency": to_json_list(raw["eff"]),
        },
        "interventions": {k: to_json_list(raw["U"][:, i]) for i, k in enumerate(m.interventions)},
        "external": {k: to_json_list(raw["D"][:, i]) for i, k in enumerate(m.externals)},
        "resources": {
            "program_hours_total": float(program.sum()),
            "program_hours_by_intervention": {k: float(program[:, i].sum()) for i, k in enumerate(m.interventions)},
            "program_hours_monthly": to_json_list(program.sum(axis=1)),
            "support_hours_total": float(support_hours[1:].sum()),
            "unit": "illustrative staff-hours",
        },
        "modes": rs.modes,
        "diagnostics": {
            "warnings": warnings,
            "mass_balance_max_error": mass_err,
            "clipped_targets": int(raw["clipped_targets"][0]),
            "min_state": float(np.min(V)), "max_state": float(np.max(V)),
        },
        "provenance": {
            "data_class": rs.data_class,
            "engine_version": ENGINE_VERSION,
            "config_hash": config_hash(cfg),
            "scenario_hash": scenario_hash(scenario),
            "parameter_status": cfg.get("parameter_set", {}).get("status", "ILLUSTRATIVE"),
            "deterministic": True,
        },
    }


def simulate(cfg: dict[str, Any], scenario: dict[str, Any], dataset: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    rs, eff_cfg = resolve(cfg, scenario, dataset)
    m = compile_model(eff_cfg)
    raw = run(m, rs)
    return package(eff_cfg, m, rs, raw, scenario)


def summary_metrics(result: dict[str, Any]) -> dict[str, float]:
    """Scalar end-of-horizon outputs used by UQ / SA / comparison."""
    N = result["horizon"]
    out = {f"{k}_end": result["indices"][k][N] for k in result["indices"]}
    out.update({f"{s}_end": result["variables"][s][N] for s in ALL_VARS})
    out["Q_end"] = result["flows"]["Q"][N]
    out["C_flow_total"] = float(np.nansum([x for x in result["flows"]["C_flow"] if x is not None]))
    out["I_total"] = float(np.nansum([x for x in result["flows"]["I"] if x is not None]))
    return out
