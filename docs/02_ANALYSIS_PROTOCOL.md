# Phase 2 Analysis Protocol
## Dynamic Flow-Termination Transients in PSV: Pre-Specified Biomechanics and ML Plan

This protocol is intentionally strict: all key thresholds and methods were locked before deep result interpretation to limit hindsight bias.

Cross-phase amendment note (2026-03-19): Mechanical downstream interpretation is governed by the redesign gates in 04_PHASE3_MECHANICAL_DESIGN.md. Phase 2 outputs remain unchanged; only Phase 3 engineering claims were reset.

**Protocol Version:** 1.2  
**Date:** March 14, 2026  
**Status:** Locked for Phase 2 initiation (revised after independent protocol audit)  
**Parent Document:** `01_MEDICAL_PROBLEM_STATEMENT.md` (v4.1)

---

## 1. Purpose and Scope

This protocol pre-specifies all major analytical decisions for Phase 2 before outcome analysis. It defines:

- Breath segmentation rules
- Flow-termination event detection criteria
- Transpulmonary pressure computation
- Machine-learning model architecture and training plan
- Validation strategy (internal and external)
- Performance metrics and reporting standards
- Contingency handling for dataset curation issues

Any post-hoc change requires an explicit amendment entry (Section 13).

---

## 2. Datasets and Roles

### 2.1 Primary Development Dataset

- **CCVW-ICU**: confirmed PSV cohort with simultaneous Pao, Flow, Pes at 200 Hz
- **Role**: physiology-grounded event definition, label creation, model development

### 2.2 External Validation Dataset

- **Ventilator Waveform Data** (Puritan Bennett collection in repository)
- **Role**: domain-shift characterization on non-Pes, lower-sampling real-world data

Important constraint: this dataset has no Pes channel, so it cannot provide Pes-ground-truth external performance metrics for the primary physiological endpoints.

### 2.3 Simulation Dataset

- **Simulated data from A Model-based Approach to Generating Annotated Pressure Support Waveforms**
- **Role**: pre-training and stress-testing under controlled parameter sweeps

Simulation labels will be used only after explicit mapping verification against this protocol's event taxonomy (Section 10.3 and Section 13.2).

### 2.4 Context-Only Dataset

- **MIMIC-IV temporal respiratory dataset**
- **Role**: epidemiological context only; excluded from waveform mechanics and ML event training

---

## 3. Signal Definitions and Conventions

- `Paw` is airway opening pressure measured as `Pao` in source files
- `Flow` uses source sign convention (positive inspiratory, negative expiratory)
- `Pes` is esophageal pressure
- Transpulmonary pressure:

$$
P_L(t) = P_{aw}(t) - P_{es}(t)
$$

- All transient magnitudes are reported in cmH2O
- Time is in seconds

---

## 4. Preprocessing and Quality Control

### 4.1 File-Level Inclusion Gates

A file is included only if all conditions pass:

1. Required channels present (`time`, `flow`, `paw/pao`; and `pes` for CCVW)
2. Monotonic increasing time
3. Effective sampling rate within +/-5% of declared value
4. Missingness per required channel <5%
5. No constant-value flatline >2.0 s in required channels

### 4.2 Sample-Level Processing

1. Unit harmonization to L/s (Flow) and cmH2O (pressure)
2. Time-base normalization from raw time vector (no forced resampling unless required)
3. Light denoising:
- Flow: zero-phase low-pass, 12 Hz cutoff
- Pressure channels: zero-phase low-pass, 20 Hz cutoff
 - These cutoffs are intentionally conservative for noise suppression in the expected event bandwidth (<20 Hz). Potential attenuation of very fast components is acknowledged and will be reported as a limitation.
4. Outlier clipping only for clear sensor spikes:
- derivative-based Hampel rule, window 11 samples, threshold 6 MAD
5. Anti-aliasing before any decimation/resampling:
- apply low-pass at `min(0.4 * target_fs, 20 Hz)` before downsampling

### 4.3 Signal Quality Flags

Each breath receives flags:

- `low_quality_flow`
- `low_quality_paw`
- `low_quality_pes` (CCVW only)
- `incomplete_window`

Operational definitions (pre-specified):

