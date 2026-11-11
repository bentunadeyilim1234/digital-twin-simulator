"""FastAPI service exposing the authoritative simulation engine.

The API is a thin layer: every number it returns is computed by ``twin_engine``.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from twin_engine import ENGINE_VERSION, config_hash, default_config, templates, validate_config
from twin_engine.anchoring import apply_anchor, derive_anchor
from twin_engine.calibration import (DEFAULT_BAYES_PARAMS, DEFAULT_CAL_PARAMS, PYMC_AVAILABLE, apply_calibration,
                                     calibrate_bayes, calibrate_lsq)
from twin_engine.config import references
from twin_engine.datasets import DATA_CLASSES, DatasetError, build_dataset, inspect, parse_upload, quality_report, to_csv
from twin_engine.equations import all_equations
from twin_engine.graph import build_graph
from twin_engine.model import compile_model, linear_stability, matrices_as_json
from twin_engine.normalization import NormSpec, normalize_series, to_json_list
from twin_engine.params import list_parameters, uncertain_parameters
from twin_engine.scenarios import comparability, instantiate_template, resolve
from twin_engine.schemas import ALL_VARS, EDITABLE_KINDS, Scenario
from twin_engine.sensitivity import SALIB_AVAILABLE, estimate_runs, run_sensitivity
from twin_engine.simulator import full_map_jacobian, simulate
from twin_engine.synthetic import generate
from twin_engine.uncertainty import run_uncertainty
from twin_engine.validation import (build_report, conceptual_validation, historical_validation, intervention_validation,
                                    validation_envelope, verification_suite)
from twin_engine.analysis_common import OUTPUT_KEYS

from . import db

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
WS_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

app = FastAPI(title="School Safety & Resilience Digital Twin API", version=ENGINE_VERSION,
              description="Deterministic institutional simulation engine. Outputs are readiness and process indicators, "
                          "never probabilities of violence or individual predictions.")

_origins = [o.strip() for o in os.environ.get("TWIN_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(DatasetError)
async def _dataset_error(_: Request, exc: DatasetError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": exc.errors})


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def _runtime_error(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ----------------------------------------------------------------------------- workspace
def _seed(ws: str) -> None:
    cfg = default_config()
    db.create_workspace(ws, cfg)
    row = db.get_workspace(ws)
    if row is not None and row["seeded"]:
        return
    for t in templates():
        sc = instantiate_template(cfg, t["id"])
        sc["labels"] = t["labels"]
        sc["id"] = f"{t['id'].lower()}_{ws[:8]}_{db.new_id('x')[-6:]}"
        db.upsert_scenario(ws, sc)
    ds = generate(cfg, months=36, seed=42, name="Synthetic demonstration series (seed 42)")
    db.save_dataset(ws, ds)
    db.mark_seeded(ws)


def workspace(x_workspace_id: Optional[str] = Header(default=None)) -> str:
    ws = x_workspace_id or "default"
    if not WS_RE.match(ws):
        raise HTTPException(400, "invalid workspace id")
    if db.get_workspace(ws) is None or not db.get_workspace(ws)["seeded"]:
        _seed(ws)
    return ws


def _cfg(ws: str) -> dict[str, Any]:
    return db.get_config(ws)


def _scenario_or_404(ws: str, sid: str) -> dict[str, Any]:
    sc = db.get_scenario(ws, sid)
    if sc is None:
        raise HTTPException(404, f"scenario {sid} not found")
    return sc


def _dataset_or_404(ws: str, did: Optional[str]) -> Optional[dict[str, Any]]:
    if not did:
        return None
    ds = db.get_dataset(ws, did)
    if ds is None:
        raise HTTPException(404, f"dataset {did} not found")
    return ds


# ----------------------------------------------------------------------------- meta
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "engine_version": ENGINE_VERSION,
            "capabilities": {"salib": SALIB_AVAILABLE, "statsmodels": importlib.util.find_spec("statsmodels") is not None,
                             "pymc": PYMC_AVAILABLE, "bayesian_backend": "numpy-adaptive-metropolis"}}


@app.get("/api/meta")
def meta(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    return {"engine_version": ENGINE_VERSION, "references": references(), "templates": templates(),
            "data_classes": DATA_CLASSES, "outputs": OUTPUT_KEYS, "variables": list(ALL_VARS),
            "default_calibration_params": DEFAULT_CAL_PARAMS, "default_bayes_params": DEFAULT_BAYES_PARAMS,
            "uncertain_parameters": [p["id"] for p in uncertain_parameters(cfg)], "capabilities": health()["capabilities"],
            "workspace": ws}


# ----------------------------------------------------------------------------- model
@lru_cache(maxsize=64)
def _verification_cached(h: str, cfg_json: str) -> dict[str, Any]:
    return verification_suite(json.loads(cfg_json))


@app.get("/api/model")
def get_model(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    return {"config": cfg, "hash": config_hash(cfg)}


@app.put("/api/model")
def put_model(body: dict[str, Any], ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = validate_config(body.get("config", body))
    db.save_config(ws, cfg)
    return {"config": cfg, "hash": config_hash(cfg)}


@app.post("/api/model/validate")
def validate_model(body: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_config(body.get("config", body))
        return {"valid": True, "errors": []}
    except ValueError as exc:
        return {"valid": False, "errors": str(exc).split("; ")}


@app.post("/api/model/reset")
def reset_model(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = default_config()
    db.save_config(ws, cfg)
    return {"config": cfg, "hash": config_hash(cfg)}


class EdgePatch(BaseModel):
    coefficient: Optional[float] = Field(default=None, ge=0, le=5)
    sign: Optional[Literal[1, -1]] = None
    enabled: Optional[bool] = None
    evidence: Optional[Literal["E1", "E2", "H", "L"]] = None
    confidence: Optional[Literal["low", "medium", "high"]] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    references: Optional[list[str]] = None
    range: Optional[tuple[float, float]] = None


def _find_edge(cfg: dict[str, Any], eid: str) -> dict[str, Any]:
    e = next((x for x in cfg["edges"] if x["id"] == eid), None)
    if e is None:
        raise HTTPException(404, f"relationship {eid} not found")
    return e


@app.patch("/api/model/edges/{eid}")
def patch_edge(eid: str, patch: EdgePatch, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = copy.deepcopy(_cfg(ws))
    e = _find_edge(cfg, eid)
    if e["kind"] == "structural":
        raise HTTPException(422, "structural (accounting) relationships cannot be edited")
    for k, v in patch.model_dump(exclude_none=True).items():
        e[k] = list(v) if k == "range" else v
    cfg = validate_config(cfg)
    db.save_config(ws, cfg)
    return {"edge": _find_edge(cfg, eid), "hash": config_hash(cfg)}


@app.post("/api/model/edges/{eid}/restore")
def restore_edge(eid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = copy.deepcopy(_cfg(ws))
    e = _find_edge(cfg, eid)
    if e.get("custom"):
        raise HTTPException(422, "custom relationships have no original assumption; delete instead")
    orig = next((x for x in default_config()["edges"] if x["id"] == eid), None)
    if orig is None:
        raise HTTPException(404, "original assumption not found")
    for k in ("sign", "coefficient", "enabled", "evidence", "confidence", "references", "range", "notes"):
        e[k] = orig[k]
    cfg = validate_config(cfg)
    db.save_config(ws, cfg)
    return {"edge": _find_edge(cfg, eid), "hash": config_hash(cfg)}


class NewEdge(BaseModel):
    source: str
    target: str
    kind: Literal["linear", "context_response", "derived"]
    sign: Literal[1, -1] = 1
    coefficient: float = Field(ge=0, le=5)
    evidence: Literal["E1", "E2", "H", "L"] = "H"
    confidence: Literal["low", "medium", "high"] = "low"
    description_en: str = ""
    description_tr: str = ""
    notes: str = ""
    references: list[str] = []


@app.post("/api/model/edges")
def add_edge(body: NewEdge, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = copy.deepcopy(_cfg(ws))
    eid = f"X-{body.source}-{body.target}"
    if any(e["id"] == eid for e in cfg["edges"]):
        raise HTTPException(409, f"relationship {eid} already exists")
    c = body.coefficient
    cfg["edges"].append({"id": eid, "source": body.source, "target": body.target, "kind": body.kind, "sign": body.sign,
                         "coefficient": c, "range": [max(0.0, c * 0.5), c * 1.5 if c > 0 else 0.1], "symbol": f"α_{body.target}{body.source}*",
                         "hypothesis": None, "evidence": body.evidence, "confidence": body.confidence, "references": body.references,
                         "enabled": True, "description": {"en": body.description_en, "tr": body.description_tr},
                         "notes": body.notes, "custom": True})
    cfg = validate_config(cfg)
    db.save_config(ws, cfg)
    return {"edge": _find_edge(cfg, eid), "hash": config_hash(cfg)}


@app.delete("/api/model/edges/{eid}")
def delete_edge(eid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = copy.deepcopy(_cfg(ws))
    e = _find_edge(cfg, eid)
    if not e.get("custom"):
        raise HTTPException(422, "only user-added relationships can be deleted; disable original assumptions instead")
    cfg["edges"] = [x for x in cfg["edges"] if x["id"] != eid]
    cfg["loops"] = [l for l in cfg["loops"] if eid not in l["edges"]]
    cfg = validate_config(cfg)
    db.save_config(ws, cfg)
    return {"deleted": eid, "hash": config_hash(cfg)}


class ParamPatch(BaseModel):
    value: Optional[float] = None
    range: Optional[tuple[float, float]] = None
    provenance: Optional[Literal["illustrative", "hypothesized", "expert", "literature", "calibrated"]] = None
    literature_ranges: Optional[list[dict[str, Any]]] = None
    expert_range: Optional[dict[str, Any]] = None


@app.get("/api/model/parameters")
def get_parameters(ws: str = Depends(workspace)) -> list[dict[str, Any]]:
    return list_parameters(_cfg(ws), include_disabled=True)


@app.patch("/api/model/parameters/{pid}")
def patch_parameter(pid: str, patch: ParamPatch, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = copy.deepcopy(_cfg(ws))
    data = patch.model_dump(exclude_none=True)
    if pid.startswith("edge."):
        e = _find_edge(cfg, pid[5:])
        if "value" in data:
            e["coefficient"] = data["value"]
        for k in ("range", "literature_ranges", "expert_range"):
            if k in data:
                e[k] = list(data[k]) if k == "range" else data[k]
    else:
        p = next((x for x in cfg["parameters"] if x["id"] == pid), None)
        if p is None:
            raise HTTPException(404, f"parameter {pid} not found")
        for k, v in data.items():
            p[k] = list(v) if k == "range" else v
    cfg = validate_config(cfg)
    db.save_config(ws, cfg)
    return {"parameter": next(x for x in list_parameters(cfg, include_disabled=True) if x["id"] == pid), "hash": config_hash(cfg)}


@app.get("/api/model/graph")
def model_graph(lang: str = "tr", ws: str = Depends(workspace)) -> dict[str, Any]:
    return build_graph(_cfg(ws), lang)


@app.get("/api/model/structure")
def model_structure(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    m = compile_model(cfg)
    base = next((s for s in db.list_scenarios(ws) if s.get("is_baseline")), None) or instantiate_template(cfg, "S0")
    rs, eff = resolve(cfg, base)
    return {"matrices": matrices_as_json(m), "linear_stability": linear_stability(m),
            "full_map_stability": full_map_jacobian(compile_model(eff), rs), "hash": config_hash(cfg)}


@app.get("/api/model/equations")
def model_equations(ws: str = Depends(workspace)) -> dict[str, Any]:
    return all_equations(_cfg(ws))


class AnchorBody(BaseModel):
    scenario_id: Optional[str] = None
    apply: bool = False


@app.post("/api/model/anchor")
def anchor(body: AnchorBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    sc = _scenario_or_404(ws, body.scenario_id) if body.scenario_id else (
        next((s for s in db.list_scenarios(ws) if s.get("is_baseline")), None) or instantiate_template(cfg, "S0"))
    res = derive_anchor(cfg, sc)
    if body.apply:
        cfg = validate_config(apply_anchor(cfg, res))
        db.save_config(ws, cfg)
    return {"anchor": res, "applied": body.apply, "hash": config_hash(cfg)}


# ----------------------------------------------------------------------------- scenarios
@app.get("/api/scenarios")
def get_scenarios(ws: str = Depends(workspace)) -> list[dict[str, Any]]:
    return db.list_scenarios(ws)


@app.get("/api/scenarios/templates")
def get_templates() -> list[dict[str, Any]]:
    return templates()


class ScenarioCreate(BaseModel):
    template_id: Optional[str] = None
    from_baseline: bool = True
    scenario: Optional[dict[str, Any]] = None
    name: Optional[str] = None


@app.post("/api/scenarios")
def create_scenario(body: ScenarioCreate, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    if body.scenario is not None:
        sc = json.loads(Scenario.model_validate(body.scenario).model_dump_json())
        sc["id"] = None
    else:
        sc = instantiate_template(cfg, body.template_id or "S0")
        t = next(x for x in templates() if x["id"] == (body.template_id or "S0"))
        sc["labels"] = t["labels"]
        sc["is_baseline"] = False if body.template_id != "S0" or body.name else sc["is_baseline"]
        if body.from_baseline:
            base = next((s for s in db.list_scenarios(ws) if s.get("is_baseline")), None)
            if base:  # identical initial/external/parameter conditions as the baseline (Section 14)
                for k in ("initial_state", "initial_stock", "external", "parameter_overrides", "context_schedule",
                          "horizon_months", "dataset_id", "dataset_anchor"):
                    sc[k] = copy.deepcopy(base.get(k, sc.get(k)))
    if body.name:
        sc["name"] = body.name
        sc.pop("labels", None)
    return db.upsert_scenario(ws, sc)


@app.get("/api/scenarios/{sid}")
def get_scenario(sid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    return _scenario_or_404(ws, sid)


@app.put("/api/scenarios/{sid}")
def put_scenario(sid: str, body: dict[str, Any], ws: str = Depends(workspace)) -> dict[str, Any]:
    old = _scenario_or_404(ws, sid)
    validated = json.loads(Scenario.model_validate(body).model_dump_json())
    validated["id"] = sid
    if body.get("labels") and body.get("name") == body["labels"].get("en"):
        validated["labels"] = body["labels"]
    if validated["dataset_id"]:
        _dataset_or_404(ws, validated["dataset_id"])
    resolve(_cfg(ws), validated, _dataset_or_404(ws, validated["dataset_id"]))  # fail fast on invalid scenarios
    if validated.get("is_baseline") and not old.get("is_baseline"):
        for s in db.list_scenarios(ws):
            if s.get("is_baseline") and s["id"] != sid:
                s["is_baseline"] = False
                db.upsert_scenario(ws, s)
    return db.upsert_scenario(ws, validated)


@app.delete("/api/scenarios/{sid}")
def remove_scenario(sid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    sc = _scenario_or_404(ws, sid)
    if sc.get("is_baseline") and sum(1 for s in db.list_scenarios(ws) if s.get("is_baseline")) <= 1:
        raise HTTPException(422, "the reference baseline cannot be deleted; mark another scenario as baseline first")
    db.delete_scenario(ws, sid)
    return {"deleted": sid}


class DuplicateBody(BaseModel):
    name: Optional[str] = None


@app.post("/api/scenarios/{sid}/duplicate")
def duplicate_scenario(sid: str, body: DuplicateBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    sc = copy.deepcopy(_scenario_or_404(ws, sid))
    sc["id"] = None
    sc["is_baseline"] = False
    sc["name"] = body.name or f"{sc['name']} (copy)"
    sc.pop("labels", None)
    return db.upsert_scenario(ws, sc)


@app.post("/api/scenarios/import")
def import_scenarios(body: dict[str, Any], ws: str = Depends(workspace)) -> dict[str, Any]:
    items = body.get("scenarios") if isinstance(body.get("scenarios"), list) else [body.get("scenario", body)]
    out = []
    for raw in items:
        sc = json.loads(Scenario.model_validate(raw).model_dump_json())
        sc["id"] = None
        sc["is_baseline"] = False
        resolve(_cfg(ws), sc)
        out.append(db.upsert_scenario(ws, sc))
    return {"imported": len(out), "scenarios": out}


# ----------------------------------------------------------------------------- simulation
class SimBody(BaseModel):
    scenario_id: Optional[str] = None
    scenario: Optional[dict[str, Any]] = None
    save: bool = False


def _summary(res: dict[str, Any]) -> dict[str, Any]:
    N = res["horizon"]
    return {"scenario_name": res["scenario_name"], "horizon": N,
            "indices_end": {k: v[N] for k, v in res["indices"].items()},
            "indices_start": {k: v[0] for k, v in res["indices"].items()},
            "Q_end": res["flows"]["Q"][N], "program_hours": res["resources"]["program_hours_total"]}


@app.post("/api/simulate")
def run_simulation(body: SimBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    if body.scenario is not None:
        sc = body.scenario
    elif body.scenario_id:
        sc = _scenario_or_404(ws, body.scenario_id)
    else:
        raise HTTPException(422, "provide scenario_id or scenario")
    res = simulate(cfg, sc, _dataset_or_404(ws, sc.get("dataset_id")))
    if body.save:
        res["run_id"] = db.save_run(ws, "simulation", res["scenario_name"] or "simulation", [sc.get("id") or ""], _summary(res), res)
    return res


class CompareBody(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=8)
    baseline_id: Optional[str] = None
    save: bool = False


def _delta(a: list[Optional[float]], b: list[Optional[float]]) -> list[Optional[float]]:
    return [None if x is None or y is None else x - y for x, y in zip(a, b)]


@app.post("/api/compare")
def compare(body: CompareBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    scs = [_scenario_or_404(ws, sid) for sid in body.scenario_ids]
    base_id = body.baseline_id or next((s["id"] for s in scs if s.get("is_baseline")), None) or scs[0]["id"]
    if base_id not in body.scenario_ids:
        scs.insert(0, _scenario_or_404(ws, base_id))
    results = {s["id"]: simulate(cfg, s, _dataset_or_404(ws, s.get("dataset_id"))) for s in scs}
    base_sc = next(s for s in scs if s["id"] == base_id)
    b = results[base_id]
    horizons = {r["horizon"] for r in results.values()}
    deltas, comp = {}, {}
    for s in scs:
        r = results[s["id"]]
        comp[s["id"]] = comparability(base_sc, s)
        if r["horizon"] != b["horizon"]:
            continue
        deltas[s["id"]] = {"indices": {k: _delta(r["indices"][k], b["indices"][k]) for k in r["indices"]},
                           "variables": {k: _delta(r["variables"][k], b["variables"][k]) for k in r["variables"]},
                           "flows": {k: _delta(r["flows"][k], b["flows"][k]) for k in ("Q", "I", "C_flow", "mu", "support_hours")}}
    out = {"baseline_id": base_id, "order": [s["id"] for s in scs], "results": results, "deltas": deltas,
           "comparability": comp, "same_horizon": len(horizons) == 1,
           "resources": {sid: r["resources"] for sid, r in results.items()}}
    if body.save:
        out["run_id"] = db.save_run(ws, "comparison", " vs ".join(r["scenario_name"] or "" for r in results.values())[:200],
                                    list(results.keys()), {sid: _summary(r) for sid, r in results.items()}, out)
    return out


@app.get("/api/runs")
def runs(kind: Optional[str] = None, limit: int = 50, ws: str = Depends(workspace)) -> list[dict[str, Any]]:
    return db.list_runs(ws, kind, min(200, max(1, limit)))


@app.get("/api/runs/{rid}")
def run_detail(rid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    r = db.get_run(ws, rid)
    if r is None:
        raise HTTPException(404, "run not found")
    return r


@app.delete("/api/runs/{rid}")
def run_delete(rid: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    if not db.delete_run(ws, rid):
        raise HTTPException(404, "run not found")
    return {"deleted": rid}


def _safe_filename(name: Optional[str]) -> str:
    """ASCII-only, header-safe file name stem (HTTP headers are latin-1)."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "scenario")).strip("_")
    return (stem or "scenario")[:40]


