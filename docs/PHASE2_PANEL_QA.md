# Phase 2 Project Presentation Guide (Panel + Paper Draft)

> **Author working note:** I put this guide together after several dry runs where the story drifted, so this version reflects the sequence that actually worked in practice.
>
> **Use it like a script backbone:** Keep the structure, but speak naturally and adapt examples to the audience in the room.

This document is a presentation-ready narrative for Phase 2 only, synthesized from:

- `02_ANALYSIS_PROTOCOL.md`
- `03_FINDINGS_REPORT.md`
- `ml_perspective/ML_DEEP_DIVE.md`

---

## 1) Describe the Problem You Worked On

Our Phase 2 project addresses a clinically important and technically difficult question:

**Can we estimate dynamic transpulmonary stress at flow-termination during Pressure Support Ventilation (PSV), using only non-invasive ventilator waveforms?**

Specifically, we study the transient around the ventilator cycling moment (`t_cycle`) and use:

$$
P_L(t) = P_{aw}(t) - P_{es}(t)
$$

as the physiological ground truth (from Pes-enabled data).

Why this is worth exploring:

- Flow-termination behavior in PSV is a known site of patient-ventilator interaction risk.
- Direct physiological signals (Pes) are rarely available in routine care.
- If robustly inferred from Paw + Flow, this could support safer monitoring and future control logic.
- Even negative results are high-value in this setting because they define real limits of generalization in small, heterogeneous ICU cohorts.

In short, this is a translational problem at the interface of physiology, machine learning, and engineering design.

---

## 2) Mention the Tools and Technologies You Used

### Core stack

- **Language:** Python
- **Environment:** local `.venv` in VS Code
- **Development tools:** VS Code, Markdown-based reproducible reporting

### Data and signal processing

- **NumPy / Pandas** for waveform and metadata handling
- **SciPy** for filtering and signal operations (e.g., Butterworth low-pass, derivative-based checks)

### Machine learning and evaluation

- **scikit-learn** for baselines, Ridge, Gaussian Process, cross-validation, and metrics
- **XGBoost** for gradient-boosted regression benchmarks
- **Permutation importance** for interpretability

### Visualization and artifacts

- Matplotlib-style figure outputs embedded in the findings report
- CSV/JSON artifact logging in `analysis/logs/`

---

## 3) Show Your Dataset

Phase 2 used four datasets, each with a clear role:

1. **CCVW-ICU (Chinese clinical waveform dataset)**
- Role: primary physiology-grounded development
- Size: 7 patients (P01-P07), 200 Hz
- Channels: Paw/Pao, Flow, Pes (Baydur-validated Pes)
- Why critical: only dataset here with direct Pes-based ground truth for $\Delta P_L$

2. **Simulation dataset (ARDS PSV runs)**
- Role: global training/stress-testing context
- Size: 1,405 runs
- Used with caution due to known `t_cycle` alignment mismatch constraints

3. **VWD (Puritan-Bennett waveform dataset)**
- Role: external/domain-shift testing context
- Size: 144 waveform files, ~50 Hz
- Limitation: no Pes channel, so not a direct physiological endpoint validator

4. **CPAP dataset**
- Role: context-only (not central for Phase 2 endpoint learning)

### Cleaning and preprocessing highlights

- Required-channel checks and strict QC gates (missingness, monotonic time, sampling-rate tolerance, flatline rejection)
- Conservative low-pass denoising and Hampel outlier filtering
- Breath-level quality flags and exclusion logic
- Deterministic segmentation and cycling-event extraction around `t_cycle`
- Event window definition: `[-150 ms, +350 ms]`

---

## 4) Walk Through Your Code

For screen-sharing, focus on architecture and decision logic rather than line-by-line reading.

### A. Protocol-to-code alignment

Start by showing how analysis was pre-specified before interpretation:

- `docs/02_ANALYSIS_PROTOCOL.md`

Narrative to say:

- We locked segmentation rules, event definitions, thresholds, and metrics first.
- This constrained post-hoc tuning and kept inference disciplined.

### B. Pipeline entry points

Then walk through the Phase 2 execution flow:

- `analysis/00_dataset_analysis.py` (dataset census + QC summaries)
- `analysis/01_preprocess.py` (signal cleaning/standardization)
- `analysis/02_split.py` (patient/run split logic)
- `analysis/03_local_pipeline.py` (Pes-grounded local modeling)
- `analysis/04_global_pipeline.py` (simulation/global context)
- `analysis/05_combined_test.py` (cross-context synthesis)
- `analysis/06_boundary_conditions.py` (engineering boundary extraction)
- `analysis/07_findings_report.py` (report and figure generation)

### C. Library-level technical modules

