# Validation Protocol

Validation follows the structure-oriented approach to system-dynamics model validity
(Barlas, 1996): structure is examined before behaviour, and behaviour reproduction is never
taken as proof of causal correctness.

## 1. Mathematical verification (automated)

`GET /api/validation/verification` runs these checks on the *current* configuration; the same
properties are covered by `backend/tests`.

| ID | Check | Criterion |
|---|---|---|
| V01 | Schema & references | configuration validates (16 variables, valid endpoints/kinds, no duplicates, bounds) |
| V02 | Matrix dimensions | A 7×7, Γ 7×7, Π 7×3, B 7×6, G 7×3, Λ 7×7, Ω 7×7 |
| V03 | Determinism | two runs of S4 are bit-identical |
| V04 | State bounds | all 16 variables ∈ [0,1] under maximal interventions for 36 months |
| V05 | Mass balance | max \|Q(t) − Q(t−1) − I(t) + C_flow(t)\| < 1e-9 across templates |
| V06 | Zero inflow | I₀ = 0 ⇒ no requests and non-increasing backlog |
| V07 | Capacity | C_flow(t) = min(Q(t−1) + I(t), μ(t)) every month |
| V08 | Linear stability | spectral radius of the linearised [X, ΔZ] map < 1 |
| V09 | Local asymptotic stability | spectral radius of the full nonlinear one-step map < 1 |
| V10 | Comparable scenarios | templates differ from the baseline only in interventions |
| V11 | Parameter bounds | uncertainty ranges within hard bounds |
| V12 | Privacy | no person-level or risk-score fields in the model |
| V13 | Bounded response | a +0.05 perturbation stays bounded and settles |

## 2. Conceptual validation

`GET /api/validation/conceptual` lists every relationship with evidence class, references and
flags (hypothesis, missing reference, modified coefficient, disabled), and checks that declared
loops are closed and have the declared polarity. Procedure for a research team:

1. Review each relationship in `CAUSAL_ASSUMPTIONS.md` with domain experts.
2. Record expert ranges (`expert_range`) and any literature ranges (`literature_ranges`) per
   parameter; never fabricate numbers.
3. Disable or re-sign relationships that experts reject; document the rationale in `notes`.

## 3. Historical (behaviour) validation

`POST /api/validation/historical` with an authorised aggregate dataset:

1. Split the series into a calibration window and a holdout window (≥ 1 month; default 6).
2. Calibrate selected parameters on the calibration window (regularised least squares).
3. Simulate the full period by replaying observed context, external conditions and recorded
   interventions; responsive context indicators (H, TR, IF) are anchored and fitted.
4. Report per variable: calibration RMSE, holdout MAE/RMSE, bias, residual series, residual lag-1
   autocorrelation, and agreement of trend direction on the holdout.

Acceptance criteria must be set **before** looking at holdout results (pre-registration),
e.g. holdout RMSE below a measurement-error benchmark and trend agreement for the main
indicators. Strong residual autocorrelation indicates missing structure.

## 4. Calibration diagnostics

- LSQ: convergence status, SSR before/after, Gauss–Newton standard errors and 95% intervals,
  condition number of the Jacobian, and identifiability flags (insensitive output, SE > ½ range,
  |correlation| > 0.95 between estimates). With the synthetic demonstration data, H1 and H2 are
  flagged as jointly weakly identifiable.
- Bayesian: prior vs posterior intervals, MAP, split-R̂ (converged if ≤ 1.1; 1.05–1.1 marginal),
  effective sample size, acceptance rates, posterior-to-prior SD ratio (> 0.8 ⇒ data weakly
  informative), posterior predictive bands.
- Synthetic parameter recovery: synthetic datasets store their generating parameters
  (`truth`), allowing recovery checks (`test_lsq_improves_fit_and_recovers_informative_parameters`).

## 5. Intervention validation

`POST /api/validation/intervention` fits an interrupted-time-series (segmented regression,
Newey–West errors) to the observed aggregate around the intervention period and compares the
estimated level/slope change with the model-implied change (replay with vs. without the recorded
intervention). Assumptions are reported with every result: stable pre-trend, no concurrent
changes, stable measurement. **Agreement is consistency evidence only; it does not prove a causal
effect.** Stronger designs (comparison schools, staggered adoption, synthetic control) are
recommended when available.

## 6. Validation envelope

`GET /api/validation/envelope` reports: supported variable ranges, supported school contexts,
validated horizon (currently **0 months** — nothing is validated against real data), data
frequency, parameter provenance counts, observed ranges in loaded datasets, unvalidated
assumptions (all enabled H relationships) and conditions outside the validated scope.

## 7. Report

`POST /api/validation/report` (`format: "markdown"` or `"json"`) exports verification,
conceptual validation, envelope and (optionally) historical validation in one document; the
Advanced Analytics page offers this as **Export validation report**.
