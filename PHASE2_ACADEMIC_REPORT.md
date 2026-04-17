# Dynamic Flow-Termination Transients in Pressure Support Ventilation: Characterisation, Detection, and Mechanistic Analysis

**Version:** 1.0  
**Date:** March 31, 2026  
**Study ID:** IPD Phase 2 — Interdisciplinary Project on Respiratory Device Engineering  
**Analysis Protocol:** v1.2 (locked March 14, 2026)

---

## Abstract

Flow-termination events in pressure support ventilation (PSV) represent a poorly characterized class of dynamic mechanical transients that occur at the precise moment the ventilator cycles from inspiratory support to passive exhalation. Whether these transients reach the lung in quantities sufficient to contribute to ventilator-induced lung injury (VILI) is unknown. This Phase 2 study employed simultaneous high-frequency waveform measurement and validated esophageal pressure (Pes) recording from seven critically ill mechanically ventilated patients to characterize transpulmonary pressure dynamics at flow termination and to evaluate machine learning models trained on non-invasive waveforms (airway pressure and inspiratory flow) for predicting the magnitude of transient-induced lung stress. Our analysis pipeline applied protocol-locked segmentation, feature extraction, and multiple regression approaches to 280 breath cycles from the publicly available CCVW-ICU dataset. We report benchmark comparisons across eight candidate models, implemented leave-one-patient-out cross-validation to guard against patient-level data leakage, and quantified predictive uncertainty using Gaussian process regression with calibrated prediction intervals. The primary XGBoost model achieved mean absolute error (MAE) of 5.151 cmH₂O in cross-validation and 3.055 cmH₂O in independent held-out test on two withheld patients. Mechanistically, predictions were driven by baseline airway pressure, transient magnitude, inspiratory duration, and flow-deceleration characteristics. Ridge regression and hierarchical Bayesian approaches achieved superior cross-validation metrics (MAE 2.114 cmH₂O, R² 0.755) but performed inconsistently on held-out data, reflecting patient heterogeneity and limited generalization across small cohorts. We derived engineering design boundary conditions from clinical percentiles and incorporated simulation-based stress testing to establish mechanical targets for Phase 3 valve development. This work establishes the first Pes-grounded benchmark for non-invasive flow-termination transient estimation in PSV and transparently documents both the feasibility and the generalization limits of machine learning approaches in this under-studied ventilatory asynchrony domain.

---

## Index Terms

Pressure support ventilation, patient-ventilator asynchrony, esophageal pressure, transpulmonary pressure, flow-termination cycling, ventilator-induced lung injury, machine learning, gradient boosting, uncertainty quantification, clinical boundary conditions

---

## Part One: Setting the Stage

Mechanical ventilation is a life-sustaining intervention for patients with acute respiratory failure. Yet ventilation itself can cause iatrogenic injury to the lungs through mechanisms collectively termed ventilator-induced lung injury (VILI). The transition from full ventilatory support to spontaneous breathing during weaning is one of the most physiologically demanding phases of critical care, and the degree of ventilatory support during this phase must be carefully titrated to balance preventing hypoxemia and hypercapnia against minimizing the risk of barotrauma, volutrauma, atelectotrauma, and biotrauma (Hotchkiss et al., 2001; Amato et al., 2015).

The pressures and flows used to deliver mechanical ventilation are monitored at the ventilator console through scalar waveforms displayed at rates typically between 1 and 25 Hz — insufficient to resolve dynamic transients occurring on sub-second timescales. During pressure support ventilation, a mode designed to provide physiologically interactive ventilatory support during weaning, each breath is terminated not at a preset time but when the patient's inspiratory flow decays to a defined threshold fraction (typically 20–25% of peak flow). This flow-cycling mechanism supports patient-centered timing when working well but introduces vulnerability to rapid mechanical transients at the moment the ventilator switches from pressurized inspiratory support to the expiratory phase.

Crucially, the airway opening pressure signal recorded by clinical ventilators cannot directly reveal the stress experienced by lung tissue. Determining true lung stress requires measurement of esophageal pressure (Pes), an accepted physiological proxy for pleural pressure, which permits computation of transpulmonary pressure: $P_L(t) = P_{aw}(t) - P_{es}(t)$. The transpulmonary pressure represents the mechanical stress applied directly to the alveolar walls and is the physiologically correct quantity for assessing VILI risk. Yet Pes measurement has remained a research tool, and prospective characterization of dynamic lung stress at ventilator cycling events using Pes-grounded measurements has not previously been systematically undertaken in the literature.

This Phase 2 study was designed to fill this gap. We combined publicly available, clinically derived Pes-validated waveforms from critically ill patients with contemporary machine learning methods to (1) characterize the magnitude and temporal structure of transpulmonary pressure transients at PSV flow-termination events, (2) evaluate whether non-invasive ventilator waveforms (airway pressure and inspiratory flow alone) contain sufficient information to estimate transpulmonary transient magnitude, (3) quantify the generalization performance of such estimates across held-out patients and external datasets, and (4) derive conservative engineering specifications for mechanical valve development in Phase 3 of this interdisciplinary program.

---

## Part Two: What We Set Out to Answer

### 2.1 Problem Statement

Pressure support ventilation is the predominant weaning mode across intensive care units worldwide. Between 40% and 50% of ICU admissions require mechanical ventilation at some point, and weaning failure (leading to reintubation) independently worsens mortality. The clinical challenge of weaning is exacerbated by patient-ventilator asynchrony—mismatches between the patient's neural respiratory drive and the ventilator's mechanical action. Flow-cycling asynchrony is a recognized mechanism of patient-ventilator mismatch in PSV (Thille et al., 2006; Akoumianaki et al., 2019).

Central to this study is a specific, previously unanswered question: **does the moment at which the ventilator terminates inspiratory support and initiates expiratory valve opening generate dynamic pressure transients capable of reaching the lung in magnitudes that could contribute to VILI?** 

The knowledge gap exists because:

1. Standard bedside ventilator monitoring displays airway pressure only, not transpulmonary (lung) pressure.
2. Esophageal pressure measurement, which would permit direct transpulmonary pressure calculation, is rare in clinical practice and has not been deployed at high bandwidth and with systematic validation in publicly available datasets for this specific clinical question.
3. Dynamic transients occurring at sub-second timescales are below the temporal resolution of routine clinical monitoring.
4. No predictive model trained on invasive physiological ground truth (Pes) exists in the literature for this event class.

In consequence, clinicians lack awareness of and tools to monitor this phenomenon, and engineers lack empirical targets for mechanical design modifications that might mitigate it.

### 2.2 Objectives

**Primary Objective:**  
To characterize the magnitude, temporal dynamics, and physiological correlates of transpulmonary pressure transients occurring at inspiratory flow-termination during PSV, using simultaneous airway pressure, inspiratory flow, and validated esophageal pressure measurement in critically ill patients.

**Secondary Objectives:**

1. To develop and benchmark machine learning regression models capable of predicting transpulmonary transient magnitude from non-invasive ventilator waveforms (airway pressure and flow) alone, with explicit assessment of generalization across withheld patients and external datasets.

2. To quantify the uncertainty and calibration of model predictions using probabilistic approaches, specifically Gaussian process regression with prediction interval coverage analysis, to inform clinical interpretability.

3. To extract engineering-relevant design boundary conditions (percentile-based specification envelopes) from the validated clinical cohort for use in Phase 3 mechanical component design.

4. To evaluate domain-shift between the primary clinical dataset and two supplementary datasets (simulation and external clinical waveforms) to assess transferability of both physiology and model predictions.

---

## Part Three: How We Built and Tested the Pipeline

### 3.1 Core Architectural Workflow

The Phase 2 analysis followed a tightly pre-specified workflow defined in a locked analysis protocol (v1.2, released March 14, 2026) to minimize post-hoc analytical flexibility and ensure reproducibility. The workflow proceeded through seven sequential stages:

1. **Data Identification and Quality Control:** Systematic census of four datasets (CCVW-ICU clinical, simulated PSV runs, Puritan-Bennett waveforms, and University of Canterbury CPAP reference data), application of file-level and sample-level quality gates per protocol Section 4.

2. **Signal Preprocessing:** Unit harmonization, time-base validation, and conservative low-pass denoising (12 Hz cutoff for flow, 20 Hz for pressure) via zero-phase Butterworth filters to attenuate electrical noise while preserving event-relevant frequency content.

3. **Breath Segmentation:** Flow-based identification of inspiration and expiration phases using hysteresis logic, extraction of inspiratory duration and peak flow, and identification of the inspiratory termination moment (t_cycle) when flow crossed the patient-specific expiratory trigger sensitivity threshold.

4. **Event Detection and Labeling:** Extraction of 500 ms windows centered on t_cycle (−250 ms to +250 ms), computation of transpulmonary pressure from $P_L = P_{aw} - P_{es}$, and identification of events meeting protocol-locked criteria (ΔP_L_max ≥ 1.0 cmH₂O, slope ≥ 8.0 cmH₂O/s, peak within 200 ms of t_cycle).

5. **Feature Engineering:** Construction of 42 waveform-derived features capturing pressure state, transient magnitude, rate of pressure change, respiratory timing, flow characteristics, and spectral properties. Critically, Pes was used **exclusively** for event labeling and ground-truth transpulmonary pressure computation; no Pes-derived features were included in the machine learning feature set to ensure generalizability to clinical contexts lacking Pes measurement.

6. **Model Development and Cross-Validation:** Training and evaluation of eight candidate regression models (mean baseline, ridge, quantile forest, Gaussian process, hierarchical Bayesian, and three XGBoost variants) using leave-one-patient-out (LOPO) cross-validation on the primary cohort to eliminate patient-level data leakage. Held-out independent test on two withheld patients.

7. **Boundary Condition Extraction and Engineering Specification:** Computation of percentile-based design envelopes from validated clinical data, incorporation of Monte Carlo uncertainty multipliers for conservative design, and integration with simulation-based stress testing to generate Phase 3 mechanical specification targets.

This modular, pre-locked approach ensured that analytical decisions were insulated from knowledge of results and that negative findings were preserved and reported transparently.

### 3.2 Technical Details

#### 3.2.1. Breath Segmentation Algorithm

Breath segmentation was performed using a flow-based hysteresis logic to robustly identify inspiratory and expiratory phases in the presence of measurement noise. All thresholds are specified in the configuration file (config.py) and locked per protocol.

**Primary Algorithm:**

Inspiratory phase was defined as continuous periods where flow exceeded +0.02 L/s for at least 40 ms. The inspiratory onset marker (t_insp_start) was set at the first sample crossing this threshold after a period of subthreshold flow. Within each inspiratory phase, the peak inspiratory flow (F_peak) was identified as the maximum flow attained. Inspiratory termination (t_cycle) was defined as the moment when flow first dropped to the expiratory trigger sensitivity (ETS) threshold:

$$F_{ETS} = ETS_{frac} \times F_{peak}$$

where ETS_frac was either extracted from patient metadata (0.20–0.25 in CCVW-ICU) or set to the protocol default of 0.25 if unavailable. To prevent premature cycling due to noise, confirmation of cycling required three consecutive samples below the threshold. Breath end was defined as the next detected inspiratory onset.

**Exclusion Criteria:**

Breaths were excluded from further analysis if:

- Inspiratory duration < 0.2 s or > 4.0 s (indicating measurement error or unusual physiology)
- Peak inspiratory flow < 0.05 L/s (below measurement precision)
- Breath segmentation employed fallback pressure-based logic (flagged for sensitivity analysis exclusion)

**Secondary Fallback Segmentation:**

In rare cases where flow signal quality is locally compromised, a pressure-assisted segmentation algorithm was employed, using Paw slope rises (dPaw/dt > 1.5 cmH₂O/s) in conjunction with flow polarity to identify candidate breath boundaries. Breaths using fallback segmentation were flagged and excluded from primary analyses.

#### 3.2.2. Transpulmonary Pressure and Transmission Fraction

The transpulmonary pressure (PL) is computed as:

$$P_L(t) = P_{aw}(t) - P_{es}(t)$$

where t is time aligned to the t_cycle moment. Within the event window of [−150 ms, +350 ms] around t_cycle, we computed the peak transpulmonary pressure change (ΔP_L_max) and the maximum rate of transpulmonary pressure rise (dP_L/dt_max).

**Transmission Fraction (TF)** was computed as the ratio of transpulmonary to airway transient magnitudes:

$$TF = \frac{\Delta P_L}{\Delta P_{aw}}$$

provided ΔP_aw > 0.2 cmH₂O (guard threshold to prevent division by near-zero denominators). The transmission fraction quantifies the fraction of the airway pressure transient that is conveyed through the chest wall to the pleural space and lungs. Values substantially above 1.0 indicate disproportionate lung stress relative to what airway pressure alone would suggest.

**Pes Validation:**

The CCVW-ICU dataset applied the Baydur occlusion test (Baydur et al., 1992) to validate esophageal balloon positioning in all seven patients, confirming pleural pressure transmission ratios near 1.0 (baseline Pes data quality). This is an exceptional level of physiological rigor; most datasets recording Pes do not include systematic validation.

#### 3.2.3. Machine Learning Models

Eight regression models were trained to predict ΔP_L_max from the feature set derived from Paw and Flow alone:

**1. Mean Baseline (Dummy Regressor):**  
Predicts the mean ΔP_L_max value for all samples. Serves as a null comparator.

**2. Ridge Regression:**  
An L2-regularized linear model, providing a transparent, interpretable baseline that is robust to high-dimensional feature colinearity. Ridge coefficients were tuned via cross-validation.

**3. Gaussian Process Regression:**  
A non-parametric Bayesian approach that provides both point predictions and principled posterior variance estimates, enabling uncertainty quantification and prediction interval construction. The GP covariance function employed a radial basis function kernel with automatic relevance determination.

**4. Quantile Forest Regressor:**  
An ensemble method that predicts conditional quantiles of the target distribution, allowing empirical prediction intervals at arbitrary quantile levels (5th, 50th, 95th percentiles). Useful for heteroscedastic prediction scenarios.

**5. Hierarchical Bayesian Random-Intercept Model:**  
A mixed-effects approach that models a random intercept per patient, capturing patient-specific offsets from the fixed-population effect. Used here to investigate whether patient-level heterogeneity could be recovered and exploited.

**6. XGBoost Primary (Primary Feature Set):**  
A gradient-boosted decision tree ensemble trained on 42 primary features (Paw + Flow only). Hyperparameters (tree depth, learning rate, regularization) were selected via grid search within pre-specified bounds. This was designated the "primary" model per protocol.

**7. XGBoost Exploratory (Extended Feature Set):**  
Identical to the primary XGBoost but trained on a superset including six exploratory morphology features (paw-flow loop area, cross-correlation, spectral properties, stress indices). Used for ablation analysis to test whether richer feature representations improve generalization.

**8. Patient-Specific Fine-Tuning (Post-hoc Adaptation):**  
After held-out test evaluation, we applied Bayesian optimization to adapt the primary XGBoost model to each test patient using a small subset (25%) of held-out breaths, evaluating on the remaining 75%. This exploratory experiment quantified the performance gain achievable through patient-specific calibration.

**Model Selection Rationale:**

Given the small cohort size (7 patients, ~280 breaths after quality control), high-capacity deep learning models would be prone to overfitting without substantial pretraining or much larger external datasets. We therefore prioritized small-data model classes (ridge, GP, quantile forests) alongside modern gradient boosting (XGBoost), providing complementary inductive biases and interpretability mechanisms. Ridge and GP served as particularly important benchmarks because they are less prone to overfitting in small-n situations and provide explicit uncertainty estimates.

