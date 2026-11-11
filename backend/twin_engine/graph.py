"""Causal graph view of the authoritative configuration (Sections 06-07).

The graph is derived from the SAME edge list the simulator compiles; there is no
separate diagram definition. Feedback loops are detected by enumerating simple cycles
and their polarity is the product of edge signs (Sterman, 2000).
"""

from __future__ import annotations

from typing import Any

from .schemas import ALL_VARS, CONTEXT_VARS, FLOW_NODES, STATE_VARS

MAX_CYCLES = 300
MAX_CYCLE_LEN = 10


def build_graph(cfg: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    nodes = []
    for v in cfg["variables"]:
        nodes.append({"id": v["symbol"], "kind": "variable", "role": v["role"], "domain": v["domain"],
                      "var_id": v["id"], "label": v["labels"].get(lang) or v["labels"]["en"],
                      "evidence": v["measurement_evidence"]})
    for f in cfg["flow_nodes"]:
        nodes.append({"id": f["key"], "kind": "flow", "role": f["kind"], "domain": None,
                      "label": f["labels"].get(lang) or f["labels"]["en"], "unit": f["unit"]})
    for i in cfg["interventions"]:
        nodes.append({"id": i["key"], "kind": "intervention", "role": "input", "domain": None,
                      "label": i["labels"].get(lang) or i["labels"]["en"]})
    for e in cfg["external_conditions"]:
        nodes.append({"id": e["key"], "kind": "external", "role": "input", "domain": None,
                      "label": e["labels"].get(lang) or e["labels"]["en"]})
    edges = [{**e, "effective": e["sign"] * e["coefficient"],
              "modified": bool(e.get("original")) and (e["original"]["coefficient"] != e["coefficient"]
                                                       or e["original"]["sign"] != e["sign"]
                                                       or e["original"]["enabled"] != e["enabled"])}
             for e in cfg["edges"]]
    loops = declared_loops(cfg)
    return {"nodes": nodes, "edges": edges, "loops": loops, "detected_loops": detect_loops(cfg)}


def declared_loops(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {e["id"]: e for e in cfg["edges"]}
    out = []
    for loop in cfg["loops"]:
        es = [by_id[x] for x in loop["edges"] if x in by_id]
        chain_ok = all(es[i]["target"] == es[(i + 1) % len(es)]["source"] for i in range(len(es))) if es else False
        sign = 1
        for e in es:
            sign *= e["sign"]
        computed = "reinforcing" if sign > 0 else "balancing"
        out.append({**loop, "closed": chain_ok, "computed_polarity": computed,
                    "polarity_consistent": computed == loop["polarity"],
                    "active": all(e["enabled"] and (e["coefficient"] > 0) for e in es),
                    "nodes": [e["source"] for e in es]})
    return out


def detect_loops(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = list(ALL_VARS) + list(FLOW_NODES)
    adj: dict[str, list[dict]] = {n: [] for n in nodes}
    for e in cfg["edges"]:
        if e["enabled"] and e["coefficient"] > 0 and e["source"] in adj and e["target"] in adj:
            adj[e["source"]].append(e)
    order = {n: i for i, n in enumerate(nodes)}
    cycles: list[list[dict]] = []

    def dfs(start: str, cur: str, path: list[dict], visited: set[str]) -> None:
        if len(cycles) >= MAX_CYCLES or len(path) > MAX_CYCLE_LEN:
            return
        for e in adj[cur]:
            nxt = e["target"]
            if nxt == start:
                cycles.append(path + [e])
            elif nxt not in visited and order[nxt] > order[start]:
                visited.add(nxt)
                dfs(start, nxt, path + [e], visited)
                visited.discard(nxt)

    for s in nodes:
        dfs(s, s, [], {s})
    out = []
    declared = {tuple(sorted(l["edges"])): l["id"] for l in cfg["loops"]}
    for cyc in cycles:
        sign = 1
        for e in cyc:
            sign *= e["sign"]
        ids = [e["id"] for e in cyc]
        out.append({"edges": ids, "nodes": [e["source"] for e in cyc], "length": len(cyc),
                    "polarity": "reinforcing" if sign > 0 else "balancing",
                    "declared_as": declared.get(tuple(sorted(ids)))})
    out.sort(key=lambda c: (c["length"], c["nodes"]))
    return out


def node_layer(sym: str) -> str:
    if sym in STATE_VARS:
        return "state"
    if sym in CONTEXT_VARS:
        return "context"
    return "derived"
