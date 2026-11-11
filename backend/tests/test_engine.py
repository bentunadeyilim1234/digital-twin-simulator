"""Mathematical verification tests for the deterministic engine (Sections 05, 08, 09, 10, 13)."""

import copy
import math

import numpy as np
import pytest

from twin_engine import compile_model, linear_stability, simulate, validate_config
from twin_engine.model import NS, NY, NZ
from twin_engine.normalization import NormSpec, denormalize, normalize, normalize_series
from twin_engine.params import apply_overrides, get_value, list_parameters, set_value
from twin_engine.scenarios import comparability, instantiate_template, intervention_matrix, resolve
from twin_engine.schemas import ALL_VARS, STATE_VARS


# ----------------------------------------------------------------------------- normalisation
def test_normalize_positive_and_negative():
    pos = NormSpec(0, 100, "positive")
    neg = NormSpec(600, 1800, "negative")
    assert normalize(25, pos) == pytest.approx(0.25)
    assert normalize(600, neg) == pytest.approx(1.0)
    assert normalize(1800, neg) == pytest.approx(0.0)
    assert normalize(1200, neg) == pytest.approx(0.5)


def test_normalize_clips_out_of_range():
    spec = NormSpec(1, 5, "positive")
    assert normalize(7, spec) == 1.0
    assert normalize(-3, spec) == 0.0


def test_missing_values_are_never_zero():
    spec = NormSpec(0, 100)
    assert math.isnan(normalize(None, spec))
    assert math.isnan(normalize(float("nan"), spec))
    arr = normalize_series([10, None, 30], spec)
    assert arr[0] == pytest.approx(0.1) and math.isnan(arr[1]) and arr[2] == pytest.approx(0.3)


def test_denormalize_roundtrip():
    for spec in (NormSpec(0, 320), NormSpec(35, 70, "negative")):
        for z in (0.0, 0.33, 1.0):
            assert normalize(denormalize(z, spec), spec) == pytest.approx(z)


def test_invalid_bounds_rejected():
    with pytest.raises(ValueError):
        NormSpec(5, 5)
    with pytest.raises(ValueError):
        NormSpec(0, 1, "sideways")


# ----------------------------------------------------------------------------- structure
def test_matrix_dimensions(cfg):
    m = compile_model(cfg)
    nu, nd = len(cfg["interventions"]), len(cfg["external_conditions"])
    assert m.A.shape == (NS, NS) and m.Gamma.shape == (NS, NZ) and m.Pi.shape == (NS, NY)
    assert m.B.shape == (NS, nu) and m.G.shape == (NS, nd) and m.Lam.shape == (NS, NS)
    assert m.Omega.shape == (NZ, NS) and m.Bz.shape == (NZ, nu) and m.Gz.shape == (NZ, nd)


def test_every_coefficient_lands_in_exactly_one_cell(cfg):
    m = compile_model(cfg)
    linear = [e for e in cfg["edges"] if e["kind"] == "linear" and e["enabled"]]
    nonzero = int(np.count_nonzero(m.A) + np.count_nonzero(m.Gamma) + np.count_nonzero(m.Pi)
                  + np.count_nonzero(m.B) + np.count_nonzero(m.G))
    assert nonzero == len(linear)
    # H1: perceived fairness -> trust lives in Γ[T, J]
    from twin_engine.model import SIDX, ZIDX
    h1 = next(e for e in cfg["edges"] if e["id"] == "H1")
    assert m.Gamma[SIDX["T"], ZIDX["J"]] == pytest.approx(h1["coefficient"])
    # Negative backlog effect on trust is signed
    assert m.Pi[SIDX["T"], 2] < 0


def test_invalid_edge_reference_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["edges"][0]["source"] = "NOT_A_VARIABLE"
    with pytest.raises(ValueError):
        validate_config(bad)


