"""Render the model equations from the live configuration (single source of truth).

Used by the API (Model Documentation page) and by scripts/generate_docs.py to produce
MATHEMATICAL_EQUATIONS.md and PARAMETER_REGISTRY.md, so documentation can never drift
from the coefficients the simulator actually uses.
"""

from __future__ import annotations

from typing import Any

from .params import list_parameters
from .schemas import CONTEXT_VARS, STATE_VARS


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def _param(cfg: dict[str, Any], pid: str) -> dict[str, Any]:
    return next(p for p in cfg["parameters"] if p["id"] == pid)


def target_equations(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for sym in STATE_VARS:
        b = _param(cfg, f"b.{sym}")
        terms = [e for e in cfg["edges"] if e["kind"] == "linear" and e["target"] == sym]
        s_parts, n_parts = [b["symbol"]], [_fmt(b["value"])]
        for e in terms:
            if not e["enabled"]:
                continue
            op = "+" if e["sign"] > 0 else "−"
            s_parts.append(f"{op} {e['symbol'] or e['id']}·{e['source']}")
            n_parts.append(f"{op} {_fmt(e['coefficient'])}·{e['source']}")
        lam = _param(cfg, f"lambda.{sym}")
        out.append({
            "target": sym, "kind": "state",
            "symbolic": f"{sym}* = clip({' '.join(s_parts)}, 0, 1)",
            "numeric": f"{sym}* = clip({' '.join(n_parts)}, 0, 1)",
            "transition": f"{sym}(t+1) = clip({sym}(t) + {lam['symbol']}·({sym}* − {sym}(t)), 0, 1),  {lam['symbol']} = {_fmt(lam['value'])}",
            "terms": [{"edge_id": e["id"], "symbol": e["symbol"], "source": e["source"], "sign": e["sign"],
                       "coefficient": e["coefficient"], "evidence": e["evidence"], "enabled": e["enabled"],
                       "hypothesis": e.get("hypothesis")} for e in terms],
        })
    return out


def context_equations(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    lz = _param(cfg, "lambda.context")
    out = []
    for sym in CONTEXT_VARS:
        terms = [e for e in cfg["edges"] if e["kind"] == "context_response" and e["target"] == sym and e["enabled"]]
        if not terms:
            out.append({"target": sym, "kind": "context", "symbolic": f"{sym}(t) = {sym}_obs(t)", "numeric": f"{sym}(t) = {sym}_obs(t)", "terms": []})
            continue
        parts_s, parts_n = [], []
        for e in terms:
            op = "+" if e["sign"] > 0 else "−"
            src = f"({e['source']}(t) − {e['source']}(0))" if e["source"] in STATE_VARS else f"{e['source']}(t)"
            parts_s.append(f"{op} {e['symbol']}·{src}")
            parts_n.append(f"{op} {_fmt(e['coefficient'])}·{src}")
        out.append({
            "target": sym, "kind": "context",
            "symbolic": f"Δ{sym}(t+1) = Δ{sym}(t) + λ_Z·({' '.join(parts_s).lstrip('+ ')} − Δ{sym}(t));  {sym}(t) = clip({sym}_obs(t) + Δ{sym}(t), 0, 1)",
            "numeric": f"Δ{sym}(t+1) = Δ{sym}(t) + {_fmt(lz['value'])}·({' '.join(parts_n).lstrip('+ ')} − Δ{sym}(t))",
            "terms": [{"edge_id": e["id"], "symbol": e["symbol"], "source": e["source"], "sign": e["sign"],
                       "coefficient": e["coefficient"], "evidence": e["evidence"]} for e in terms],
        })
    return out


def flow_equations(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    p = {x["id"]: x for x in cfg["parameters"]}
    edges = [e for e in cfg["edges"] if e["enabled"]]
    inflow = [e for e in edges if e["kind"] == "flow_multiplier" and e["target"] == "I"]
    eff = [e for e in edges if e["kind"] == "flow_multiplier" and e["target"] == "mu"]
    gain = next((e for e in edges if e["kind"] == "feedback_gain"), None)
    L_terms = [e for e in edges if e["kind"] == "derived" and e["target"] == "L"]
    svar = next(v for v in cfg["variables"] if v["symbol"] == "S")["measurement"]

    def mult(es):
        return " · ".join(f"max(0, 1 {'+' if e['sign'] > 0 else '−'} {_fmt(e['coefficient'])}·({e['source']} − {e.get('reference', 0.5)}))" for e in es) or "1"
    L_num = " ".join(f"{'+' if e['sign'] > 0 else '−'} {_fmt(e['coefficient'])}·{e['source']}" for e in L_terms)
    return [
        {"name": "Stock", "symbolic": "Q(t) = max(0, Q(t−1) + I(t) − C_flow(t))", "numeric": f"Q(0) = {cfg['initial_stock']['Q']:.2f} processes"},
        {"name": "Capacity constraint", "symbolic": "C_flow(t) = min(Q(t−1) + I(t), μ(t))", "numeric": ""},
        {"name": "Inflow", "symbolic": "I(t) = I₀ · Π_k max(0, 1 + κ_k·(x_k(t) − ref_k))",
         "numeric": f"I(t) = {_fmt(p['flow.I_base']['value'])} · {mult(inflow)}"},
        {"name": "Support hours", "symbolic": "hours(t) = L_S + S(t)·(U_S − L_S)",
         "numeric": f"hours(t) = {svar['lower']} + S(t)·{svar['upper'] - svar['lower']} h/month"},
        {"name": "Processing capacity", "symbolic": "μ(t) = (hours(t)·φ + flex(t)) · eff(t) / h",
         "numeric": f"μ(t) = (hours(t)·{_fmt(p['flow.alloc_share']['value'])} + flex(t)) · {mult(eff)} / {_fmt(p['flow.h_proc']['value'])}"},
        {"name": "Backlog pressure", "symbolic": "W(t) = Q(t)/μ(t);  Qp(t) = W(t)/(W(t) + w½)",
         "numeric": f"w½ = {_fmt(p['flow.w_half']['value'])} months"},
        {"name": "Reallocated hours (loop B1)", "symbolic": "flex(t+1) = flex(t) + λ_flex·(β_B1·Qp(t)·H_flex − flex(t))",
         "numeric": f"λ_flex = {_fmt(p['flow.lambda_flex']['value'])}, β_B1 = {_fmt(gain['coefficient']) if gain else '0 (disabled)'}, H_flex = {_fmt(p['flow.flex_max_hours']['value'])} h"},
        {"name": "Timely completion (derived R)", "symbolic": "R(t) = C_flow(t) / (Q(t−1) + I(t))", "numeric": ""},
        {"name": "Follow-up continuity (derived L)", "symbolic": "L(t) = clip(b_L + Σ ω·x(t) − ω_LQ·Qp(t), 0, 1)",
         "numeric": f"L(t) = clip({_fmt(p['b.L']['value'])} {L_num}, 0, 1)"},
    ]


def index_equations(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    w = {d: next(p for p in cfg["parameters"] if p["id"] == f"weights.domain.{d}")["value"] for d in ("ENV", "SOC", "ORG", "SUP")}
    tot = sum(w.values()) or 1
    return [{"name": d["id"], "symbolic": f"{d['id']} = weighted_mean({', '.join(d['variables'])})",
             "numeric": f"weights {[cfg['variable_weights'][s] for s in d['variables']]}"} for d in cfg["domains"]] + [
        {"name": "TOTAL", "symbolic": "TOTAL = Σ_d w_d·domain_d,  Σ w_d = 1",
         "numeric": " + ".join(f"{w[d] / tot:.3f}·{d}" for d in w)},
        {"name": "MIN_DOMAIN", "symbolic": "MIN_DOMAIN = min(ENV, SOC, ORG, SUP)", "numeric": ""},
    ]


def all_equations(cfg: dict[str, Any]) -> dict[str, Any]:
    return {"general": [
        "X(t+1) = clip[X(t) + Λ·(X*(t) − X(t)), 0, 1]",
        "X*(t) = clip[b + A·X(t) + Γ·Z(t) + Π·Y(t) + B·U(t) + G·D(t), 0, 1],  Y = [R, L, Qp]",
        "Z(t) = clip[Z_obs(t) + ΔZ(t), 0, 1],  ΔZ(t+1) = ΔZ(t) + λ_Z·(Ω·(X(t) − X(0)) + B_z·U(t) + G_z·D(t) − ΔZ(t))",
    ], "state": target_equations(cfg), "context": context_equations(cfg), "flows": flow_equations(cfg),
        "indices": index_equations(cfg), "parameters": list_parameters(cfg, include_disabled=True)}
