# Phase 3 Mechanical Design - Safety-Gated Redesign

> **Author working note:** I rewrote this after we invalidated the earlier "final" claims, so the tone is intentionally explicit about what is verified versus what is still provisional.
>
> **How I use this doc:** It is my checklist-backed baseline for deciding what can move forward and what stays blocked.

Document Version: 4.0
Date: March 19, 2026
Status: Active Redesign - Not approved for prototyping or clinical use

Parent Documents:
- 01_MEDICAL_PROBLEM_STATEMENT.md
- 02_ANALYSIS_PROTOCOL.md
- 03_FINDINGS_REPORT.md

---

## Executive Summary

This document replaces the previous "final" Phase 3 report.

The previous design baseline is rejected for safety and engineering reasons, including:
- Non-manufacturable poppet spring-seat geometry
- Incorrect flow-area sizing math in the design narrative
- Overstated spring and actuator force requirements
- Incomplete safety architecture and standards mapping

The current objective is a data-anchored adaptive concept with explicit safety gates and staged verification. No claim of human safety is made in this phase.

---

## 1. Design Reset Principles

1. Patient heterogeneity from Phase 2 is accepted as a hard requirement.
2. Fixed one-size-fits-all opening profiles are treated as a legacy baseline only.
3. Mechanical geometry must be manufacturable before simulation claims are accepted.
4. Safety controls are designed first, not appended later.
5. Every quantitative claim must include equations, units, and source assumptions.

---

## 2. Corrected Engineering Baseline

### 2.1 Flow-area sizing correction

Using:

Q = C_d * A * sqrt(2 * DeltaP / rho)

with:
- Q = 2.29e-3 m^3/s
- C_d = 0.7
- DeltaP = 196 Pa (2 cmH2O)
- rho = 1.2 kg/m^3

A = 1.81e-4 m^2 = 181 mm^2

Equivalent bore diameter:

d = sqrt(4A/pi) = 15.2 mm

Design baseline is updated to a 16 mm bore for tolerance and margin.

### 2.2 Closing force correction

With seat diameter aligned to the new bore, pressure-only opening force at 25 cmH2O is approximately 0.49 N. A 2x safety factor sets a closed-force target near 1.0 N, not 7.0 N.

### 2.3 Manufacturability correction

The poppet spring seat is moved from a stem-only shoulder to a dedicated flange seat in the redesign path. A spring seat larger than stem OD is not accepted in the new baseline.

### 2.4 Dynamic sealing correction

Legacy O-ring stretch concerns are removed from the redesign baseline by moving toward a low-friction dynamic seal architecture (PTFE/U-cup class) with catalog-backed gland geometry.

### 2.5 Spring force and actuator margin (implemented baseline)

Current CAD-derived spring metrics from `analysis/valve_export/valve_metadata.json`:

- Spring rate: 0.334 N/mm
- Installed length at closed: 3.80 mm
- Closed spring force: 1.003 N
- Open spring force (full lift): approximately 0.0 N
- Target closed force: 1.0 N

Interpretation:
- Closed-force target is met within 0.003 N.
- The current baseline is intentionally light at full-open to reduce re-closing bias and actuator burden.
- Additional dynamic margin checks with flow-force coupling remain required in CFD/lumped co-simulation.

### 2.6 Relief valve sizing correction (implemented baseline)

Relief sizing uses the orifice relation for flow target 2.29 L/s across 30 to 35 cmH2O:

- Required area: 114.44 mm^2
- Required equivalent diameter: 12.07 mm
- Configured seat diameter: 12.10 mm

Interpretation:
- Geometry now matches orifice-based first-order sizing.
- Dynamic opening response and spring preload behavior still require transient validation.

Relief transient check snapshot (`analysis/logs/phase3_relief_transient_summary.json`):
- Nominal baseline (mass 2.0 g, damping 0.08 N*s/m, spring 120 N/m, preload 0.35 N) fails both gates:
	- Response-time pass: false
	- Flow-capacity pass: false
	- Peak flow: 0.50 L/s vs 2.29 L/s target
