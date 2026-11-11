// Types mirror the JSON returned by the FastAPI engine. No calculation lives here.

export type Lang = "tr" | "en";
export type LangText = { en: string; tr: string };
export type Evidence = "E1" | "E2" | "H" | "L";
export type DomainId = "ENV" | "SOC" | "ORG" | "SUP";

export interface Measurement {
  unit: string;
  lower: number;
  upper: number;
  direction: "positive" | "negative";
  sources: string[];
  components?: { name: string; unit: string; lower: number; upper: number; direction: string }[];
}

export interface Variable {
  id: string;
  symbol: string;
  key: string;
  domain: DomainId;
  role: "state" | "context" | "derived";
  initial: number;
  labels: LangText;
  definition: LangText;
  measurement: Measurement;
  measurement_evidence: Evidence;
  references: string[];
  notes: string;
}

export interface Edge {
  id: string;
  source: string;
  target: string;
  kind: "linear" | "context_response" | "derived" | "flow_multiplier" | "feedback_gain" | "structural";
  sign: 1 | -1;
  coefficient: number;
  range?: [number, number] | null;
  reference?: number;
  symbol: string;
  hypothesis: string | null;
  evidence: Evidence;
  confidence: "low" | "medium" | "high";
  references: string[];
  enabled: boolean;
  description: LangText;
  notes: string;
  custom?: boolean;
  original?: { sign: number; coefficient: number; enabled: boolean };
  modified?: boolean;
  effective?: number;
}

export interface Parameter {
  id: string;
  group: string;
  symbol: string;
  value: number;
  min: number;
  max: number;
  range?: [number, number] | null;
  unit: string;
  provenance: string;
  description: LangText;
  evidence?: Evidence;
  kind?: string;
  source?: string;
  target?: string;
  enabled?: boolean;
  expert_range?: { low: number; mode: number; high: number; expert?: string; rationale?: string } | null;
  literature_ranges?: { reference: string; low: number; high: number; note?: string }[];
}

export interface ModelConfig {
  schema_version: string;
  model_id: string;
  parameter_set: { name: string; status: string; statement: LangText };
  time: { default_horizon: number; max_horizon: number; calendar_start_month: number };
  domains: { id: DomainId; labels: LangText; variables: string[] }[];
  variables: Variable[];
  flow_nodes: { key: string; labels: LangText; unit: string; kind: string }[];
  interventions: { key: string; labels: LangText; cost_param: string }[];
  external_conditions: { key: string; default: number; labels: LangText; description: LangText }[];
  edges: Edge[];
  loops: { id: string; polarity: string; edges: string[]; labels: LangText; description: LangText }[];
  parameters: Parameter[];
  initial_stock: { Q: number; flex: string | number };
  validation_envelope: Record<string, unknown>;
}

export interface SeriesSpec {
  value?: number | null;
  values?: (number | null)[] | null;
}

export interface InterventionSchedule {
  key: string;
  intensity: number;
  start_month: number;
  ramp_months: number;
  end_month: number | null;
}

export interface Scenario {
  id: string;
  name: string;
  labels?: LangText | null;
  description: string;
  notes: string;
  template_id: string | null;
  is_baseline: boolean;
  horizon_months: number;
  initial_state: Record<string, number>;
  initial_stock: Record<string, number>;
  variable_modes: Record<string, "model" | "manual">;
  overrides: Record<string, SeriesSpec>;
  context_schedule: Record<string, SeriesSpec>;
  interventions: InterventionSchedule[];
  external: Record<string, SeriesSpec>;
  parameter_overrides: Record<string, number>;
  dataset_id: string | null;
  dataset_anchor: "latest" | "replay";
  created_at?: string;
  updated_at?: string;
}

export type Series = (number | null)[];

export interface SimResult {
  scenario_id: string | null;
  scenario_name: string | null;
  horizon: number;
  months: number[];
  variables: Record<string, Series>;
  targets: Record<string, Series>;
  indices: Record<string, Series>;
  flows: Record<string, Series>;
  interventions: Record<string, Series>;
  external: Record<string, Series>;
  resources: {
    program_hours_total: number;
    program_hours_by_intervention: Record<string, number>;
    program_hours_monthly: Series;
    support_hours_total: number;
    unit: string;
  };
  modes: Record<string, string>;
  diagnostics: { warnings: string[]; mass_balance_max_error: number; clipped_targets: number };
  provenance: { data_class: string; engine_version: string; config_hash: string; scenario_hash: string; parameter_status: string };
  run_id?: string;
}

export interface CompareResult {
  baseline_id: string;
  order: string[];
  results: Record<string, SimResult>;
  deltas: Record<string, { indices: Record<string, Series>; variables: Record<string, Series>; flows: Record<string, Series> }>;
  comparability: Record<string, string[]>;
  same_horizon: boolean;
  resources: Record<string, SimResult["resources"]>;
  run_id?: string;
}

export interface DatasetSummary {
  id: string;
  name: string;
  data_class: "SYNTHETIC" | "PUBLIC_RESEARCH" | "AUTHORIZED_SCHOOL";
  created_at: string;
  n_periods: number;
  periods: string[];
  variables: string[];
  quality: QualityReport;
  provenance: Record<string, unknown>;
}

export interface QualityReport {
  n_periods: number;
  completeness_pct: number;
  variables: Record<string, { present: boolean; n: number; missing: number; missing_pct: number; longest_gap?: number; min?: number | null; max?: number | null; mean?: number | null; constant?: boolean }>;
  flows_present: string[];
  flow_mass_balance: { checked_periods: number; max_abs_error: number | null; consistent: boolean | null } | null;
  data_class: string;
  all_records_labelled: boolean;
}

export interface Dataset {
  id: string;
  name: string;
  data_class: string;
  periods: string[];
  variables: Record<string, Series>;
  flows: Record<string, Series>;
  counts?: Record<string, Series>;
  provenance: Record<string, unknown>;
  quality?: QualityReport;
}

export interface RunSummary {
  id: string;
  kind: string;
  name: string;
  scenario_ids: string[];
  summary: Record<string, unknown>;
  created_at: string;
}

export interface Meta {
  engine_version: string;
  references: { id: string; type: string; citation: string; doi?: string; url?: string; verification: string }[];
  templates: { id: string; is_baseline: boolean; name: string; labels: LangText; description: LangText; interventions: InterventionSchedule[] }[];
  data_classes: string[];
  outputs: string[];
  variables: string[];
  default_calibration_params: string[];
  default_bayes_params: string[];
  uncertain_parameters: string[];
  capabilities: { salib: boolean; statsmodels: boolean; pymc: boolean; bayesian_backend: string };
  workspace: string;
}