def test_invalid_edge_kind_target_rejected(cfg):
    bad = copy.deepcopy(cfg)
    e = next(x for x in bad["edges"] if x["id"] == "H1")
    e["target"] = "J"  # context variable cannot be the target of a linear state equation
    with pytest.raises(ValueError):
        validate_config(bad)


def test_duplicate_relationship_rejected(cfg):
    bad = copy.deepcopy(cfg)
    dup = copy.deepcopy(next(x for x in bad["edges"] if x["id"] == "H1"))
    dup["id"] = "H1-dup"
    bad["edges"].append(dup)
    with pytest.raises(ValueError):
        validate_config(bad)


def test_parameter_hard_bounds(cfg):
    with pytest.raises(ValueError):
        set_value(copy.deepcopy(cfg), "lambda.E", 1.5)
    with pytest.raises(ValueError):
        set_value(copy.deepcopy(cfg), "edge.H1", -0.1)
    with pytest.raises(ValueError):
        set_value(copy.deepcopy(cfg), "edge.ST-I-Q", 2.0)


def test_linear_stability_default(cfg):
    st = linear_stability(compile_model(cfg))
    assert st["stable"] and st["spectral_radius"] < 1


# ----------------------------------------------------------------------------- determinism & bounds
def test_identical_inputs_identical_outputs(cfg, baseline):
    s4 = instantiate_template(cfg, "S4")
    a, b = simulate(cfg, s4), simulate(cfg, s4)
    assert a["variables"] == b["variables"] and a["flows"] == b["flows"] and a["indices"] == b["indices"]


def test_states_stay_within_bounds_under_extreme_inputs(cfg, baseline):
    extreme = copy.deepcopy(cfg)
    for e in extreme["edges"]:
        if e["kind"] in ("linear", "context_response", "derived"):
            e["coefficient"] = 3.0
    extreme = validate_config(extreme)
    sc = instantiate_template(extreme, "S4")
    sc["horizon_months"] = 48
    sc["interventions"] = [{"key": k["key"], "intensity": 1.0, "start_month": 1, "ramp_months": 0} for k in cfg["interventions"]]
    r = simulate(extreme, sc)
    for s in ALL_VARS:
        assert all(0.0 <= x <= 1.0 for x in r["variables"][s])
    assert all(x >= 0 for x in r["flows"]["Q"])


def test_twelve_month_horizon(cfg, baseline):
    r = simulate(cfg, baseline)
    assert r["horizon"] == 12 and len(r["months"]) == 13
    assert all(len(v) == 13 for v in r["variables"].values())


def test_demo_baseline_is_equilibrium(cfg, baseline):
    r = simulate(cfg, baseline)
    for s in ALL_VARS:
        series = r["variables"][s]
        assert max(series) - min(series) < 1e-6, s  # anchoring stored to 6 decimals
    assert r["provenance"]["data_class"] == "SYNTHETIC"


# ----------------------------------------------------------------------------- stock-flow
def test_mass_balance(cfg):
    for tid in ("S0", "S1", "S2", "S3", "S4"):
        r = simulate(cfg, instantiate_template(cfg, tid))
        Q, I, C = r["flows"]["Q"], r["flows"]["I"], r["flows"]["C_flow"]
        for t in range(1, 13):
            assert Q[t] == pytest.approx(Q[t - 1] + I[t] - C[t], abs=1e-9)
        assert r["diagnostics"]["mass_balance_max_error"] < 1e-9


def test_zero_inflow_creates_no_requests(cfg, baseline):
    z = apply_overrides(cfg, {"flow.I_base": 0.0})
    sc = copy.deepcopy(baseline)
    r = simulate(z, sc)
    assert all(x == 0 for x in r["flows"]["I"][1:])
    Q = r["flows"]["Q"]
    assert all(Q[t] <= Q[t - 1] + 1e-12 for t in range(1, 13))  # stock can only drain


