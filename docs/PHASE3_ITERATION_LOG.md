# Phase 3 Iteration Log

This log records what changed, why it changed, and which evidence artifact supports the change.

Document Version: 1.0
Date: March 20, 2026
Status: Active (research-stage, hardware gate closed)

---

## Purpose

This log records major Phase 3 design iterations, rationale, and verification artifacts.
It is intended for reproducibility, peer review, and design-control traceability.

---

## Completed Iterations

### v1.0 - Initial Concept Baseline (superseded)
- Date: 2026-03-17
- Change: Initial mechanical/control concept drafted for adaptive expiratory valve.
- Rationale: Establish a first executable baseline for integrated CAD + simulation exploration.
- Verification: Initial simulations and design review exposed major defects.
- Key outcome: Superseded after flow-area, force, and manufacturability flaws were identified.

### v2.0 - Safety-Gated Mechanical Redesign
- Date: 2026-03-19
- Change: Bore sizing corrected to 16 mm baseline; poppet spring-seat moved to flange concept; relief sizing rebased on orifice equation.
- Rationale: Remove non-manufacturable geometry and incorrect sizing assumptions.
- Verification artifacts:
  - docs/04_PHASE3_MECHANICAL_DESIGN.md
  - analysis/phase3_cadquery_valve.py
  - analysis/valve_export/valve_metadata.json

### v2.1 - Dynamic Seal Placeholder Update
- Date: 2026-03-19
- Change: Legacy O-ring assumption replaced with PTFE-style placeholder gland geometry.
- Rationale: Reduce unrealistic seal assumptions and prepare for supplier-qualified seal selection.
- Verification artifacts:
  - analysis/phase3_cadquery_valve.py
  - analysis/valve_export/valve_metadata.json

### v2.2 - Controller Robustness Escalation
- Date: 2026-03-20
- Change: Added plant-aware controller optimization with strict patient-level gate checks.
- Rationale: Eliminate worst-patient severe-case failures hidden by aggregate metrics.
- Verification artifacts:
  - analysis/14_phase3_plant_aware_controller_eval.py
  - analysis/logs/phase3_plant_aware_summary.json
  - analysis/12_phase3_adaptive_plant_coupled_check.py
  - analysis/logs/phase3_plant_coupled_plant_aware_summary.json

### v2.3 - Relief Transient Feasibility Envelope
- Date: 2026-03-20
- Change: Relief search split into unconstrained and hardware-feasible envelope candidates.
- Rationale: Prevent over-claiming from non-feasible parameter combinations.
- Verification artifacts:
  - analysis/09_relief_valve_transient_check.py
  - analysis/logs/phase3_relief_transient_summary.json

### v2.4 - External Validation Gating
- Date: 2026-03-20
- Change: Added external domain-shift checks, mitigation path, and external controller replay.
- Rationale: Quantify and gate transfer risk beyond the CCVW-only development set.
- Verification artifacts:
  - analysis/16_phase3_external_domain_shift_check.py
  - analysis/17_phase3_external_shift_mitigation.py
  - analysis/18_phase3_external_controller_replay.py
  - analysis/logs/phase3_external_domain_shift_summary.json
  - analysis/logs/phase3_external_domain_shift_mitigated_summary.json
  - analysis/logs/phase3_external_controller_replay_external_raw_summary.json

### v2.5 - Hardware Gate, Tracker, and Closure Orchestration
- Date: 2026-03-20
- Change: Added strict hardware transition gate, blocker tracker, evidence-pack scaffolds, and one-command readiness packet.
- Rationale: Convert narrative risk status into machine-checkable closure workflow.
- Verification artifacts:
  - analysis/15_phase3_hardware_gate_check.py
  - analysis/19_phase3_readiness_packet.py
  - analysis/20_phase3_blocker_tracker.py
  - analysis/21_phase3_evidence_pack_init.py
  - analysis/22_phase3_closure_plan.py
  - analysis/logs/phase3_hardware_gate_summary.json