Point out reusable logic in:

- `analysis/lib/features.py` (feature construction)
- `analysis/lib/models.py` (model training/evaluation wrappers)
- `analysis/lib/metrics.py` (MAE, RMSE, R2, CCC, uncertainty summaries)
- `analysis/lib/qc.py` and `analysis/lib/segmentation.py` (signal quality and breath/event logic)

### D. Key technical decisions to explain aloud

- Why Paw + Flow were used as model inputs (generalisability), while Pes remained target-grounding only
- Why LOPO-CV was used (patient-level leakage avoidance)
- Why uncertainty estimation was included (decision support, not deterministic control)
- Why negative findings were retained and reported transparently

---

## 5) Show Your Outputs and Results

Use the generated report and figures:

- Main report: `docs/03_FINDINGS_REPORT.md`
- Figure examples:
  - `docs/figures/benchmark_mae.png`
  - `docs/figures/feature_importance.png`
  - `docs/figures/gp_uncertainty.png`
  - `docs/figures/combined_prediction_scatter.png`

### What to say while presenting outputs

- **Benchmark MAE chart:** compares small-data models; demonstrates that model class choice matters strongly under low-$N$ heterogeneity.
- **Feature importance:** highlights clinically plausible predictors (`paw_base`, `delta_paw_max`, inspiratory timing/deceleration descriptors).
- **GP uncertainty plot:** shows broad predictive intervals; communicates practical uncertainty and caution.
- **Measured vs predicted scatter:** visual summary of fit limitations and spread across local/global contexts.

### Core interpretation

- The pipeline successfully produced reproducible Pes-grounded targets and benchmark comparisons.
- Generalization remained limited in held-out patients, which is a meaningful scientific finding for this domain.
- The work still yields practical engineering value via conservative boundary-condition extraction.

---

## 6) Discuss Your Evaluation Metrics

Phase 2 is regression-first, so key metrics were:

- **MAE** (clinical absolute error scale)
- **RMSE** (penalizes larger misses)
- **$R^2$** (explained variance)
- **CCC** (concordance of agreement)
- For probabilistic models: **predictive std** and **PI coverage**

### Representative reported values (from findings/deep dive)

Local LOPO-CV (XGBoost primary):

- MAE: **5.151**
- RMSE: **5.949**
- $R^2$: **-0.438**
- CCC: **-0.078**
- N: **222**

Held-out local test P06-P07 (XGBoost primary):

- MAE: **3.055**
- RMSE: **3.338**
- $R^2$: **-1.128**
- CCC: **0.015**
- N: **58**

LOPO-CV benchmark highlights:

- Ridge / hierarchical Bayesian: MAE **2.114**, $R^2$ **0.755**, CCC **0.840**
- Gaussian Process: MAE **3.205**, $R^2$ **0.469**, CCC **0.660**

Gaussian Process uncertainty on held-out local test:

- Mean predictive std: **4.196 cmH2O**
- Median predictive std: **4.730 cmH2O**
- Approx. 95% PI coverage: **84.48%**

### Practical interpretation for panel discussion

- Some models fit local structure in cross-validation, but robust held-out generalization remains weak.
- Uncertainty magnitudes are non-trivial; this supports a decision-support framing rather than autonomous control.
- Transparent reporting of these limits strengthens scientific credibility.

---

## 7) Wrap Up

### What Phase 2 achieved

- Built a reproducible Pes-grounded analysis pipeline for PSV flow-termination transients.
- Quantified what can and cannot be inferred from non-invasive Paw + Flow alone in a small ICU cohort.
- Produced interpretable ML diagnostics and uncertainty analysis.
- Delivered engineering-relevant boundary-condition outputs for Phase 3.

### Key takeaways

- Physiological grounding and protocol locking were major strengths.
- Cross-patient generalization is the central unresolved challenge.
- Negative findings were informative and methodologically valuable.

### How this can be extended

- Expand multi-center Pes-enabled cohorts
- Improve label alignment for simulation-to-clinical transfer
- Explore calibrated sequence/deep models only after data scale and alignment improve
- Maintain uncertainty-aware, safety-first deployment framing

---

## Suggested 2-3 Minute Closing Script

"In Phase 2, we set out to estimate a clinically meaningful but hard-to-observe quantity, dynamic transpulmonary stress at PSV flow termination, using non-invasive waveform inputs. We built and audited a fully reproducible pipeline grounded in Pes physiology, compared multiple model families, and quantified uncertainty explicitly. The most important outcome is not just model scores; it is a high-confidence map of current capability limits under realistic small-cohort heterogeneity. That evidence now informs both our Phase 3 engineering constraints and our research agenda for larger, better-aligned datasets."