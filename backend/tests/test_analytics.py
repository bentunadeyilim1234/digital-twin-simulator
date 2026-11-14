"""Tests for synthetic data, datasets/privacy, UQ, SA, calibration and validation."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from twin_engine.calibration import calibrate_bayes, calibrate_lsq, default_targets, responsive_contexts
from twin_engine.datasets import DatasetError, build_dataset, inspect, parse_upload, quality_report, to_csv
from twin_engine.graph import build_graph, declared_loops, detect_loops
from twin_engine.scenarios import instantiate_template
from twin_engine.schemas import ALL_VARS
from twin_engine.sensitivity import run_sensitivity
from twin_engine.synthetic import generate
from twin_engine.uncertainty import run_uncertainty
from twin_engine.validation import (build_report, conceptual_validation, historical_validation,
                                    intervention_validation, verification_suite)


@pytest.fixture(scope="module")
def ds():
    from twin_engine import default_config
    return generate(default_config(), months=30, seed=42)


# ----------------------------------------------------------------------------- synthetic
def test_synthetic_reproducible_and_labelled(cfg):
    a, b = generate(cfg, months=24, seed=5), generate(cfg, months=24, seed=5)
    assert a["variables"] == b["variables"] and a["flows"] == b["flows"]
    assert a["data_class"] == "SYNTHETIC" and set(a["record_labels"]) == {"SYNTHETIC"}
    assert "NOT REAL SCHOOL MEASUREMENTS" in a["provenance"]["statement"]
    c = generate(cfg, months=24, seed=6)
    assert c["variables"] != a["variables"]


def test_synthetic_bounds_missing_and_mass_balance(cfg):
    d = generate(cfg, months=48, seed=1, missing_rate=0.2)
    vals = [v for s in ALL_VARS for v in d["variables"][s]]
    assert all(v is None or 0 <= v <= 1 for v in vals)
    assert sum(v is None for v in vals) > 0
    q = quality_report(d)
    assert q["flow_mass_balance"]["consistent"] is True
    assert q["all_records_labelled"]


# ----------------------------------------------------------------------------- import & privacy
def _csv(text):
    return parse_upload(text.encode(), "x.csv")


def test_privacy_guard_rejects_identifiers(cfg):
    df = _csv("period,student_id,T\n2024-09,17,0.5\n")
    assert inspect(cfg, df)["forbidden_columns"] == ["student_id"]
    with pytest.raises(DatasetError):
        build_dataset(cfg, df, {"period": "period", "student_id": "ignore", "T": "T"}, "SYNTHETIC", "x")


def test_sensitive_attributes_rejected(cfg):
    for col in ("ethnicity", "religion", "diagnosis", "cinsiyet", "risk_score"):
        df = _csv(f"period,{col}\n2024-09,1\n")
        assert col in inspect(cfg, df)["forbidden_columns"]


def test_rows_must_be_aggregate(cfg):
    df = _csv("period,T\n2024-09,0.5\n2024-09,0.6\n")
    with pytest.raises(DatasetError, match="one aggregate row per month"):
        build_dataset(cfg, df, {"period": "period", "T": "T"}, "SYNTHETIC", "x")


def test_unknown_columns_never_silently_mapped(cfg):
    df = _csv("period,T,mystery\n2024-09,0.5,3\n")
    insp = inspect(cfg, df)
    assert insp["unmapped"] == ["mystery"]
    with pytest.raises(DatasetError, match="unmapped"):
        build_dataset(cfg, df, {"period": "period", "T": "T"}, "SYNTHETIC", "x")
    ok = build_dataset(cfg, df, {"period": "period", "T": "T", "mystery": "ignore"}, "SYNTHETIC", "x")
    assert "mystery" not in ok["variables"]


def test_raw_scale_normalisation_and_missing(cfg):
    df = _csv("period,trust,co2\n2024-09,3,1200\n2024-10,,600\n")
    ds_ = build_dataset(cfg, df, {"period": "period", "trust": {"target": "T", "scale": "raw"},
                                   "co2": {"target": "E", "scale": "raw", "lower": 600, "upper": 1800, "direction": "negative"}},
                        "SYNTHETIC", "x")
    assert ds_["variables"]["T"] == [pytest.approx(0.5), None]  # Likert 1-5 -> 0.5 ; missing stays None
    assert ds_["variables"]["E"] == [pytest.approx(0.5), pytest.approx(1.0)]


def test_normalized_out_of_range_rejected(cfg):
    df = _csv("period,T\n2024-09,3.2\n")
    with pytest.raises(DatasetError, match="outside"):
        build_dataset(cfg, df, {"period": "period", "T": "T"}, "SYNTHETIC", "x")


def test_authorized_school_requires_provenance(cfg):
    df = _csv("period,T\n2024-09,0.5\n")
    with pytest.raises(DatasetError, match="authorization_reference"):
        build_dataset(cfg, df, {"period": "period", "T": "T"}, "AUTHORIZED_SCHOOL", "x")
    ok = build_dataset(cfg, df, {"period": "period", "T": "T"}, "AUTHORIZED_SCHOOL", "x",
                       {"authorization_reference": "REF-1", "data_controller": "School"})
    assert ok["data_class"] == "AUTHORIZED_SCHOOL"


def test_small_cell_suppression(cfg):
    df = _csv("period,T,n_respondents\n2024-09,0.5,6\n2024-10,0.6,40\n")
    d = build_dataset(cfg, df, {"period": "period", "T": "T", "n_respondents": "n_respondents"}, "SYNTHETIC", "x")
    assert d["variables"]["T"][0] is None and d["variables"]["T"][1] == pytest.approx(0.6)


def test_csv_export_import_roundtrip(cfg, ds):
    text = to_csv(ds)
    df = parse_upload(text.encode(), "r.csv")
    insp = inspect(cfg, df)
    assert not insp["unmapped"]
    back = build_dataset(cfg, df, insp["suggested_mapping"], "SYNTHETIC", "roundtrip")
    for s in ALL_VARS:
        a = [None if v is None else round(v, 5) for v in ds["variables"][s]]
        b = [None if v is None else round(v, 5) for v in back["variables"][s]]
        assert a == b
    assert back["flows"]["Q"] == ds["flows"]["Q"]


def test_json_dataset_import(cfg, ds):
    df = parse_upload(json.dumps(ds).encode(), "d.json")
    assert len(df) == len(ds["periods"])


# ----------------------------------------------------------------------------- UQ / SA
def test_uncertainty_bands_ordered_and_reproducible(cfg):
    scs = [instantiate_template(cfg, "S0"), instantiate_template(cfg, "S4")]
    a = run_uncertainty(cfg, scs, n_samples=40, seed=3)
    b = run_uncertainty(cfg, scs, n_samples=40, seed=3)
    assert a["scenarios"][1]["bands"]["TOTAL"]["p50"] == b["scenarios"][1]["bands"]["TOTAL"]["p50"]
    band = a["scenarios"][1]["bands"]["TOTAL"]
    assert all(lo <= mid <= hi for lo, mid, hi in zip(band["p5"], band["p50"], band["p95"]))
    assert "difference_to_baseline" in a["scenarios"][1]


def test_uncertainty_guard(cfg):
    with pytest.raises(ValueError):
        run_uncertainty(cfg, [instantiate_template(cfg, "S0")], n_samples=5000)


def test_sensitivity_methods(cfg):
    sc = instantiate_template(cfg, "S4")
    ids = ["edge.H1", "edge.H7", "flow.h_proc", "lambda.T"]
    t = run_sensitivity(cfg, sc, method="tornado", param_ids=ids)
    assert len(t["tornado"]) == 4
    m = run_sensitivity(cfg, sc, method="morris", param_ids=ids, n=6)
    assert m["n_runs"] == 6 * 5 and len(m["indices"]["TOTAL"]) == 4
    s = run_sensitivity(cfg, sc, method="sobol", param_ids=ids, n=32)
    assert s["n_runs"] == 32 * (4 + 2)
    assert all("ST" in r for r in s["indices"]["TOTAL"])


def test_sensitivity_guard(cfg):
    with pytest.raises(ValueError):
        run_sensitivity(cfg, instantiate_template(cfg, "S0"), method="sobol", n=1024, max_runs=1000)
    with pytest.raises(ValueError):
        run_sensitivity(cfg, instantiate_template(cfg, "S0"), method="sobol", n=100)  # not a power of two


# ----------------------------------------------------------------------------- calibration
def test_responsive_contexts_are_targets(cfg, ds):
    assert responsive_contexts(cfg) == ["H", "TR", "IF"]
    assert "H" in default_targets(ds, cfg)


def test_lsq_improves_fit_and_recovers_informative_parameters(cfg, ds):
    r = calibrate_lsq(cfg, ds, holdout=4)
    assert r["objective_fitted"] <= r["objective_initial"]
    est = {p["id"]: p["estimate"] for p in r["parameters"]}
    for pid in ("edge.H7", "edge.H9", "edge.SOC-T-C"):
        assert abs(est[pid] - ds["truth"][pid]) < 0.06, pid
    assert all("identifiable" in p for p in r["parameters"])


def test_bayes_runs_and_reports_diagnostics(cfg, ds):
    r = calibrate_bayes(cfg, ds, param_ids=["edge.H7", "edge.H9"], n_chains=2, n_iter=600, burn=200)
    for p in r["parameters"]:
        assert p["posterior"]["q05"] <= p["posterior"]["mean"] <= p["posterior"]["q95"]
        assert "rhat" in p and "ess" in p
    assert len(r["acceptance_rate"]) == 2


def test_pymc_backend_unavailable_is_explicit(cfg, ds):
    with pytest.raises(RuntimeError):
        calibrate_bayes(cfg, ds, backend="pymc")


# ----------------------------------------------------------------------------- validation & graph
def test_verification_suite_passes(cfg):
    v = verification_suite(cfg)
    assert v["all_passed"], [c for c in v["checks"] if c["status"] != "pass"]


def test_conceptual_validation_and_loops(cfg):
    c = conceptual_validation(cfg)
    assert c["evidence_counts"]["E1"] + c["evidence_counts"]["E2"] + c["evidence_counts"]["H"] > 0
    assert c["loop_issues"] == []
    loops = {l["id"]: l for l in declared_loops(cfg)}
    assert loops["R1"]["computed_polarity"] == "reinforcing" and loops["B1"]["computed_polarity"] == "balancing"
    detected = detect_loops(cfg)
    assert any(d["declared_as"] == "R1" for d in detected) and any(d["declared_as"] == "B1" for d in detected)


def test_graph_uses_model_configuration(cfg):
    g = build_graph(cfg)
    assert {e["id"] for e in g["edges"]} == {e["id"] for e in cfg["edges"]}
    mod = copy.deepcopy(cfg)
    next(e for e in mod["edges"] if e["id"] == "H1")["coefficient"] = 0.31
    assert next(e for e in build_graph(mod)["edges"] if e["id"] == "H1")["modified"]


def test_historical_and_intervention_validation(cfg, ds):
    h = historical_validation(cfg, ds, holdout=6)
    assert h["n_holdout"] == 6 and h["mean_holdout_rmse"] is not None
    p = ds["provenance"]["generator"]["intervention"]["start_month"]
    iv = intervention_validation(cfg, ds, "A", p)
    assert "level_change" in iv["its"] and iv["model"]["intervention_inputs_present"]
    rep = build_report(cfg, [ds], h)
    assert "Validation Report" in rep["markdown"] and rep["verification"]["all_passed"]


def test_ols_hac_matches_statsmodels():
    sm = pytest.importorskip("statsmodels.api")  # dev-only dependency, not deployed
    from twin_engine.validation import ols_hac
    rng = np.random.default_rng(1)
    n = 30
    t = np.arange(n, dtype=float)
    post = (t >= 18).astype(float)
    X = np.column_stack([np.ones(n), t, post, (t - 18) * post])
    y = 0.5 + 0.002 * t + 0.03 * post + rng.normal(0, 0.02, n).cumsum() * 0.3
    ref = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    params, ci, pvalues = ols_hac(y, X, maxlags=2)
    np.testing.assert_allclose(params, ref.params, atol=1e-12)
    np.testing.assert_allclose(ci, ref.conf_int(), atol=1e-12)
    np.testing.assert_allclose(pvalues, ref.pvalues, atol=1e-12)