### v2.6 - CAD Seat Topology Hardening
- Date: 2026-03-20
- Change: Replaced revolved ring-profile seat generation with robust boolean construction (outer cylinder minus conical inner bore).
- Rationale: Reduce non-manifold/degenerate topology risk at seat outer diameter and improve STEP/meshing robustness.
- Verification artifacts:
  - analysis/phase3_cadquery_valve.py
  - analysis/valve_export/valve_metadata.json

### v2.7 - Dual-Path Passive+Active Concept Exploration
- Date: 2026-03-20
- Change: Added a novel dual-path CAD concept (active central poppet + passive annular bypass fuse ring) with cost-aware metadata output.
- Rationale: Explore higher safety margin under actuator delay/fault while keeping geometry manufacturable and low-cost candidate paths visible.
- Verification artifacts:
  - analysis/phase3_cadquery_valve_dualpath_concept.py
  - analysis/valve_export_dualpath_concept/dualpath_metadata.json

### v2.8 - Low-Cost Blocker Closure Planning
- Date: 2026-03-20
- Change: Expanded blocker tracker and closure planner with low-cost action guidance, estimated budget fields, and owner/date persistence.
- Rationale: Make hardware verification closure executable under constrained budget while preserving gate rigor.
- Verification artifacts:
  - analysis/20_phase3_blocker_tracker.py
  - analysis/22_phase3_closure_plan.py
  - docs/PHASE3_LOW_COST_HARDWARE_VERIFICATION_PLAN.md

### v2.9 - Evidence Status Initialization and Mitigated-Mode Default
- Date: 2026-03-20
- Change: Added an idempotent hardware-evidence status initializer and integrated it into readiness orchestration; set external shift mode default to mitigated.
- Rationale: Prevent missing-evidence-status failures and align research-phase external evaluation mode with documented review path.
- Verification artifacts:
  - analysis/23_phase3_init_hardware_evidence_status.py
  - analysis/19_phase3_readiness_packet.py
  - analysis/logs/phase3_hardware_evidence_status.json

### v2.10 - Blocker Evidence Scaffold Initialization
- Date: 2026-03-20
- Change: Added concrete report/checklist templates for P1/P2 blocker evidence artifacts (HIL timing, relief bench, actuator, seal, external reviews, standards drafts, independent review).
- Rationale: Convert blocker closure from planning-only to execution-ready documentation workflow.
- Verification artifacts:
  - analysis/logs/hil_timing_report.md
  - analysis/logs/relief_bench_transient_report.md
  - analysis/logs/actuator_characterization_report.md
  - analysis/logs/seal_friction_leak_report.md
  - analysis/logs/phase3_external_validation_decision.md
  - analysis/logs/phase3_external_shift_review.md
  - analysis/logs/phase3_external_replay_review.md
  - analysis/valve_export/RELEASE_NOTES.md
  - docs/ISO14971_Risk_Management_File.md
  - docs/IEC60601-1_Preliminary_Assessment.md
  - docs/INDEPENDENT_REVIEW_CHECKLIST.md

### v2.11 - Readiness Preflight for Required Simulation Inputs
- Date: 2026-03-20
- Change: Added explicit readiness preflight checks for required gate inputs (plant-aware controller summary, relief transient summary, safety fault summary) with actionable producers in packet outputs.
- Rationale: Prevent late pipeline failures and make missing prerequisite simulations explicit before running gate orchestration.
- Verification artifacts:
  - analysis/19_phase3_readiness_packet.py
  - analysis/logs/phase3_readiness_packet.json
  - analysis/logs/phase3_readiness_packet.md

### v2.12 - Compact Single-Source Consolidation and Housekeeping
- Date: 2026-03-20
- Change: Added compact single-source generator and integrated it into readiness orchestration with automatic cleanup of redundant run*.txt logs.
- Rationale: Reduce artifact sprawl and centralize project status into one compact navigable file without removing key findings.
- Verification artifacts:
  - analysis/24_phase3_single_source_compact.py
  - analysis/logs/phase3_single_source_of_truth.json
  - analysis/logs/phase3_single_source_of_truth.md

