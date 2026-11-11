"""Parameter registry: one flat view over every numeric model parameter.

Edge coefficients are addressed as ``edge.<edge_id>`` and stored on the edge itself
(single source of truth); all other parameters live in ``cfg['parameters']``.
"""

from __future__ import annotations

import copy
from typing import Any, Optional


def list_parameters(cfg: dict[str, Any], include_disabled: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in cfg["edges"]:
        if e["kind"] == "structural":
            continue
        if not e["enabled"] and not include_disabled:
            continue
        out.append({
            "id": f"edge.{e['id']}", "group": "edge", "symbol": e.get("symbol") or e["id"], "value": e["coefficient"],
            "sign": e["sign"], "min": 0.0, "max": 5.0, "range": e.get("range"), "unit": "normalised effect",
            "provenance": "hypothesized" if e["evidence"] == "H" else "illustrative" if e["evidence"] in ("E1", "E2") else "calibrated",
            "evidence": e["evidence"], "edge_id": e["id"], "source": e["source"], "target": e["target"], "kind": e["kind"],
            "enabled": e["enabled"], "description": e.get("description", {}),
            "literature_ranges": e.get("literature_ranges", []), "expert_range": e.get("expert_range"),
            "calibration": e.get("calibration"),
        })
    for p in cfg["parameters"]:
        out.append({**p})
    return out


def _find(cfg: dict[str, Any], pid: str) -> tuple[str, dict[str, Any]]:
    if pid.startswith("edge."):
        eid = pid[5:]
        for e in cfg["edges"]:
            if e["id"] == eid:
                if e["kind"] == "structural":
                    raise ValueError(f"{pid} is a structural accounting identity and is not a free parameter")
                return "edge", e
        raise KeyError(f"unknown edge parameter {pid}")
    for p in cfg["parameters"]:
        if p["id"] == pid:
            return "param", p
    raise KeyError(f"unknown parameter {pid}")


def get_value(cfg: dict[str, Any], pid: str) -> float:
    kind, obj = _find(cfg, pid)
    return float(obj["coefficient"] if kind == "edge" else obj["value"])


def get_range(cfg: dict[str, Any], pid: str) -> Optional[tuple[float, float]]:
    kind, obj = _find(cfg, pid)
    r = obj.get("range")
    return (float(r[0]), float(r[1])) if r else None


def get_bounds(cfg: dict[str, Any], pid: str) -> tuple[float, float]:
    kind, obj = _find(cfg, pid)
    if kind == "edge":
        return 0.0, 5.0
    return float(obj["min"]), float(obj["max"])


def set_value(cfg: dict[str, Any], pid: str, value: float) -> None:
    """Mutates cfg in place, enforcing hard bounds."""
    kind, obj = _find(cfg, pid)
    lo, hi = get_bounds(cfg, pid)
    v = float(value)
    if not (lo - 1e-12 <= v <= hi + 1e-12):
        raise ValueError(f"{pid}: value {v} outside hard bounds [{lo}, {hi}]")
    if kind == "edge":
        obj["coefficient"] = v
    else:
        obj["value"] = v


def apply_overrides(cfg: dict[str, Any], overrides: dict[str, float]) -> dict[str, Any]:
    new = copy.deepcopy(cfg)
    for pid, v in overrides.items():
        set_value(new, pid, v)
    return new


def uncertain_parameters(cfg: dict[str, Any], groups: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Enabled parameters that carry an uncertainty range (used by UQ / SA defaults)."""
    out = []
    for p in list_parameters(cfg):
        if not p.get("range"):
            continue
        if groups and p["group"] not in groups:
            continue
        lo, hi = p["range"]
        if hi > lo:
            out.append(p)
    return out
