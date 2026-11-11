# Mathematical Equations

This document states every equation implemented in `backend/twin_engine`. The numeric
sections at the end are regenerated from the live configuration by
`scripts/generate_docs.py`, and the in-app **Model Documentation** page renders the same
equations from `/api/model/equations`, so the documentation cannot drift from the code.

All coefficients are **illustrative** until validated (see `PARAMETER_REGISTRY.md`).

## 1. Notation

| Symbol | Meaning | Dimension |
|---|---|---|
| X(t) = [E, C, T, A, K, S, P] | dynamic state variables | 7, each in [0, 1] |
| Z(t) = [F, O, M, J, H, TR, IF] | observed context indicators | 7, each in [0, 1] |
| Y(t) = [R, L, Qp] | derived operational indicators | 3, each in [0, 1] |
| U(t) | intervention intensities | 6, each in [0, 1] |
| D(t) | external conditions | 3, each in [0, 1] |
| Q(t) | pending support processes (stock) | processes |
| I(t), C_flow(t), μ(t) | inflow, completed outflow, processing capacity | processes / month |
| flex(t) | reallocated support hours (loop B1 stock) | hours / month |
| t | month index, t = 0 … N (default N = 12) | month |

`clip(x, 0, 1)` = min(max(x, 0), 1) applied element-wise.

## 2. Normalisation (Section 05)

For a raw observation x with configured reference bounds L < U:

- positive direction: z = clip((x − L)/(U − L), 0, 1)
- negative direction: z = clip((U − x)/(U − L), 0, 1)

Bounds are fixed in configuration and never re-estimated from a scenario or dataset, so
all scenarios share one scale. Missing observations remain missing (NaN / `None`); they are
never set to zero. Out-of-range raw values are clipped and counted in the import report.

## 3. State transition (Section 08)

```text
X(t+1)  = clip[ X(t) + Λ·(X*(t) − X(t)), 0, 1 ]
X*(t)   = clip[ b + A·X(t) + Γ·Z(t) + Π·Y(t) + B·U(t) + G·D(t), 0, 1 ]
```

- **Λ** (7×7) transition-speed matrix: diagonal λ_i ∈ [0, 1] (monthly adjustment speed),
  optional off-diagonal entries in `transition_offdiagonal`.
- **A** (7×7) state→state causal matrix; **Γ** (7×7) context→state; **Π** (7×3) derived
  operational→state; **B** (7×6) interventions→state; **G** (7×3) external→state; **b**
  baseline intercepts.
- The specification's general form is `b + A·X + Γ·Z + B·U + G·D`. The example equations
  (T*, K*, S*) also use L, R and backlog pressure. To keep both consistent, Y = [R, L, Qp]
  enters through an explicit block **Π**; equivalently Γ̃ = [Γ Π] acts on the augmented
  observed/derived vector Z̃ = [Z; Y]. The research meaning is unchanged.

Every enabled relationship in `config/model_config.json` is compiled into exactly one matrix
cell (`twin_engine/model.py`); the test `test_every_coefficient_lands_in_exactly_one_cell`
checks this. Disabled relationships contribute zero.

### 3.1 Timing convention

Month 0 holds the initial (observed) conditions, including R(0) and L(0). For month t ≥ 1,
X*(t−1) uses information available at the end of month t−1 (X, Z, R, L, Qp at t−1) and the
interventions U(t) and external conditions D(t) acting in month t. The derived indicators
therefore feed back with a **one-month information delay**. The stock-flow block of month t
is evaluated with the updated state X(t).

## 4. Observed context with responsive deviations

Context indicators are observed (dataset or scenario schedule). Hypothesised responses —
such as H4 (trust → help-seeking) or training programmes acting on TR — are modelled as a
lagged deviation from the observed path:

```text
ΔZ(0)   = 0
ΔZ(t+1) = ΔZ(t) + λ_Z·( Ω·(X(t) − X(0)) + B_z·U(t) + G_z·D(t) − ΔZ(t) )
Z(t)    = clip[ Z_obs(t) + ΔZ(t), 0, 1 ]
```

The anchor X(0) is the state at which Z_obs was observed. A consequence (verified by check
V13) is that each run settles at an equilibrium that depends on its own initial state; local
stability is verified separately (V09). Context indicators without incoming responsive
relationships equal their observed path exactly. In **manual override** mode a context
indicator is fixed to the override value and its response is switched off.