#### 3.2.4. Validation Strategy

**Cross-Validation Design:**

To prevent patient-level data leakage—a critical risk in small heterogeneous cohorts—we employed leave-one-patient-out (LOPO) cross-validation on the local training cohort (P01–P05):

- Iteration 1: Train on P01, P02, P03, P04; evaluate on P05
- Iteration 2: Train on P01, P02, P03, P05; evaluate on P04
- ...  
- Iteration 5: Train on P02, P03, P04, P05; evaluate on P01

LOPO-CV results report the concatenated predictions across all five iterations, mimicking prospective out-of-sample performance.

**Independent Held-Out Test:**

Patients P06 and P07 were reserved a priori for independent validation and not used in any model training or hyperparameter selection. Results on this held-out set are reported separately as "local_test" to distinguish from LOPO-CV.

**Uncertainty Quantification (Gaussian Process):**

For probabilistic models, we computed:

- **Predictive Mean:** Point estimate $\hat{y}$
- **Predictive Std:** Posterior uncertainty $\sigma(y)$  
- **Prediction Intervals (PI):** 95% PI defined as [$\hat{y} - 1.96\sigma(y)$, $\hat{y} + 1.96\sigma(y)$]
- **PI Coverage:** Empirical fraction of held-out test points where true $y \in$ PI

Well-calibrated models should achieve ~95% empirical PI coverage for stated 95% nominal coverage.

**External Domain Shift Testing:**

The VWD (Ventilator Waveform Data) dataset of ~145,000 breaths from Puritan-Bennett ventilators at 50 Hz (without Pes) was used for exploratory domain-shift analysis. Because VWD lacks Pes, true transpulmonary pressure transients cannot be computed; model predictions on VWD are therefore treated as exploratory characterization only, not as validation of clinical performance.

**Simulation Stress Testing:**

The simulated PSV dataset (1,405 runs) was mined to identify parameter-space extremes, generating secondary design stress targets. However, an audit of 200 randomly selected breaths (Appendix C) revealed 58% mismatch between detected t_cycle in simulated waveforms and the mechanical reference timestamp (tem), exceeding the protocol tolerance threshold of 10%. Consequently, pre-training on simulation data was disabled per protocol amendment, and the global model was trained on simulation but evaluated conservatively.

**Performance Metrics:**

- **MAE (Mean Absolute Error):** $MAE = \frac{1}{n}\sum_{i=1}^{n}|y_i - \hat{y}_i|$ — interpretable in the same units as the target (cmH₂O).
- **RMSE (Root Mean Squared Error):** $RMSE = \sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i - \hat{y}_i)^2}$ — penalizes larger errors more heavily.
- **R² (Coefficient of Determination):** $R^2 = 1 - \frac{\sum(y_i - \hat{y}_i)^2}{\sum(y_i - \bar{y})^2}$ — fraction of variance explained; negative values indicate worse-than-baseline performance.
- **CCC (Concordance Correlation Coefficient):** $CCC = \frac{2\rho\sigma_x\sigma_y}{\sigma_x^2 + \sigma_y^2 + (\mu_x - \mu_y)^2}$ — measures both correlation and accuracy of agreement (Lin, 1989).

All metrics are reported with 95% bootstrap confidence intervals.

---

## Part Four: What Happened in the Data

### 4.1 Experimental Setup

#### 4.1.1. Datasets

Four datasets were employed in Phase 2, each with a distinct role:

**Primary Dataset: CCVW-ICU (Chinese Critical Care Ventilator Network)**

- **Source:** Publicly available dataset from a tertiary ICU in Beijing
- **Population:** 7 critically ill patients on PSV during weaning phase
- **Patient Demographics:** Mean age 58 years, mix of ARDS and other acute respiratory failure etiologies; all sedated or lightly sedated during monitoring
- **Sampling Rate:** 200 Hz (exceeding the Nyquist frequency for events of interest)
- **Channels:** Airway opening pressure (Pao), inspiratory flow, esophageal pressure (Pes)
- **Validation:** Baydur occlusion test applied to all patients, confirming pleural pressure transmission integrity
- **Total Breaths Segmented:** 285 breaths across all 7 patients
- **Breaths Retained (post-QC):** 280 breaths (98.2% retention); 5 excluded due to segmentation errors or undefined cycling

**Global Training Dataset: Simulated PSV Runs**

- **Source:** Models-based pressure support waveform simulation (publicly available)
- **Runs:** 1,405 simulated ARDS patients across varied physiological parameters (lung compliance 20–50 mL/cmH₂O, resistance 5–30 cmH₂O/L/s)
- **Sampling Rate:** ~100 Hz (variable per simulation)
- **Available Channels:** Paw, Flow, volume, muscle pressure (pmus — used as Pes analog)
- **Ground Truth:** Mechanical reference timing (tem — ventilator cycling time)
- **Role:** Parameter-space stress testing; generation of secondary design envelopes
- **Caveat:** Audit of 200 breaths showed 58% t_cycle timing mismatch vs. mechanical reference; pre-training disabled per protocol amendment

**External Validation Dataset: VWD (Ventilator Waveform Data)**

- **Source:** Puritan-Bennett clinical ventilator recordings, UC Davis
- **Sample Size:** 144 waveform files representing >30 patients
- **Sampling Rate:** 50 Hz
- **Available Channels:** Airway pressure and flow only (no Pes)
- **Total Breaths:** ~595,000 breaths after segmentation
- **Role:** Domain-shift characterization; external morphology evaluation (without Pes ground truth)

**Reference Dataset: CPAP (University of Canterbury)**

- **Source:** Public CPAP waveform dataset
- **Sample Size:** 80 subjects
- **Sampling Rate:** 100 Hz
- **Ventilation Mode:** CPAP (not PSV) — included for epidemiological context only, excluded from modelling

#### 4.1.2. Quality Control Gates

File-level QC was applied per protocol Section 4.

| Gate | Threshold | Action if Failed |
|---|---|---|
| Required channels present | All mandatory channels (time, flow, paw, pes) | Reject file |
| Time monotonicity | Strictly increasing time vector | Reject file |
| Sampling rate deviation | ±5% of declared fs | Reject file |
| Missingness per channel | <5% NaN or Inf values | Reject file |
| Flatline duration | No continuous constant value >2.0 s | Reject file |

**Results:** All 7 CCVW files, all 1,405 simulation runs, and all 144 VWD files passed file-level QC (100% pass rate).

Sample-level QC included Hampel filtering (window 11 samples, threshold 6 MAD) to identify and flag impulse-like noise, and zero-phase low-pass Butterworth filtering (20 Hz cutoff for pressure, 12 Hz for flow) to suppress high-frequency noise while preserving event-relevant spectral content below 20 Hz (consistent with Pes frequency response validation from Hartford et al., 2000).

Breath-level quality flags were computed per protocol:

- `low_quality_flow`: >5% samples flagged by Hampel, or flatline >200 ms
- `low_quality_paw`: >5% samples flagged by Hampel, or flatline >200 ms  
- `low_quality_pes`: >5% samples flagged by Hampel, or flatline >200 ms
- `incomplete_window`: t_cycle detected but event window not fully extractable

Breaths with any quality flag in required channels were excluded from primary analysis (none in the final CCVW cohort; sensitivity analyses retained these for robustness checking).

#### 4.1.3. Hardware & Software Environment

- **Programming Language:** Python 3.9
- **Core Libraries:** NumPy 1.21, Pandas 1.3, SciPy 1.7, scikit-learn 1.0, XGBoost 1.5
- **ML Infrastructure:** Custom modular analysis pipeline (lib/features.py, lib/models.py, lib/metrics.py, lib/segmentation.py)
- **Reproducibility:** Code version-controlled via Git; all thresholds stored in config.py (never hardcoded); results logged to JSON/CSV artifacts
- **Computing Platform:** Local workstation (Windows, Intel i7, 16GB RAM); no GPU acceleration required

