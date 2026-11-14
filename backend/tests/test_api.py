"""API integration tests: persistence, scenario lifecycle, simulation, comparison, analytics, import/export."""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_db):
    from api.main import _verification_cached, app
    _verification_cached.cache_clear()
    return TestClient(app, headers={"X-Workspace-Id": "test-ws"})


def test_health_and_seeding(client):
    assert client.get("/api/health").json()["status"] == "ok"
    scs = client.get("/api/scenarios").json()
    assert {s["template_id"] for s in scs} == {"S0", "S1", "S2", "S3", "S4"}
    assert sum(s["is_baseline"] for s in scs) == 1
    ds = client.get("/api/datasets").json()
    assert len(ds) == 1 and ds[0]["data_class"] == "SYNTHETIC"


def test_workspaces_are_isolated(client, tmp_db):
    from api.main import app
    other = TestClient(app, headers={"X-Workspace-Id": "other-ws"})
    client.post("/api/scenarios", json={"template_id": "S1", "name": "Mine"})
    assert not any(s["name"] == "Mine" for s in other.get("/api/scenarios").json())
    assert client.get("/api/health", headers={"X-Workspace-Id": "bad id!"}).status_code == 200
    assert client.get("/api/scenarios", headers={"X-Workspace-Id": "bad id!"}).status_code == 400


def test_scenario_lifecycle_and_simulation(client):
    base = next(s for s in client.get("/api/scenarios").json() if s["is_baseline"])
    created = client.post("/api/scenarios", json={"template_id": "S2", "name": "Custom prep"}).json()
    assert created["initial_state"] == base["initial_state"]  # inherits baseline conditions
    created["interventions"][0]["intensity"] = 0.9
    created["initial_state"]["E"] = 0.75
    updated = client.put(f"/api/scenarios/{created['id']}", json=created).json()
    assert updated["interventions"][0]["intensity"] == 0.9
    dup = client.post(f"/api/scenarios/{created['id']}/duplicate", json={}).json()
    assert dup["id"] != created["id"] and dup["name"].endswith("(copy)")
    res = client.post("/api/simulate", json={"scenario_id": created["id"], "save": True}).json()
    assert res["horizon"] == 12 and len(res["indices"]["TOTAL"]) == 13 and res["run_id"]
    assert res["provenance"]["data_class"] == "SYNTHETIC"
    assert client.delete(f"/api/scenarios/{dup['id']}").status_code == 200
    assert client.delete(f"/api/scenarios/{base['id']}").status_code == 422  # baseline protected


def test_invalid_scenario_rejected(client):
    sc = client.get("/api/scenarios").json()[0]
    sc["initial_state"]["E"] = 3
    r = client.put(f"/api/scenarios/{sc['id']}", json=sc)
    assert r.status_code == 422


def test_compare_against_baseline(client):
    scs = client.get("/api/scenarios").json()
    ids = [s["id"] for s in scs]
    r = client.post("/api/compare", json={"scenario_ids": ids, "save": True}).json()
    base = r["baseline_id"]
    assert all(v == [] for v in r["comparability"].values())
    assert all(abs(x) < 1e-12 for x in r["deltas"][base]["indices"]["TOTAL"])
    s4 = next(s["id"] for s in scs if s["template_id"] == "S4")
    assert r["deltas"][s4]["indices"]["TOTAL"][12] > 0
    assert r["resources"][s4]["program_hours_total"] > 0


def test_edge_edit_changes_simulation_and_restore(client):
    s2 = next(s for s in client.get("/api/scenarios").json() if s["template_id"] == "S2")
    before = client.post("/api/simulate", json={"scenario_id": s2["id"]}).json()["variables"]["P"][12]
    e = client.patch("/api/model/edges/H7", json={"coefficient": 0.45}).json()["edge"]
    assert e["coefficient"] == 0.45
    after = client.post("/api/simulate", json={"scenario_id": s2["id"]}).json()["variables"]["P"][12]
    assert after > before
    g = client.get("/api/model/graph").json()
    assert next(x for x in g["edges"] if x["id"] == "H7")["modified"]
    client.post("/api/model/edges/H7/restore")
    assert client.post("/api/simulate", json={"scenario_id": s2["id"]}).json()["variables"]["P"][12] == pytest.approx(before)
    assert client.patch("/api/model/edges/ST-I-Q", json={"coefficient": 2}).status_code == 422
    assert client.patch("/api/model/edges/H7", json={"coefficient": -1}).status_code == 422


