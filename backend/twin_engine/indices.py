"""Preventive system readiness indices (Section 10).

ENV = weighted_mean(E, F, O, M)     SOC = weighted_mean(C, T, J, H)
ORG = weighted_mean(A, R, L, K)     SUP = weighted_mean(S, TR, P, IF)
TOTAL = Σ w_d · domain_d  (domain weights normalised to sum to 1)
MIN_DOMAIN = min(ENV, SOC, ORG, SUP)  — exposes a weak domain that TOTAL could mask.

These are institutional readiness/process indicators. They are NOT probabilities of
violence or attack and must never be presented as such.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .schemas import ALL_VARS, DOMAINS

if TYPE_CHECKING:  # pragma: no cover
    from .model import CompiledModel

IDX = {s: i for i, s in enumerate(ALL_VARS)}


def domain_indices(V: np.ndarray, m: "CompiledModel") -> dict[str, np.ndarray]:
    V = np.atleast_2d(V)
    out: dict[str, np.ndarray] = {}
    for d in DOMAINS:
        syms = m.domain_vars[d]
        w = np.array([m.var_weights.get(s, 1.0) for s in syms], dtype=float)
        vals = V[:, [IDX[s] for s in syms]]
        mask = np.isfinite(vals)
        wm = np.where(mask, w[None, :], 0.0)
        denom = wm.sum(axis=1)
        num = np.where(mask, vals, 0.0) @ w
        out[d] = np.where(denom > 0, num / np.where(denom > 0, denom, 1.0), np.nan)
    dw = np.array([max(0.0, m.domain_weights[d]) for d in DOMAINS], dtype=float)
    dw = dw / dw.sum() if dw.sum() > 0 else np.full(len(DOMAINS), 1 / len(DOMAINS))
    stack = np.vstack([out[d] for d in DOMAINS]).T
    out["TOTAL"] = stack @ dw
    out["MIN_DOMAIN"] = np.min(stack, axis=1)
    return out


def normalised_domain_weights(m: "CompiledModel") -> dict[str, float]:
    dw = np.array([max(0.0, m.domain_weights[d]) for d in DOMAINS], dtype=float)
    dw = dw / dw.sum() if dw.sum() > 0 else np.full(len(DOMAINS), 1 / len(DOMAINS))
    return {d: float(w) for d, w in zip(DOMAINS, dw)}