## 5. Stock-flow block (Section 09)

```text
I(t)      = I₀ · Π_k max(0, 1 + κ_k·(x_k(t) − ref_k))           (A, H, academic load)
hours(t)  = L_S + S(t)·(U_S − L_S)                               (inverse normalisation of S)
eff(t)    = max(0.1, Π_j (1 + η_j·(x_j(t) − ref_j)))             (H6: coordination → efficiency)
μ(t)      = (hours(t)·φ + flex(t)) · eff(t) / h
C_flow(t) = min(Q(t−1) + I(t), μ(t))
Q(t)      = max(0, Q(t−1) + I(t) − C_flow(t))
W(t)      = Q(t) / μ(t)                                          (expected waiting time, Little's law)
Qp(t)     = W(t) / (W(t) + w½)                                   (backlog pressure, bounded in [0,1))
flex(t+1) = flex(t) + λ_flex·(β_B1·Qp(t)·H_flex − flex(t))       (loop B1)
```

Units: Q in processes; I, C_flow, μ in processes/month; hours and flex in hours/month;
h in hours/process; w½ in months. Mass balance Q(t) − Q(t−1) = I(t) − C_flow(t) holds
exactly (verification V05); with I = 0 the stock can only drain (V06); completions never
exceed capacity or available work (V07).

**Interpretation.** I(t) is generic support-service demand. Higher accessibility and
help-seeking raise I(t) — this is *not* an indicator of violence or danger.

### 5.1 Derived operational indicators

```text
R(t) = C_flow(t) / (Q(t−1) + I(t))            (share of open workload completed; 1 if no work)
L(t) = clip(b_L + Σ ω·x(t) − ω_LQ·Qp(t), 0, 1)  (follow-up continuity; H9 via −ω_LQ)
```

Each can be switched to **manual override**, in which case the scenario value is used.

### 5.2 Two backlog effects on support capacity

The specification's S* equation contains −α_SQ·backlog_pressure (strain), while loop B1 states
that backlog increases capacity. Both are retained with distinct mechanisms: strain lowers the
target *support capacity readiness* S*, while B1 reallocates *hours* (flex) into processing
capacity μ with a managerial delay. Either can be switched off (α_SQ = 0 or β_B1 = 0).

## 6. Readiness indices (Section 10)

```text
ENV = Σ w_i·{E,F,O,M} / Σ w_i       SOC = …{C,T,J,H}     ORG = …{A,R,L,K}     SUP = …{S,TR,P,IF}
TOTAL = Σ_d w_d·domain_d,  w_d normalised to Σ w_d = 1 (default equal weights)
MIN_DOMAIN = min(ENV, SOC, ORG, SUP)
```

Missing variables are excluded from a domain mean (weights renormalised), never set to zero.
These indices are institutional readiness and process indicators, **not** probabilities of any
event.

## 7. Resource requirements

```text
programme staff-hours = Σ_t Σ_k U_k(t)·c_k          (c_k = cost.U_*)
support hours delivered = Σ_{t≥1} hours(t)·φ + flex(t)
```

Both are illustrative and expressed in staff-hours.

## 8. Equilibrium anchoring of the demonstration baseline

`twin_engine/anchoring.py` (and `scripts/anchor_demo_baseline.py`) derive the values that make
the synthetic initial state a steady state of the baseline (standard system-dynamics practice):

```text
Q(0)  = μ(0)·(1/R(0) − 1)                     (with flex at its B1 fixed point)
I₀    = μ(0) / Π multipliers(X(0), Z(0), D(0))
b     = X(0) − (A·X(0) + Γ·Z(0) + Π·Y(0) + G·D(0))
b_L   = L(0) − (ω·X(0) + ω·Z(0) − ω_LQ·Qp(0) + ω·D(0))
```

Differences between a scenario and the baseline then isolate the effect of the scenario inputs.
After editing coefficients the baseline is no longer an equilibrium; the Causal Model page offers
**Re-anchor baseline equilibrium** (`POST /api/model/anchor`).

## 9. Stability analysis