### v2.13 - Markdown Compendium Consolidation
- Date: 2026-03-20
- Change: Added markdown compactor that merges project markdown sources into a single indexed compendium and cleans redundant generated markdown outputs.
- Rationale: Make markdown-based project records compact and easy to access from one artifact.
- Verification artifacts:
  - analysis/25_phase3_markdown_compact.py
  - analysis/logs/phase3_markdown_compendium.md
  - analysis/logs/phase3_markdown_index.json

### v2.14 - Dual-Path Comparative Simulation (Step 2.2)
- Date: 2026-03-20
- Change: Added an exploratory dual-path variant comparator using the same surrogate plant stress scenarios as the plant-aware baseline.
- Rationale: Quantify whether passive bypass/fuse assist improves robustness before creating a separate gated hardware branch.
- Verification artifacts:
  - analysis/26_phase3_dualpath_variant_compare.py
  - analysis/logs/phase3_dualpath_comparison_summary.json
  - analysis/logs/phase3_dualpath_comparison_per_patient.csv

### v2.15 - Dual-Path Parameter Sweep Enhancement
- Date: 2026-03-20
- Change: Extended dual-path comparison with bounded parameter sweep and best-candidate selection, including sweep export for sensitivity review.
- Rationale: Replace single-point comparison with data-backed parameter envelope assessment before branch-integration decisions.
- Verification artifacts:
  - analysis/26_phase3_dualpath_variant_compare.py
  - analysis/logs/phase3_dualpath_sweep.csv
  - analysis/logs/phase3_dualpath_comparison_summary.json

### v2.16 - Dependency-Aware Parallel Simulation Runner
- Date: 2026-03-20
- Change: Added a dependency-aware parallel runner for core scripts 08-14 and plant-coupled checks to reduce turnaround time.
- Rationale: Improve execution efficiency while preserving simulation dependency correctness.
- Verification artifacts:
  - analysis/27_phase3_parallel_runner.py
  - analysis/logs/phase3_parallel_runner_summary.json
  - analysis/logs/phase3_parallel_runner_summary.md

### v2.17 - P1 Closure Assignment Bootstrap
- Date: 2026-03-20
- Change: Added a tracker assignment utility to auto-populate owner/date placeholders for open P1 blockers without changing evidence flags.
- Rationale: Move from planning to scheduled execution and accelerate hardware-verification workstream start.
- Verification artifacts:
  - analysis/28_phase3_assign_closure_defaults.py
  - analysis/logs/phase3_blocker_tracker.csv

---

## Planned Iterations

### v3.0 - Supplier Component Freeze
- Scope: Spring, seal, relief components, actuator, sensors.
- Required outputs: Supplier part numbers, datasheets, tolerance-fit evidence.
- Gate linkage: process evidence flags in analysis/logs/phase3_hardware_evidence_status.json.

### v3.1 - Manufacturing Release Package
- Scope: 2D drawings, GD&T, materials, surface finishes, assembly notes.
- Required outputs: CAD release evidence and procurement-ready package.
- Gate linkage: cad_release_ready, seal_supplier_qualified, actuator_characterized.

### v3.2 - Bench and HIL Validation
- Scope: Relief transient bench, safety timing on target hardware, fault injection.
- Required outputs: Bench reports + HIL timing traces.
- Gate linkage: relief_bench_transient_verified, safety_timing_verified_on_hardware.

### v3.3 - External Validation Decision
- Scope: Approved external replay mode policy and review sign-offs.
- Required outputs: External shift/replay review package and intended-use statement.
- Gate linkage: external_shift_review_signed, external_replay_review_signed, external_dataset_validation_complete.

### v3.4 - Regulatory and Independent Review Closure
- Scope: ISO 14971 file completion, IEC 60601-1 preliminary package, external review sign-off.
- Required outputs: Review-ready compliance package.
- Gate linkage: iso14971_file_complete, iec60601_1_prelim_complete, independent_review_signed.

---

## Non-Use Reminder

This repository remains research-stage engineering work and is not approved for clinical use or hardware prototyping at this time.
