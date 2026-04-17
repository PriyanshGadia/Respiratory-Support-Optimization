# Phase 3 Risk Register (Draft)

Document Version: 1.0
Date: March 19, 2026
Status: Draft baseline for ISO 14971-oriented workflow

Linked documents:
- 04_PHASE3_MECHANICAL_DESIGN.md
- PHASE3_ITERATION_LOG.md
- PHASE3_COMPONENT_FREEZE_PLAN.md
- PHASE3_LOW_COST_HARDWARE_VERIFICATION_PLAN.md
- analysis/logs/phase3_adaptive_rule_summary.json
- analysis/valve_export/valve_metadata.json

---

## Scope

This register captures current Phase 3 hazards, controls, and verification gates for redesign tracking.
It is not yet a complete regulatory risk management file.

---

## Risk Scale

- Severity (S): 1 (negligible) to 5 (catastrophic)
- Occurrence (O): 1 (remote) to 5 (frequent)
- Detection (D): 1 (highly detectable) to 5 (poorly detectable)
- RPN = S * O * D

Working action thresholds:
- RPN > 35: mitigation implementation + verification mandatory before hardware gate
- RPN 25-35: mitigation implementation required; verification plan approved
- RPN < 25: monitor under standard verification cadence

---

## Risk Table

| ID | Hazard | Effect | S | O | D | RPN | Current Controls | Verification Artifact | Residual Status |
|---|---|---|---:|---:|---:|---:|---|---|---|
| R-01 | Valve remains closed during inspiration | Acute pressure rise, severe patient harm | 5 | 2 | 3 | 30 | Normally-open mechanical default; watchdog cutoff logic with timing simulation | analysis/logs/phase3_safety_fault_summary.json + bench timing (pending) | Open |
| R-02 | Sensor disagreement or drift | Incorrect valve position estimate | 4 | 3 | 3 | 36 | Dual Hall disagreement threshold/debounce with timing simulation | analysis/logs/phase3_safety_fault_summary.json + sensor fault bench test (pending) | Open (high, reduced confidence gap) |
| R-03 | Relief path under-capacity | Over-pressure persists despite fault | 5 | 2 | 4 | 40 | Relief diameter first-order orifice sizing; transient candidate search with passing dynamic pair | analysis/logs/phase3_relief_transient_summary.json + bench/CFD confirmation (pending) | Open (high, reduced confidence gap) |
| R-04 | Dynamic seal friction rise/leak | Delayed response, leakage, instability | 4 | 3 | 3 | 36 | PTFE-style placeholder geometry and gland baseline | Supplier-qualified seal and endurance plan (pending) | Open (high) |
| R-05 | Controller timing miscommand | Excess transient or asynchrony | 4 | 3 | 2 | 24 | Bounded open-time commands, clamp logic, severity-cluster strategy, robust-guard headroom policy | analysis/logs/phase3_adaptive_rule_summary.json + analysis/logs/phase3_adaptive_robustness_summary.json | Open (simulation only) |
| R-06 | Spring force out of target range | Fail-safe/opening dynamics degraded | 4 | 2 | 2 | 16 | Spring force derived checks in valve metadata | Dynamic co-simulation with flow force (pending) | Open |

---

## Current Quantitative Evidence

From analysis/logs/phase3_adaptive_rule_summary.json:
- Aggregate pass rate for DeltaPaw <= 5.0 cmH2O: 100.0% (current surrogate run)
- Gate target: >= 90%
- Gate status: surrogate met; robustness/plant-coupled validation still pending

From analysis/logs/phase3_adaptive_robustness_summary.json:
- Robustness gate definition:
	- moderate scenario minimum pass-rate >= 90%
	- combined severe pass-rate >= 80%
- Observed:
	- moderate_min_pass_rate: 100.0% (pass)
	- combined_severe_pass_rate: 99.6% (pass)
	- robustness_gate_met: true
