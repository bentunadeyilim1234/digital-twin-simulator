"""Anchor the illustrative demonstration parameter set so the demo baseline starts in equilibrium.

Standard system-dynamics practice (Sterman, 2000, ch. 13) is to initialise a model in
equilibrium so that differences between scenarios isolate the effect of the scenario
inputs. This script derives — transparently and reproducibly — the values that make the
SYNTHETIC demonstration initial state (Section 19) a steady state of the baseline:

  1. Stock-flow equilibrium: incoming requests equal processing capacity (I = μ) and the
     completion ratio equals the demonstration R(0):  Q0 = μ0·(1/R0 - 1),
     with reallocated hours at their B1 fixed point.
  2. Intercepts b so that X*(0) = X(0):   b = X0 - (A·X0 + Γ·Z0 + Π·Y0 + G·D0).
  3. Follow-up intercept b_L so that the follow-up equation reproduces L(0).

The derived numbers are as illustrative as the coefficients they are derived from.
Run:  backend/.venv/bin/python scripts/anchor_demo_baseline.py [--write]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from twin_engine.config import validate_config  # noqa: E402
from twin_engine.model import compile_model  # noqa: E402
from twin_engine.schemas import CONTEXT_VARS, STATE_VARS  # noqa: E402
from twin_engine.simulator import _term_product, capacity, equilibrium_flex, pressure  # noqa: E402


def derive(cfg: dict) -> dict:
    m = compile_model(cfg)
    init = {v["symbol"]: v["initial"] for v in cfg["variables"]}
    X0 = np.array([init[s] for s in STATE_VARS])
    Z0 = np.array([init[s] for s in CONTEXT_VARS])
    D0 = np.array([e["default"] for e in cfg["external_conditions"]])
    R0, L0 = init["R"], init["L"]

    Q0 = float(cfg["initial_stock"]["Q"])
    for _ in range(200):
        flex0 = equilibrium_flex(m, X0, Z0, D0, Q0)
        mu0, _, _ = capacity(m, X0, Z0, D0, flex0)
        newQ = mu0 * (1.0 / R0 - 1.0)
        if abs(newQ - Q0) < 1e-10:
            break
        Q0 = newQ
    flex0 = equilibrium_flex(m, X0, Z0, D0, Q0)
    mu0, _, _ = capacity(m, X0, Z0, D0, flex0)
    _, Qp0 = pressure(Q0, mu0, m.w_half)
    I_base = mu0 / _term_product(m.inflow_terms, X0, Z0, D0)

    m.I_base = I_base
    Y0 = np.array([R0, L0, Qp0])
    b = X0 - (m.A @ X0 + m.Gamma @ Z0 + m.Pi @ Y0 + m.G @ D0)
    b_L = L0 - (m.L_state @ X0 + m.L_ctx @ Z0 + m.L_qp * Qp0 + m.L_ext @ D0)
    return {"Q0": Q0, "I_base": I_base, "flex0": flex0, "mu0": mu0, "Qp0": Qp0,
            "b": {s: float(v) for s, v in zip(STATE_VARS, b)}, "b_L": float(b_L)}


def write(path: Path, res: dict) -> None:
    text = path.read_text(encoding="utf-8")

    def set_param(pid: str, value: float) -> None:
        nonlocal text
        pat = re.compile(r'(\{"id": "' + re.escape(pid) + r'"[^\n]*?"value": )(-?[0-9.eE+-]+)')
        text, n = pat.subn(lambda mm: mm.group(1) + f"{value:.6f}", text)
        if n != 1:
            raise RuntimeError(f"could not update {pid}")

    for s, v in res["b"].items():
        set_param(f"b.{s}", v)
    set_param("b.L", res["b_L"])
    set_param("flow.I_base", res["I_base"])
    text, n = re.subn(r'"initial_stock": \{"Q": [0-9.]+', f'"initial_stock": {{"Q": {res["Q0"]:.6f}', text)
    if n != 1:
        raise RuntimeError("could not update initial_stock.Q")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    path = ROOT / "config" / "model_config.json"
    cfg = validate_config(json.loads(path.read_text(encoding="utf-8")))
    res = derive(cfg)
    print(json.dumps(res, indent=2))
    if "--write" in sys.argv:
        write(path, res)
        print(f"written to {path}")