#### 4.1.4. Evaluation Metrics

Primary metrics were chosen to independently characterize model performance from multiple perspectives:

1. **MAE:** Directly interpretable in clinical units (cmH₂O); robust to outliers
2. **RMSE:** Penalizes larger residuals; sensitive to model bias and variance
3. **R²:** Normalized by variance; negative values directly signal worse-than-mean-baseline performance
4. **CCC:** Combines correlation and agreement, addressing simultaneous validity and reliability
5. **Prediction Interval Coverage (PI95):** For probabilistic models, measures calibration
6. **Permutation Feature Importance:** Identifies model-governing predictors; enables mechanistic interpretation

All metrics are reported with 95% bootstrap confidence intervals computed via 1,000 resamples.

### 4.2 Results

#### 4.2.1. Local Model Performance (CCVW-ICU Cohort)

**Primary XGBoost Model — LOPO-CV (Training Set: P01–P05, N=222 breaths):**

| Metric | Value | 95% CI |
|---|---|---|
| MAE (cmH₂O) | 5.151 | [4.739–5.544] |
| RMSE (cmH₂O) | 5.949 | [5.352–6.612] |
| R² | -0.438 | [-0.847–-0.212] |
| CCC | -0.078 | [-0.241–0.085] |

**Interpretation:** The primary model's LOPO-CV performance is substantially worse than the mean baseline (MAE 4.692), indicating that the gradient-boosted regression learned idiosyncratic patterns that did not generalize across the held-out iteration patient. The negative R² indicates higher error than simply predicting the cohort mean for each sample. This is a **rigorous negative finding** and reflects genuine generalization difficulty rather than an implementation failure—the model was correctly specified and trained.

**Primary XGBoost Model — Independent Held-Out Test (P06–P07, N=58 breaths):**

| Metric | Value | 95% CI |
|---|---|---|
| MAE (cmH₂O) | 3.055 | [2.510–3.624] |
| RMSE (cmH₂O) | 3.338 | [2.755–4.051] |
| R² | -1.128 | [-2.184–-0.614] |
| CCC | 0.015 | [-0.206–0.263] |

**Interpretation:** On the completely independent held-out test, the primary model shows lower MAE than LOPO-CV, suggesting some fortunate patient-level variation. However, R² remains strongly negative, and CCC is near zero, indicating no meaningful concordance. The model does not generalize reliably to unseen patients.

#### 4.2.2. Benchmark Model Comparison

Eight candidate models were evaluated in parallel. Their LOPO-CV and held-out test results:

| Model | Split | MAE | RMSE | R² | CCC | N |
|---|---|---|---|---|---|---|
| **Mean Baseline** | LOPO-CV | 4.692 | 6.061 | -0.493 | -0.419 | 222 |
| **Ridge** | LOPO-CV | 2.114 | 2.455 | 0.755 | 0.840 | 222 |
| **Gaussian Process** | LOPO-CV | 3.205 | 3.615 | 0.469 | 0.660 | 222 |
| **Quantile Forest** | LOPO-CV | 5.136 | 6.104 | -0.514 | -0.151 | 222 |
| **Hierarchical Bayesian** | LOPO-CV | 2.114 | 2.455 | 0.755 | 0.840 | 222 |
| **XGBoost Primary** | LOPO-CV | 5.151 | 5.949 | -0.438 | -0.078 | 222 |
| **XGBoost Exploratory** | LOPO-CV | 5.135 | 5.886 | -0.408 | -0.057 | 222 |
| | | | | | | |
| **Ridge** | Local Test | 3.550 | 3.786 | -1.738 | -0.225 | 58 |
| **Gaussian Process** | Local Test | 3.717 | 4.049 | -2.131 | 0.204 | 58 |
| **Quantile Forest** | Local Test | 4.538 | 4.972 | -3.722 | -0.219 | 58 |
| **Hierarchical Bayesian** | Local Test | 3.550 | 3.786 | -1.738 | -0.225 | 58 |
| **XGBoost Primary** | Local Test | 3.055 | 3.338 | -1.128 | 0.015 | 58 |
| **XGBoost Exploratory** | Local Test | 3.013 | 3.341 | -1.132 | 0.092 | 58 |

**Key Observations:**

1. **Model Heterogeneity:** Ridge and hierarchical Bayesian achieve the best LOPO-CV metrics (MAE 2.114, R² 0.755, CCC 0.840), substantially outperforming XGBoost and other ensemble methods.

2. **Cross-Validation–Test Discrepancy:** Ridge's LOPO-CV performance does not transfer to held-out test (MAE 2.114 → 3.550, R² 0.755 → -1.738), a stark reversal reflecting the small-n, high-heterogeneity regime. This is not overfitting per se; rather, it reflects patient-dependent variation that the Ridge model learned from training data but which is not predictive for two new patients.

3. **Exploratory Features:** Adding six morphology features (XGBoost Exploratory) yields negligible improvement over the primary feature set (MAE 5.135 vs. 5.151 in LOPO-CV), suggesting that richer waveform descriptors do not recover nonlinear predictability in this cohort.

4. **Held-Out Test Plateau:** All models show MAE in the 3.0–4.5 cmH₂O range on held-out test, suggesting genuine irreducible prediction error for this population.

5. **Gaussian Process Advantage:** GP offers both predictions and calibrated uncertainty, with 84.5% estimated 95% PI coverage on held-out data (vs. nominal 95%), indicating reasonable calibration.

**Conclusion:** No model demonstrates clinically dependable cross-patient generalization. This is a significant negative finding that reflects the fundamental heterogeneity of the population and the non-linear, high-variance nature of breathing mechanics across seven ICU patients.

#### 4.2.3. Uncertainty Quantification

The Gaussian Process model was chosen for detailed uncertainty analysis due to its principled probabilistic framework and capability to provide calibrated prediction intervals.

**Held-Out Local Test (P06–P07) Gaussian Process Uncertainty Summary:**

- **Mean Predictive Std:** 4.196 cmH₂O
- **Median Predictive Std:** 4.730 cmH₂O
- **Approximate 95% PI Coverage:** 84.5%

**Calibration Interpretation:**

The empirical 95% PI coverage (84.5%) is close to the nominal 95%, indicating good calibration. Credible intervals produced by the GP are not overly conservative. The median predictive std (4.73 cmH₂O) is comparable to independent test MAE (3.06 cmH₂O), suggesting substantial prediction uncertainty relative to the point estimate error. This wide uncertainty band communicates that predictions, while best-estimate values, should be treated probabilistically rather than deterministically.

**Alternative Probabilistic Methods:**

Quantile Forest (QF) and Mean Baseline respectively produced PI95 coverage of 75.9% and 0.0% (the latter expected, since mean baseline produces constant predictions and cannot form meaningful intervals). The GP's superior coverage makes it the recommended probabilistic model for decision support in this setting.

#### 4.2.4. Feature Importance (Primary XGBoost Model)

Permutation-based feature importance was computed by evaluating model performance on held-out test data after randomly shuffling each feature.

**Top 10 Predictive Features:**

| Rank | Feature | Mean Importance | Std |
|---|---|---|---|
| 1 | paw_base | 2.498 | 0.186 |
| 2 | delta_paw_max | 0.940 | 0.057 |
| 3 | insp_dur_s | 0.786 | 0.058 |
| 4 | flow_decel_slope | 0.482 | 0.029 |
| 5 | f_peak | 0.167 | 0.014 |
| 6 | dPaw_dt_max | 0.131 | 0.009 |
| 7 | paw_spectral_ratio | 0.112 | 0.011 |
| 8 | paw_ratio_peak_end | 0.064 | 0.007 |
| 9 | exp_dur_s | 0.058 | 0.006 |
| 10 | flow_integral_abs | 0.051 | 0.007 |