- Unconstrained best candidate remains aggressive and non-feasible (`best_unconstrained`):
	- mass 0.8 g, damping 0.03 N*s/m, spring 40 N/m, preload 0.05 N
	- Response-time pass: true
	- Flow-capacity pass: true
	- Reaches target flow in approximately 4.0 ms
- Hardware-feasible-envelope candidate search (`best_hardware_feasible`) now also finds a passing simulation candidate:
	- mass 1.5 g, damping 0.08 N*s/m, spring 80 N/m, preload 0.20 N
	- Response-time pass: true
	- Flow-capacity pass: true
	- Reaches target flow in approximately 8.7 ms

Interpretation update:
- Transient feasibility is now demonstrated in simulation for both unconstrained and hardware-feasible-envelope candidates.
- The hardware-feasible envelope is still a screening proxy, not supplier-qualified hardware evidence.
- Hardware gate remains open until candidate bounds are tied to supplier catalog components, tolerance stacks, and bench-transient evidence.

### 2.7 Dynamic seal placeholder update

Legacy O-ring geometry has been replaced by a PTFE-style seal placeholder (`PTFE_Seal_Placeholder`) and matching gland parameters in CAD metadata.

Interpretation:
- This is a gland-layout placeholder, not a finalized catalog-qualified seal release.
- Final seal selection still requires supplier-specific gland tolerance and friction qualification.

### 2.8 Dual-path concept branch (research exploration)

A separate concept branch now explores a dual-path architecture where:
- Path A is the existing active central poppet modulation path.
- Path B is a passive annular bypass path with a compliant fuse ring intended to vent if differential pressure exceeds a configured threshold.

Reference artifact:
- `analysis/phase3_cadquery_valve_dualpath_concept.py`

Interpretation:
- This branch is exploratory and does not change the hardware gate status.
- Any claimed benefit requires the same closure evidence path: supplier freeze, bench timing/flow validation, and independent review.

---

## 3. Adaptive Control Concept (Phase 3A)

Because cross-patient ML generalization remains limited, immediate adaptation is rule-based and bounded.

Candidate real-time features from Phase 2:
- paw_base
- delta_paw_max_prev_breath
- insp_dur_s
- flow_decel_slope
- f_peak

Controller output:
- valve opening time command in a clamped safety window (20-100 ms)
- optional adaptive ETS correction in a bounded range (0.15-0.35)

This layer is not a deployable clinical controller. It is a simulation controller for feasibility testing.

---

## 4. Safety Architecture Baseline (Phase 3B)

Minimum safety architecture for further development:
- Normally-open mechanical fail-safe
- Dual watchdog strategy (MCU watchdog + external hardware watchdog)
- Redundant position sensing (dual Hall channels)
- Upstream/downstream pressure monitoring for valve-fault detection
- Mechanical end-stop verification
- Independently sized over-pressure relief path

Any build plan requires risk controls mapped to ISO 14971 and traceability to verification tests.

### 4.2 Fault-response timing snapshot (2026-03-19)

Source: `analysis/logs/phase3_safety_fault_summary.json` from `analysis/10_phase3_safety_fault_injection.py`.

Baseline control assumptions currently fail full timing gate:
- Watchdog cutoff: 9.0 ms (pass)
- Sensor disagreement latch: 11.3 ms (fail)
- Pressure fault latch: 16.0 ms (fail)

Bounded candidate search demonstrates timing-feasible settings in software simulation:
- Watchdog cutoff: 6.5 ms (pass)
- Sensor disagreement latch: 8.3 ms (pass)
- Pressure fault latch: 9.3 ms (pass)

Interpretation:
- Safety timing feasibility is now demonstrated for all three fault paths in bounded simulation.
- Baseline settings remain insufficient, and hardware timing verification is still mandatory before any gate change.

### 4.1 Quantitative FMEA Draft (working)

