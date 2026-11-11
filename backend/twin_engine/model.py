"""Compile the authoritative configuration into explicit matrices.

Target-state equation (Section 08 of the specification), with the derived operational
indicators Y(t) = [R, L, Qp] written as an explicit block of the augmented context:

    X*(t) = clip( b + A·X(t) + Γ·Z(t) + Π·Y(t) + B·U(t) + G·D(t), 0, 1 )
    X(t+1) = clip( X(t) + Λ·(X*(t) - X(t)), 0, 1 )

Equivalently Γ̃ = [Γ Π] acts on the augmented vector Z̃ = [Z; Y].

Observed context indicators respond to the state as a lagged deviation Δz from their
observed path:

    Δz(t+1) = Δz(t) + λ_Z·( Ω·(X(t) - X(0)) + B_z·U(t) + G_z·D(t) - Δz(t) )
    Z(t)    = clip( Z_obs(t) + Δz(t), 0, 1 )

Every coefficient lives in exactly one matrix cell (``param_slots`` maps parameter ids to
cells), so the causal graph, the parameter registry and the simulator share one source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .schemas import CONTEXT_VARS, DOMAINS, OPERATIONAL_VARS, STATE_VARS

NS, NZ, NY = len(STATE_VARS), len(CONTEXT_VARS), len(OPERATIONAL_VARS)
SIDX = {s: i for i, s in enumerate(STATE_VARS)}
ZIDX = {s: i for i, s in enumerate(CONTEXT_VARS)}
YIDX = {s: i for i, s in enumerate(OPERATIONAL_VARS)}

# Source categories for multiplicative flow terms
SRC_STATE, SRC_CONTEXT, SRC_EXTERNAL = 0, 1, 2


@dataclass
class CompiledModel:
    interventions: list[str]
    externals: list[str]
    b: np.ndarray
    A: np.ndarray
    Gamma: np.ndarray
    Pi: np.ndarray
    B: np.ndarray
    G: np.ndarray
    Lam: np.ndarray
    Omega: np.ndarray
    Bz: np.ndarray
    Gz: np.ndarray
    lambda_z: float
    # Follow-up continuity equation L = clip(b_L + wX·X + wZ·Z + wQ·Qp + wD·D)
    L_base: float
    L_state: np.ndarray
    L_ctx: np.ndarray
    L_qp: float
    L_ext: np.ndarray
    # Multiplicative flow modifiers: arrays (src_type, src_index, signed_coef, reference)
    inflow_terms: np.ndarray
    eff_terms: np.ndarray
    b1_gain: float
    I_base: float
    alloc_share: float
    h_proc: float
    w_half: float
    flex_max: float
    lambda_flex: float
    S_lower: float
    S_upper: float
    S_direction: str
    domain_weights: dict[str, float]
    var_weights: dict[str, float]
    domain_vars: dict[str, list[str]]
    costs: np.ndarray
    initial_Q: float
    flex_init: Any
    param_slots: dict[str, Callable[["CompiledModel", float], None]] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    def copy(self) -> "CompiledModel":
        new = CompiledModel(**{k: (v.copy() if isinstance(v, np.ndarray) else (dict(v) if isinstance(v, dict) else v))
                              for k, v in self.__dict__.items()})
        new.param_slots = self.param_slots  # setters are stateless closures over the target object argument
        return new

    def with_params(self, values: dict[str, float]) -> "CompiledModel":
        """Return a copy with parameter values replaced (fast path for UQ / SA / calibration)."""
        new = self.copy()
        for pid, v in values.items():
            setter = self.param_slots.get(pid)
            if setter is None:
                raise KeyError(f"parameter '{pid}' is not an active slot in the compiled model (disabled edge or unknown id)")
            setter(new, float(v))
        return new

    def hours_from_S(self, S: float) -> float:
        span = self.S_upper - self.S_lower
        return self.S_lower + S * span if self.S_direction == "positive" else self.S_upper - S * span


def _setter_matrix(name: str, i: int, j: int, sign: int) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        getattr(m, name)[i, j] = sign * v
    return _set


def _setter_vec(name: str, i: int, sign: int = 1) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        getattr(m, name)[i] = sign * v
    return _set


def _setter_scalar(name: str, sign: int = 1) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        setattr(m, name, sign * v)
    return _set


def _setter_term(name: str, row: int, sign: int) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        getattr(m, name)[row, 2] = sign * v
    return _set


def _setter_domain_weight(dom: str) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        m.domain_weights[dom] = v
    return _set


def _setter_cost(idx: int) -> Callable[[CompiledModel, float], None]:
    def _set(m: CompiledModel, v: float) -> None:
        m.costs[idx] = v
    return _set


def compile_model(cfg: dict[str, Any]) -> CompiledModel:
    iv = [i["key"] for i in cfg["interventions"]]
    ex = [e["key"] for e in cfg["external_conditions"]]
    UIDX = {k: i for i, k in enumerate(iv)}
    DIDX = {k: i for i, k in enumerate(ex)}
    params = {p["id"]: p for p in cfg["parameters"]}
    slots: dict[str, Callable[[CompiledModel, float], None]] = {}

    b = np.array([params[f"b.{s}"]["value"] for s in STATE_VARS], dtype=float)
    for s in STATE_VARS:
        slots[f"b.{s}"] = _setter_vec("b", SIDX[s])

    A = np.zeros((NS, NS)); Gamma = np.zeros((NS, NZ)); Pi = np.zeros((NS, NY))
    B = np.zeros((NS, len(iv))); G = np.zeros((NS, len(ex)))
    Omega = np.zeros((NZ, NS)); Bz = np.zeros((NZ, len(iv))); Gz = np.zeros((NZ, len(ex)))
    L_state = np.zeros(NS); L_ctx = np.zeros(NZ); L_ext = np.zeros(len(ex)); L_qp = 0.0
    inflow: list[list[float]] = []; eff: list[list[float]] = []
    b1_gain = 0.0

    def src_ref(name: str) -> tuple[int, int]:
        if name in SIDX:
            return SRC_STATE, SIDX[name]
        if name in ZIDX:
            return SRC_CONTEXT, ZIDX[name]
        if name in DIDX:
            return SRC_EXTERNAL, DIDX[name]
        raise ValueError(f"invalid flow-term source {name}")

    for e in cfg["edges"]:
        if not e["enabled"] or e["kind"] == "structural":
            continue
        sgn, c, s, t, pid = int(e["sign"]), float(e["coefficient"]), e["source"], e["target"], f"edge.{e['id']}"
        k = e["kind"]
        if k == "linear":
            i = SIDX[t]
            if s in SIDX:
                A[i, SIDX[s]] = sgn * c; slots[pid] = _setter_matrix("A", i, SIDX[s], sgn)
            elif s in ZIDX:
                Gamma[i, ZIDX[s]] = sgn * c; slots[pid] = _setter_matrix("Gamma", i, ZIDX[s], sgn)
            elif s in YIDX:
                Pi[i, YIDX[s]] = sgn * c; slots[pid] = _setter_matrix("Pi", i, YIDX[s], sgn)
            elif s in UIDX:
                B[i, UIDX[s]] = sgn * c; slots[pid] = _setter_matrix("B", i, UIDX[s], sgn)
            elif s in DIDX:
                G[i, DIDX[s]] = sgn * c; slots[pid] = _setter_matrix("G", i, DIDX[s], sgn)
            else:
                raise ValueError(f"edge {e['id']}: unresolvable source {s}")
        elif k == "context_response":
            j = ZIDX[t]
            if s in SIDX:
                Omega[j, SIDX[s]] = sgn * c; slots[pid] = _setter_matrix("Omega", j, SIDX[s], sgn)
            elif s in UIDX:
                Bz[j, UIDX[s]] = sgn * c; slots[pid] = _setter_matrix("Bz", j, UIDX[s], sgn)
            elif s in DIDX:
                Gz[j, DIDX[s]] = sgn * c; slots[pid] = _setter_matrix("Gz", j, DIDX[s], sgn)
            else:
                raise ValueError(f"edge {e['id']}: unresolvable source {s}")
        elif k == "derived":
            if s in SIDX:
                L_state[SIDX[s]] = sgn * c; slots[pid] = _setter_vec("L_state", SIDX[s], sgn)
            elif s in ZIDX:
                L_ctx[ZIDX[s]] = sgn * c; slots[pid] = _setter_vec("L_ctx", ZIDX[s], sgn)
            elif s == "Qp":
                L_qp = sgn * c; slots[pid] = _setter_scalar("L_qp", sgn)
            elif s in DIDX:
                L_ext[DIDX[s]] = sgn * c; slots[pid] = _setter_vec("L_ext", DIDX[s], sgn)
        elif k == "flow_multiplier":
            st, si = src_ref(s)
            row = [st, si, sgn * c, float(e.get("reference", 0.5))]
            if t == "I":
                slots[pid] = _setter_term("inflow_terms", len(inflow), sgn); inflow.append(row)
            else:
                slots[pid] = _setter_term("eff_terms", len(eff), sgn); eff.append(row)
        elif k == "feedback_gain":
            b1_gain = sgn * c; slots[pid] = _setter_scalar("b1_gain", sgn)

    Lam = np.diag([params[f"lambda.{s}"]["value"] for s in STATE_VARS]).astype(float)
    for s in STATE_VARS:
        slots[f"lambda.{s}"] = (lambda i: (lambda m, v: m.Lam.__setitem__((i, i), v)))(SIDX[s])
    for od in cfg.get("transition_offdiagonal", []):
        Lam[SIDX[od["row"]], SIDX[od["col"]]] = float(od["value"])
    slots["lambda.context"] = _setter_scalar("lambda_z")
    slots["b.L"] = _setter_scalar("L_base")

    scalar_map = {
        "flow.I_base": "I_base", "flow.alloc_share": "alloc_share", "flow.h_proc": "h_proc",
        "flow.w_half": "w_half", "flow.flex_max_hours": "flex_max", "flow.lambda_flex": "lambda_flex",
    }
    for pid, attr in scalar_map.items():
        slots[pid] = _setter_scalar(attr)
    for d in DOMAINS:
        slots[f"weights.domain.{d}"] = _setter_domain_weight(d)
    costs = np.array([params[i["cost_param"]]["value"] if i["cost_param"] in params else 0.0 for i in cfg["interventions"]], dtype=float)
    for idx, i in enumerate(cfg["interventions"]):
        slots[i["cost_param"]] = _setter_cost(idx)

    svar = next(v for v in cfg["variables"] if v["symbol"] == "S")
    m = CompiledModel(
        interventions=iv, externals=ex, b=b, A=A, Gamma=Gamma, Pi=Pi, B=B, G=G, Lam=Lam,
        Omega=Omega, Bz=Bz, Gz=Gz, lambda_z=float(params["lambda.context"]["value"]),
        L_base=float(params["b.L"]["value"]), L_state=L_state, L_ctx=L_ctx, L_qp=L_qp, L_ext=L_ext,
        inflow_terms=np.array(inflow, dtype=float).reshape(-1, 4),
        eff_terms=np.array(eff, dtype=float).reshape(-1, 4),
        b1_gain=b1_gain,
        I_base=float(params["flow.I_base"]["value"]), alloc_share=float(params["flow.alloc_share"]["value"]),
        h_proc=float(params["flow.h_proc"]["value"]), w_half=float(params["flow.w_half"]["value"]),
        flex_max=float(params["flow.flex_max_hours"]["value"]), lambda_flex=float(params["flow.lambda_flex"]["value"]),
        S_lower=float(svar["measurement"]["lower"]), S_upper=float(svar["measurement"]["upper"]),
        S_direction=svar["measurement"]["direction"],
        domain_weights={d: float(params[f"weights.domain.{d}"]["value"]) for d in DOMAINS},
        var_weights={k: float(v) for k, v in cfg["variable_weights"].items()},
        domain_vars={d["id"]: list(d["variables"]) for d in cfg["domains"]},
        costs=costs,
        initial_Q=float(cfg["initial_stock"].get("Q", 0.0)),
        flex_init=cfg["initial_stock"].get("flex", "equilibrium"),
    )
    m.param_slots = slots
    check_dimensions(m)
    return m


def check_dimensions(m: CompiledModel) -> None:
    nu, nd = len(m.interventions), len(m.externals)
    expected = {
        "b": (NS,), "A": (NS, NS), "Gamma": (NS, NZ), "Pi": (NS, NY), "B": (NS, nu), "G": (NS, nd),
        "Lam": (NS, NS), "Omega": (NZ, NS), "Bz": (NZ, nu), "Gz": (NZ, nd),
        "L_state": (NS,), "L_ctx": (NZ,), "L_ext": (nd,), "costs": (nu,),
    }
    for name, shape in expected.items():
        arr = getattr(m, name)
        if arr.shape != shape:
            raise ValueError(f"matrix {name} has shape {arr.shape}, expected {shape}")
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"matrix {name} contains non-finite values")
    if m.inflow_terms.shape[1] != 4 or m.eff_terms.shape[1] != 4:
        raise ValueError("flow term arrays must have 4 columns")
    lam_diag = np.diag(m.Lam)
    if np.any(lam_diag < 0) or np.any(lam_diag > 1):
        raise ValueError("transition speeds λ must lie in [0, 1]")
    if m.h_proc <= 0:
        raise ValueError("hours per process must be positive")
    if m.w_half <= 0:
        raise ValueError("w_half must be positive")


def linear_stability(m: CompiledModel) -> dict[str, Any]:
    """Spectral radius of the linear part of the coupled [X, Δz] update (clipping and the
    nonlinear stock-flow terms excluded). ρ < 1 indicates locally contracting dynamics."""
    I7 = np.eye(NS)
    top = np.hstack([I7 + m.Lam @ (m.A - I7), m.Lam @ m.Gamma])
    bot = np.hstack([m.lambda_z * m.Omega, (1 - m.lambda_z) * np.eye(NZ)])
    J = np.vstack([top, bot])
    eig = np.linalg.eigvals(J)
    rho = float(np.max(np.abs(eig)))
    return {
        "spectral_radius": rho,
        "stable": bool(rho < 1.0),
        "eigenvalues": [{"re": float(z.real), "im": float(z.imag)} for z in sorted(eig, key=lambda z: -abs(z))],
        "note": "Linearised [X, Δz] update; excludes clipping and the stock-flow nonlinearities.",
    }


def matrices_as_json(m: CompiledModel) -> dict[str, Any]:
    return {
        "state": list(STATE_VARS), "context": list(CONTEXT_VARS), "operational": list(OPERATIONAL_VARS),
        "interventions": m.interventions, "externals": m.externals,
        "b": m.b.tolist(), "A": m.A.tolist(), "Gamma": m.Gamma.tolist(), "Pi": m.Pi.tolist(),
        "B": m.B.tolist(), "G": m.G.tolist(), "Lambda": m.Lam.tolist(), "Omega": m.Omega.tolist(),
        "Bz": m.Bz.tolist(), "Gz": m.Gz.tolist(), "lambda_z": m.lambda_z,
        "follow_up": {"b_L": m.L_base, "state": m.L_state.tolist(), "context": m.L_ctx.tolist(), "Qp": m.L_qp, "external": m.L_ext.tolist()},
    }
