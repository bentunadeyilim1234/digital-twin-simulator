"""Typed schemas for the authoritative model configuration and for scenarios.

The JSON file ``config/model_config.json`` is validated against :class:`ModelConfig`.
Validation is strict: unknown edge endpoints, invalid edge kinds, out-of-range
coefficients and inconsistent weights are rejected with actionable messages.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Fixed vocabulary of the model structure
# ---------------------------------------------------------------------------

STATE_VARS: tuple[str, ...] = ("E", "C", "T", "A", "K", "S", "P")
CONTEXT_VARS: tuple[str, ...] = ("F", "O", "M", "J", "H", "TR", "IF")
DERIVED_VARS: tuple[str, ...] = ("R", "L")
OPERATIONAL_VARS: tuple[str, ...] = ("R", "L", "Qp")  # Y(t) entering target equations
ALL_VARS: tuple[str, ...] = ("E", "F", "O", "M", "C", "T", "J", "H", "A", "R", "L", "K", "S", "TR", "P", "IF")
FLOW_NODES: tuple[str, ...] = ("Q", "I", "C_flow", "mu", "Qp", "flex")
DOMAINS: tuple[str, ...] = ("ENV", "SOC", "ORG", "SUP")

Evidence = Literal["E1", "E2", "H", "L"]
EdgeKind = Literal["linear", "context_response", "derived", "flow_multiplier", "feedback_gain", "structural"]
Provenance = Literal["illustrative", "hypothesized", "expert", "literature", "calibrated", "structural"]
EDITABLE_KINDS = ("linear", "context_response", "derived", "flow_multiplier", "feedback_gain")


class LangText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str = ""
    tr: str = ""


class MeasurementComponent(BaseModel):
    name: str
    unit: str
    lower: float
    upper: float
    direction: Literal["positive", "negative"]


class Measurement(BaseModel):
    unit: str
    lower: float
    upper: float
    direction: Literal["positive", "negative"]
    sources: list[str] = Field(default_factory=list)
    components: list[MeasurementComponent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounds(self) -> "Measurement":
        if not (math.isfinite(self.lower) and math.isfinite(self.upper)) or self.upper <= self.lower:
            raise ValueError(f"measurement bounds must satisfy lower < upper (got {self.lower}, {self.upper})")
        return self


class Variable(BaseModel):
    id: str
    symbol: str
    key: str
    domain: Literal["ENV", "SOC", "ORG", "SUP"]
    role: Literal["state", "context", "derived"]
    initial: float = Field(ge=0.0, le=1.0)
    labels: LangText
    definition: LangText
    measurement: Measurement
    measurement_evidence: Evidence
    references: list[str] = Field(default_factory=list)
    notes: str = ""


class FlowNode(BaseModel):
    key: str
    labels: LangText
    unit: str
    kind: str


class Intervention(BaseModel):
    key: str
    labels: LangText
    cost_param: str


class ExternalCondition(BaseModel):
    key: str
    default: float = Field(ge=0.0, le=1.0)
    labels: LangText
    description: LangText = LangText()


class Edge(BaseModel):
    id: str
    source: str
    target: str
    kind: EdgeKind
    sign: Literal[1, -1]
    coefficient: float = Field(ge=0.0)
    range: Optional[tuple[float, float]] = None
    reference: float = 0.5
    symbol: str = ""
    hypothesis: Optional[str] = None
    evidence: Evidence
    confidence: Literal["low", "medium", "high"] = "low"
    references: list[str] = Field(default_factory=list)
    enabled: bool = True
    description: LangText = LangText()
    notes: str = ""
    custom: bool = False
    original: Optional[dict] = None  # snapshot of original assumptions (sign/coef/enabled)

    @model_validator(mode="after")
    def _check(self) -> "Edge":
        if not math.isfinite(self.coefficient):
            raise ValueError(f"edge {self.id}: coefficient must be finite")
        if self.coefficient > 5.0:
            raise ValueError(f"edge {self.id}: coefficient {self.coefficient} exceeds the supported maximum 5.0")
        if self.range is not None:
            lo, hi = self.range
            if lo > hi:
                raise ValueError(f"edge {self.id}: range lower bound exceeds upper bound")
            if lo < 0:
                raise ValueError(f"edge {self.id}: range must be non-negative (sign is stored separately)")
        if self.kind == "structural" and self.coefficient != 1.0:
            raise ValueError(f"edge {self.id}: structural (accounting) edges are fixed at coefficient 1")
        return self


class LiteratureRange(BaseModel):
    reference: str
    low: float
    high: float
    note: str = ""


class ExpertRange(BaseModel):
    low: float
    mode: float
    high: float
    expert: str = ""
    date: str = ""
    rationale: str = ""

    @model_validator(mode="after")
    def _order(self) -> "ExpertRange":
        if not (self.low <= self.mode <= self.high):
            raise ValueError("expert range must satisfy low <= mode <= high")
        return self


class Parameter(BaseModel):
    id: str
    group: Literal["baseline", "transition", "flow", "weights", "cost"]
    symbol: str
    value: float
    min: float
    max: float
    range: Optional[tuple[float, float]] = None
    unit: str = ""
    provenance: Provenance = "illustrative"
    description: LangText = LangText()
    literature_ranges: list[LiteratureRange] = Field(default_factory=list)
    expert_range: Optional[ExpertRange] = None
    calibration: Optional[dict] = None

    @model_validator(mode="after")
    def _bounds(self) -> "Parameter":
        if not math.isfinite(self.value):
            raise ValueError(f"parameter {self.id}: value must be finite")
        if self.min > self.max:
            raise ValueError(f"parameter {self.id}: min > max")
        if not (self.min - 1e-12 <= self.value <= self.max + 1e-12):
            raise ValueError(f"parameter {self.id}: value {self.value} outside hard bounds [{self.min}, {self.max}]")
        if self.range is not None and self.range[0] > self.range[1]:
            raise ValueError(f"parameter {self.id}: uncertainty range lower bound exceeds upper bound")
        return self


class Loop(BaseModel):
    id: str
    polarity: Literal["reinforcing", "balancing"]
    edges: list[str]
    labels: LangText
    description: LangText = LangText()


class OffDiagonal(BaseModel):
    row: str
    col: str
    value: float


class Domain(BaseModel):
    id: Literal["ENV", "SOC", "ORG", "SUP"]
    labels: LangText
    variables: list[str]


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    model_id: str
    parameter_set: dict
    time: dict
    domains: list[Domain]
    variables: list[Variable]
    flow_nodes: list[FlowNode]
    interventions: list[Intervention]
    external_conditions: list[ExternalCondition]
    edges: list[Edge]
    loops: list[Loop]
    parameters: list[Parameter]
    transition_offdiagonal: list[OffDiagonal] = Field(default_factory=list)
    variable_weights: dict[str, float]
    initial_stock: dict
    validation_envelope: dict = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def _sixteen(cls, v: list[Variable]) -> list[Variable]:
        symbols = [x.symbol for x in v]
        if sorted(symbols) != sorted(ALL_VARS):
            raise ValueError(f"exactly the 16 model variables {ALL_VARS} are required; got {symbols}")
        for var in v:
            expected = "state" if var.symbol in STATE_VARS else "context" if var.symbol in CONTEXT_VARS else "derived"
            if var.role != expected:
                raise ValueError(f"variable {var.symbol} must have role '{expected}' (got '{var.role}')")
        return v

    @model_validator(mode="after")
    def _structure(self) -> "ModelConfig":
        errors: list[str] = []
        iv = [i.key for i in self.interventions]
        ex = [e.key for e in self.external_conditions]
        pids = [p.id for p in self.parameters]
        eids = [e.id for e in self.edges]
        for name, ids in (("parameter", pids), ("edge", eids), ("intervention", iv), ("external condition", ex)):
            dup = {x for x in ids if ids.count(x) > 1}
            if dup:
                errors.append(f"duplicate {name} ids: {sorted(dup)}")
        state, ctx = set(STATE_VARS), set(CONTEXT_VARS)
        src_linear = state | ctx | set(OPERATIONAL_VARS) | set(iv) | set(ex)
        allowed = {
            "linear": (src_linear, state),
            "context_response": (state | set(iv) | set(ex), ctx),
            "derived": (state | ctx | {"Qp"} | set(ex), {"L"}),
            "flow_multiplier": (state | ctx | set(ex), {"I", "mu"}),
            "feedback_gain": ({"Qp"}, {"flex"}),
        }
        all_nodes = set(ALL_VARS) | set(FLOW_NODES) | set(iv) | set(ex)
        n_gain = 0
        for e in self.edges:
            if e.kind == "structural":
                if e.source not in all_nodes or e.target not in all_nodes:
                    errors.append(f"structural edge {e.id} references unknown node")
                continue
            sources, targets = allowed[e.kind]
            if e.source not in sources:
                errors.append(f"edge {e.id}: source '{e.source}' is not valid for kind '{e.kind}'")
            if e.target not in targets:
                errors.append(f"edge {e.id}: target '{e.target}' is not valid for kind '{e.kind}'")
            if e.source == e.target:
                errors.append(f"edge {e.id}: self-loops are not permitted (use the transition matrix)")
            if e.kind == "feedback_gain":
                n_gain += 1
        if n_gain > 1:
            errors.append("only one feedback_gain edge (B1) is permitted")
        # Duplicate source/target/kind pairs would silently double-count.
        pairs = [(e.source, e.target, e.kind) for e in self.edges if e.kind != "structural"]
        dup_pairs = {p for p in pairs if pairs.count(p) > 1}
        if dup_pairs:
            errors.append(f"duplicate relationships (same source, target, kind): {sorted(dup_pairs)}")
        eid_set = set(eids)
        for loop in self.loops:
            missing = [x for x in loop.edges if x not in eid_set]
            if missing:
                errors.append(f"loop {loop.id} references unknown edges {missing}")
        for p in self.interventions:
            if p.cost_param not in pids:
                errors.append(f"intervention {p.key}: cost parameter {p.cost_param} missing")
        for od in self.transition_offdiagonal:
            if od.row not in STATE_VARS or od.col not in STATE_VARS or od.row == od.col:
                errors.append(f"transition off-diagonal entry ({od.row},{od.col}) invalid")
        for sym in ALL_VARS:
            w = self.variable_weights.get(sym)
            if w is None or w < 0 or not math.isfinite(w):
                errors.append(f"variable weight for {sym} must be a non-negative number")
        for d in self.domains:
            if sum(self.variable_weights.get(s, 0) for s in d.variables) <= 0:
                errors.append(f"domain {d.id}: within-domain weights must not all be zero")
        dom_w = [p.value for p in self.parameters if p.group == "weights"]
        if dom_w and sum(dom_w) <= 0:
            errors.append("domain weights must not all be zero")
        required = [f"b.{s}" for s in STATE_VARS] + ["b.L"] + [f"lambda.{s}" for s in STATE_VARS] + [
            "lambda.context", "flow.I_base", "flow.alloc_share", "flow.h_proc", "flow.w_half",
            "flow.flex_max_hours", "flow.lambda_flex",
        ] + [f"weights.domain.{d}" for d in DOMAINS]
        missing_p = [r for r in required if r not in pids]
        if missing_p:
            errors.append(f"missing required parameters: {missing_p}")
        if errors:
            raise ValueError("; ".join(errors))
        return self


# ---------------------------------------------------------------------------
# Scenario schema
# ---------------------------------------------------------------------------


class SeriesSpec(BaseModel):
    """A constant value or a per-month schedule (months 0..N). Short schedules hold their last value."""

    value: Optional[float] = None
    values: Optional[list[Optional[float]]] = None

    @model_validator(mode="after")
    def _one(self) -> "SeriesSpec":
        if self.value is None and not self.values:
            raise ValueError("series spec requires 'value' or a non-empty 'values' list")
        for v in ([self.value] if self.value is not None else []) + [x for x in (self.values or []) if x is not None]:
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"normalised series values must lie in [0, 1] (got {v})")
        return self


class InterventionSchedule(BaseModel):
    key: str
    intensity: float = Field(ge=0.0, le=1.0)
    start_month: int = Field(ge=1, default=1)
    ramp_months: int = Field(ge=0, default=0)
    end_month: Optional[int] = None

    @model_validator(mode="after")
    def _end(self) -> "InterventionSchedule":
        if self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("end_month must be >= start_month")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: str = "Untitled scenario"
    description: str = ""
    notes: str = ""
    template_id: Optional[str] = None
    is_baseline: bool = False
    horizon_months: int = Field(default=12, ge=1, le=60)
    initial_state: dict[str, float] = Field(default_factory=dict)
    initial_stock: dict[str, float] = Field(default_factory=dict)
    variable_modes: dict[str, Literal["model", "manual"]] = Field(default_factory=dict)
    overrides: dict[str, SeriesSpec] = Field(default_factory=dict)
    context_schedule: dict[str, SeriesSpec] = Field(default_factory=dict)
    interventions: list[InterventionSchedule] = Field(default_factory=list)
    external: dict[str, SeriesSpec] = Field(default_factory=dict)
    parameter_overrides: dict[str, float] = Field(default_factory=dict)
    dataset_id: Optional[str] = None
    dataset_anchor: Literal["latest", "replay"] = "latest"

    @field_validator("initial_state")
    @classmethod
    def _init(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if k not in ALL_VARS:
                raise ValueError(f"initial_state: unknown variable '{k}'")
            if x is None or not (0.0 <= float(x) <= 1.0):
                raise ValueError(f"initial_state[{k}] must lie in [0, 1]")
        return v

    @field_validator("variable_modes", "overrides")
    @classmethod
    def _vars(cls, v: dict) -> dict:
        for k in v:
            if k not in ALL_VARS:
                raise ValueError(f"unknown variable '{k}'")
        return v

    @field_validator("context_schedule")
    @classmethod
    def _ctx(cls, v: dict) -> dict:
        for k in v:
            if k not in CONTEXT_VARS:
                raise ValueError(f"context_schedule: '{k}' is not an observed context indicator {CONTEXT_VARS}")
        return v

    @field_validator("initial_stock")
    @classmethod
    def _stock(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if k not in ("Q", "flex"):
                raise ValueError(f"initial_stock: unknown stock '{k}'")
            if x < 0 or not math.isfinite(x):
                raise ValueError(f"initial_stock[{k}] must be a non-negative number")
        return v