- `low_quality_flow`: >5% samples in breath window flagged as Hampel outliers, or any flatline segment >200 ms
- `low_quality_paw`: >5% samples in breath window flagged as Hampel outliers, or any flatline segment >200 ms
- `low_quality_pes`: >5% samples in breath window flagged as Hampel outliers, or any flatline segment >200 ms
- `incomplete_window`: missing start/end samples preventing full [-150 ms, +350 ms] extraction around `t_cycle`

Breaths with any required-channel low-quality flag are excluded from primary analysis and included only in sensitivity analyses.

---

## 5. Breath Segmentation Algorithm

### 5.1 Primary Segmentation (Flow-Based)

Breaths are segmented from flow with hysteresis to avoid noise crossings.

Definitions:

- `eps = 0.02 L/s` (zero-crossing hysteresis)
- Inspiratory phase: `Flow > +eps`
- Expiratory phase: `Flow < -eps`

Algorithm:

1. Find transitions from expiratory/non-inspiratory to inspiratory (`Flow` crossing above `+eps` and staying above for at least 40 ms)
2. Mark inspiratory onset `t_insp_start`
3. Within inspiratory phase, identify peak inspiratory flow `F_peak`
4. Detect inspiratory termination `t_cycle` (Section 6)
5. Breath end is next inspiratory onset

### 5.2 Secondary Fallback Segmentation (Pressure-Assisted)

If flow signal quality fails locally, fallback uses pressure/flow joint logic:

- candidate onset from local Paw slope rise (`dPaw/dt > 1.5 cmH2O/s`) plus non-negative flow
- candidate termination from return to expiratory flow or Paw downstroke

Fallback breaths are flagged and excluded from primary endpoint analyses.

### 5.3 Segmentation Exclusion Rules

Exclude breath if any of the following:

- Inspiratory duration <0.20 s or >4.0 s
- `F_peak < 0.05 L/s`
- Missing >10% samples in analysis window
- Ambiguous multi-crossing around cycling without stable phase transition

---

## 6. Flow-Termination Event Detection Criteria

### 6.1 Cycling Moment Definition

For each segmented breath:

1. Compute `F_peak` during inspiration
2. Compute ETS threshold flow:

$$
F_{ETS} = ETS_{frac} \cdot F_{peak}
$$

3. ETS assignment hierarchy:
- If breath-level ETS metadata exists, use breath-level value
- Else if session-level ETS metadata exists, use session value
- Else if patient-level ETS metadata exists, use patient value
4. If ETS metadata is unavailable, assign provisional `ETS_frac = 0.25`, flag breath as `ets_defaulted`, and include in sensitivity analyses varying ETS from 0.15 to 0.35 (step 0.05)
5. Define `t_cycle` deterministically as the first sample after `F_peak` where:
- `Flow <= F_ETS`, and
- `Flow` remains `<= F_ETS` for at least 3 consecutive samples
6. If no such sample exists, breath is flagged `cycle_undefined` and excluded from event analysis

Rationale note: the 3-sample confirmation may exclude extremely brief threshold crossings (for example, transient flutter-like dips), especially in simulated signals. This is an intentional trade-off to improve robustness against noise and spurious threshold crossings.

### 6.2 Event Window

For each `t_cycle`, extract window:

- Pre-window: `[-150 ms, 0]`
- Post-window: `[0, +350 ms]`

### 6.3 Primary Continuous Event Magnitudes

Let baseline values be medians in pre-window:

- `Paw_base = median(Paw[-150,0] ms)`
- `PL_base = median(PL[-150,0] ms)`

Compute:

- $$\Delta P_{aw,max} = \max_{0..350ms} |P_{aw}(t)-Paw_{base}|$$
- $$\Delta P_{L,max} = \max_{0..350ms} |P_{L}(t)-PL_{base}|$$
- Max slope terms: `max |dPaw/dt|`, `max |dPL/dt|` in post-window

Primary biomechanics analyses use these continuous metrics (no dichotomization required).

### 6.4 Binary Event Label (for ML Classification)

A breath is labeled `event_positive` if all conditions hold:

1. `Delta PL max >= 1.0 cmH2O`
2. `max |dPL/dt| >= 8.0 cmH2O/s`
3. Event peak occurs within 200 ms after `t_cycle`
4. Required quality flags are clean

