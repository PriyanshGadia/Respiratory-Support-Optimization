# Phase 3 Safety Architecture (Component-Level Draft)

This architecture maps control logic to testable timing behavior; simulation-only items remain provisional until hardware evidence is linked.

Document Version: 1.0
Date: March 19, 2026
Status: Draft - component-level control definitions for simulation and pre-prototype planning

Linked files:
- 04_PHASE3_MECHANICAL_DESIGN.md
- 05_PHASE3_RISK_REGISTER.md
- analysis/09_relief_valve_transient_check.py
- analysis/10_phase3_safety_fault_injection.py

---

## Purpose

Translate high-level safety concepts into concrete, testable architecture elements.
This is still pre-prototype and does not replace formal regulatory design controls.

---

## 1. Safety Control Stack

1. Mechanical fail-safe:
- Normally-open valve bias via return spring
- Independent mechanical relief path

2. Electrical fail-safe:
- MCU watchdog timer
- External hardware watchdog supervising actuator-enable line

3. Sensing fail-safe:
- Dual independent position channels
- Upstream/downstream pressure supervision
- End-stop state inference check

4. Software fail-safe:
- Bounded command envelope
- Fault-state latching and forced-open command

---

## 2. Candidate Components (Draft BOM-Level)

| Function | Candidate Component Class | Candidate Example | Notes |
|---|---|---|---|
| MCU watchdog | Internal independent watchdog | STM32-class IWDG | Must be permanently enabled in runtime config |
| External watchdog | Window watchdog supervisor IC | TI TPS3430 class | Drives actuator-enable cutoff on timeout |
| Position sensing (dual) | Linear Hall sensors (redundant) | Allegro A1302/A1304 class | Two channels, independent ADC paths |
| Pressure sensing | Differential/absolute pressure transducers | Medical low-pressure MEMS class | Upstream + downstream for fault detection |
| Relief element | Spring-loaded poppet branch | Custom branch per CAD | Sizing checked by script + transient check |
| Actuator cutoff | High-side safety switch | Protected load switch class | Controlled by external watchdog + MCU |

Notes:
- Part family references are placeholders for architecture lock.
- Final part-number freeze requires supply, qualification, and derating review.

---

## 3. Control Logic (Fault-Relevant)

### 3.1 Position disagreement

Trigger condition:
- abs(pos_ch1_mm - pos_ch2_mm) > 0.10 mm for >= 5 ms

Action:
- force actuator disable
- command/open fail-safe state
- raise alarm bit and latched fault code

### 3.2 Watchdog timeout

Trigger condition:
- missing service event in <= 10 ms window

Action:
- external watchdog cuts actuator-enable
- valve defaults toward open state
- fault persists until operator reset sequence

### 3.3 Pressure differential fault

Trigger condition:
- DeltaP across valve exceeds threshold in open-command state

Action:
- classify probable mechanical blockage or non-response
- enforce fail-open command
- trigger alarm and log event

---

## 4. Verification Matrix (Architecture-Level)

| Control | Verification Method | Pass Criterion | Artifact |
|---|---|---|---|
| Dual Hall disagreement handling | Injected bias simulation | Fault detected and fail-open within 10 ms | analysis/logs/phase3_safety_fault_summary.json |
| Watchdog cutoff path | Timeout injection test | Actuator-enable removed within 10 ms | analysis/logs/phase3_safety_fault_summary.json |
| Relief branch response | Lumped transient simulation | target flow reached with <=20 ms opening response | phase3_relief_transient_summary.json |
| Command clamp safety | Unit/integration tests | Commands stay in bounded envelope [20,100] ms | phase3_adaptive_rule_summary.json |
| Adaptive robustness under perturbation | Scenario stress replay (noise/jitter/lag) | moderate min pass-rate >=90% and combined severe >=80% | phase3_adaptive_robustness_summary.json |
| Adaptive robustness under plant coupling | Actuator-delay/latency surrogate replay | aggregate: plant_moderate >=90% and plant_severe >=80%; patient-level: every patient moderate >=90% and severe >=80% | phase3_adaptive_plant_coupled_summary.json |
| Hardware transition gate | Multi-artifact gate checker (controller + relief + safety timing + process evidence) | `hardware_prototyping_gate.pass = true` with no blockers | phase3_hardware_gate_summary.json |
| External domain-shift screen | Reference vs external Paw/Flow feature distribution screen | shifted-feature fraction <=20% and external_domain_shift_pass=true | phase3_external_domain_shift_summary.json |
| External controller replay screen | Plant-aware policy replay on external artifact feature space | strict replay gate true on approved replay mode and external replay review signed | phase3_external_controller_replay_external_raw_summary.json / phase3_external_controller_replay_external_mitigated_summary.json |

