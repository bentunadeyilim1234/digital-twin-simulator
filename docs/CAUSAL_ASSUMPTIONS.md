# Causal Assumptions

The causal graph contains **proposed directional relationships**. They are hypotheses to be
investigated, not established causal facts. The same edge list drives the simulator, the
interactive graph, the parameter registry and the documentation.

## Evidence classification

| Class | Meaning | How it is used here |
|---|---|---|
| **E1** | Strong external research foundation | Reserved for accounting identities (mass balance, Little's law). No behavioural relationship in the demonstration model reaches E1 for the exact construct pair modelled. |
| **E2** | Limited external research foundation | Published work supports an association between related constructs (often cross-sectional or from non-school settings). Direction and magnitude remain assumptions. |
| **H** | Research hypothesis | No adequate external evidence identified; plausible mechanism to test. |
| **L** | Supported by local aggregate data | To be assigned only after calibration *and* holdout validation on authorised local data. Calibrated coefficients keep their class until reviewed. |

Confidence (low / medium / high) is a separate qualitative judgement and is editable.

## Hypotheses H1–H10 (Section 06)

| ID | Hypothesis | Implementation | Class | Basis and caveats |
|---|---|---|---|---|
| H1 | Perceived fairness → institutional trust (+) | Γ[T, J] | E2 | Procedural-justice research (Tyler & Huo, 2002); school discipline legitimacy (Arum, 2003); structure-and-support climate (Gregory et al., 2010). Mostly non-experimental. |
| H2 | Follow-up continuity → trust (+) | Π[T, L] | H | Mechanism plausible; no direct school evidence identified. Part of loop R1. Jointly weakly identifiable with H1 from aggregate data (see calibration). |
| H3 | Timely processes → trust (+) | Π[T, R] | H | Plausible; untested. |
| H4 | Trust → help-seeking (+) | Ω[H, T] (context response) | E2 | Supportive climate is associated with willingness to seek help (Eliot et al., 2010; Williams & Cornell, 2006); cross-sectional. |
| H5 | Support capacity → belonging (+) | A[C, S] | E2 | Teacher support is a strong correlate of belonging (Allen et al., 2018); CDC (2009) connectedness guidance. Extension from teacher support to professional support capacity is an assumption. |
| H6 | Coordination → process efficiency (+) | efficiency multiplier on μ | H | Plausible organisational mechanism; untested. |
| H7 | Staff training → preparedness (+) | Γ[P, TR] | E2 | Institutional guidance (REMS, 2013); effect sizes not established. |
| H8 | Improvement follow-through → preparedness (+) | Γ[P, IF] | H | Continuous-improvement logic in guidance; untested. |
| H9 | Backlog → follow-up continuity (−) | −ω_LQ·Qp in L(t) | H | Little (1961) links backlog to waiting time (identity); the effect on follow-up is hypothesised. |
| H10 | Environmental conditions → supportive experience (+) | A[C, E] | E2 | Building condition is associated with social climate (Maxwell, 2016) and classroom design with learning (Barrett et al., 2015); not belonging directly. |

Supporting relationships required by the specified target equations (e.g. F, O, M → E;
interventions → targets; staff turnover; resources) are listed in the generated table below.
Most are class **H**.

## Feedback loops (Section 07)

- **R1 — Trust and support (reinforcing):** T → H (H4) → A (help-seeking raises effective
  accessibility) → L (accessible channels ease follow-up) → T (H2).
- **B1 — Workload and capacity (balancing):** Q → Qp (waiting time) → flex (hour
  reallocation, gain β_B1) → μ → C_flow → Q (−).

The interaction of R1 with demand creates an emergent balancing loop that the cycle
enumeration also detects: A, H → I → Q → Qp → L → T → H. Better accessibility raises
incoming support requests; if capacity does not follow, backlog pressure lowers follow-up and
trust. With the illustrative parameters, **S1 (accessibility only)** lowers ORG by 0.028 and
TOTAL by 0.011 at month 12 relative to the baseline, while **S4 (integrated)** raises SOC
(+0.042), ORG (+0.254) and SUP (+0.161); ENV is unchanged because S4 contains no
environmental intervention. These magnitudes are properties of the illustrative parameter set,
not empirical predictions.

An increase in incoming requests reflects accessibility and willingness to seek help. It is
**never** interpreted as increased violence or institutional danger.

## Editing assumptions

In the **Causal Model** page users can change coefficients, signs, evidence class and
notes, disable relationships, add experimental relationships (custom edges, kind `linear`,
`context_response` or `derived`), and restore originals. Structural accounting identities
cannot be edited. All changes are validated (endpoints, kinds, duplicates, bounds) and take
effect in the next simulation.

## Generated relationship table

<!-- BEGIN GENERATED -->
### Relationship table

| ID | Hyp. | Source → Target | Kind | Sign | Coef. | Range | Evidence | Confidence | References |
|---|---|---|---|---|---|---|---|---|---|
| `ENV-F-E` |  | `F` → `E` | linear | + | 0.200 | [0.1, 0.3] | H | low | — |
| `ENV-O-E` |  | `O` → `E` | linear | + | 0.120 | [0.05, 0.2] | H | low | — |
| `ENV-M-E` |  | `M` → `E` | linear | + | 0.050 | [0.0, 0.1] | H | low | — |
| `U-ENV-E` |  | `U_environment` → `E` | linear | + | 0.250 | [0.1, 0.4] | H | low | — |
| `SOC-T-C` |  | `T` → `C` | linear | + | 0.200 | [0.1, 0.3] | E2 | medium | thapa2013, wang_degol2016 |
| `H5` | H5 | `S` → `C` | linear | + | 0.150 | [0.05, 0.25] | E2 | medium | allen2018, cdc2009 |
| `SOC-J-C` |  | `J` → `C` | linear | + | 0.150 | [0.05, 0.25] | E2 | medium | thapa2013 |
| `H10` | H10 | `E` → `C` | linear | + | 0.080 | [0.0, 0.15] | E2 | low | maxwell2016, barrett2015 |
| `H1` | H1 | `J` → `T` | linear | + | 0.250 | [0.1, 0.35] | E2 | medium | tyler_huo2002, arum2003, gregory2010 |
| `H2` | H2 | `L` → `T` | linear | + | 0.200 | [0.05, 0.3] | H | low | — |
| `H3` | H3 | `R` → `T` | linear | + | 0.100 | [0.0, 0.2] | H | low | — |
| `QP-T` |  | `Qp` → `T` | linear | − | 0.100 | [0.0, 0.2] | H | low | — |
| `U-ACC-A` |  | `U_access` → `A` | linear | + | 0.300 | [0.15, 0.45] | H | low | — |
| `SOC-H-A` |  | `H` → `A` | linear | + | 0.150 | [0.05, 0.25] | H | low | forsberg2023 |
| `U-COORD-K` |  | `U_coordination` → `K` | linear | + | 0.300 | [0.15, 0.45] | H | low | — |
| `SUP-TR-K` |  | `TR` → `K` | linear | + | 0.150 | [0.05, 0.25] | H | low | — |
| `ORG-L-K` |  | `L` → `K` | linear | + | 0.100 | [0.0, 0.2] | H | low | — |
| `U-CAP-S` |  | `U_capacity` → `S` | linear | + | 0.350 | [0.2, 0.5] | H | low | — |
| `EXT-RES-S` |  | `resource_availability` → `S` | linear | + | 0.200 | [0.1, 0.3] | H | low | — |
| `QP-S` |  | `Qp` → `S` | linear | − | 0.100 | [0.0, 0.2] | H | low | — |
| `EXT-TURN-S` |  | `staff_turnover` → `S` | linear | − | 0.100 | [0.0, 0.2] | H | low | — |
| `EXT-TURN-K` |  | `staff_turnover` → `K` | linear | − | 0.080 | [0.0, 0.15] | H | low | — |
| `H7` | H7 | `TR` → `P` | linear | + | 0.200 | [0.1, 0.3] | E2 | medium | rems2013 |
| `ENV-M-P` |  | `M` → `P` | linear | + | 0.100 | [0.0, 0.2] | E2 | low | rems2013 |
| `ORG-K-P` |  | `K` → `P` | linear | + | 0.150 | [0.05, 0.25] | H | low | rems2013 |
| `H8` | H8 | `IF` → `P` | linear | + | 0.150 | [0.05, 0.25] | H | low | rems2013 |
| `H4` | H4 | `T` → `H` | context_response | + | 0.400 | [0.2, 0.6] | E2 | medium | eliot2010, williams2006 |
| `U-TRAIN-TR` |  | `U_training` → `TR` | context_response | + | 0.300 | [0.15, 0.45] | H | low | — |
| `U-FOLLOW-IF` |  | `U_followthrough` → `IF` | context_response | + | 0.350 | [0.15, 0.5] | H | low | — |
| `ORG-K-L` |  | `K` → `L` | derived | + | 0.200 | [0.1, 0.3] | H | low | — |
| `SUP-S-L` |  | `S` → `L` | derived | + | 0.200 | [0.1, 0.3] | H | low | — |
| `ORG-A-L` |  | `A` → `L` | derived | + | 0.100 | [0.0, 0.2] | H | low | forsberg2023 |
| `H9` | H9 | `Qp` → `L` | derived | − | 0.300 | [0.15, 0.45] | H | medium | little1961 |
| `FLOW-A-I` |  | `A` → `I` | flow_multiplier | + | 0.800 | [0.4, 1.2] | H | low | — |
| `FLOW-H-I` |  | `H` → `I` | flow_multiplier | + | 0.500 | [0.2, 0.8] | H | low | eliot2010 |
| `FLOW-LOAD-I` |  | `academic_load` → `I` | flow_multiplier | + | 0.600 | [0.2, 1.0] | H | low | — |
| `H6` | H6 | `K` → `mu` | flow_multiplier | + | 0.600 | [0.2, 1.0] | H | low | — |
| `B1-GAIN` |  | `Qp` → `flex` | feedback_gain | + | 1.000 | [0.0, 1.5] | H | low | sterman2000 |
| `ST-I-Q` |  | `I` → `Q` | structural | + | 1.000 | — | E1 | high | forrester1961, sterman2000 |
| `ST-C-Q` |  | `C_flow` → `Q` | structural | − | 1.000 | — | E1 | high | forrester1961, sterman2000 |
| `ST-Q-C` |  | `Q` → `C_flow` | structural | + | 1.000 | — | E1 | high | — |
| `ST-MU-C` |  | `mu` → `C_flow` | structural | + | 1.000 | — | E1 | high | — |
| `ST-Q-QP` |  | `Q` → `Qp` | structural | + | 1.000 | — | E1 | high | little1961 |
| `ST-MU-QP` |  | `mu` → `Qp` | structural | − | 1.000 | — | E1 | high | little1961 |
| `ST-S-MU` |  | `S` → `mu` | structural | + | 1.000 | — | E1 | high | — |
| `ST-FLEX-MU` |  | `flex` → `mu` | structural | + | 1.000 | — | E1 | high | — |
| `ST-C-R` |  | `C_flow` → `R` | structural | + | 1.000 | — | E1 | high | — |
| `ST-Q-R` |  | `Q` → `R` | structural | − | 1.000 | — | E1 | high | — |

### Declared feedback loops

- **R1 — Trust and support loop** (declared reinforcing, computed reinforcing, closed: True): T → H → A → L → T. Higher trust -> more help-seeking -> more accessible/used support -> better follow-up -> higher trust.
- **B1 — Workload and capacity loop** (declared balancing, computed balancing, closed: True): Q → Qp → flex → mu → C_flow → Q. Pending processes -> backlog pressure -> reallocated capacity -> more completions -> reduced backlog.

Automatic cycle enumeration finds **32** simple feedback cycles among enabled relationships (16 reinforcing, 16 balancing). The ten shortest:

- reinforcing: L → K → L
- balancing: Q → C_flow → Q
- reinforcing: S → mu → Qp → S
- balancing: mu → Qp → flex → mu
- reinforcing: L → K → mu → Qp → L
- reinforcing: T → H → A → L → T (= R1)
- reinforcing: L → K → mu → Qp → S → L
- balancing: Q → Qp → flex → mu → C_flow → Q (= B1)
- reinforcing: S → mu → C_flow → Q → Qp → S
- balancing: T → H → I → Q → Qp → T

<!-- END GENERATED -->