| Hazard | Severity (1-5) | Occurrence (1-5) | Detection (1-5) | Initial RPN | Primary Controls | Verification Gate |
|---|---:|---:|---:|---:|---|---|
| Valve fails closed during inspiration | 5 | 2 | 3 | 30 | Normally-open default, dual watchdog, pressure-delta monitor | Fault injection: watchdog trip <= 10 ms |
| Position sensing disagreement/drift | 4 | 3 | 3 | 36 | Dual Hall channels, disagreement threshold, end-stop checks | Sensor-fault simulation and injected bias tests |
| Relief path under-capacity | 5 | 2 | 4 | 40 | Relief seat sized by orifice baseline, independent relief path | Flow bench / transient CFD at over-pressure condition |
| Seal friction rise / leakage | 4 | 3 | 3 | 36 | PTFE-style seal architecture, gland tolerance control | Friction/leak endurance test plan |
| Controller timing miscommand | 4 | 3 | 2 | 24 | Bounded command window (20-100 ms), clamp + logging | Software unit tests + timing trace audit |

RPN thresholds for redesign gates (working):
- RPN > 35: must have implemented and verified mitigation before hardware gate.
- RPN 25-35: mitigation implemented and verification plan approved.
- RPN < 25: monitor with routine verification evidence.

---

## 5. Validation Pipeline (Phase 3C)

1. Dynamic lumped simulation against all 7 Phase 2 patients.
2. Transient CFD with moving lift profile (not steady-only).
3. FEA focused on impact/fatigue as well as static pressure.
4. Hardware-in-the-loop on a lung simulator before any in-vivo planning.
5. Animal work only after simulation and HIL success criteria are met.

Primary quantitative simulation target:
- DeltaPaw <= 5.0 cmH2O for at least 90% of breaths per patient cohort with no net asynchrony worsening.

### 5.1 Current Simulation Snapshot (2026-03-19)

Source: `analysis/logs/phase3_adaptive_rule_summary.json` from `analysis/08_phase3_adaptive_rule_sim.py`.

- Cohort breaths evaluated: 280 (P01-P07)
- Baseline DeltaPaw mean: 6.34 cmH2O
- Adaptive DeltaPaw mean: 3.31 cmH2O
- Baseline DeltaPaw p95: 11.36 cmH2O
- Adaptive DeltaPaw p95: 3.68 cmH2O
- Pass rate for DeltaPaw <= 5.0 cmH2O: 100.0% (current concept surrogate run)

Gate status:
- Simulation gate met for the current bounded surrogate configuration (target >= 90%).
- Clinical/hardware gate remains open pending robustness checks, external validation, and dynamic plant-coupled verification.

Tuning status:
- Bounded grid search added and executed.
- Bounded assist-policy escalation added and executed.
- Added severity-cluster strategy escalation layer with bounded floor and gain limits.
- Current selected strategy reaches the pass-rate target in this surrogate framework.
- Conclusion: target is reachable in-silico, but control robustness is not yet proven for deployment conditions.

### 5.2 Robustness Stress Snapshot (2026-03-20)

Source: `analysis/logs/phase3_adaptive_robustness_summary.json` from `analysis/11_phase3_adaptive_robustness_check.py`.

Scenario pass rates for DeltaPaw <= 5.0 cmH2O:
- nominal_replay: 100.0%
- sensor_noise_light: 100.0%
- sensor_noise_moderate: 100.0%
- timing_jitter_moderate: 100.0%
- actuator_lag_moderate: 100.0%
- combined_moderate: 100.0%
- combined_severe: 99.6%

Working robustness gate definition:
- Minimum pass-rate across moderate scenarios >= 90%
- Combined severe pass-rate >= 80%

Observed robustness result:
- moderate_min_pass_rate: 100.0% (pass)
- combined_severe_pass_rate: 99.6% (pass)
- robustness_gate_met: true

