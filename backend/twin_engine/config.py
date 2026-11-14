"""Loading, validating and hashing the authoritative model configuration."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import ModelConfig

ENGINE_VERSION = "1.0.0"


def config_dir() -> Path:
    env = os.environ.get("TWIN_CONFIG_DIR")
    if env:
        return Path(env)
    # backend/twin_engine/config.py -> backend/config
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "config" / "model_config.json"
        if cand.exists():
            return cand.parent
    raise FileNotFoundError("could not locate config/model_config.json; set TWIN_CONFIG_DIR")


@lru_cache(maxsize=1)
def _default_raw() -> str:
    return (config_dir() / "model_config.json").read_text(encoding="utf-8")


def default_config() -> dict[str, Any]:
    """Return a fresh deep copy of the shipped default configuration (validated)."""
    cfg = json.loads(_default_raw())
    cfg = validate_config(cfg)
    return cfg


def snapshot_originals(cfg: dict[str, Any]) -> dict[str, Any]:
    """Store original sign/coefficient/enabled of each edge so the UI can show modifications and restore them."""
    for e in cfg["edges"]:
        if not e.get("original"):
            e["original"] = {"sign": e["sign"], "coefficient": e["coefficient"], "enabled": e["enabled"]}
    return cfg


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate against the schema and return a normalised plain-dict copy. Raises ValueError on failure."""
    model = ModelConfig.model_validate(cfg)
    out = json.loads(model.model_dump_json())
    return snapshot_originals(out)


@lru_cache(maxsize=1)
def templates() -> list[dict[str, Any]]:
    data = json.loads((config_dir() / "scenario_templates.json").read_text(encoding="utf-8"))
    return data["templates"]


@lru_cache(maxsize=1)
def references() -> list[dict[str, Any]]:
    data = json.loads((config_dir() / "references.json").read_text(encoding="utf-8"))
    return data["references"]


def numeric_fingerprint(cfg: dict[str, Any]) -> dict[str, Any]:
    """The parts of the configuration that influence numerical output."""
    return {
        "edges": sorted(
            [(e["id"], e["source"], e["target"], e["kind"], e["sign"], round(e["coefficient"], 12), e["enabled"], e.get("reference", 0.5))
             for e in cfg["edges"]]
        ),
        "parameters": sorted([(p["id"], round(p["value"], 12)) for p in cfg["parameters"]]),
        "offdiag": sorted([(o["row"], o["col"], o["value"]) for o in cfg.get("transition_offdiagonal", [])]),
        "variables": sorted([(v["symbol"], v["measurement"]["lower"], v["measurement"]["upper"], v["measurement"]["direction"]) for v in cfg["variables"]]),
        "weights": sorted(cfg["variable_weights"].items()),
        "initial_stock": sorted((k, str(v)) for k, v in cfg["initial_stock"].items()),
    }


def config_hash(cfg: dict[str, Any]) -> str:
    blob = json.dumps(numeric_fingerprint(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def deep_copy(cfg: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(cfg)
