"""Equilibrium anchoring of baseline intercepts (see scripts/anchor_demo_baseline.py).

Given a configuration and a baseline scenario, derive the values that make the scenario's
initial state a steady state of the no-intervention dynamics:

  Q0     = μ0·(1/R0 − 1)                 (stock-flow equilibrium with completion ratio R0)
  I_base = μ0 / Π multipliers(X0, Z0, D0) (inflow equals capacity)
  b      = X0 − (A·X0 + Γ·Z0 + Π·Y0 + G·D0)
  b_L    = L0 − (wX·X0 + wZ·Z0 + wQ·Qp0 + wD·D0)

Anchored values inherit the (illustrative) status of the coefficients they depend on.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .model import compile_model
from .params import set_value
from .scenarios import resolve
from .schemas import CONTEXT_VARS, STATE_VARS
from .simulator import _term_product, capacity, equilibrium_flex, pressure


def derive_anchor(cfg: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    rs, eff = resolve(cfg, scenario)
    m = compile_model(eff)
    X0 = np.array([rs.initial[s] for s in STATE_VARS])
    Z0 = rs.Z_obs[0].copy()
    D0 = rs.D[0].copy()
    R0, L0 = rs.initial["R"], rs.initial["L"]
    if not (0.02 <= R0 <= 0.98):
        raise ValueError("anchoring requires an initial timely-completion R(0) strictly between 0.02 and 0.98")
    Q0 = rs.Q0 if rs.Q0 > 0 else 10.0
    for _ in range(500):
        flex0 = equilibrium_flex(m, X0, Z0, D0, Q0)
        mu0, _, _ = capacity(m, X0, Z0, D0, flex0)
        new_q = mu0 * (1.0 / R0 - 1.0)
        if abs(new_q - Q0) < 1e-10:
            break
        Q0 = new_q
    flex0 = equilibrium_flex(m, X0, Z0, D0, Q0)
    mu0, _, _ = capacity(m, X0, Z0, D0, flex0)
    _, Qp0 = pressure(Q0, mu0, m.w_half)
    mult = _term_product(m.inflow_terms, X0, Z0, D0)
    if mult <= 0:
        raise ValueError("inflow multipliers are zero at the initial state; cannot anchor demand")
    I_base = mu0 / mult
    Y0 = np.array([R0, L0, Qp0])
    b = X0 - (m.A @ X0 + m.Gamma @ Z0 + m.Pi @ Y0 + m.G @ D0)
    b_L = L0 - float(m.L_state @ X0 + m.L_ctx @ Z0 + m.L_qp * Qp0 + m.L_ext @ D0)
    return {"Q0": float(Q0), "I_base": float(I_base), "flex0": float(flex0), "mu0": float(mu0), "Qp0": float(Qp0),
            "b": {s: float(v) for s, v in zip(STATE_VARS, b)}, "b_L": float(b_L),
            "context_used": {s: float(v) for s, v in zip(CONTEXT_VARS, Z0)}}


def apply_anchor(cfg: dict[str, Any], anchor: dict[str, Any]) -> dict[str, Any]:
    import copy
    new = copy.deepcopy(cfg)
    for s, v in anchor["b"].items():
        set_value(new, f"b.{s}", round(v, 6))
    set_value(new, "b.L", round(anchor["b_L"], 6))
    set_value(new, "flow.I_base", round(anchor["I_base"], 6))
    new["initial_stock"]["Q"] = round(anchor["Q0"], 6)
    return new