Interpretation:
- The adaptive strategy can hit the cohort surrogate target under nominal replay.
- Current perturbation stress gate is met under the defined bounded scenarios.
- High-burden sensitivity is reduced in this scenario model (worst case remains P05 in combined_severe), but evidence is still simulation-limited.
- Hardware gate remains closed until plant-coupled and external validation contexts are completed.

### 5.3 Plant-Coupled Snapshot (2026-03-20)

Source: `analysis/logs/phase3_plant_coupled_adaptive_summary.json` from `analysis/12_phase3_adaptive_plant_coupled_check.py --output-tag adaptive`.

Plant-coupled scenario pass rates for DeltaPaw <= 5.0 cmH2O:
- plant_nominal: 100.0%
- plant_moderate: 76.1%
- plant_severe: 52.9%

Working plant-coupled gate definition:
- plant_moderate pass-rate >= 90%
- plant_severe pass-rate >= 80%

Observed plant-coupled result:
- plant_moderate_pass_rate: 76.1% (fail)
- plant_severe_pass_rate: 52.9% (fail)
- plant_moderate_min_patient_pass_rate: 0.0% (fail)
- plant_severe_min_patient_pass_rate: 0.0% (fail)
- plant_coupled_gate_met: false
- Worst-case patient/scenario: P01 under plant_severe (pass-rate 0.0%, dpaw_p95 6.85 cmH2O)

Interpretation:
- Plant-aware retuning improved moderate-case pass rate but still fails plant gate thresholds.
- Task 1 remains open for hardware gating and must be reworked against dynamic actuator/latency behavior.
- External replay remains pending because current combined predictions include CCVW-only rows.

### 5.4 Model-Based Benchmark Snapshot (2026-03-20)

Source scripts:
- `analysis/13_phase3_model_based_controller_eval.py`
- `analysis/12_phase3_adaptive_plant_coupled_check.py --input analysis/logs/phase3_model_based_predictions.csv --target-column delta_paw_model_based`

Benchmark intent:
- Evaluate a delay-compensated, model-based control mapping as an alternative to the current rule-plus-guard policy.

Plant-coupled benchmark result:
- plant_nominal_pass_rate: 100.0%
- plant_moderate_pass_rate: 92.5% (pass)
- plant_severe_pass_rate: 58.9% (fail)
- plant_coupled_gate_met: false

Interpretation:
- A model-based delay compensation improves moderate plant-coupled behavior compared with the current active policy.
- Severe plant-coupled behavior remains unacceptable; the core blocker is reduced but not removed.
- This benchmark is simulation-only and is not sufficient for hardware gate transition.

### 5.5 Plant-Aware Benchmark Snapshot (2026-03-20)

Source scripts:
- `analysis/14_phase3_plant_aware_controller_eval.py`
- `analysis/12_phase3_adaptive_plant_coupled_check.py --input analysis/logs/phase3_plant_aware_predictions.csv --target-column delta_paw_plant_aware --output-tag plant_aware`

Source artifact:
- `analysis/logs/phase3_plant_coupled_plant_aware_summary.json`

Benchmark intent:
- Evaluate a plant-aware strategy that jointly tunes opening-time commands and delay-compensated target pressures.

Plant-coupled benchmark result (aggregate):
- plant_nominal_pass_rate: 100.0%
- plant_moderate_pass_rate: 100.0% (pass)
- plant_severe_pass_rate: 99.6% (pass)
- plant_coupled_gate_met_aggregate: true

Patient-level result:
- Worst-case patient/scenario: P05 under plant_severe pass-rate 97.8% and dpaw_p95 4.89 cmH2O.
- patient_level_gate_met (moderate >=90% and severe >=80% for every patient): true
- strict_gate_met (aggregate and patient-level): true

Interpretation:
- Script 14 now uses a lexicographic max-min objective and found a strict-gate-feasible candidate in the focused search (`search_outcome = feasible_patient_level_gate`).
- This remains surrogate-level evidence on a small cohort and does not close hardware-gate requirements without external replay, HIL corroboration, and unresolved mechanical risk closure.

### 5.6 Hardware Transition Gate Snapshot (2026-03-20)