- Worst-case patient/scenario remains P05 under combined_severe (pass-rate 97.8%, dpaw_p95 4.76 cmH2O)
- Residual concern: robustness evidence remains perturbation-model based and requires plant-coupled + external replay confirmation.

From analysis/logs/phase3_plant_coupled_adaptive_summary.json:
- Plant-coupled gate definition:
	- plant_moderate pass-rate >= 90%
	- plant_severe pass-rate >= 80%
	- plant_moderate_min_patient_pass_rate >= 90%
	- plant_severe_min_patient_pass_rate >= 80%
- Observed:
	- plant_nominal_pass_rate: 100.0%
	- plant_moderate_pass_rate: 76.1% (fail)
	- plant_severe_pass_rate: 52.9% (fail)
	- plant_moderate_min_patient_pass_rate: 0.0% (fail)
	- plant_severe_min_patient_pass_rate: 0.0% (fail)
	- plant_coupled_gate_met_aggregate: false
	- plant_coupled_gate_met_patient_level: false
	- plant_coupled_gate_met: false
- Worst-case patient/scenario: P01 under plant_severe (pass-rate 0.0%, dpaw_p95 6.85 cmH2O)

From analysis/logs/phase3_model_based_summary.json and model-based plant replay:
- Delay-compensated model-based benchmark achieved:
	- plant_moderate_pass_rate: 92.5% (pass)
	- plant_severe_pass_rate: 58.9% (fail)
	- plant_coupled_gate_met: false
- Interpretation: model-based compensation narrows the plant gap but severe-case risk remains unresolved.

From analysis/logs/phase3_plant_aware_summary.json and analysis/logs/phase3_plant_coupled_plant_aware_summary.json:
- Plant-aware benchmark achieved aggregate plant gate in the current surrogate:
	- plant_moderate_pass_rate: 100.0% (pass)
	- plant_severe_pass_rate: 99.6% (pass)
	- plant_coupled_gate_met_aggregate: true
- Patient-level severe robustness in the focused max-min search run:
	- plant_moderate_min_patient_pass_rate: 100.0%
	- plant_severe_min_patient_pass_rate: 97.8% (pass)
	- plant_coupled_gate_met_patient_level: true
	- plant_coupled_gate_met (strict aggregate + patient-level): true
	- search_outcome: feasible_patient_level_gate
	- objective: lexicographic_maximin
- Interpretation: this materially improves the controller surrogate evidence, but R-05 remains open until external replay and HIL/bench timing corroboration are complete.

From analysis/valve_export/valve_metadata.json:
- spring_force_closed_n: 1.003 N (target 1.0 N)
- relief_required_dia_mm: 12.07 mm
- relief_seat_dia configured: 12.10 mm
- seat_contact_error_closed: 0.0
- spring_length_fit_error_closed: 0.0

From analysis/logs/phase3_relief_transient_summary.json:
- Nominal transient baseline fails response and flow-capacity gates.

- Unconstrained best candidate passes but is non-feasible:
	- mass 0.8 g, damping 0.03 N*s/m, spring 40 N/m, preload 0.05 N
	- response_time_pass: true
	- flow_capacity_pass: true

- Hardware-feasible-envelope candidate also passes in simulation:
	- mass 1.5 g, damping 0.08 N*s/m, spring 80 N/m, preload 0.20 N
	- response_time_pass: true
	- flow_capacity_pass: true
	- t_to_target_flow_ms: 8.7
	- hardware_feasible_pass_found: true
- Residual concern: feasibility envelope is still model-side screening; supplier-locked hardware and bench-transient confirmation are required before closing R-03.

From analysis/logs/phase3_safety_fault_summary.json:
- Baseline timing simulation:
	- watchdog cutoff: 9.0 ms (pass)
	- sensor disagreement latch: 11.3 ms (fail)
	- pressure fault latch: 16.0 ms (fail)