def _result_csv(res: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = (["month"] + [f"var_{s}" for s in ALL_VARS] + [f"index_{k}" for k in res["indices"]]
            + [f"flow_{k}" for k in res["flows"]] + [f"U_{k}" for k in res["interventions"]])
    w.writerow(["# data_class", res["provenance"]["data_class"], "config_hash", res["provenance"]["config_hash"],
                "parameter_status", res["provenance"]["parameter_status"], "note", "institutional indicators; not probabilities of any event"])
    w.writerow(cols)
    for t in res["months"]:
        row = [t] + [res["variables"][s][t] for s in ALL_VARS] + [res["indices"][k][t] for k in res["indices"]] \
            + [res["flows"][k][t] for k in res["flows"]] + [res["interventions"][k][t] for k in res["interventions"]]
        w.writerow(["" if v is None else (round(v, 6) if isinstance(v, float) else v) for v in row])
    return buf.getvalue()


@app.post("/api/export/simulation.csv")
def export_simulation_csv(body: SimBody, ws: str = Depends(workspace)) -> Response:
    res = run_simulation(SimBody(scenario_id=body.scenario_id, scenario=body.scenario, save=False), ws)
    return Response(_result_csv(res), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="simulation_{_safe_filename(res["scenario_name"])}.csv"'})


@app.get("/api/runs/{rid}/export.csv")
def export_run_csv(rid: str, ws: str = Depends(workspace)) -> Response:
    r = run_detail(rid, ws)
    if r["kind"] != "simulation":
        raise HTTPException(422, "CSV export is available for simulation runs; use JSON for other analyses")
    return Response(_result_csv(r["payload"]), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{rid}.csv"'})


# ----------------------------------------------------------------------------- analytics
class UQBody(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=5)
    param_ids: Optional[list[str]] = None
    n_samples: int = Field(default=200, ge=10, le=2000)
    seed: int = 7
    outputs: Optional[list[str]] = None
    ranges: Optional[dict[str, list[float]]] = None
    save: bool = True


@app.post("/api/analysis/uncertainty")
def uncertainty(body: UQBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    scs = [_scenario_or_404(ws, s) for s in body.scenario_ids]
    base_idx = next((i for i, s in enumerate(scs) if s.get("is_baseline")), 0)
    res = run_uncertainty(cfg, scs, body.param_ids, body.n_samples, body.seed, body.outputs, body.ranges, base_idx,
                          [_dataset_or_404(ws, s.get("dataset_id")) for s in scs])
    if body.save:
        res["run_id"] = db.save_run(ws, "uncertainty", f"UQ n={body.n_samples}", body.scenario_ids,
                                    {"n_samples": body.n_samples, "n_params": len(res["parameters"])}, res)
    return res


class SABody(BaseModel):
    scenario_id: str
    method: Literal["morris", "sobol", "tornado"] = "morris"
    param_ids: Optional[list[str]] = None
    outputs: Optional[list[str]] = None
    month: Optional[int] = None
    n: Optional[int] = None
    seed: int = 3
    second_order: bool = False
    save: bool = True


@app.post("/api/analysis/sensitivity")
def sensitivity(body: SABody, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    sc = _scenario_or_404(ws, body.scenario_id)
    res = run_sensitivity(cfg, sc, body.method, body.param_ids, body.outputs, body.month, body.n, body.seed, None, body.second_order)
    if body.save:
        res["run_id"] = db.save_run(ws, "sensitivity", f"{body.method} ({sc['name']})", [body.scenario_id],
                                    {"method": body.method, "n_runs": res["n_runs"]}, res)
    return res


@app.get("/api/analysis/sensitivity/estimate")
def sensitivity_estimate(method: str, n_params: int, n: Optional[int] = None, second_order: bool = False) -> dict[str, Any]:
    runs = estimate_runs(method, n_params, n, second_order)
    return {"runs": runs, "approx_seconds": round(runs * 0.0012, 1), "limit": 20000}


class CalBody(BaseModel):
    dataset_id: str
    param_ids: Optional[list[str]] = None
    targets: Optional[list[str]] = None
    holdout: int = Field(default=0, ge=0)
    reg_lambda: float = Field(default=0.05, ge=0, le=100)
    prior_source: Literal["config", "expert", "literature"] = "config"
    save: bool = True


@app.post("/api/calibration/lsq")
def cal_lsq(body: CalBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    ds = _dataset_or_404(ws, body.dataset_id)
    res = calibrate_lsq(_cfg(ws), ds, body.param_ids, body.targets, body.reg_lambda, body.holdout, prior_source=body.prior_source)  # type: ignore[arg-type]
    res["dataset_name"] = ds["name"]  # type: ignore[index]
    if body.save:
        res["run_id"] = db.save_run(ws, "calibration_lsq", f"LSQ · {ds['name']}", [], {"status": res["status"]}, res)  # type: ignore[index]
    return res


class BayesBody(CalBody):
    n_chains: int = Field(default=3, ge=1, le=6)
    n_iter: int = Field(default=3000, ge=200, le=20000)
    burn: int = Field(default=1000, ge=0)
    seed: int = 11
    backend: Literal["numpy", "pymc"] = "numpy"
    concentration: float = Field(default=6.0, ge=2.5, le=200)


@app.post("/api/calibration/bayes")
def cal_bayes(body: BayesBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    ds = _dataset_or_404(ws, body.dataset_id)
    res = calibrate_bayes(_cfg(ws), ds, body.param_ids, body.targets, body.n_chains, body.n_iter, body.burn, body.seed,  # type: ignore[arg-type]
                          body.holdout, body.concentration, body.prior_source, body.backend)
    res["dataset_name"] = ds["name"]  # type: ignore[index]
    if body.save:
        res["run_id"] = db.save_run(ws, "calibration_bayes", f"Bayes · {ds['name']}", [], {"converged": res["converged"]}, res)  # type: ignore[index]
    return res


class ApplyCal(BaseModel):
    estimates: dict[str, float]
    method: str
    dataset_name: str = ""


@app.post("/api/calibration/apply")
def cal_apply(body: ApplyCal, ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = validate_config(apply_calibration(_cfg(ws), body.estimates, body.method, body.dataset_name))
    db.save_config(ws, cfg)
    return {"applied": list(body.estimates), "hash": config_hash(cfg)}


@app.get("/api/validation/verification")
def verification(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    return _verification_cached(config_hash(cfg), json.dumps(cfg))


@app.get("/api/validation/conceptual")
def conceptual(ws: str = Depends(workspace)) -> dict[str, Any]:
    return conceptual_validation(_cfg(ws))


class HistBody(BaseModel):
    dataset_id: str
    holdout: int = Field(default=6, ge=1)
    calibrate: bool = True
    param_ids: Optional[list[str]] = None


@app.post("/api/validation/historical")
def historical(body: HistBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    res = historical_validation(_cfg(ws), _dataset_or_404(ws, body.dataset_id), body.holdout, body.param_ids, body.calibrate)  # type: ignore[arg-type]
    res["run_id"] = db.save_run(ws, "validation", "historical", [], {"mean_holdout_rmse": res["mean_holdout_rmse"]}, res)
    return res


class IVBody(BaseModel):
    dataset_id: str
    variable: str
    intervention_period: int
    intervention: Optional[dict[str, Any]] = None


@app.post("/api/validation/intervention")
def intervention(body: IVBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    return intervention_validation(_cfg(ws), _dataset_or_404(ws, body.dataset_id), body.variable,  # type: ignore[arg-type]
                                   body.intervention_period, body.intervention)


@app.get("/api/validation/envelope")
def envelope(ws: str = Depends(workspace)) -> dict[str, Any]:
    dss = [db.get_dataset(ws, d["id"]) for d in db.list_datasets(ws)]
    return validation_envelope(_cfg(ws), [d for d in dss if d])


class ReportBody(BaseModel):
    dataset_id: Optional[str] = None
    holdout: int = 6
    format: Literal["json", "markdown"] = "json"


@app.post("/api/validation/report")
def report(body: ReportBody, ws: str = Depends(workspace)):
    cfg = _cfg(ws)
    ds = _dataset_or_404(ws, body.dataset_id)
    hist = historical_validation(cfg, ds, body.holdout) if ds else None
    rep = build_report(cfg, [ds] if ds else [], hist)
    if body.format == "markdown":
        return PlainTextResponse(rep["markdown"], media_type="text/markdown",
                                 headers={"Content-Disposition": 'attachment; filename="validation_report.md"'})
    return rep


# ----------------------------------------------------------------------------- datasets
@app.get("/api/datasets")
def datasets(ws: str = Depends(workspace)) -> list[dict[str, Any]]:
    return db.list_datasets(ws)


@app.get("/api/datasets/{did}")
def dataset(did: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    return _dataset_or_404(ws, did)  # type: ignore[return-value]


@app.delete("/api/datasets/{did}")
def dataset_delete(did: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    if not db.delete_dataset(ws, did):
        raise HTTPException(404, "dataset not found")
    return {"deleted": did}


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file exceeds the 2 MB limit for aggregate monthly datasets")
    return content


@app.post("/api/datasets/inspect")
async def dataset_inspect(file: UploadFile = File(...), ws: str = Depends(workspace)) -> dict[str, Any]:
    df = parse_upload(await _read_upload(file), file.filename or "upload.csv")
    return inspect(_cfg(ws), df)


@app.post("/api/datasets/import")
async def dataset_import(file: UploadFile = File(...), mapping: str = Form(...), data_class: str = Form(...),
                         name: str = Form(...), provenance: str = Form("{}"), suppress_small_cells: bool = Form(True),
                         ws: str = Depends(workspace)) -> dict[str, Any]:
    try:
        mp = json.loads(mapping)
        prov = json.loads(provenance or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"mapping/provenance must be JSON: {exc.msg}") from exc
    df = parse_upload(await _read_upload(file), file.filename or "upload.csv")
    ds = build_dataset(_cfg(ws), df, mp, data_class, name.strip() or "Imported dataset", prov, suppress_small_cells)
    saved = db.save_dataset(ws, ds)
    return {"id": saved["id"], "name": saved["name"], "data_class": saved["data_class"], "quality": saved["quality"],
            "warnings": saved.get("import_warnings", [])}


class SynthBody(BaseModel):
    months: int = Field(default=36, ge=6, le=120)
    seed: int = 42
    missing_rate: float = Field(default=0.05, ge=0, le=0.5)
    noise_sd: float = Field(default=0.02, ge=0, le=0.2)
    smoothing: float = Field(default=0.6, ge=0, lt=1)
    start_period: str = Field(default="2023-09", pattern=r"^\d{4}-\d{2}$")
    seasonal: bool = True
    include_intervention: bool = True
    name: Optional[str] = None


@app.post("/api/datasets/synthetic")
def dataset_synthetic(body: SynthBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    ds = generate(_cfg(ws), body.months, body.seed, body.missing_rate, body.noise_sd, body.smoothing, body.start_period,
                  seasonal=body.seasonal, include_intervention=body.include_intervention, name=body.name)
    ds["quality"] = quality_report(ds)
    saved = db.save_dataset(ws, ds)
    return {"id": saved["id"], "name": saved["name"], "data_class": "SYNTHETIC", "quality": saved["quality"]}


@app.get("/api/datasets/{did}/quality")
def dataset_quality(did: str, ws: str = Depends(workspace)) -> dict[str, Any]:
    return quality_report(_dataset_or_404(ws, did))  # type: ignore[arg-type]


@app.get("/api/datasets/{did}/export.csv")
def dataset_csv(did: str, ws: str = Depends(workspace)) -> Response:
    ds = _dataset_or_404(ws, did)
    return Response(to_csv(ds), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{did}.csv"'})  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- normalisation helper
class NormBody(BaseModel):
    symbol: str
    values: list[Optional[float]]
    lower: Optional[float] = None
    upper: Optional[float] = None
    direction: Optional[Literal["positive", "negative"]] = None


@app.post("/api/normalize")
def normalize_values(body: NormBody, ws: str = Depends(workspace)) -> dict[str, Any]:
    var = next((v for v in _cfg(ws)["variables"] if v["symbol"] == body.symbol), None)
    if var is None:
        raise HTTPException(404, "unknown variable")
    m = var["measurement"]
    spec = NormSpec(body.lower if body.lower is not None else m["lower"], body.upper if body.upper is not None else m["upper"],
                    body.direction or m["direction"])
    return {"normalized": to_json_list(normalize_series(body.values, spec)), "spec": spec.__dict__}


# ----------------------------------------------------------------------------- overview
@app.get("/api/overview")
def overview(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    dflt = default_config()
    scen = db.list_scenarios(ws)
    base = next((s for s in scen if s.get("is_baseline")), None) or instantiate_template(cfg, "S0")
    base_res = simulate(cfg, base, _dataset_or_404(ws, base.get("dataset_id")))
    dvals = {p["id"]: p["value"] for p in dflt["parameters"]}
    modified_params = [p["id"] for p in cfg["parameters"] if abs(p["value"] - dvals.get(p["id"], p["value"])) > 1e-12]
    dedges = {e["id"]: e for e in dflt["edges"]}
    modified_edges = [e["id"] for e in cfg["edges"] if e["id"] not in dedges or any(
        e[k] != dedges[e["id"]][k] for k in ("coefficient", "sign", "enabled"))]
    ver = _verification_cached(config_hash(cfg), json.dumps(cfg))
    con = conceptual_validation(cfg)
    dsl = db.list_datasets(ws)
    latest = db.list_runs(ws, None, 5)
    return {
        "hash": config_hash(cfg), "parameter_status": cfg["parameter_set"]["status"], "engine_version": ENGINE_VERSION,
        "baseline": {"id": base.get("id"), "name": base.get("name"), "labels": base.get("labels"),
                     "indices_start": {k: v[0] for k, v in base_res["indices"].items()},
                     "indices_end": {k: v[-1] for k, v in base_res["indices"].items()},
                     "variables_start": {k: v[0] for k, v in base_res["variables"].items()},
                     "Q_start": base_res["flows"]["Q"][0], "data_class": base_res["provenance"]["data_class"]},
        "changes": {"modified_parameters": modified_params, "modified_edges": modified_edges,
                    "custom_edges": [e["id"] for e in cfg["edges"] if e.get("custom")]},
        "verification": {"passed": ver["passed"], "total": ver["total"], "all_passed": ver["all_passed"]},
        "evidence_counts": con["evidence_counts"],
        "datasets": {c: sum(1 for d in dsl if d["data_class"] == c) for c in DATA_CLASSES},
        "n_scenarios": len(scen), "latest_runs": latest,
        "validated_horizon_months": cfg.get("validation_envelope", {}).get("validated_horizon_months", 0),
    }


# ----------------------------------------------------------------------------- export / import
@app.get("/api/export/project")
def export_project(include_datasets: bool = True, ws: str = Depends(workspace)) -> dict[str, Any]:
    return {"format": "ssrdt-project", "version": 1, "engine_version": ENGINE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": _cfg(ws), "scenarios": db.list_scenarios(ws),
            "datasets": [db.get_dataset(ws, d["id"]) for d in db.list_datasets(ws)] if include_datasets else []}


@app.post("/api/import/project")
def import_project(body: dict[str, Any], ws: str = Depends(workspace)) -> dict[str, Any]:
    if body.get("format") != "ssrdt-project":
        raise HTTPException(422, "not a School Safety & Resilience Digital Twin project file (format != 'ssrdt-project')")
    cfg = validate_config(body["model"])
    scs = [json.loads(Scenario.model_validate(s).model_dump_json()) | {"id": s.get("id"), "labels": s.get("labels")} for s in body.get("scenarios", [])]
    for s in scs:
        resolve(cfg, s)
    dss = body.get("datasets") or []
    for d in dss:
        if d.get("data_class") not in DATA_CLASSES or not d.get("periods"):
            raise HTTPException(422, f"dataset '{d.get('name')}' lacks a valid data class or periods")
    db.save_config(ws, cfg)
    for s in db.list_scenarios(ws):
        db.delete_scenario(ws, s["id"])
    for d in db.list_datasets(ws):
        db.delete_dataset(ws, d["id"])
    # Re-issue identifiers so a project can be imported into any workspace without collisions
    id_map: dict[str, str] = {}
    for d in dss:
        old_id = d.get("id")
        d = dict(d)
        d["id"] = db.new_id("ds")
        if old_id:
            id_map[old_id] = d["id"]
        db.save_dataset(ws, d)
    for s in scs:
        s["id"] = db.new_id("scn")
        if s.get("dataset_id"):
            s["dataset_id"] = id_map.get(s["dataset_id"])
        db.upsert_scenario(ws, s)
    return {"model_hash": config_hash(cfg), "scenarios": len(scs), "datasets": len(dss)}


@app.post("/api/workspace/reset")
def workspace_reset(ws: str = Depends(workspace)) -> dict[str, Any]:
    db.reset_workspace(ws)
    _seed(ws)
    return {"reset": ws}


@app.get("/api/export/research-metadata")
def research_metadata(ws: str = Depends(workspace)) -> dict[str, Any]:
    cfg = _cfg(ws)
    return {"format": "ssrdt-research-metadata", "engine_version": ENGINE_VERSION, "config_hash": config_hash(cfg),
            "parameter_set": cfg["parameter_set"], "variables": cfg["variables"],
            "relationships": [e for e in cfg["edges"]], "loops": cfg["loops"], "parameters": list_parameters(cfg, include_disabled=True),
            "references": references(), "validation_envelope": validation_envelope(cfg), "data_classes": DATA_CLASSES,
            "editable_relationship_kinds": EDITABLE_KINDS,
            "boundaries": ["No individual-level prediction or scoring", "No attack/violence probabilities",
                           "Aggregate, anonymised institutional data only"]}