Source script:
- `analysis/15_phase3_hardware_gate_check.py`

Source artifacts:
- `analysis/logs/phase3_hardware_gate_summary.json`
- `analysis/logs/phase3_hardware_evidence_status.json`

Current gate outcome:
- `hardware_prototyping_gate.pass`: false

Current blocker set:
- `safety_timing_not_hardware_verified`
- `process_evidence_missing:relief_supplier_components_frozen`
- `process_evidence_missing:relief_bench_transient_verified`
- `process_evidence_missing:cad_release_ready`
- `process_evidence_missing:seal_supplier_qualified`
- `process_evidence_missing:actuator_characterized`
- `process_evidence_missing:external_dataset_validation_complete`
- `process_evidence_missing:iso14971_file_complete`
- `process_evidence_missing:iec60601_1_prelim_complete`
- `process_evidence_missing:independent_review_signed`

Interpretation:
- Controller and relief simulation gates can pass while hardware gate remains closed.
- Hardware gate transition is blocked until hardware/process evidence flags are explicitly satisfied.

### 5.7 External Domain-Shift Snapshot (2026-03-20)

Source script:
- `analysis/16_phase3_external_domain_shift_check.py`

Source artifacts:
- `analysis/logs/phase3_external_domain_shift_per_feature.csv`
- `analysis/logs/phase3_external_domain_shift_summary.json`

Current result:
- Shared Paw/Flow-derived features between reference and external artifacts: 16
- Shift-flagged features: 16
- Shifted-feature fraction: 1.00
- External domain-shift gate: false

Mitigation attempt snapshot (`analysis/17_phase3_external_shift_mitigation.py`):
- Quantile-mapping harmonization plus bounded operating-envelope evaluation was executed.
- Shifted-feature fraction improved from 1.00 to 0.438 (16 -> 7 shifted features), but gate still fails (target <=0.20).
- Mitigated summary artifact: `analysis/logs/phase3_external_domain_shift_mitigated_summary.json`.

Top shifted features (current run):
- ets_defaulted_flag
- flow_rise_time_ms
- paw_base
- insp_dur_s
- delta_paw_max
- ets_frac
- flow_decel_slope
- f_peak

Interpretation:
- External artifact distributions are materially different from the current CCVW reference feature space.
- Current controller simulation success cannot be treated as externally generalized performance.
- External shift mitigation improves but does not close the external gate under current thresholds.
- Hardware transition remains blocked until external-shift mitigation and review are completed.

### 5.8 External Controller Replay Snapshot (2026-03-20)

Source script:
- analysis/18_phase3_external_controller_replay.py

Source artifacts:
- analysis/logs/phase3_external_controller_replay_external_raw_summary.json
- analysis/logs/phase3_external_controller_replay_external_mitigated_summary.json

Raw external replay result (full external artifact):
- plant_moderate_pass_rate: 98.9%
- plant_severe_pass_rate: 64.9%
- plant_moderate_min_patient_pass_rate: 71.3%
- plant_severe_min_patient_pass_rate: 0.4%
- strict external replay gate: false

Mitigated replay result (harmonized sample artifact):
- plant_moderate_pass_rate: 100.0%
- plant_severe_pass_rate: 98.7%
- plant_severe_min_patient_pass_rate: 97.5%
- strict external replay gate: true

Interpretation:
- Raw external replay currently fails severe aggregate and worst-group criteria, confirming major transfer risk.
- Mitigated sample replay demonstrates a possible path but is not sufficient as sole evidence for gate closure.
- Hardware transition remains blocked until external replay review is completed and conservative gate criteria are satisfied.

---

## 6. CAD and Code Status

Current CAD script:
- analysis/phase3_cadquery_valve.py

Current status:
- Parametric concept generator available
- Legacy geometry assumptions still present in parts of the model
- Not a manufacturing release

Near-term CAD objectives:
- 16 mm bore baseline
- Poppet flange spring-seat geometry
- Revised seal gland
- Updated relief path sizing
- Assembly checks tied to explicit closed/open contact conditions