- **Linear part** (`linear_stability`): spectral radius of
  `J = [[I + Λ(A − I), ΛΓ], [λ_Z Ω, (1 − λ_Z) I]]` for the coupled [X, ΔZ] update.
- **Full nonlinear map** (`full_map_jacobian`): central-difference Jacobian of the complete
  one-step map s(t) → s(t+1), s = [X, ΔZ, flex, Q, R, L, Qp], at the baseline state.
  Spectral radius < 1 ⇒ locally asymptotically stable (default: 0.897).

## 10. Outer analysis layers

- **Uncertainty**: Latin-hypercube samples θ⁽ⁱ⁾ over parameter ranges; each sample is one
  deterministic run; P5/P50/P95 per month; paired differences to the baseline use the same samples.
- **Sensitivity**: Morris elementary effects (μ, μ*, σ), Sobol S1/ST/S2 (Saltelli sampling,
  N(D+2) or N(2D+2) runs), and one-at-a-time tornado swings.
- **Least squares**: θ̂ = argmin Σ_t (Y_t − Ŷ_t(θ))ᵀW(Y_t − Ŷ_t(θ)) + λ‖(θ − θ₀)/s‖²,
  bounded trust-region reflective; Cov ≈ σ̂²(JᵀJ)⁻¹.
- **Bayesian**: P(θ|D) ∝ P(D|θ)P(θ); scaled-Beta priors on bounded intervals sampled in logit
  space (Jacobian included), Gaussian likelihood with unknown σ (log-normal prior), MAP +
  Laplace initialisation, adaptive Metropolis (Haario et al., 2001), split-R̂ and ESS.

In calibration replay, observed context is replayed as input except for *responsive* context
indicators (H, TR, IF), which are anchored at their first observation and fitted as targets —
replaying their observed path would double-count the modelled response.

## 11. Current numeric form

<!-- BEGIN GENERATED -->
### State target equations (current coefficients)

```text
E* = clip(b_E + α_EF·F + α_EO·O + α_EM·M + α_EU·U_environment, 0, 1)
E* = clip(0.432 + 0.200·F + 0.120·O + 0.050·M + 0.250·U_environment, 0, 1)
E(t+1) = clip(E(t) + λ_E·(E* − E(t)), 0, 1),  λ_E = 0.300
```

```text
C* = clip(b_C + α_CT·T + α_CS·S + α_CJ·J + α_CE·E, 0, 1)
C* = clip(0.306 + 0.200·T + 0.150·S + 0.150·J + 0.080·E, 0, 1)
C(t+1) = clip(C(t) + λ_C·(C* − C(t)), 0, 1),  λ_C = 0.150
```

```text
T* = clip(b_T + α_TJ·J + α_TL·L + α_TR·R − α_TQ·Qp, 0, 1)
T* = clip(0.202 + 0.250·J + 0.200·L + 0.100·R − 0.100·Qp, 0, 1)
T(t+1) = clip(T(t) + λ_T·(T* − T(t)), 0, 1),  λ_T = 0.200
```

```text
A* = clip(b_A + α_AU·U_access + α_AH·H, 0, 1)
A* = clip(0.460 + 0.300·U_access + 0.150·H, 0, 1)
A(t+1) = clip(A(t) + λ_A·(A* − A(t)), 0, 1),  λ_A = 0.350
```

```text
K* = clip(b_K + α_KU·U_coordination + α_KTR·TR + α_KL·L − γ_K,turnover·staff_turnover, 0, 1)
K* = clip(0.498 + 0.300·U_coordination + 0.150·TR + 0.100·L − 0.080·staff_turnover, 0, 1)
K(t+1) = clip(K(t) + λ_K·(K* − K(t)), 0, 1),  λ_K = 0.300
```

```text
S* = clip(b_S + α_SU·U_capacity + α_Sresource·resource_availability − α_SQ·Qp − γ_S,turnover·staff_turnover, 0, 1)
S* = clip(0.487 + 0.350·U_capacity + 0.200·resource_availability − 0.100·Qp − 0.100·staff_turnover, 0, 1)
S(t+1) = clip(S(t) + λ_S·(S* − S(t)), 0, 1),  λ_S = 0.250
```