Else `event_negative`.

Role of binary label: secondary/exploratory endpoint for classification only. Primary ML endpoint is continuous regression (`Delta PL max`).

Sensitivity thresholds (pre-specified):

- `Delta PL max` at 0.75 and 1.25 cmH2O
- slope at 6.0 and 10.0 cmH2O/s

---

## 7. Transpulmonary Pressure Computation

### 7.1 Core Formula

$$
P_L(t) = P_{aw}(t) - P_{es}(t)
$$

### 7.2 Derived Indices

Per breath:

- `PL_at_cycle = PL(t_cycle)`
- `Delta PL max` (Section 6.3)
- Transmission fraction:

$$
TF = \frac{\Delta P_{L,max}}{\Delta P_{aw,max}}
$$

- `TF` is computed only when `Delta Paw max > 0.2 cmH2O`; otherwise set to missing
- `TF` is winsorized at 99th percentile for summary statistics only (raw retained for modeling)

Rationale note: the `0.2 cmH2O` denominator threshold excludes negligible Paw transients where `TF` is numerically unstable and physiologically non-informative. The affected breath fraction will be reported per dataset and per patient.

### 7.3 Interpretation Rule

No claim of inspiratory-vs-expiratory muscle decomposition is made (no Pga available). `PL` is treated as net lung-facing mechanical stress signal.

---

## 8. Feature Set for Statistical Modeling

### 8.1 Breath-Level Features (Primary)

- `F_peak`, inspiratory duration, expiratory duration
- ETS fraction (from metadata or default flag)
- `Paw_base`, `Pes_base`, `PL_at_cycle`
- `Delta Paw max`, `Delta PL max`
- `max |dPaw/dt|`, `max |dPL/dt|`
- PS level, PEEP, FiO2 (if available at breath time)
- Compliance/resistance surrogate features from waveform shape

Feature governance:

- If ETS is constant within patient, ETS is excluded from within-patient ML predictors and retained only for between-patient descriptive/mixed-effects analyses
- `ets_defaulted` is retained as a binary quality/covariate flag for sensitivity analyses
- If PS, PEEP, or FiO2 are missing for a breath, that breath is excluded from analyses that require the missing feature(s); no imputation is performed

### 8.2 Context Features

- Patient ID (grouping variable, never as direct predictor in final deployment model)
- Ventilator/source dataset indicator (for domain-shift analysis)

---

## 9. ML Architecture and Training Plan

### 9.1 Tasks

1. **Primary ML task (regression):** estimate `Delta PL max` from Paw + Flow
2. **Secondary ML task (classification, exploratory):** detect `event_positive` from Paw + Flow only (Pes not used as model input)

### 9.2 Inputs

Per breath window centered at `t_cycle`:

- Primary input tensor: 2 channels (`Paw`, `Flow`)
- Window length: 500 ms pre + 500 ms post (1.0 s total)
- Native sample rate per dataset, with anti-aliasing-aware resampling to 100 Hz for deep models

### 9.3 Models

Pre-specified model family order:

1. **Primary model**: XGBoost on engineered features
2. **Secondary model**: compact 1D CNN (shallow, regularized)
3. **Tertiary model**: BiLSTM

Transformer models are excluded from primary analysis due to small cohort size and overfitting risk; may be reported as exploratory appendix only.

### 9.4 Training Rules

- No patient leakage across splits
- Class imbalance handling: weighted loss + threshold optimization on validation only
- Early stopping on patient-wise validation metric
- Hyperparameter search restricted to predefined grid (Appendix A)
- With N=7, performance uncertainty is expected to be wide; all model comparisons are interpreted with confidence-interval overlap, not point estimates alone
- Hyperparameter tuning uses a single grouped validation patient within each training fold (fixed per fold by pre-set random seed) to avoid unstable multi-split tuning on tiny cohorts

### 9.5 Output

- Classification: probability of event
- Regression: predicted `Delta PL max`
- Deployment target: Paw+Flow-only inference calibrated against Pes-grounded labels

---

## 10. Validation Strategy

### 10.1 Internal Validation (CCVW-ICU)