- Candidate search found timing-feasible fault settings:
	- watchdog cutoff: 6.5 ms (pass)
	- sensor disagreement latch: 8.3 ms (pass)
	- pressure fault latch: 9.3 ms (pass)
- Residual concern: candidate settings are simulation-only and require hardware timing confirmation.

From analysis/logs/phase3_hardware_gate_summary.json:
- Hardware transition gate currently reports `pass: false`.
- Controller and relief simulation checks pass in the gate script, but transition remains blocked by missing hardware/process evidence flags.
- Immediate blockers include:
	- safety timing not hardware verified
	- relief supplier freeze and bench transient confirmation not complete
	- CAD/procurement readiness incomplete
	- external dataset validation incomplete
	- formal standards and independent review evidence incomplete
- Interpretation: current status is suitable for next-phase validation work, not hardware prototyping.

From analysis/logs/phase3_readiness_packet.json and phase3_readiness_packet.md:
- One-command orchestration now runs scripts 16/17/18/15 and emits a consolidated readiness packet.
- Packet includes current gate status, blocker list, and recommended actions snapshot.

From analysis/logs/phase3_blocker_tracker.csv and phase3_blocker_tracker.json:
- Gate blockers are now expanded into a closure checklist with required evidence and explicit closure checks.
- This tracker is intended as the working artifact for blocker retirement between review cycles.

From analysis/logs/phase3_evidence_pack/index.json:
- Per-blocker evidence template files are now scaffolded under analysis/logs/phase3_evidence_pack/.
- Each blocker file contains owner/date placeholders, required evidence text, and review sign-off fields.
- This evidence pack is intended to capture closure artifacts before toggling any hardware evidence flags.

From analysis/logs/phase3_external_domain_shift_summary.json:
- Shared Paw/Flow-derived features: 16
- Shifted features: 16
- Shifted-feature fraction: 1.00
- external_domain_shift_pass: false
- Top shifted features include: ets_defaulted_flag, flow_rise_time_ms, paw_base, insp_dur_s, delta_paw_max.
- Interpretation: external generalization risk remains high and is now quantitatively confirmed.

From analysis/logs/phase3_external_domain_shift_mitigated_summary.json:
- Quantile-mapping mitigation reduces shifted-feature fraction from 1.00 to 0.438.
- external_domain_shift_pass remains false (7/16 features still shifted).
- Interpretation: mitigation narrows domain mismatch but does not yet meet transition-gate requirements.

From analysis/logs/phase3_external_controller_replay_external_raw_summary.json:
- Raw external replay strict gate is false.
- Severe aggregate pass-rate is 64.9% and severe min-group pass-rate is 0.4%.
- Interpretation: controller transfer risk remains high on raw external artifact space.

From analysis/logs/phase3_external_controller_replay_external_mitigated_summary.json:
- Mitigated external replay strict gate is true on the mitigated sample artifact.
- Interpretation: harmonization may recover replay performance, but review and conservative gate policy are still required before changing external validation status.

---

## Immediate Risk Actions

1. Lock safety debounce/time constants in firmware requirements and confirm <=10 ms behavior on HIL/bench for watchdog, sensor disagreement, and pressure-fault paths.
2. Freeze relief candidate to supplier-qualified mass/damping/spring/preload and confirm response/flow on bench/CFD to close R-03.
3. Finalize supplier-specific dynamic seal and gland tolerances to address R-04.
4. Keep strict plant gate on patient-level criteria (moderate >=90% and severe >=80% for every patient), then corroborate with external replay and HIL evidence before changing R-05 status.
5. Run external domain-shift mitigation/recalibration and sign external-shift review before enabling external validation completion.
6. Complete external replay review sign-off and document acceptable replay mode policy (raw versus mitigated evidence path).
7. Record every blocker-closing design change in PHASE3_ITERATION_LOG.md before updating any hardware evidence flag to true.

---

## Change Control

- Update this file whenever risk controls, metrics, or verification status changes.
- Each risk-row update should reference the producing script/log artifact.

---

End of document.