### 4.1 Current timing simulation snapshot (2026-03-19)

Source: `analysis/logs/phase3_safety_fault_summary.json` from `analysis/10_phase3_safety_fault_injection.py`.

Baseline control assumptions:
- Watchdog cutoff: 9.0 ms (pass)
- Sensor disagreement latch: 11.3 ms (fail)
- Pressure-fault latch: 16.0 ms (fail)
- Overall timing gate (<=10 ms each): fail

Bounded candidate search (software-tuning envelope):
- Watchdog cutoff: 6.5 ms (pass)
- Sensor disagreement latch: 8.3 ms (pass)
- Pressure-fault latch: 9.3 ms (pass)
- Overall timing gate: pass

Interpretation:
- Timing-feasible fault handling is demonstrated in simulation with tightened debounce/time constants.
- Baseline settings still violate two timing gates, so control-parameter hardening and hardware timing validation remain required.

### 4.2 Adaptive robustness snapshot (2026-03-20)

Source: `analysis/logs/phase3_adaptive_robustness_summary.json` from `analysis/11_phase3_adaptive_robustness_check.py`.

Working criteria:
- moderate scenario minimum pass-rate >= 90%
- combined severe pass-rate >= 80%

Latest result:
- moderate_min_pass_rate: 100.0% (pass)
- combined_severe_pass_rate: 99.6% (pass)
- robustness_gate_met: true

Interpretation:
- Bounded perturbation stress criteria are currently met.
- This remains software-level evidence and does not replace plant-coupled simulation or bench/HIL verification.

### 4.3 Plant-coupled snapshot (2026-03-20)

Source: `analysis/logs/phase3_plant_coupled_adaptive_summary.json` and `analysis/logs/phase3_plant_coupled_plant_aware_summary.json` from `analysis/12_phase3_adaptive_plant_coupled_check.py`.

Working criteria:
- plant_moderate >= 90%
- plant_severe >= 80%
- plant_moderate_min_patient_pass_rate >= 90%
- plant_severe_min_patient_pass_rate >= 80%

Latest result:
- plant_nominal_pass_rate: 100.0%
- plant_moderate_pass_rate: 100.0% (pass)
- plant_severe_pass_rate: 99.6% (pass)
- plant_coupled_gate_met_aggregate: true
- plant_moderate_min_patient_pass_rate: 100.0%
- plant_severe_min_patient_pass_rate: 97.8% (pass)
- plant_coupled_gate_met_patient_level: true
- plant_coupled_gate_met: true

Interpretation:
- Script 14 lexicographic max-min search reports `feasible_patient_level_gate` and closes strict surrogate plant-coupled criteria in the focused run.
- This evidence remains simulation-only and must be corroborated by external replay and HIL before any hardware gate transition.

Model-based benchmark note:
- A delay-compensated controller benchmark (`analysis/13_phase3_model_based_controller_eval.py`) improves plant_moderate to 92.5% but still fails plant_severe at 58.9%.
- Conclusion: controller architecture needs further severe-case dynamic compensation before hardware transition.

Plant-aware benchmark note:
- A plant-aware benchmark (`analysis/14_phase3_plant_aware_controller_eval.py`) reaches strict plant gate in current surrogate replay (moderate 100.0%, severe 99.6%, severe min-patient 97.8%).
- Updated objective now prioritizes worst-patient severe robustness and checks a strict patient-level gate.
- Hardware gate remains closed because verification is still simulation-only and non-controller risks (relief valve credibility, safety timing on hardware, manufacturable CAD) remain open.

---

## 5. Open Items Before Hardware Gate

1. Freeze component part numbers and tolerance stacks.
2. Add explicit electrical isolation and abnormal-operation checks for IEC 60601-1 mapping.
3. Close plant-coupled adaptive robustness gap (moderate/severe thresholds) and then corroborate with external-dataset replay.
4. Perform independent design review sign-off.

---

End of document.