- Leave-one-patient-out cross-validation (LOPO-CV)
- Outer loop: 7 folds (one patient held out each fold)
- Inner tuning: grouped split within training patients only

### 10.2 External Validation (Puritan Bennett)

- Freeze model after CCVW training
- Harmonize units/channels and map segmentation pipeline
- Identify high-confidence PSV epochs using available metadata; if metadata are incomplete, use conservative waveform-morphology screening and flag uncertainty
- Do not report Pes-ground-truth classification metrics on Puritan Bennett (no Pes available)
- External assessment outputs are limited to:
1. Domain-shift characterization of model score distributions
2. Plausibility assessment on high-score and low-score breath samples by pre-specified waveform review checklist (Appendix B)
3. Calibration-shift diagnostics relative to CCVW score distributions
- If reliable PSV-epoch identification fails, declare external evaluation infeasible for that subset and report only curated subset analyses
- Breaths with `ets_defaulted` are included in primary external analyses; sensitivity analysis excluding `ets_defaulted` breaths is mandatory

### 10.3 Simulation Validation

- Use simulation labels for pre-training and stress tests
- Report transfer performance from simulation to CCVW and CCVW to PB
- Keep simulation-only metrics separate from clinical metrics
- Before pre-training, verify label mapping by manual review of a random sample of 200 simulated breaths against protocol-defined `t_cycle` and event criteria
- Sampling strategy for the 200 reviewed breaths: stratified random sampling across simulation parameter strata (ETS, compliance, resistance, PS level) with proportional allocation to each stratum
- Mismatch definition (either criterion):
1. absolute `t_cycle` disagreement >20 ms between provided simulation label and protocol detector, or
2. event-label disagreement (`event_positive` vs `event_negative`) under protocol criteria
- If mapping mismatch rate exceeds 10%, simulation pre-training is disabled and simulation is used only for parameter-sweep stress testing

---

## 11. Pre-Specified Performance Metrics

### 11.1 Classification Metrics

- Sensitivity (recall)
- Specificity
- Precision (PPV)
- NPV
- F1 score
- Balanced accuracy
- AUROC
- AUPRC
- Calibration: Brier score, calibration slope/intercept

### 11.2 Regression Metrics

- MAE
- RMSE
- R-squared
- Concordance correlation coefficient

### 11.3 Uncertainty Reporting

- 95% confidence intervals by patient-level bootstrap
- Primary reporting unit: patient-aggregated metric distribution, not pooled-breath-only estimates

---

## 12. Statistical Analysis Plan (Non-ML)

1. Describe distribution of `Delta Paw max` and `Delta PL max` by patient
2. Estimate association with ETS, PS, PEEP, and mechanics surrogates using mixed-effects models:

$$
\Delta P_{L,max} \sim ETS + PS + PEEP + (1|Patient)
$$

3. Compare synchronous vs asynchronous breaths (where labels available)
4. Exploratory clinical trajectory association only (N=7, no inferential outcome claims)

Multiplicity control:

- Primary endpoints limited to two: `Delta PL max` characterization and regression performance (MAE and RMSE)
- Secondary analyses reported with false discovery rate control where applicable

Convergence and identifiability fallback:

- If mixed-effects models fail to converge, or if predictors show insufficient within-patient variation, switch to descriptive patient-stratified summaries and fixed-effects models with patient indicators as exploratory support only
- Any fallback is reported as a protocol-constrained analytical limitation, not as confirmatory inference
- If predictors are near-constant within patient, mixed-effects coefficients are interpreted primarily as between-patient associations (random intercept absorbs most within-patient structure)
- Multicollinearity is assessed (variance inflation factor and condition index); if severe collinearity is present, simplified models are reported with explicit caveats on coefficient interpretability

---

## 13. Curation Contingency Plan

### 13.1 If Secondary Dataset Curation Fails

If Puritan Bennett data cannot be curated to analyzable PSV segments:

1. Declare external validation unavailable
2. Run fallback validation:
- Leave-one-patient-out only (CCVW)
- Simulation stress tests
3. Label manuscript claims as internal-validation only

### 13.2 If Simulation Label Mapping Fails

1. Disable simulation pre-training
2. Use augmentation-only strategy on CCVW (noise/time scaling)
3. Mark simulation contribution as not executed
4. Retain simulation only for non-label-dependent stress tests