def test_capacity_constraint(cfg):
    r = simulate(cfg, instantiate_template(cfg, "S1"))
    Q, I, C, mu = r["flows"]["Q"], r["flows"]["I"], r["flows"]["C_flow"], r["flows"]["mu"]
    for t in range(1, 13):
        assert C[t] <= mu[t] + 1e-12
        assert C[t] <= Q[t - 1] + I[t] + 1e-12
        assert C[t] == pytest.approx(min(Q[t - 1] + I[t], mu[t]))


def test_b1_loop_reduces_backlog(cfg):
    sc = instantiate_template(cfg, "S1")
    with_b1 = simulate(cfg, sc)
    without = simulate(apply_overrides(cfg, {"edge.B1-GAIN": 0.0}), sc)
    assert with_b1["flows"]["Q"][12] < without["flows"]["Q"][12]


def test_accessibility_raises_requests_not_risk(cfg, baseline):
    s1 = simulate(cfg, instantiate_template(cfg, "S1"))
    s0 = simulate(cfg, baseline)
    assert s1["flows"]["I"][12] > s0["flows"]["I"][12]
    # No output anywhere is labelled as risk / probability of violence
    keys = " ".join(list(s1.keys()) + list(s1["indices"].keys()) + list(s1["flows"].keys())).lower()
    for forbidden in ("risk", "danger", "attack", "violence", "threat"):
        assert forbidden not in keys


# ----------------------------------------------------------------------------- variables & edges affect output
@pytest.mark.parametrize("sym", ALL_VARS)
def test_each_variable_changes_output(cfg, baseline, sym):
    ref = simulate(cfg, baseline)
    sc = copy.deepcopy(baseline)
    sc["initial_state"][sym] = min(1.0, sc["initial_state"][sym] + 0.2)
    out = simulate(cfg, sc)
    assert out["variables"] != ref["variables"] or out["indices"] != ref["indices"]


def test_disabling_edge_changes_output(cfg):
    sc = instantiate_template(cfg, "S2")
    ref = simulate(cfg, sc)
    off = copy.deepcopy(cfg)
    next(e for e in off["edges"] if e["id"] == "H7")["enabled"] = False
    out = simulate(validate_config(off), sc)
    assert out["variables"]["P"][12] < ref["variables"]["P"][12]


def test_editing_coefficient_changes_output(cfg):
    sc = instantiate_template(cfg, "S2")
    ref = simulate(cfg, sc)
    out = simulate(apply_overrides(cfg, {"edge.H7": 0.4}), sc)
    assert out["variables"]["P"][12] > ref["variables"]["P"][12]


def test_parameter_slots_match_config_path(cfg):
    sc = instantiate_template(cfg, "S4")
    from twin_engine.simulator import run
    rs, _ = resolve(cfg, sc)
    m = compile_model(cfg)
    fast = run(m.with_params({"edge.H1": 0.33, "lambda.T": 0.27, "flow.h_proc": 3.3}), rs)
    slow = run(compile_model(apply_overrides(cfg, {"edge.H1": 0.33, "lambda.T": 0.27, "flow.h_proc": 3.3})), rs)
    np.testing.assert_allclose(fast["V"], slow["V"])


def test_every_listed_parameter_has_slot(cfg):
    m = compile_model(cfg)
    for p in list_parameters(cfg):
        assert p["id"] in m.param_slots, p["id"]


# ----------------------------------------------------------------------------- scenarios
def test_intervention_ramp_schedule():
    U = intervention_matrix([{"key": "U_access", "intensity": 0.6, "start_month": 3, "ramp_months": 3, "end_month": 8}],
                            ["U_access"], 12)
    assert U[2, 0] == 0
    assert U[3, 0] == pytest.approx(0.2) and U[4, 0] == pytest.approx(0.4) and U[5, 0] == pytest.approx(0.6)
    assert U[8, 0] == pytest.approx(0.6) and U[9, 0] == 0


