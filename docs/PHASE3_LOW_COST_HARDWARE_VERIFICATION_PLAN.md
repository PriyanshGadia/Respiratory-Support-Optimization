# Phase 3 Low-Cost Hardware Verification Plan

Document Version: 1.0
Date: March 20, 2026
Status: Research-stage execution plan (hardware gate remains closed)

---

## Purpose

Provide a practical, low-cost path to retire current hardware gate blockers with auditable evidence artifacts.
This plan is for research verification only and does not authorize clinical or animal use.

---

## Budget Envelope

Target out-of-pocket budget: <= 500 USD (excluding existing lab equipment).

Indicative spend profile:
- MCU + logic analyzer for timing verification: ~60 USD
- Relief bench sensors/fixture consumables: ~140 USD
- Seal samples and bench consumables: ~30 USD
- Actuator characterization fixtures/components: ~120 USD
- Independent peer review support: ~150 USD
- Total indicative envelope: ~500 USD

---

## Blocker Closure Actions

1. safety_timing_not_hardware_verified
- Action: Implement watchdog/sensor/pressure fault logic on a low-cost MCU board and capture cutoff latencies with logic analyzer traces.
- Evidence: analysis/logs/hil_timing_report.md
- Acceptance: all latch paths <=10 ms on target hardware path.

2. relief_supplier_components_frozen
- Action: Freeze catalog relief parts with part numbers and datasheets.
- Evidence: docs/PHASE3_COMPONENT_FREEZE_PLAN.md plus linked evidence-pack entry.

3. relief_bench_transient_verified
- Action: Build a pressure-step bench rig and measure flow/pressure transient response against simulation target.
- Evidence: analysis/logs/relief_bench_transient_report.md

4. cad_release_ready
- Action: Export release STEP set with dimensions/material notes and prototype manufacturing instructions.
- Evidence: analysis/valve_export/RELEASE_NOTES.md

5. seal_supplier_qualified
- Action: Select a supplier seal and validate friction/leak behavior in bench fixture.
- Evidence: analysis/logs/seal_friction_leak_report.md

6. actuator_characterized
- Action: Measure force-current and step response for selected actuator candidate.
- Evidence: analysis/logs/actuator_characterization_report.md

7. external_dataset_validation_complete
- Action: Finalize raw-versus-mitigated mode policy and dataset acceptance decision.
- Evidence: analysis/logs/phase3_external_validation_decision.md

8. external_shift_review_signed
- Action: Archive shift summary and obtain reviewer sign-off.
- Evidence: analysis/logs/phase3_external_shift_review.md

9. external_replay_review_signed
- Action: Archive replay summary and obtain reviewer sign-off.
- Evidence: analysis/logs/phase3_external_replay_review.md

10. iso14971_file_complete
- Action: Convert risk register into a complete risk file with control traceability.
- Evidence: docs/ISO14971_Risk_Management_File.md

11. iec60601_1_prelim_complete
- Action: Complete a preliminary IEC 60601-1 clause checklist with explicit gaps.
- Evidence: docs/IEC60601-1_Preliminary_Assessment.md

12. independent_review_signed
- Action: Run independent or peer red-team review with checklist and sign-off.
- Evidence: docs/INDEPENDENT_REVIEW_CHECKLIST.md

13. iteration_log_current
- Action: Record each significant closure task in iteration log before evidence-flag updates.
- Evidence: docs/PHASE3_ITERATION_LOG.md

14. component_freeze_plan_current
- Action: Maintain part freeze plan with owner/date/status and supplier references.
- Evidence: docs/PHASE3_COMPONENT_FREEZE_PLAN.md

15. external_domain_shift_gate_not_met
- Action: Run mitigated shift workflow, enforce envelope constraints, and document pass/fail policy.
- Evidence: analysis/logs/phase3_external_domain_shift_mitigated_summary.json plus review memo.

16. external_replay_gate_not_met
- Action: Tune replay mapping under approved mode and re-run strict replay gate.
- Evidence: analysis/logs/phase3_external_controller_replay_external_mitigated_summary.json plus review memo.

---

## Execution Cadence

- Update blocker owners and target dates in analysis/logs/phase3_blocker_tracker.csv.
- Re-run readiness packet after each closure batch:
  - python REBOOT/analysis/19_phase3_readiness_packet.py
- Do not toggle any evidence flag to true until the corresponding artifact is archived and peer-reviewed.

---

## Non-Use Statement

This plan does not authorize hardware prototyping for clinical or animal application.
Hardware transition remains blocked until phase3_hardware_gate_summary.json reports pass=true.
