"""SQLite persistence, scoped by workspace.

A workspace is an opaque identifier sent by the browser (X-Workspace-Id). It separates
scenario libraries in a hosted deployment; it is NOT an authentication mechanism.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

_LOCK = threading.Lock()
MAX_RUNS_PER_WORKSPACE = 150

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL, seeded INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL, json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_scen_ws ON scenarios(workspace);
CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL, data_class TEXT NOT NULL, json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ds_ws ON datasets(workspace);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, workspace TEXT NOT NULL, kind TEXT NOT NULL, name TEXT, scenario_ids TEXT, summary_json TEXT, json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_runs_ws ON runs(workspace, kind);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def db_path() -> Path:
    # Vercel functions may only write to /tmp.
    # shortcut: /tmp is per-instance and wiped on cold start, so saved scenarios are not durable on Vercel; move to a hosted DB for real use.
    default = Path("/tmp/twin.sqlite3") if os.environ.get("VERCEL") else Path(__file__).resolve().parents[1] / "data" / "twin.sqlite3"
    p = Path(os.environ.get("TWIN_DB_PATH", default))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        c = sqlite3.connect(db_path(), timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.executescript(SCHEMA)
            yield c
            c.commit()
        finally:
            c.close()


# ----------------------------------------------------------------------------- workspace / model
def get_workspace(ws: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM workspaces WHERE id=?", (ws,)).fetchone()


def create_workspace(ws: str, config: dict[str, Any]) -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO workspaces(id, created_at, config_json, seeded) VALUES (?,?,?,0)", (ws, now(), json.dumps(config)))


def mark_seeded(ws: str) -> None:
    with conn() as c:
        c.execute("UPDATE workspaces SET seeded=1 WHERE id=?", (ws,))


def get_config(ws: str) -> dict[str, Any]:
    row = get_workspace(ws)
    if row is None:
        raise KeyError(ws)
    return json.loads(row["config_json"])


def save_config(ws: str, config: dict[str, Any]) -> None:
    with conn() as c:
        c.execute("UPDATE workspaces SET config_json=? WHERE id=?", (json.dumps(config), ws))


# ----------------------------------------------------------------------------- scenarios
def list_scenarios(ws: str) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT json, created_at, updated_at FROM scenarios WHERE workspace=? ORDER BY created_at, rowid", (ws,)).fetchall()
    return [{**json.loads(r["json"]), "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]


def get_scenario(ws: str, sid: str) -> Optional[dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT json, created_at, updated_at FROM scenarios WHERE workspace=? AND id=?", (ws, sid)).fetchone()
    return None if r is None else {**json.loads(r["json"]), "created_at": r["created_at"], "updated_at": r["updated_at"]}


def upsert_scenario(ws: str, sc: dict[str, Any]) -> dict[str, Any]:
    sc = {k: v for k, v in sc.items() if k not in ("created_at", "updated_at")}
    if not sc.get("id"):
        sc["id"] = new_id("scn")
    t = now()
    with conn() as c:
        exists = c.execute("SELECT 1 FROM scenarios WHERE id=? AND workspace=?", (sc["id"], ws)).fetchone()
        if exists:
            c.execute("UPDATE scenarios SET name=?, json=?, updated_at=? WHERE id=? AND workspace=?", (sc["name"], json.dumps(sc), t, sc["id"], ws))
        else:
            c.execute("INSERT INTO scenarios(id, workspace, name, json, created_at, updated_at) VALUES (?,?,?,?,?,?)", (sc["id"], ws, sc["name"], json.dumps(sc), t, t))
    return get_scenario(ws, sc["id"])  # type: ignore[return-value]


def delete_scenario(ws: str, sid: str) -> bool:
    with conn() as c:
        return c.execute("DELETE FROM scenarios WHERE id=? AND workspace=?", (sid, ws)).rowcount > 0


# ----------------------------------------------------------------------------- datasets
def list_datasets(ws: str) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT id, name, data_class, json, created_at FROM datasets WHERE workspace=? ORDER BY created_at DESC, rowid DESC", (ws,)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["json"])
        out.append({"id": r["id"], "name": r["name"], "data_class": r["data_class"], "created_at": r["created_at"],
                    "n_periods": len(d.get("periods", [])), "periods": [d["periods"][0], d["periods"][-1]] if d.get("periods") else [],
                    "variables": sorted(d.get("variables", {}).keys()), "quality": d.get("quality"), "provenance": d.get("provenance")})
    return out


def get_dataset(ws: str, did: str) -> Optional[dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT json FROM datasets WHERE workspace=? AND id=?", (ws, did)).fetchone()
    return None if r is None else json.loads(r["json"])


def save_dataset(ws: str, ds: dict[str, Any]) -> dict[str, Any]:
    ds = dict(ds)
    ds["id"] = ds.get("id") or new_id("ds")
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO datasets(id, workspace, name, data_class, json, created_at) VALUES (?,?,?,?,?,?)",
                  (ds["id"], ws, ds["name"], ds["data_class"], json.dumps(ds), now()))
    return ds


def delete_dataset(ws: str, did: str) -> bool:
    with conn() as c:
        return c.execute("DELETE FROM datasets WHERE id=? AND workspace=?", (did, ws)).rowcount > 0


# ----------------------------------------------------------------------------- runs
def save_run(ws: str, kind: str, name: str, scenario_ids: list[str], summary: dict[str, Any], payload: dict[str, Any]) -> str:
    rid = new_id("run")
    with conn() as c:
        c.execute("INSERT INTO runs(id, workspace, kind, name, scenario_ids, summary_json, json, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (rid, ws, kind, name, json.dumps(scenario_ids), json.dumps(summary), json.dumps(payload), now()))
        old = c.execute("SELECT id FROM runs WHERE workspace=? ORDER BY created_at DESC, rowid DESC LIMIT -1 OFFSET ?", (ws, MAX_RUNS_PER_WORKSPACE)).fetchall()
        for o in old:
            c.execute("DELETE FROM runs WHERE id=?", (o["id"],))
    return rid


def list_runs(ws: str, kind: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    q = "SELECT id, kind, name, scenario_ids, summary_json, created_at FROM runs WHERE workspace=?"
    args: list[Any] = [ws]
    if kind:
        q += " AND kind=?"
        args.append(kind)
    q += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        rows = c.execute(q, args).fetchall()
    return [{"id": r["id"], "kind": r["kind"], "name": r["name"], "scenario_ids": json.loads(r["scenario_ids"] or "[]"),
             "summary": json.loads(r["summary_json"] or "{}"), "created_at": r["created_at"]} for r in rows]


def get_run(ws: str, rid: str) -> Optional[dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT * FROM runs WHERE workspace=? AND id=?", (ws, rid)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "kind": r["kind"], "name": r["name"], "scenario_ids": json.loads(r["scenario_ids"] or "[]"),
            "summary": json.loads(r["summary_json"] or "{}"), "created_at": r["created_at"], "payload": json.loads(r["json"])}


def delete_run(ws: str, rid: str) -> bool:
    with conn() as c:
        return c.execute("DELETE FROM runs WHERE id=? AND workspace=?", (rid, ws)).rowcount > 0


def reset_workspace(ws: str) -> None:
    with conn() as c:
        for t in ("scenarios", "datasets", "runs"):
            c.execute(f"DELETE FROM {t} WHERE workspace=?", (ws,))
        c.execute("DELETE FROM workspaces WHERE id=?", (ws,))