def test_custom_edge_add_delete(client):
    r = client.post("/api/model/edges", json={"source": "K", "target": "C", "kind": "linear", "coefficient": 0.1})
    assert r.status_code == 200
    bad = client.post("/api/model/edges", json={"source": "K", "target": "J", "kind": "linear", "coefficient": 0.1})
    assert bad.status_code == 422
    assert client.delete("/api/model/edges/X-K-C").status_code == 200
    assert client.delete("/api/model/edges/H1").status_code == 422


def test_parameter_patch_and_anchor(client):
    assert client.patch("/api/model/parameters/lambda.E", json={"value": 0.5}).status_code == 200
    assert client.patch("/api/model/parameters/lambda.E", json={"value": 2.0}).status_code == 422
    client.patch("/api/model/edges/H1", json={"coefficient": 0.35})
    a = client.post("/api/model/anchor", json={"apply": True}).json()
    assert a["applied"]
    base = next(s for s in client.get("/api/scenarios").json() if s["is_baseline"])
    tot = client.post("/api/simulate", json={"scenario_id": base["id"]}).json()["indices"]["TOTAL"]
    assert max(tot) - min(tot) < 1e-5  # re-anchored baseline is again an equilibrium


def test_structure_equations_and_validation(client):
    st = client.get("/api/model/structure").json()
    assert st["linear_stability"]["stable"] and st["full_map_stability"]["stable"]
    eq = client.get("/api/model/equations").json()
    assert any(e["target"] == "T" and "α_TJ" in e["symbolic"] for e in eq["state"])
    v = client.get("/api/validation/verification").json()
    assert v["all_passed"]
    assert client.get("/api/validation/conceptual").json()["loop_issues"] == []
    ov = client.get("/api/overview").json()
    assert ov["verification"]["all_passed"] and "TOTAL" in ov["baseline"]["indices_end"]


def test_analytics_endpoints(client):
    scs = client.get("/api/scenarios").json()
    base = next(s for s in scs if s["is_baseline"])["id"]
    s4 = next(s for s in scs if s["template_id"] == "S4")["id"]
    uq = client.post("/api/analysis/uncertainty", json={"scenario_ids": [base, s4], "n_samples": 20}).json()
    assert len(uq["scenarios"]) == 2 and uq["run_id"]
    sa = client.post("/api/analysis/sensitivity", json={"scenario_id": s4, "method": "morris", "n": 4,
                                                        "param_ids": ["edge.H1", "edge.H7", "flow.h_proc"]}).json()
    assert sa["n_runs"] == 16
    est = client.get("/api/analysis/sensitivity/estimate", params={"method": "sobol", "n_params": 10, "n": 128}).json()
    assert est["runs"] == 128 * 12
    ds = client.get("/api/datasets").json()[0]["id"]
    lsq = client.post("/api/calibration/lsq", json={"dataset_id": ds, "param_ids": ["edge.H7", "edge.H9"], "holdout": 4}).json()
    assert lsq["status"] == "converged"
    applied = client.post("/api/calibration/apply", json={"estimates": {p["id"]: p["estimate"] for p in lsq["parameters"]},
                                                          "method": "lsq", "dataset_name": "synthetic"}).json()
    assert applied["applied"] == ["edge.H7", "edge.H9"]
    hist = client.post("/api/validation/historical", json={"dataset_id": ds, "holdout": 6, "param_ids": ["edge.H7"]}).json()
    assert hist["n_holdout"] == 6
    md = client.post("/api/validation/report", json={"dataset_id": ds, "format": "markdown"})
    assert md.status_code == 200 and "Validation Report" in md.text