---

## 7. Compliance and Regulatory Workstream

Standards are treated as design inputs, not post-hoc references.

### 7.1 Traceability Matrix (working draft)

| Standard / Clause | Requirement Theme | Design Control | Verification Artifact | Status |
|---|---|---|---|---|
| ISO 80601-2-12 (pressure/flow performance) | Controlled expiratory resistance and pressure behavior | 16 mm bore baseline, adaptive opening-time logic, relief-path redesign target | `analysis/08_phase3_adaptive_rule_sim.py` outputs + CFD transient plan | In progress |
| ISO 80601-2-12 (alarm/fault behavior) | Detect unsafe valve state and timing faults | Dual watchdog concept, dual sensing concept, pressure-delta monitoring concept | To-be-authored fault-injection simulation report | Planned |
| IEC 60601-1 (abnormal operation) | Safe state under single fault | Normally-open mechanical default + independent cutoff pathway | Hardware architecture review checklist (pending) | Planned |
| IEC 60601-1 (temperature/electrical) | Thermal and electrical safety margins | Voice-coil thermal model workstream (not yet finalized) | Thermal lumped model and bench equivalence test plan | In progress |
| ISO 14971 (risk management) | Hazard identification, controls, residual risk acceptance | FMEA/HAZOP expansion with quantitative severity-probability controls | Risk log + control verification matrix (pending) | In progress |

### 7.2 Repository Deliverables Required for Gate Exit

1. Quantitative simulation evidence for DeltaPaw control objective.
2. Fault-response timing evidence for watchdog/sensor disagreement logic.
3. Structured risk table with residual-risk justification per hazard.
4. Configuration-controlled linkage between CAD revision and validation logs.

Risk register baseline artifact:
- `05_PHASE3_RISK_REGISTER.md`

This repository currently records engineering preparation work, not a regulatory submission package.

---

## 8. Task Checklist (Revision Plan)

| Task | Description | Status |
|------|-------------|--------|
| 1 | Adaptive rule-based controller derived from Phase 2 features | Implemented + tuned + escalated; strict plant gate (aggregate + patient-level severe) remains open, and external replay remains pending |
| 2 | Correct flow-area and bore sizing basis | Completed in document baseline |
| 3 | Redesign poppet with manufacturable spring-seat flange | Completed baseline |
| 4 | Simplify and verify assembly/contact positioning | Implemented baseline checks in metadata |
| 5 | Recalculate spring force and actuator margin | Completed baseline (dynamic validation pending) |
| 6 | Replace legacy dynamic O-ring assumption with suitable dynamic seal concept | Implemented placeholder + gland baseline; supplier lock pending |
| 7 | Redesign relief valve path and sizing | First-order sizing completed; transient candidate pass demonstrated; hardware-realistic closure pending |
| 8 | Expand safety architecture and FMEA depth | Draft quantitative FMEA added; risk register baseline added |
| 9 | Define staged validation plan with quantitative gates | Completed in plan; execution pending |
| 10 | Rebuild CAD with manufacturable integrity | In progress |
| 11 | Rewrite Phase 3 report with full traceability | In progress |
| 12 | Independent engineering review sign-off | Pending external reviewer |

---

## 9. Immediate Actions Completed in This Revision

- Removed prior claims that the design is final, safe, or prototype-ready.
- Rebased bore sizing to corrected orifice math in the document baseline.
- Reframed Phase 3 as a staged safety-gated redesign.
- Added a traceable 12-task execution checklist.
- Added initial rule-based adaptive simulation runner: `analysis/08_phase3_adaptive_rule_sim.py`.
- Added CAD metadata checks for closed-seat contact and spring floor-to-floor fit consistency.
- Added standards traceability matrix draft with verification artifact mapping.

---

## 10. Non-Use Statement

This work is research-stage mechanical and control design. It must not be used for clinical decision-making or patient care.

---

End of document.