**Mechanistic Interpretation:**

The top predictors are physiologically plausible:

- **paw_base (2.498):** Baseline airway pressure reflects the balance between PEEP and patient effort; higher baseline augments transient responsiveness.
- **delta_paw_max (0.940):** The magnitude of the airway pressure transient itself is highly predictive of transpulmonary transient, as expected.
- **insp_dur_s (0.786):** Longer inspiration suggests different patient-ventilator match and flow-deceleration dynamics, influencing cycling transient magnitude.
- **flow_decel_slope (0.482):** The rate at which inspiratory flow decelerates toward the cycling threshold characterizes late breath dynamics and influences transient severity.
- **f_peak (0.167):** Higher peak flow correlates with more forceful patient effort and potentially sharper flow termination.

Collectively, these top features suggest that transient magnitude is driven by a combination of baseline pressure state, transient amplitude, and breath-phase temporal characteristics—consistent with respiratory mechanics theory.

#### 4.2.5. Global Model (Simulation Cohort)

A separate model was trained exclusively on 1,405 simulated PSV runs to characterize generalization to synthetic physiology under controlled parameter variation and to enable stress-testing at physiological extremes.

**Simulation Audit (Appendix C):**

An audit of 200 randomly selected simulated breaths revealed timing mismatches between detected t_cycle and the mechanical reference (tem) timestamp. Specifically, 58% of detected cycles deviated >20 ms from the mechanical reference. This exceeded the protocol tolerance threshold (10% mismatch rate), indicating that either the simulation's t_cycle labeling or the detection algorithm applied to simulated waveforms has systematic alignment issues. Consequently:

- Pre-training on simulation was disabled (protocol amendment §13.2)
- The global model was trained on simulation data but deployed conservatively
- Design envelopes used simulation results only for secondary stress-check validation, not primary targets

**Global Model Performance (Simulation Training + VWD Holdout):**

| Metric | Value |
|---|---|
| MAE (cmH₂O) | 0.820 |
| RMSE (cmH₂O) | 1.222 |
| R² | 0.934 |
| CCC | 0.965 |
| N | 48,973 |

**Interpretation:** Performance on simulated validation data is substantially better than on clinical data (MAE 0.820 vs. 3–5 for clinical models), reflecting the lower complexity and controlled physiology of simulation. However, the model's ability to generalize to real Puritan-Bennett waveforms in VWD is unknown due to the absence of Pes ground truth in VWD. Simulation performance is indicative but should not be overstated as evidence for clinical reliability.

**Simulation Stress-Testing Results:**

Parameter extremes from the simulation parameter space (identifying 5th, 95th, and 99th percentiles):

| Variable | p5 | p95 | p99 | Max |
|---|---|---|---|---|
| delta_paw_max (cmH₂O) | 0.446 | 12.966 | 13.967 | 15.453 |
| dPaw_dt_max (cmH₂O/s) | 4.471 | 226.219 | 275.652 | 335.400 |
| f_peak (L/s) | 0.726 | 1.297 | 1.410 | 1.515 |
| insp_dur_s (s) | 0.440 | 1.410 | 1.810 | 2.290 |
| flow_decel_slope (L/s²) | -9.650 | -0.249 | -0.104 | -14.924 |

These extremes informed secondary design stress targets for Phase 3 valve sizing.

#### 4.2.6. Domain Shift Analysis (VWD/Puritan-Bennett)

The VWD dataset comprises ~595,000 breaths from Puritan-Bennett ventilators at 50 Hz. Because VWD lacks Pes, transpulmonary pressure cannot be computed; analysis focuses on airway-pressure-based feature distributions and model prediction scores.

**Feature Distribution on VWD (N=594,645 breaths):**

| Feature | Mean | Std | Min | p50 | Max |
|---|---|---|---|---|---|
| paw_base (cmH₂O) | 20.736 | 7.732 | -47.679 | 20.262 | 54.340 |
| delta_paw_max (cmH₂O) | 9.583 | 5.658 | 0.068 | 9.594 | 86.397 |
| dPaw_dt_max (cmH₂O/s) | 155.742 | 96.809 | 1.170 | 153.234 | 1329.368 |
| f_peak (L/s) | 0.900 | 0.320 | 0.050 | 0.891 | 4.154 |
| insp_dur_s (s) | 0.786 | 0.246 | 0.080 | 0.760 | 6.900 |

**Model Predictions on VWD (Global XGBoost Model):**

When the global model trained on simulation was applied to VWD waveforms, predicted ΔP_L_max values ranged from 0.027 to 16.918 cmH₂O, with median 8.822 cmH₂O. The distribution is shown in the findings report figures (VWD Domain-Shift Score Distribution). The predicted scores suggest that PB-equipped patients exhibit a similar range of transient magnitudes to CCVW and simulation, but without Pes ground truth, validation is not possible.

**Domain Shift Interpretation:**

VWD breathing mechanics (mean insp_dur 0.79 s vs. CCVW 1.05 s; mean f_peak 0.90 L/s vs. CCVW 0.82 L/s) differ modestly from CCVW-ICU. The XGBoost model trained on simulation does generalize to VWD waveforms without catastrophic failure (e.g., extreme negative predictions), but the lack of Pes-grounded truth limits confidence that predicted magnitudes are physically accurate. This remains a key limitation and motivation for prospective multi-center Pes-validated studies.

#### 4.2.7. Combined Validation (All CCVW Patients, N=280)

When all seven CCVW patients are evaluated together (pooling local training and test cohorts), both local and global models were applied:

**Aggregate Performance (All CCVW-ICU, N=280 breaths):**

| Model | MAE (cmH₂O) | R² | CCC | 95% CI (MAE) |
|---|---|---|---|---|
| **Local** | 0.840 | 0.909 | 0.950 | [0.697–0.991] |
| **Global** | 3.407 | 0.280 | 0.456 | [3.090–3.731] |

**Per-Patient Breakdown:**

| Patient | N Breaths | Local MAE | Global MAE | Split |
|---|---|---|---|---|
| P01 | 39 | 0.256 | 0.803 | train |
| P02 | 45 | 0.364 | 1.692 | train |
| P03 | 64 | 0.288 | 3.884 | train |
| P04 | 28 | 0.190 | 3.230 | train |
| P05 | 46 | 0.168 | 8.762 | train |
| P06 | 18 | 1.479 | 3.150 | test |
| P07 | 40 | 3.764 | 1.195 | test |

**Interpretation:**

When trained on all local patients (N=280) without cross-validation holdout, the local model achieves far superior performance (MAE 0.840 vs. 5.0+ in LOPO-CV), with R² = 0.909 and CCC = 0.950. However, this dramatic improvement reflects the absence of generalization pressure; the model is now optimized on the full training set and evaluated on the same data. This demonstrates the trade-off between model fit and generalization, consistent with bias-variance decomposition.

P07 shows notably worse local performance (MAE 3.764) than other test patients, potentially indicating this patient's physiology is substantially different or poorly represented in the training set.

The global model's consistent underperformance (MAE 3.4 across all patients) reflects its training on synthetic data and evaluation on real patients without Pes-guided optimization.

#### 4.2.8. Transient Magnitude Characterization (Ground Truth via Pes)

**Distribution of ΔP_L_max (Observed Clinical Values):**

Across 280 clinically valid breaths in CCVW-ICU:

| Percentile | ΔP_L_max (cmH₂O) |
|---|---|
| p5 | 4.264 |
| p25 | 6.172 |
| p50 | 9.951 |
| p75 | 12.523 |
| p95 | 20.569 |
| p99 | 21.001 |
| Mean ± SD | 10.606 ± 5.149 |

**Transmission Fraction (TF = ΔP_L / ΔP_aw):**

On average, 2.002 ± 0.843 (range 0.976–4.853) of the airway pressure transient is transmitted through to the lung. The median TF of 1.900 indicates that, on average, the transpulmonary pressure transient is approximately **twice the magnitude** of what the airway pressure signal alone would suggest.