def test_dataset_import_flow_and_privacy(client):
    csv = "period,T,C,student_name\n2024-09,0.5,0.6,x\n"
    r = client.post("/api/datasets/inspect", files={"file": ("d.csv", csv, "text/csv")}).json()
    assert r["forbidden_columns"] == ["student_name"]
    imp = client.post("/api/datasets/import", files={"file": ("d.csv", csv, "text/csv")},
                      data={"mapping": json.dumps({"period": "period", "T": "T", "C": "C", "student_name": "ignore"}),
                            "data_class": "SYNTHETIC", "name": "bad"})
    assert imp.status_code == 422 and "privacy guard" in imp.json()["detail"]
    good = "period,T,C,mystery\n2024-09,0.5,0.6,1\n2024-10,0.55,0.62,2\n2024-11,0.52,,3\n2024-12,0.6,0.64,4\n"
    r = client.post("/api/datasets/import", files={"file": ("g.csv", good, "text/csv")},
                    data={"mapping": json.dumps({"period": "period", "T": "T", "C": "C"}), "data_class": "SYNTHETIC", "name": "g"})
    assert r.status_code == 422 and "unmapped" in r.json()["detail"]
    r = client.post("/api/datasets/import", files={"file": ("g.csv", good, "text/csv")},
                    data={"mapping": json.dumps({"period": "period", "T": "T", "C": "C", "mystery": "ignore"}),
                          "data_class": "PUBLIC_RESEARCH", "name": "g", "provenance": json.dumps({"source": "Example (2024)"})}).json()
    assert r["quality"]["variables"]["C"]["missing"] == 1
    syn = client.post("/api/datasets/synthetic", json={"months": 24, "seed": 9}).json()
    assert syn["data_class"] == "SYNTHETIC"
    assert "period,data_class" in client.get(f"/api/datasets/{syn['id']}/export.csv").text


def test_exports_and_project_roundtrip_persistence(client, tmp_db):
    scs = client.get("/api/scenarios").json()
    csv_text = client.post("/api/export/simulation.csv", json={"scenario_id": scs[0]["id"]}).text
    assert "index_TOTAL" in csv_text and "SYNTHETIC" in csv_text
    client.post("/api/scenarios", json={"template_id": "S3", "name": "Persist me"})
    client.patch("/api/model/edges/H4", json={"coefficient": 0.5})
    proj = client.get("/api/export/project").json()
    meta = client.get("/api/export/research-metadata").json()
    assert meta["format"] == "ssrdt-research-metadata" and len(meta["variables"]) == 16
    # "reload": new client, same DB file
    from api.main import app
    fresh = TestClient(app, headers={"X-Workspace-Id": "test-ws"})
    assert any(s["name"] == "Persist me" for s in fresh.get("/api/scenarios").json())
    assert next(e for e in fresh.get("/api/model").json()["config"]["edges"] if e["id"] == "H4")["coefficient"] == 0.5
    # import into a different workspace
    other = TestClient(app, headers={"X-Workspace-Id": "imported"})
    r = other.post("/api/import/project", json=proj).json()
    assert r["scenarios"] == len(proj["scenarios"])
    assert any(s["name"] == "Persist me" for s in other.get("/api/scenarios").json())
    assert other.post("/api/import/project", json={"format": "nope"}).status_code == 422


def test_concurrent_first_requests_seed_once(tmp_db):
    """A new browser fires several requests in parallel; the workspace must be seeded exactly once."""
    from concurrent.futures import ThreadPoolExecutor
    from api.main import app
    c = TestClient(app, headers={"X-Workspace-Id": "race-ws"})
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda p: c.get(p), ["/api/meta", "/api/model", "/api/scenarios", "/api/datasets", "/api/overview", "/api/scenarios"]))
    assert len(c.get("/api/scenarios").json()) == 5
    assert len(c.get("/api/datasets").json()) == 1


def test_seeded_dataset_has_quality_report(client):
    ds = client.get("/api/datasets").json()
    assert ds[0]["quality"] and ds[0]["quality"]["n_periods"] == 36


def test_deps_in_sync():
    """requirements.txt (Docker/dev) and pyproject.toml (Vercel) must list the same runtime packages."""
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    req = [l.strip() for l in (root / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    proj = tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"]
    assert sorted(req) == sorted(proj)
