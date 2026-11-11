"""Dataset import, validation, privacy guard and quality reporting (Sections 02, 18).

Rules enforced here:
* Only AGGREGATE institutional data: exactly one row per period. Multiple rows per period
  suggest person-level records and are rejected.
* Columns that look like identifiers, names, demographic or sensitive attributes
  (ethnicity, religion, diagnoses, health, social media, ...) are rejected outright.
* Unknown columns are never silently mapped: each must be mapped or explicitly ignored.
* Missing values remain missing (None); they are never converted to zero.
* Every dataset carries a data class: SYNTHETIC, PUBLIC_RESEARCH or AUTHORIZED_SCHOOL.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from .normalization import NormSpec, normalize, was_clipped
from .schemas import ALL_VARS

DATA_CLASSES = ("SYNTHETIC", "PUBLIC_RESEARCH", "AUTHORIZED_SCHOOL")
FLOW_TARGETS = ("I", "C_flow", "Q")
COUNT_TARGETS = ("n_respondents",)
SURVEY_VARS = ("C", "T", "J", "H")
SMALL_CELL_THRESHOLD = 10
MAX_ROWS = 600

# Patterns indicating person-level identifiers or sensitive attributes (EN + TR).
FORBIDDEN_PATTERNS = [
    r"student", r"ogrenci", r"öğrenci", r"pupil", r"\bname\b", r"first_?name", r"last_?name", r"surname", r"\bad\b", r"soyad",
    r"\bisim\b", r"\btc\b", r"tckn", r"kimlik", r"national_?id", r"\bssn\b", r"passport", r"e-?mail", r"phone", r"telefon",
    r"address", r"adres", r"birth", r"dogum", r"doğum", r"\bage\b", r"\byas\b", r"\byaş\b", r"gender", r"cinsiyet", r"\bsex\b",
    r"ethnic", r"etnik", r"\brace\b", r"irk", r"ırk", r"religio", r"\bdin\b", r"mezhep", r"diagnos", r"tani", r"tanı",
    r"health", r"saglik", r"sağlık", r"medical", r"medication", r"ilac", r"ilaç", r"disab", r"engel", r"psychiatr", r"psikiyatr",
    r"social_?media", r"sosyal_?medya", r"instagram", r"twitter", r"tiktok", r"facebook", r"username", r"kullanici", r"kullanıcı",
    r"threat_?score", r"risk_?score", r"danger", r"tehlike", r"offender", r"suspect", r"şüpheli", r"supheli", r"profile",
]
PERIOD_NAMES = ("period", "month", "date", "donem", "dönem", "ay", "tarih", "time", "t")
FLOW_ALIASES = {
    "I": ("i", "incoming_requests", "requests", "gelen_talep", "inflow"),
    "C_flow": ("c_flow", "completed_processes", "completed", "tamamlanan", "outflow"),
    "Q": ("q", "pending_processes", "pending", "backlog", "bekleyen"),
}


class DatasetError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _var_meta(cfg: dict[str, Any]) -> dict[str, dict]:
    return {v["symbol"]: v for v in cfg["variables"]}


def forbidden_columns(columns: list[str]) -> list[str]:
    bad = []
    for c in columns:
        low = c.strip().lower()
        if any(re.search(p, low) for p in FORBIDDEN_PATTERNS):
            bad.append(c)
    return bad


def parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError(["file must be UTF-8 encoded text (CSV or JSON)"]) from exc
    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DatasetError([f"invalid JSON: {exc.msg} (line {exc.lineno})"]) from exc
        if isinstance(data, dict) and "periods" in data and "variables" in data:
            rows = []
            for t, p in enumerate(data["periods"]):
                row = {"period": p}
                for s, ser in data.get("variables", {}).items():
                    row[s] = ser[t] if t < len(ser) else None
                for s, ser in data.get("flows", {}).items():
                    row[s] = ser[t] if t < len(ser) else None
                for s, ser in data.get("counts", {}).items():
                    row[s] = ser[t] if t < len(ser) else None
                rows.append(row)
            return pd.DataFrame(rows)
        if isinstance(data, list) and all(isinstance(r, dict) for r in data):
            return pd.DataFrame(data)
        raise DatasetError(["JSON must be a list of row objects or a dataset object with 'periods' and 'variables'"])
    if name.endswith(".csv") or name.endswith(".txt"):
        try:
            return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=["", "NA", "NaN", "null", "None"])
        except Exception as exc:  # pandas raises several types
            raise DatasetError([f"could not parse CSV: {exc}"]) from exc
    raise DatasetError(["unsupported file type; upload a .csv or .json file"])


def suggest_mapping(cfg: dict[str, Any], columns: list[str]) -> dict[str, Optional[str]]:
    meta = _var_meta(cfg)
    by_id = {v["id"].lower(): s for s, v in meta.items()}
    by_key = {v["key"].lower(): s for s, v in meta.items()}
    out: dict[str, Optional[str]] = {}
    for c in columns:
        raw, low = c.strip(), c.strip().lower()
        target: Optional[str] = None
        if raw in ALL_VARS:
            target = raw
        elif low in by_id:
            target = by_id[low]
        elif low in by_key:
            target = by_key[low]
        elif low in PERIOD_NAMES:
            target = "period"
        elif low in ("n_respondents", "respondents", "katilimci", "katılımcı", "n"):
            target = "n_respondents"
        elif low in ("data_class", "record_label", "veri_sinifi"):
            target = "ignore"
        else:
            for flow, aliases in FLOW_ALIASES.items():
                if low in aliases:
                    target = flow
        out[c] = target
    return out


def inspect(cfg: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    cols = [str(c) for c in df.columns]
    forbidden = forbidden_columns(cols)
    suggestion = suggest_mapping(cfg, cols)
    preview = df.head(5).replace({np.nan: None}).to_dict(orient="records")
    return {
        "columns": cols,
        "n_rows": int(len(df)),
        "suggested_mapping": suggestion,
        "unmapped": [c for c, t in suggestion.items() if t is None],
        "forbidden_columns": forbidden,
        "privacy_ok": not forbidden,
        "preview": preview,
        "targets": ["period", "ignore", *ALL_VARS, *FLOW_TARGETS, *COUNT_TARGETS],
    }


def _parse_period(values: list[str]) -> list[str]:
    out = []
    for v in values:
        s = str(v).strip()
        if re.fullmatch(r"\d{4}-\d{2}", s):
            out.append(s)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            out.append(s[:7])
        elif re.fullmatch(r"\d+", s):
            out.append(f"t{int(s):04d}")
        else:
            raise DatasetError([f"period value '{s}' is not YYYY-MM, YYYY-MM-DD or an integer index"])
    return out


def build_dataset(
    cfg: dict[str, Any],
    df: pd.DataFrame,
    mapping: dict[str, dict[str, Any] | str],
    data_class: str,
    name: str,
    provenance: Optional[dict[str, Any]] = None,
    suppress_small_cells: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    provenance = dict(provenance or {})
    if data_class not in DATA_CLASSES:
        errors.append(f"data_class must be one of {DATA_CLASSES}")
    if data_class == "AUTHORIZED_SCHOOL":
        for f in ("authorization_reference", "data_controller"):
            if not str(provenance.get(f, "")).strip():
                errors.append(f"AUTHORIZED_SCHOOL data requires provenance field '{f}'")
    if data_class == "PUBLIC_RESEARCH" and not str(provenance.get("source", "")).strip():
        errors.append("PUBLIC_RESEARCH data requires a 'source' citation in provenance")
    if len(df) == 0:
        errors.append("dataset contains no rows")
    if len(df) > MAX_ROWS:
        errors.append(f"dataset has {len(df)} rows; at most {MAX_ROWS} monthly aggregate rows are supported")
    cols = [str(c) for c in df.columns]
    forbidden = forbidden_columns(cols)
    if forbidden:
        errors.append(f"columns rejected by privacy guard (identifiers or sensitive attributes are never accepted): {forbidden}")

    spec: dict[str, dict[str, Any]] = {}
    for c in cols:
        m = mapping.get(c)
        if m is None:
            continue
        spec[c] = {"target": m} if isinstance(m, str) else dict(m)
    unmapped = [c for c in cols if c not in spec]
    if unmapped:
        errors.append(f"unmapped columns {unmapped}: map each to a model variable or mark it 'ignore' (unknown columns are never mapped silently)")
    targets = [s["target"] for s in spec.values() if s["target"] != "ignore"]
    valid_targets = set(ALL_VARS) | set(FLOW_TARGETS) | set(COUNT_TARGETS) | {"period"}
    bad_t = sorted({t for t in targets if t not in valid_targets})
    if bad_t:
        errors.append(f"invalid mapping targets {bad_t}")
    dups = sorted({t for t in targets if targets.count(t) > 1})
    if dups:
        errors.append(f"multiple columns mapped to the same target: {dups}")
    if "period" not in targets:
        errors.append("one column must be mapped to 'period'")
    if errors:
        raise DatasetError(errors)

    period_col = next(c for c, s in spec.items() if s["target"] == "period")
    periods = _parse_period(df[period_col].tolist())
    if len(set(periods)) != len(periods):
        raise DatasetError(["periods must be unique: one aggregate row per month is required (multiple rows per period suggest person-level data, which is not accepted)"])
    order = np.argsort(np.array(periods, dtype=object))
    periods = [periods[i] for i in order]
    df = df.iloc[order].reset_index(drop=True)

    meta = _var_meta(cfg)
    variables: dict[str, list[Optional[float]]] = {}
    flows: dict[str, list[Optional[float]]] = {}
    counts: dict[str, list[Optional[float]]] = {}
    clipped: dict[str, int] = {}
    scales: dict[str, Any] = {}
    for c, s in spec.items():
        t = s["target"]
        if t in ("period", "ignore"):
            continue
        vals: list[Optional[float]] = []
        for r, raw in enumerate(df[c].tolist()):
            if raw is None or (isinstance(raw, float) and np.isnan(raw)) or str(raw).strip() == "":
                vals.append(None)
                continue
            try:
                vals.append(float(str(raw).replace(",", ".")) if isinstance(raw, str) else float(raw))
            except ValueError:
                errors.append(f"column '{c}', row {r + 1}: '{raw}' is not numeric")
                vals.append(None)
        if t in ALL_VARS:
            scale = s.get("scale", "normalized")
            if scale == "normalized":
                bad = [i + 1 for i, v in enumerate(vals) if v is not None and not (0.0 <= v <= 1.0)]
                if bad:
                    errors.append(f"column '{c}' declared normalized but rows {bad[:10]} lie outside [0, 1]; declare scale 'raw' with reference bounds")
                variables[t] = vals
                scales[t] = {"scale": "normalized"}
            elif scale == "raw":
                mm = meta[t]["measurement"]
                ns = NormSpec(float(s.get("lower", mm["lower"])), float(s.get("upper", mm["upper"])), s.get("direction", mm["direction"]))
                clipped[t] = sum(was_clipped(v, ns) for v in vals)
                variables[t] = [None if v is None else round(normalize(v, ns), 6) for v in vals]
                scales[t] = {"scale": "raw", "lower": ns.lower, "upper": ns.upper, "direction": ns.direction}
                if clipped[t]:
                    warnings.append(f"{t}: {clipped[t]} raw value(s) outside reference bounds were clipped to [0, 1]")
            else:
                errors.append(f"column '{c}': scale must be 'normalized' or 'raw'")
        elif t in FLOW_TARGETS:
            if any(v is not None and v < 0 for v in vals):
                errors.append(f"column '{c}': process counts must be non-negative")
            flows[t] = vals
        else:
            counts[t] = vals
    if errors:
        raise DatasetError(errors)

    if suppress_small_cells and "n_respondents" in counts:
        for t, n in enumerate(counts["n_respondents"]):
            if n is not None and n < SMALL_CELL_THRESHOLD:
                for sym in SURVEY_VARS:
                    if sym in variables and variables[sym][t] is not None:
                        variables[sym][t] = None
                warnings.append(f"period {periods[t]}: survey aggregates suppressed (n_respondents={int(n)} < {SMALL_CELL_THRESHOLD})")

    ds = {
        "name": name, "data_class": data_class, "frequency": "monthly", "periods": periods,
        "record_labels": [data_class] * len(periods), "variables": variables, "flows": flows, "counts": counts,
        "value_scale": "normalized", "mapping": {c: s for c, s in spec.items()}, "scales": scales,
        "provenance": {**provenance, "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "import_warnings": warnings,
    }
    ds["quality"] = quality_report(ds)
    return ds


def quality_report(ds: dict[str, Any]) -> dict[str, Any]:
    n = len(ds.get("periods", []))
    per_var: dict[str, Any] = {}
    total_cells = 0
    total_missing = 0
    for sym in ALL_VARS:
        ser = ds.get("variables", {}).get(sym)
        if ser is None:
            per_var[sym] = {"present": False, "n": 0, "missing": n, "missing_pct": 100.0 if n else 0.0}
            total_cells += n
            total_missing += n
            continue
        vals = np.array([np.nan if v is None else v for v in ser], dtype=float)
        miss = int(np.isnan(vals).sum())
        gaps, run_len = 0, 0
        for v in vals:
            run_len = run_len + 1 if np.isnan(v) else 0
            gaps = max(gaps, run_len)
        finite = vals[np.isfinite(vals)]
        per_var[sym] = {
            "present": True, "n": int(len(vals) - miss), "missing": miss,
            "missing_pct": round(100 * miss / max(1, len(vals)), 2), "longest_gap": gaps,
            "min": float(finite.min()) if finite.size else None, "max": float(finite.max()) if finite.size else None,
            "mean": float(finite.mean()) if finite.size else None,
            "constant": bool(finite.size > 1 and np.ptp(finite) < 1e-9),
        }
        total_cells += len(vals)
        total_missing += miss
    fl = ds.get("flows", {})
    mass = None
    if all(k in fl for k in FLOW_TARGETS):
        Q, I, C = fl["Q"], fl["I"], fl["C_flow"]
        errs = [abs(Q[t] - Q[t - 1] - I[t] + C[t]) for t in range(1, n)
                if None not in (Q[t], Q[t - 1], I[t], C[t])]
        mass = {"checked_periods": len(errs), "max_abs_error": max(errs) if errs else None,
                "consistent": (max(errs) < 1e-6) if errs else None}
    return {
        "n_periods": n,
        "completeness_pct": round(100 * (1 - total_missing / max(1, total_cells)), 2),
        "variables": per_var,
        "flows_present": sorted(fl.keys()),
        "flow_mass_balance": mass,
        "data_class": ds.get("data_class"),
        "all_records_labelled": ds.get("record_labels", []) == [ds.get("data_class")] * n,
    }


def to_csv(ds: dict[str, Any]) -> str:
    rows = []
    for t, p in enumerate(ds["periods"]):
        row: dict[str, Any] = {"period": p, "data_class": ds["data_class"]}
        for s in ALL_VARS:
            if s in ds.get("variables", {}):
                row[s] = ds["variables"][s][t]
        for k, ser in ds.get("flows", {}).items():
            row[k] = ser[t]
        for k, ser in ds.get("counts", {}).items():
            row[k] = ser[t]
        rows.append(row)
    return pd.DataFrame(rows).to_csv(index=False)