def test_templates_differ_only_in_interventions(cfg, baseline):
    for tid in ("S1", "S2", "S3", "S4"):
        assert comparability(baseline, instantiate_template(cfg, tid)) == []


def test_comparability_flags_other_differences(cfg, baseline):
    other = instantiate_template(cfg, "S1")
    other["initial_state"]["T"] = 0.9
    assert any("initial_state" in d for d in comparability(baseline, other))


def test_manual_override_holds_value(cfg):
    sc = instantiate_template(cfg, "S4")
    sc["variable_modes"] = {"T": "manual", "R": "manual"}
    sc["overrides"] = {"T": {"value": 0.42}, "R": {"values": [0.6, 0.5, 0.4]}}
    r = simulate(cfg, sc)
    assert all(x == pytest.approx(0.42) for x in r["variables"]["T"])
    assert r["variables"]["R"][1] == pytest.approx(0.5) and r["variables"]["R"][12] == pytest.approx(0.4)
    assert any("manual override" in w for w in r["diagnostics"]["warnings"])


def test_context_schedule_applied(cfg, baseline):
    sc = copy.deepcopy(baseline)
    sc["context_schedule"] = {"F": {"values": [0.75, 0.75, 0.3]}}
    r = simulate(cfg, sc)
    assert r["variables"]["F"][5] == pytest.approx(0.3)
    assert r["variables"]["E"][12] < r["variables"]["E"][0]


def test_unknown_inputs_rejected(cfg, baseline):
    sc = copy.deepcopy(baseline)
    sc["initial_state"]["XYZ"] = 0.5
    with pytest.raises(ValueError):
        simulate(cfg, sc)
    sc = copy.deepcopy(baseline)
    sc["interventions"] = [{"key": "U_nonexistent", "intensity": 0.5}]
    with pytest.raises(ValueError):
        simulate(cfg, sc)
    sc = copy.deepcopy(baseline)
    sc["initial_state"]["E"] = 1.4
    with pytest.raises(ValueError):
        simulate(cfg, sc)


def test_dataset_replay_and_missing_handling(cfg, baseline):
    ds = {"data_class": "SYNTHETIC", "periods": ["2024-09", "2024-10", "2024-11"],
          "variables": {s: [0.5, None, 0.6] for s in ALL_VARS}, "flows": {"Q": [10, 12, 11]}}
    sc = copy.deepcopy(baseline)
    sc["dataset_anchor"] = "replay"
    r = simulate(cfg, sc, ds)
    # Missing month 1 carried forward, not zero
    assert r["variables"]["F"][1] == pytest.approx(0.5)
    assert r["variables"]["F"][2] == pytest.approx(0.6)
    assert any("last observation carried forward" in w for w in r["diagnostics"]["warnings"])
    assert r["flows"]["Q"][0] == pytest.approx(10)


def test_indices_and_min_domain(cfg):
    r = simulate(cfg, instantiate_template(cfg, "S1"))
    for t in range(13):
        doms = [r["indices"][d][t] for d in ("ENV", "SOC", "ORG", "SUP")]
        assert r["indices"]["TOTAL"][t] == pytest.approx(sum(doms) / 4)
        assert r["indices"]["MIN_DOMAIN"][t] == pytest.approx(min(doms))


def test_domain_weights_normalised(cfg, baseline):
    w = apply_overrides(cfg, {"weights.domain.ENV": 1.0, "weights.domain.SOC": 1.0,
                              "weights.domain.ORG": 1.0, "weights.domain.SUP": 1.0})
    a, b = simulate(cfg, baseline), simulate(w, baseline)
    assert a["indices"]["TOTAL"] == pytest.approx(b["indices"]["TOTAL"])


def test_get_value_roundtrip(cfg):
    c = copy.deepcopy(cfg)
    set_value(c, "edge.H4", 0.55)
    assert get_value(c, "edge.H4") == 0.55
    assert get_value(c, "lambda.C") == pytest.approx(0.15)