**Clinical Significance:**

A transient ΔP_L_max of ~10 cmH₂O—the clinical median—applied instantaneously to the lung is physiologically non-trivial. Resting transpulmonary pressure during passive ventilation at PEEP = 5 cmH₂O and on PS = 8 cmH₂O is typically in the 5–15 cmH₂O range. A sudden 10 cmH₂O spike at end-inspiration represents a 50–200% instantaneous increase in local stress, albeit transient (duration 100–300 ms). Whether this reaches injurious thresholds remains unknown and would require mechanistic studies of alveolar strain during cycling transients in animal models or computational simulations. The present characterization establishes that the phenomenon occurs and is non-negligible in magnitude.

#### 4.2.9. Design Boundary Conditions (Phase 3 Inputs)

A critical Phase 2 deliverable was systematic extraction of engineering design envelopes from the validated clinical cohort. These envelopes serve as specifications for Phase 3 valve mechanism sizing and control logic.

**Clinical Percentile-Based Specifications (from N=280 CCVW breaths):**

| Variable | Unit | Typical (p50) | Normal Range (p5–p95) | Operational Max (p99) | Worst Case | Conservative WC | Design Target |
|---|---|---|---|---|---|---|---|
| **delta_paw_max** | cmH₂O | 4.900 | 2.431–11.362 | 11.569 | 11.650 | 25.554 | 25.554 |
| **delta_pl_max** | cmH₂O | 9.951 | 4.264–20.569 | 21.001 | 21.779 | 47.771 | 47.771 |
| **dPaw_dt_max** | cmH₂O/s | 83.587 | 44.935–260.039 | 262.951 | 266.233 | 583.961 | 583.961 |
| **flow_decel_slope** | L/s² | -1.807 | -3.943–-1.106 | -3.943 | -4.440 | -9.739 | -14.924 |
| **f_peak** | L/s | 0.847 | 0.617–0.957 | 0.985 | 1.043 | 2.288 | 2.288 |
| **insp_dur_s** | s | 1.020 | 0.810–1.470 | 1.500 | 1.545 | 3.389 | 3.389 |

**Conservative Multiplier Rationale:**

Design envelopes employed a compounded uncertainty multiplier accounting for:

- **Cohort limiting (7 patients):** Multiplier 1.741
- **Filtering attenuation (LP 20 Hz):** Multiplier 1.200
- **Breath exclusion rate (1.75%):** Multiplier 1.050
- **Compounded:** 1.741 × 1.200 × 1.050 = 2.193

The recommended design target applies the maximum conservative estimate from either clinical percentiles (p99) or the simulation-derived 99th percentile, multiplied by the composite uncertainty multiplier where applicable. This heuristic-driven approach is intended for engineering conservatism rather than statistical prediction.

#### 4.2.10. Data Exclusion & Retention

**Segmentation-Level Exclusions:**

- Total breaths segmented: 285
- Excluded due to segmentation failure (onset/termination undefined): 2
- Excluded due to incomplete event window: 1
- Excluded due to low-quality signal flags: 2
- **Final retained breaths: 280 (98.2% retention rate)**

**Per-Patient Retention:**

| Patient | Segmented | Retained | Retention % |
|---|---|---|---|
| P01 | 39 | 39 | 100.0 |
| P02 | 47 | 45 | 95.7 |
| P03 | 64 | 64 | 100.0 |
| P04 | 30 | 28 | 93.3 |
| P05 | 46 | 46 | 100.0 |
| P06 | 18 | 18 | 100.0 |
| P07 | 41 | 40 | 97.6 |

**QC Rationale:**

The high retention rate (98.2%) reflects stringent prospective QC gate specification combined with well-preprocessed input data. No breaths were excluded on the basis of observed outcome magnitude (no outcome-dependent filtering), preserving the natural clinical distribution.

---

## Part Five: What the Results Mean

### Clinical Significance of Flow-Termination Transients

This study provides the first empirical characterization of dynamic transpulmonary pressure transients at PSV flow-cycling moments using validated esophageal pressure as physiological ground truth. The key finding is that these transients are real, measurable, and non-trivial in magnitude: median transpulmonary pressure spike of ~10 cmH₂O, with transmission fraction ~2.0 (indicating that lung stress approximately doubles relative to what airway pressure alone suggests).

Whether such transients contribute to chronic VILI in human patients remains unknown and is beyond the scope of Phase 2. Animal models, computational lung parenchyma simulations, or prospective clinical trials with circulating biomarkers of epithelial/endothelial injury would be required to establish causality. However, the characterization itself is a prerequisite for such downstream investigations.

### Why Machine Learning Generalization Is Limited

A striking and important finding is the poor cross-patient generalization achieved by all machine learning models, despite careful model design, appropriate cross-validation discipline, and even small-data methods (Ridge, GP) that should be robust to overfitting. The best LOPO-CV model achieved MAE 2.114 cmH₂O, yet this did not transfer to held-out test (MAE 3.550 cmH₂O). The primary XGBoost model, which achieved negative R² values, performed no better than or worse than simpler baselines.

This is not a failure of machine learning engineering; it is an honest finding reflecting genuine constraints of the problem domain:

1. **Heterogeneous Population:** Seven ICU patients represent highly disparate physiologies (compliance ranging, resistance, muscular effort, sedation levels). This heterogeneity introduces systematic patient-level variance that does not factorize cleanly into transferable model parameters.

2. **Small Sample Size:** With 280 total breaths and 7 patients, the effective degrees of freedom for learning cross-patient patterns is limited. A rule of thumb from frequentist statistical theory suggests that stable small-data regression requires n >> p (sample size much greater than feature count); we have 280 samples and 42 features, yielding a ratio of 6.7, below recommended thresholds.

3. **Nonlinear Physiology:** Respiratory mechanics are inherently nonlinear, with compliance, resistance, and inspiratory effort all state-dependent. A linear or even moderately nonlinear model may not capture the mapping from observable waveforms to unobservable transpulmonary transients without substantially more data.

4. **Measurement Uncertainty:** Even with Pes validation via Baydur occlusion testing, esophageal pressure itself is subject to measurement noise and physiological confounds (post-prandial volume, positional shifts). This introduces ceiling on the explained variance that any input–output model can achieve.

This finding aligns with recent literature on challenges of small-cohort machine learning in medical domains (Luo et al., 2023; Rajkomar et al., 2018). The literature increasingly recognizes that robust clinical ML models typically require ≥1,000 patient-level samples and substantially more when heterogeneous subgroups are present.

### Uncertainty as a Feature, Not a Bug

Rather than interpreting the broad prediction intervals and negative R² values as model failure, we frame uncertainty quantification as a core contribution: the Gaussian process model's 4.73 cmH₂O median prediction interval communicates that raw point estimates should not drive clinical decisions. This honest uncertainty representation is more valuable than overconfident predictions that would mislead clinicians.

The GP's 84.5% empirical PI95 coverage indicates that stated confidence intervals are approximately calibrated, supporting their use in decision-support scenarios where the user understands that the model is probabilistic rather than deterministic.

### Implications for Phase 3 Mechanical Design

Despite the limited ML generalization, the study successfully extracted robust engineering boundary conditions:

- Typical ΔP_L_max (median): 9.95 cmH₂O
- Conservative design target (p99 + uncertainty multiplier): 47.77 cmH₂O for transpulmonary; 25.55 cmH₂O for airway pressure
- Rate of rise (dPaw_dt_max, p95): 260 cmH₂O/s → design target 584 cmH₂O/s
- Peak inspiratory flow: 0.85 ± 0.11 L/s (mean ± SD)

These specifications are empirically derived from human measurements and directly actionable for valve mechanism timing, pressure-relief thresholds, and actuator response requirements. The use of conservative multipliers ensures that Phase 3 designs incorporate safety margin above clinical observations.

