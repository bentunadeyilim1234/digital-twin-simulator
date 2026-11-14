# Model Specification

## 1. Purpose

The School Safety & Resilience Digital Twin is a deterministic, monthly system-dynamics
model of **one school as an institution**. It is designed to investigate:

- how physical/environmental, social-climate, organisational and support conditions interact;
- how organisational conditions affect support processes and their capacity limits;
- how prevention-oriented interventions may change institutional preparedness over time;
- where limited resources create bottlenecks (stock-flow block);
- which parameters dominate model outputs (sensitivity) and how parameter uncertainty
  propagates (uncertainty analysis);
- how alternative policies compare under identical initial conditions.

**Output = institutional readiness and process performance.** The model never produces
probabilities of violence, attack, harm or any individual-level quantity.

## 2. Research boundaries (enforced in code and data handling)

The system does not and must not:

- predict which student will commit violence or assign any individual score;
- generate attack probabilities, dates, routes, vulnerability maps or tactical recommendations;
- use identities, diagnoses, health records, ethnicity, religion, gender, age or social-media data;
- profile individuals psychologically or demographically.

Enforcement: there are no person-level inputs in the schema; dataset import rejects
identifier/sensitive columns and multiple rows per period (`twin_engine/datasets.py`); the
3D model contains no security features; outputs and labels avoid risk terminology (tested by
`test_accessibility_raises_requests_not_risk` and verification check V12). Research on targeted
school violence explicitly finds no accurate student profile (Vossekuil et al., 2002; National
Threat Assessment Center, 2019), which is consistent with an institution-level design.

## 3. Structure

Four domains, sixteen variables (details in `VARIABLE_DICTIONARY.md`):

| Domain | Variables | Roles |
|---|---|---|
| A — Physical & environmental (ENV) | E, F, O, M | E state; F, O, M context |
| B — Social school climate (SOC) | C, T, J, H | C, T state; J, H context (H responsive) |
| C — Organisational processes (ORG) | A, R, L, K | A, K state; R, L derived |
| D — Support & preparedness (SUP) | S, TR, P, IF | S, P state; TR, IF context (responsive to programmes) |

Plus the stock-flow block (Q, I, C_flow, μ, Qp, flex), six intervention inputs U and three
external conditions D. Equations: `MATHEMATICAL_EQUATIONS.md`. Relationships and evidence:
`CAUSAL_ASSUMPTIONS.md`. Parameters: `PARAMETER_REGISTRY.md`.

## 4. Variable classification decisions

- **State X** = [E, C, T, A, K, S, P] evolve by first-order adjustment toward targets X*.
- **Context Z** = [F, O, M, J, H, TR, IF] are observed (dataset or scenario schedule). Where
  the specification hypothesises that a context indicator responds (H4: T → H; training and
  follow-through programmes → TR, IF), the response is a lagged deviation ΔZ added to the
  observed path. This keeps Z observable while making loop R1 operational.
- **Derived R, L** are computed each month from the stock-flow block in model-calculated mode
  (R = completion ratio; L = follow-up equation including H9), or held at scenario values in
  manual override mode.

## 5. Scenarios

A scenario specifies: name, horizon (1–60 months, default 12), initial state for all 16
variables, initial backlog, per-variable model/manual mode and overrides, context schedules,
intervention schedules (intensity 0–1, start month, ramp-up months, optional end month),
external-condition values or schedules, parameter overrides, dataset selection (start from
latest observation, or replay observed context) and notes.

Templates S0–S4 (`backend/config/scenario_templates.json`) are illustrative and editable:

| ID | Interventions |
|---|---|
| S0 Baseline | none |
| S1 Accessibility | U_access 0.6 from month 1, 3-month ramp |
| S2 Organisational preparedness | U_training 0.6, U_coordination 0.5 (month 1, 4-month ramp), U_followthrough 0.5 (month 2) |
| S3 Support capacity | U_capacity 0.6 from month 1, 3-month ramp |
| S4 Integrated | S1 + S2 + S3 |

New scenarios inherit the baseline's initial state, external conditions, parameters and
dataset, so comparisons differ only in interventions unless the user changes something;
`/api/compare` lists every other difference (comparability report).

## 6. Default demonstration

The demonstration initial values (Section 19 of the brief) are stored in the configuration and
shown as **SYNTHETIC DEMONSTRATION DATA — NOT REAL SCHOOL MEASUREMENTS** on every page. The
baseline intercepts are anchored so this state is an equilibrium (see `MATHEMATICAL_EQUATIONS.md` §8).

## 7. Determinism and reproducibility

The simulator has no random component; identical inputs give bit-identical outputs (V03).
Random elements exist only in clearly separated outer layers (synthetic data, Latin-hypercube
sampling, MCMC) and are seeded. Every result carries an engine version, configuration hash,
scenario hash and data class.

## 8. Scope of use

Appropriate: exploring hypotheses, structuring discussions about institutional prevention,
teaching system dynamics, planning data collection, and — after calibration and validation with
authorised aggregate data — comparing policy options *within the validated envelope*.

Not appropriate: decisions about individual students, security or tactical planning, claims that
an intervention works, or any use of indices as probabilities.