### 13.3 If Pes Quality Is Inadequate in Any CCVW Segment

1. Exclude low-quality Pes windows from label generation
2. Keep Paw+Flow segmentation statistics separately
3. Report exclusion fraction by patient and reason

---

## 14. Reproducibility and Governance

- All code under `REBOOT/analysis/`
- Deterministic random seeds fixed and logged
- Every exclusion rule produces a machine-readable audit log
- No undocumented manual label edits allowed
- Amendments to this protocol must be appended below before running modified analyses

---

## 15. Amendment Log

- **v1.0 (2026-03-14):** Initial locked protocol for Phase 2
- **v1.1 (2026-03-14):** Addressed independent audit findings: deterministic `t_cycle`; ETS hierarchy and sensitivity analysis; external validation reframed as domain-shift/plausibility (no Pes-ground-truth metrics on PB); quality-flag operational definitions; TF denominator guard; primary ML shifted to XGBoost with deep models secondary; simulation label mapping verification with >10% mismatch cutoff; mixed-model fallback rules.
- **v1.2 (2026-03-14):** Added residual-issue refinements: explicit 3-sample `t_cycle` trade-off note; TF threshold rationale and required reporting of affected breath fraction; missing PS/PEEP/FiO2 handling (no imputation); pre-specified external waveform plausibility checklist appendix; stratified simulation mapping audit with formal mismatch criteria; mixed-model interpretation notes for low within-patient variation and multicollinearity checks.

---

## Appendix A: Hyperparameter Grid (Pre-Specified)

### A.1 1D CNN

- Conv blocks: 2, 3
- Filters: 16, 32, 64
- Kernel sizes: 5, 9, 15
- Dropout: 0.1, 0.2, 0.3
- Learning rate: 1e-3, 3e-4

### A.2 BiLSTM

- Hidden units: 32, 64
- Layers: 1, 2
- Dropout: 0.1, 0.2
- Learning rate: 1e-3, 3e-4

### A.3 XGBoost

- Max depth: 3, 5, 7
- Learning rate: 0.03, 0.1
- N estimators: 200, 500
- Subsample: 0.7, 1.0

---

## Appendix B: External Waveform Plausibility Review Checklist (Pre-Specified)

Applied to sampled high-score and low-score breaths in Puritan Bennett external evaluation.

### B.1 Sampling for Review

- Review sets per evaluation run:
1. Top-decile model-score breaths: random sample of 100
2. Bottom-decile model-score breaths: random sample of 100
- Exclude breaths with `incomplete_window` or unresolved channel mapping

### B.2 Itemized Checklist (binary pass/fail per item)

1. Breath displays a clear inspiratory flow-decay morphology before cycling
2. Candidate cycling moment aligns with expected late-inspiratory threshold behavior
3. Visible Paw inflection/perturbation near predicted cycling window (0 to +350 ms)
4. Signal is free of obvious artifact (flatline, clipping, abrupt implausible spikes)
5. Predicted high-probability breaths appear physiologically plausible relative to low-probability breaths by waveform morphology

### B.3 Review Process

- Two independent reviewers, blinded to each other
- Inter-rater agreement reported (percent agreement and Cohen's kappa)
- Disagreements adjudicated by third reviewer
- This checklist is descriptive/face-validity support only and does not create external ground-truth labels

---

## Appendix C: Simulation Label-Mapping Audit Procedure

### C.1 Audit Sampling

- Stratified random sample of 200 breaths across simulation strata:
1. ETS settings
2. Compliance bins
3. Resistance bins
4. PS level bins
- Proportional allocation by stratum size; minimum 5 breaths per non-empty stratum when feasible

### C.2 Mismatch Criteria

A sampled breath is counted as mismatch if either condition is met:

1. `|t_cycle_sim_label - t_cycle_protocol| > 20 ms`
2. `event_label_sim != event_label_protocol`

### C.3 Decision Rule

- Compute mismatch rate and 95% CI
- If mismatch rate >10%, disable simulation pre-training and restrict simulation use to non-label-dependent stress testing
- Record audit outputs in machine-readable log under `REBOOT/analysis/logs/`

---

*End of Phase 2 Analysis Protocol v1.2*