```text
P* = clip(b_P + α_PTR·TR + α_PM·M + α_PK·K + α_PIF·IF, 0, 1)
P* = clip(0.207 + 0.200·TR + 0.100·M + 0.150·K + 0.150·IF, 0, 1)
P(t+1) = clip(P(t) + λ_P·(P* − P(t)), 0, 1),  λ_P = 0.250
```

### Observed context indicators with responsive deviations

```text
F(t) = F_obs(t)
F(t) = F_obs(t)
```

```text
O(t) = O_obs(t)
O(t) = O_obs(t)
```

```text
M(t) = M_obs(t)
M(t) = M_obs(t)
```

```text
J(t) = J_obs(t)
J(t) = J_obs(t)
```

```text
ΔH(t+1) = ΔH(t) + λ_Z·(ω_HT·(T(t) − T(0)) − ΔH(t));  H(t) = clip(H_obs(t) + ΔH(t), 0, 1)
ΔH(t+1) = ΔH(t) + 0.250·(0.400·(T(t) − T(0)) − ΔH(t))
```

```text
ΔTR(t+1) = ΔTR(t) + λ_Z·(β_TR·U_training(t) − ΔTR(t));  TR(t) = clip(TR_obs(t) + ΔTR(t), 0, 1)
ΔTR(t+1) = ΔTR(t) + 0.250·(0.300·U_training(t) − ΔTR(t))
```

```text
ΔIF(t+1) = ΔIF(t) + λ_Z·(β_IF·U_followthrough(t) − ΔIF(t));  IF(t) = clip(IF_obs(t) + ΔIF(t), 0, 1)
ΔIF(t+1) = ΔIF(t) + 0.250·(0.350·U_followthrough(t) − ΔIF(t))
```

### Stock-flow block

**Stock**

```text
Q(t) = max(0, Q(t−1) + I(t) − C_flow(t))
Q(0) = 22.60 processes
```

**Capacity constraint**

```text
C_flow(t) = min(Q(t−1) + I(t), μ(t))

```

**Inflow**

```text
I(t) = I₀ · Π_k max(0, 1 + κ_k·(x_k(t) − ref_k))
I(t) = 31.049 · max(0, 1 + 0.800·(A − 0.5)) · max(0, 1 + 0.500·(H − 0.5)) · max(0, 1 + 0.600·(academic_load − 0.5))
```

**Support hours**

```text
hours(t) = L_S + S(t)·(U_S − L_S)
hours(t) = 0.0 + S(t)·320.0 h/month
```

**Processing capacity**

```text
μ(t) = (hours(t)·φ + flex(t)) · eff(t) / h
μ(t) = (hours(t)·0.600 + flex(t)) · max(0, 1 + 0.600·(K − 0.5)) / 4.000
```

**Backlog pressure**

```text
W(t) = Q(t)/μ(t);  Qp(t) = W(t)/(W(t) + w½)
w½ = 0.750 months
```

**Reallocated hours (loop B1)**

```text
flex(t+1) = flex(t) + λ_flex·(β_B1·Qp(t)·H_flex − flex(t))
λ_flex = 0.300, β_B1 = 1.000, H_flex = 40.000 h
```

**Timely completion (derived R)**

```text
R(t) = C_flow(t) / (Q(t−1) + I(t))

```

**Follow-up continuity (derived L)**

```text
L(t) = clip(b_L + Σ ω·x(t) − ω_LQ·Qp(t), 0, 1)
L(t) = clip(0.396 + 0.200·K + 0.200·S + 0.100·A − 0.300·Qp, 0, 1)
```

### Readiness indices

```text
ENV = weighted_mean(E, F, O, M)   weights [1.0, 1.0, 1.0, 1.0]
```

```text
SOC = weighted_mean(C, T, J, H)   weights [1.0, 1.0, 1.0, 1.0]
```

```text
ORG = weighted_mean(A, R, L, K)   weights [1.0, 1.0, 1.0, 1.0]
```

```text
SUP = weighted_mean(S, TR, P, IF)   weights [1.0, 1.0, 1.0, 1.0]
```

```text
TOTAL = Σ_d w_d·domain_d,  Σ w_d = 1   0.250·ENV + 0.250·SOC + 0.250·ORG + 0.250·SUP
```

```text
MIN_DOMAIN = min(ENV, SOC, ORG, SUP)   
```


<!-- END GENERATED -->