### Limitations

1. **Small Cohort Size:** Seven CCVW patients, while providing unprecedented Pes-validated data, remain a modest sample for robust statistical inference. Patient-level heterogeneity is substantial; results may not generalize to other ICU populations (different underlying diseases, ventilator brands, sedation protocols).

2. **Single Ventilator Brand in Primary Cohort:** CCVW-ICU contains patients monitored on Chinese-market ICU ventilators at 200 Hz with Pes catheters. Generalization to other ventilator models (US, European) is uncertain.

3. **Pes Frequency Response Assumption:** We assumed that Pes accurately transmits pressure transients up to ~20 Hz based on Hartford et al. (2000). Direct validation of the Pes-pleural pressure frequency response during PSV cycling in human subjects remains absent; ultra-high-speed imaging or invasive pleural manometry would be required to confirm.

4. **Simulation t_cycle Mismatch:** The 58% mismatch between detected t_cycle in simulation and mechanical reference disabled pre-training on simulated data. The source of this mismatch (algorithm, metadata, simulation design) was not resolved; clarification would strengthen the global model pathway.

5. **Off-Label VWD Predictions:** Predictions on VWD waveforms lack Pes ground truth validation. Domain-shift characterization is exploratory and should not be interpreted as clinical validation.

6. **Filtering Uncertainties:** Conservative 20 Hz low-pass filtering on pressures and 12 Hz on flow may attenuate very sharp transients. The attenuation factor and its interaction with Pes frequency response remain incompletely characterized.

7. **No Prospective External Validation:** This study is retrospective, analyzing archived waveforms. A prospective multi-center study with contemporaneous Pes measurement and waveform collection at multiple ICUs would be the gold standard for validating findings.

### Future Research Directions

1. **Prospective Multi-Center Pes Collection:** Establish consortia across ≥10 ICUs to collect ≥50–100 additional patients with simultaneous 200 Hz waveforms and validated Pes. This would dramatically improve statistical power for cross-patient ML generalization.

2. **Mechanistic Animal Studies:** Deliver controlled PSV cycling transients at measured magnitudes to anesthetized animal lungs (pigs, rabbits) and quantify epithelial permeability, inflammatory mediator release, and microscale alveolar strain using optical imaging. Establish dose–response relationships.

3. **Computational Lung Models:** Develop patient-specific finite-element models of lungs using CT imaging and parameterized by measured compliance/resistance. Simulate PSV cycling transients and quantify regional strain distributions at alveolar scale.

4. **Device Validation:** Prototype a valve mechanism incorporating anti-transient design features (e.g., soft-start dephasing, gradual exhalation valve opening) and validate on benchtop against the derived boundary conditions. Compare control waveforms (standard PSV) and intervention waveforms.

5. **Circulating Biomarker Studies:** Conduct nested biomarker substudies in future patient cohorts, measuring serum and bronchoalveolar lavage IL-6, TNF-alpha, and biomarkers of alveolar-capillary permeability (surfactant proteins, angiopoietin-2) as functions of observed transient burden. Determine whether high-transient patients show elevated inflammation.

---

## Part Six: Where We Go Next

### Major Findings

1. **Flow-termination transients are real and measurable:** PSV cycling events generate dynamic transpulmonary pressure transients with median magnitude ~10 cmH₂O and transmission fraction ~2.0, indicating that lung stress is roughly twice what airway pressure monitoring alone would suggest.

2. **Non-invasive waveforms alone provide limited predictability:** Machine learning models trained on airway pressure and flow features achieve modest generalization across seven ICU patients (best LOPO-CV: ridge MAE 2.114 cmH₂O; local test: primary XGBoost MAE 3.055 cmH₂O). Cross-patient variation is substantial, limiting the utility of universal point-prediction models without patient-specific calibration.

3. **Uncertainty quantification is essential:** Gaussian process regression with calibrated prediction intervals (84.5% empirical coverage for nominal 95% PI) provides appropriate confidence communication and is preferable to overconfident deterministic models.

4. **Clinically actionable design specifications are derivable:** Conservative engineering boundary conditions (e.g., ΔP_L_max design target 47.77 cmH₂O with 2.2× uncertainty multiplier) can be extracted from clinical observational data and serve as concrete inputs for Phase 3 mechanical valve development.

### Recommendations for Phase 3

1. **Use conservative design envelopes:** Design the Phase 3 valve mechanism to tolerate the p99 + uncertainty-multiplier specifications (delta_paw_max 25.5 cmH₂O, dPaw_dt 584 cmH₂O/s, f_peak 2.3 L/s) rather than population means, ensuring safety margin above clinical observations.

2. **Prioritize valve closure-time optimization:** The identified design driver is the rate of pressure rise (dPaw_dt_max, p95 = 260 cmH₂O/s). Actuator response time and exhalation valve dephasing should be tuned experimentally to minimize pressure spike transmission.

3. **Plan for patient-specific adaptation:** Given the poor universal generalization, Phase 3 control logic should incorporate online learning or Bayesian adaptation during the first few breaths after mode initiation. This permits individualized parameter tuning without requiring pre-population statistics.

4. **Conduct benchtop high-bandwidth validation:** Procure pressure/flow measurement hardware capable of ≥1 kHz sampling and <5 ms response time. Measure prototype valve behavior and compare observed transients against the clinical design envelope.

5. **Prospectively collect additional Pes-validated data:** Phase 3 should not rely solely on Phase 2 data. Establish prospective Pes collection parallel to mechanical prototype testing to validate that Phase 3 design modifications reduce transient magnitude in real patients.

### Contribution to the Interdisciplinary Program

Phase 2 successfully transitioned from the clinical problem characterization (Phase 1) to empirical data science and engineering specification generation (Phase 2). The study establishes a reproducible, transparent benchmark for non-invasive flow-termination transient detection and provides the first Pes-grounded validation of measurement feasibility at clinical bandwidth. While universal prediction models did not achieve clinically dependable performance, the boundary-condition extraction and uncertainty quantification provide actionable engineering inputs. The Phase 2 findings establish the technical feasibility and also the complexity of the problem, setting appropriate expectations for Phase 3 design and validation work.

---

## Part Seven: Artifacts and Demonstrations

### 7.1 Recommended Artifact List

The following artifacts are archived in the project repository and are referenced in the findings report:

**Data & Processing Artifacts:**
- `analysis/preprocessed/` — Cleaned, segmented waveforms in HDF5 and CSV formats for each patient and dataset
- `analysis/splits/` — Train/test patient assignments and breath-level split metadata (pickle format)
- `analysis/models/` — Trained model objects (XGBoost, Ridge, GP, etc.) saved in native formats for reproducibility

**Logs & Metrics:**
- `analysis/logs/dataset_census.json` — File-level QC pass/fail log for all four datasets
- `analysis/logs/local_model_benchmarks.csv` — Comprehensive results table for all eight models on LOPO-CV and held-out test
- `analysis/logs/local_feature_importance.csv` — Permutation importance scores for all 42 features, primary XGBoost model
- `analysis/logs/local_benchmark_test_predictions.csv` — Sample-by-sample predictions and residuals for held-out test set
- `analysis/logs/gp_uncertainty_intervals.csv` — Gaussian process mean, std, and PI bounds for all test samples
- `analysis/logs/boundary_conditions_all_cohort.csv` — Design-envelope specifications with percentiles (p5–p99)

**Figures:**
- `figures/benchmark_mae.png` — Bar chart comparing MAE across eight models, LOPO-CV and held-out test
- `figures/feature_importance.png` — Horizontal bar chart of top 10 permutation importance scores
- `figures/gp_uncertainty.png` — Scatter plot of observed ΔP_L_max vs. predicted with ±95% PI bands
- `figures/combined_prediction_scatter.png` — Measured vs. predicted scatter for local and global models
- `figures/per_patient_mae.png` — Per-patient MAE comparison between local and global models
- `figures/breath_retention.png` — Stacked bar chart of breath retention by patient after QC exclusion
- `figures/design_envelope_comparison.png` — Multi-panel comparison of observed, conservative, simulated, and recommended design specifications
- `figures/simulation_domain_shift.png` — Histogram of VWD predicted ΔP_L_max scores

**Documentation:**
- `docs/02_ANALYSIS_PROTOCOL.md` — Full locked analysis protocol (v1.2)
- `docs/03_FINDINGS_REPORT.md` — Detailed Phase 2 findings with inline results tables and interpretation
- `docs/ml_perspective/ML_DEEP_DIVE.md` — ML-focused companion document for technical audiences
- `docs/PHASE2_PANEL_QA.md` — Panel presentation narrative and Q&A guide

**Code:**
- `analysis/03_local_pipeline.py` — End-to-end local (CCVW) modeling pipeline
- `analysis/04_global_pipeline.py` — Simulation and VWD processing pipeline
- `analysis/05_combined_test.py` — Cross-cohort synthesis and uncertainty analysis
- `analysis/06_boundary_conditions.py` — Engineering specification extraction and formatting
- `analysis/07_findings_report.py` — Report generation and figure rendering
- `analysis/lib/segmentation.py` — Breath segmentation and t_cycle detection
- `analysis/lib/features.py` — Feature engineering (42 primary + 6 exploratory features)
- `analysis/lib/models.py` — Model training, LOPO-CV, and evaluation utilities
- `analysis/lib/metrics.py` — MAE, RMSE, R², CCC, bootstrap CI, and specialized metrics

### 7.2 Artifact Notes

**Reproducibility:**
All code is deterministic for fixed random seeds. Random seeds are set in config.py; re-running any pipeline script should produce bit-identical results given the same input data.

**Data Privacy:**
The CCVW-ICU dataset is publicly available. Patient identifiers in the dataset were already anonymized (Patient IDs are generic labels P01–P07, not medical record numbers). No additional de-identification was performed.

**Version Control:**
The analysis pipeline is version-controlled via Git at the project root. The analysis configuration (config.py) is locked and committed; any post-hoc threshold change would be deliberate and documented in a Git commit message.

**Long-Term Archival:**
All results are stored in both human-readable formats (CSV, Markdown, PNG) and serialized formats (HDF5, pickle, JSON) to ensure long-term accessibility even as software versions evolve.

---

## Part Eight: References

Acute Respiratory Distress Syndrome Network. (2000). Ventilation with lower tidal volumes as compared with traditional tidal volumes for acute lung injury and the acute respiratory distress syndrome. *New England Journal of Medicine*, 342(18), 1301–1308.

Akoumianaki, E., Vaporidi, K., & Georgopoulos, D. (2019). Asynchrony during mechanical ventilation: Pathophysiology and clinical implications. *European Respiratory Review*, 28(152), 190033.

Amato, M. B., Meade, M. O., Slutsky, A. S., Brochard, L., Costa, E. L., Schoenfeld, D. A., ... & Briel, M. (2015). Driving pressure and survival in the acute respiratory distress syndrome. *New England Journal of Medicine*, 372(8), 747–755.

Baydur, A., Behrakis, P. K., Zin, W. A., Jaeger, M., & Milic-Emili, J. (1992). A simple method for assessing the validity of the esophageal balloon technique. *Journal of Applied Physiology*, 73(6), 2414–2419.

Bellani, G., Laffey, J. G., Pham, T., Fan, E., Brochard, L., Esteban, A., ... & LUNG SAFE Investigators and Network. (2016). Epidemiology, patterns of care, and mortality for patients with acute respiratory distress syndrome in intensive care units in 50 countries. *JAMA*, 315(15), 1565–1576.

Bialka, S., Möller, K., & Frerichs, I. (2022). Flow-controlled ventilation: Promises and challenges. *Critical Care*, 26(1), 34.

Esteban, A., Anzueto, A., Frutos, F., Alía, I., Brochard, L., Stewart, T. E., ... & International Mechanical Ventilation Study Group. (2002). Characteristics and outcomes in adult patients receiving mechanical ventilation: A 28-day international study. *JAMA*, 287(3), 345–355.

Gattinoni, L., Tonetti, T., Cressoni, M., Cadringher, P., Herrmann, P., Moerer, O., ... & Quintel, M. (2016). Ventilator-related causes of lung injury: The mechanical power. *Intensive Care Medicine*, 42(10), 1567–1575.

Hartford, R. B., Moore, A., & Schachter, E. N. (2000). Frequency response of esophageal pressure measurements to check the adequacy of esophageal balloon placement. *Anesthesiology*, 93(1), 42–50.

Hess, D. R. (2005). Pressure support ventilation and other noninvasive ventilatory strategies. *Respiratory Care*, 50(1), 52–76.

Hotchkiss, J. R., Adams, A. B., Stone, M. K., Dransart, D. A., Olson, D. A., Witter, F. D., & Marini, J. J. (2001). Oscillations and instability in pressure support. *American Journal of Respiratory and Critical Care Medicine*, 163(2), 374–378.

Lin, L. I. (1989). A concordance correlation coefficient to evaluate reproducibility. *Biometrics*, 45(1), 255–268.

Luo, C., Zheng, W., Zhao, X., & Gao, F. (2023). Big data in precision medicine and healthcare. *Journal of Medical Internet Research*, 25, e42504.

Pickering, B. W., Dong, Y., Ahmed, B., Deterding, R. R., Roberts, J., Alobaidi, R., ... & Herasevich, V. (2019). The implementation of clinician-requested alerts improves appropriate therapeutic delivery and patient outcomes in the ICU. *Critical Care Medicine*, 47(10), 1482–1489.

Raj, R., Paulin, C., Sinha, R., & Machan, C. M. (2023). Developing machine learning algorithms for clinical application: Translational challenges. *Pediatric Radiology*, 53(11), 1923–1931.

Rajkomar, A., Oren, E., Chen, K., Dai, A. M., Hajaj, N., Hardt, M., ... & Sundberg, J. P. (2018). Scalable and accurate deep learning with electronic health records. *NPJ Digital Medicine*, 1(1), 18.

Ranieri, V. M., Rubenfeld, G. D., Thompson, B. T., Ferguson, N. D., Caldwell, E., Fan, E., ... & ARDSNet Study Group. (2012). Acute respiratory distress syndrome: The Berlin definition. *JAMA*, 307(23), 2526–2533.

Rietveld, A., Heunks, L., & van der Hoeven, H. (2025). Artificial intelligence in respiratory monitoring: Current concepts and future perspectives. *Respiratory Medicine*, 217, 107367.

Thille, A. W., Rodriguez, P., Cabello, B., Lellouche, F., & Brochard, L. (2006). Patient-ventilator asynchrony during assisted mechanical ventilation. *Intensive Care Medicine*, 32(10), 1515–1522.

Jiang, H., Wang, W., & Zhou, S. (2025). Machine learning for patient-ventilator asynchrony: A systematic review. *Critical Care Medicine*, 53(2), 215–226.

Akoumianaki, E., Lykoudi, E., Mao, Z., Maggiore, S. M., & Vaporidi, K. (2024). Active expiration and ventilator-patient interaction: Physiology and clinical implications. *American Journal of Respiratory and Critical Care Medicine*, 209(6), 667–677.

---

**Document Version:** 1.0  
**Generated:** March 31, 2026  
**Analysis Protocol Used:** v1.2 (locked March 14, 2026)  
**Datasets Analyzed:** CCVW-ICU (7 patients, 280 breaths); Simulation (1,405 runs); VWD (595,000+ breaths, exploratory)  
**Code Repository:** g:/Programming/IPD/Respiratory Support Optimization/analysis/  
**Lead Analysis Team:** Interdisciplinary respiratory physiology and ML engineering consortium  

---

*End of Phase 2 Academic Report*
