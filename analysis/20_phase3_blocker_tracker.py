#!/usr/bin/env python
# =============================================================================
# 20_phase3_blocker_tracker.py  —  Hardware gate blocker tracker
# Version: 1.0  |  2026-03-20
#
# Builds a structured blocker checklist from phase3_hardware_gate_summary.json
# to support evidence closure tracking.
# =============================================================================

from __future__ import annotations

import json
import os

import pandas as pd

import config as C

IN_GATE = os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json")
OUT_CSV = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv")
OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.json")


def _clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"", "nan", "none", "nat"}:
        return ""
    return s


def _meta(blocker: str) -> dict:
    mapping = {
        "safety_timing_not_hardware_verified": {
            "domain": "safety",
            "required_evidence": "HIL timing traces for watchdog/sensor/pressure latches <=10 ms",
            "closure_check": "set safety_timing_verified_on_hardware=true",
            "low_cost_action": "Use a low-cost MCU dev board plus logic analyzer to measure watchdog/sensor/pressure cutoff timing.",
            "evidence_artifact": "analysis/logs/hil_timing_report.md",
            "estimated_cost_usd": 60.0,
            "suggested_owner_role": "firmware",
        },
        "external_domain_shift_gate_not_met": {
            "domain": "external_validation",
            "required_evidence": "phase3_external_domain_shift(_mitigated)_summary.json with pass=true",
            "closure_check": "external shift summary pass true on approved mode",
            "low_cost_action": "Run mitigated mode policy with documented operating-envelope constraints and reviewer sign-off.",
            "evidence_artifact": "analysis/logs/phase3_external_validation_decision.md",
            "estimated_cost_usd": 0.0,
            "suggested_owner_role": "ml",
        },
        "external_replay_gate_not_met": {
            "domain": "external_validation",
            "required_evidence": "phase3_external_controller_replay_*_summary.json strict gate true on approved mode",
            "closure_check": "external replay strict gate true + review signed",
            "low_cost_action": "Re-run replay in approved mode and archive strict-gate evidence with external review notes.",
            "evidence_artifact": "analysis/logs/phase3_external_replay_review.md",
            "estimated_cost_usd": 0.0,
            "suggested_owner_role": "ml",
        },
    }

    if blocker in mapping:
        return mapping[blocker]

    if blocker.startswith("process_evidence_missing:"):
        key = blocker.split(":", 1)[1]
        if key == "iteration_log_current":
            return {
                "domain": "design_control",
                "required_evidence": "Updated docs/PHASE3_ITERATION_LOG.md entry for all recent design/control changes",
                "closure_check": "set iteration_log_current=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Add versioned entries for each closure task and link artifacts before toggling flags.",
                "evidence_artifact": "docs/PHASE3_ITERATION_LOG.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "systems",
            }
        if key == "component_freeze_plan_current":
            return {
                "domain": "design_control",
                "required_evidence": "Updated docs/PHASE3_COMPONENT_FREEZE_PLAN.md with owner/date/status and supplier evidence links",
                "closure_check": "set component_freeze_plan_current=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Assign owners and freeze candidate catalog parts with linked datasheets.",
                "evidence_artifact": "docs/PHASE3_COMPONENT_FREEZE_PLAN.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "mechanical",
            }
        process_mapping = {
            "relief_supplier_components_frozen": {
                "domain": "relief",
                "required_evidence": "Catalog supplier relief component selection with part numbers and datasheets",
                "closure_check": "set relief_supplier_components_frozen=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Select off-the-shelf relief parts from catalog vendors and archive datasheets in evidence pack.",
                "evidence_artifact": "analysis/logs/phase3_evidence_pack/process_evidence_missing__relief_supplier_components_frozen.json",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "mechanical",
            },
            "relief_bench_transient_verified": {
                "domain": "relief",
                "required_evidence": "Bench transient report with pressure/flow traces vs simulation target",
                "closure_check": "set relief_bench_transient_verified=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Build a low-cost pressure-step bench rig using commodity differential pressure and flow sensors.",
                "evidence_artifact": "analysis/logs/relief_bench_transient_report.md",
                "estimated_cost_usd": 140.0,
                "suggested_owner_role": "test",
            },
            "cad_release_ready": {
                "domain": "mechanical",
                "required_evidence": "Release package with STEP exports, dimensions, tolerances, and notes",
                "closure_check": "set cad_release_ready=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Export final STEP files and create prototype drawing notes with material and tolerance callouts.",
                "evidence_artifact": "analysis/valve_export/RELEASE_NOTES.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "mechanical",
            },
            "seal_supplier_qualified": {
                "domain": "mechanical",
                "required_evidence": "Seal datasheet, gland drawing, and friction/leak check report",
                "closure_check": "set seal_supplier_qualified=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Select a catalog PTFE/U-cup seal and run friction/leak checks in the same bench fixture.",
                "evidence_artifact": "analysis/logs/seal_friction_leak_report.md",
                "estimated_cost_usd": 30.0,
                "suggested_owner_role": "mechanical",
            },
            "actuator_characterized": {
                "domain": "electromechanical",
                "required_evidence": "Force-current and step-response characterization report",
                "closure_check": "set actuator_characterized=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Characterize a low-cost voice-coil/solenoid candidate with load-cell and step tests.",
                "evidence_artifact": "analysis/logs/actuator_characterization_report.md",
                "estimated_cost_usd": 120.0,
                "suggested_owner_role": "electrical",
            },
            "external_dataset_validation_complete": {
                "domain": "external_validation",
                "required_evidence": "Signed dataset validation decision and approved evaluation mode",
                "closure_check": "set external_dataset_validation_complete=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Document acceptance criteria for raw versus mitigated evidence path and sign dataset review.",
                "evidence_artifact": "analysis/logs/phase3_external_validation_decision.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "ml",
            },
            "external_shift_review_signed": {
                "domain": "external_validation",
                "required_evidence": "Signed shift-review memo with mode and thresholds",
                "closure_check": "set external_shift_review_signed=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Run shift summary pack and get reviewer sign-off on selected mode.",
                "evidence_artifact": "analysis/logs/phase3_external_shift_review.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "ml",
            },
            "external_replay_review_signed": {
                "domain": "external_validation",
                "required_evidence": "Signed replay-review memo including strict-gate status",
                "closure_check": "set external_replay_review_signed=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Archive replay outputs and complete independent replay decision checklist.",
                "evidence_artifact": "analysis/logs/phase3_external_replay_review.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "ml",
            },
            "iso14971_file_complete": {
                "domain": "quality",
                "required_evidence": "Risk management file with hazard-control traceability",
                "closure_check": "set iso14971_file_complete=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Populate an ISO 14971 style risk file from existing register and evidence links.",
                "evidence_artifact": "docs/ISO14971_Risk_Management_File.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "quality",
            },
            "iec60601_1_prelim_complete": {
                "domain": "quality",
                "required_evidence": "Preliminary IEC 60601-1 clause checklist with gap notes",
                "closure_check": "set iec60601_1_prelim_complete=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Draft a preliminary IEC 60601-1 assessment focused on applicable clauses and open gaps.",
                "evidence_artifact": "docs/IEC60601-1_Preliminary_Assessment.md",
                "estimated_cost_usd": 0.0,
                "suggested_owner_role": "quality",
            },
            "independent_review_signed": {
                "domain": "quality",
                "required_evidence": "Signed independent design review checklist and findings",
                "closure_check": "set independent_review_signed=true in phase3_hardware_evidence_status.json",
                "low_cost_action": "Run structured peer red-team review and archive checklist, findings, and sign-off.",
                "evidence_artifact": "docs/INDEPENDENT_REVIEW_CHECKLIST.md",
                "estimated_cost_usd": 150.0,
                "suggested_owner_role": "systems",
            },
        }
        if key in process_mapping:
            return process_mapping[key]
        return {
            "domain": "process_or_compliance",
            "required_evidence": f"Documented artifact for {key}",
            "closure_check": f"set {key}=true in phase3_hardware_evidence_status.json",
            "low_cost_action": f"Create and archive evidence for {key}.",
            "evidence_artifact": "analysis/logs/phase3_evidence_pack/index.json",
            "estimated_cost_usd": 0.0,
            "suggested_owner_role": "systems",
        }

    if blocker == "controller_strict_gate_not_met":
        return {
            "domain": "controller",
            "required_evidence": "phase3_plant_coupled_plant_aware_summary.json strict gate true",
            "closure_check": "controller strict gate true",
            "low_cost_action": "Re-run plant-aware search and tighten guard constraints until strict gate is recovered.",
            "evidence_artifact": "analysis/logs/phase3_plant_coupled_plant_aware_summary.json",
            "estimated_cost_usd": 0.0,
            "suggested_owner_role": "ml",
        }

    if blocker == "relief_no_hardware_feasible_sim_pass":
        return {
            "domain": "relief",
            "required_evidence": "phase3_relief_transient_summary.json hardware_feasible_pass_found=true",
            "closure_check": "relief simulation feasibility true",
            "low_cost_action": "Expand relief parameter sweep within supplier-constrained bounds and re-evaluate.",
            "evidence_artifact": "analysis/logs/phase3_relief_transient_summary.json",
            "estimated_cost_usd": 0.0,
            "suggested_owner_role": "ml",
        }

    return {
        "domain": "unmapped",
        "required_evidence": "manual review",
        "closure_check": "manual closure",
        "low_cost_action": "Manual blocker review and closure plan.",
        "evidence_artifact": "analysis/logs/phase3_hardware_gate_summary.json",
        "estimated_cost_usd": 0.0,
        "suggested_owner_role": "systems",
    }


def main() -> int:
    if not os.path.exists(IN_GATE):
        raise FileNotFoundError(f"Missing gate summary: {IN_GATE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)
    with open(IN_GATE, "r", encoding="utf-8") as fh:
        gate = json.load(fh)

    blockers = gate.get("hardware_prototyping_gate", {}).get("blockers", [])
    actions = gate.get("hardware_prototyping_gate", {}).get("recommended_actions", [])
    action_join = " | ".join(actions)

    existing: dict[str, dict] = {}
    if os.path.exists(OUT_CSV):
        try:
            prev = pd.read_csv(OUT_CSV)
            for _, r in prev.iterrows():
                b = str(r.get("blocker", "")).strip()
                if b:
                    existing[b] = {
                        "owner": _clean_text(r.get("owner", "")),
                        "target_date": _clean_text(r.get("target_date", "")),
                        "status": _clean_text(r.get("status", "open")) or "open",
                        "notes": _clean_text(r.get("notes", "")),
                    }
        except Exception:
            existing = {}

    tracker_rows = []
    for b in blockers:
        m = _meta(b)
        prev_row = existing.get(b, {})
        tracker_rows.append(
            {
                "blocker": b,
                "domain": m["domain"],
                "suggested_owner_role": m["suggested_owner_role"],
                "estimated_cost_usd": float(m["estimated_cost_usd"]),
                "low_cost_action": m["low_cost_action"],
                "evidence_artifact": m["evidence_artifact"],
                "required_evidence": m["required_evidence"],
                "closure_check": m["closure_check"],
                "owner": _clean_text(prev_row.get("owner", "")),
                "target_date": _clean_text(prev_row.get("target_date", "")),
                "status": _clean_text(prev_row.get("status", "open")) or "open",
                "notes": _clean_text(prev_row.get("notes", "")),
            }
        )

    tracker_df = pd.DataFrame(tracker_rows)
    tracker_df.to_csv(OUT_CSV, index=False)

    total_estimated_cost = float(tracker_df["estimated_cost_usd"].sum()) if len(tracker_df) else 0.0
    assigned = int((tracker_df["owner"].astype(str).str.strip() != "").sum()) if len(tracker_df) else 0

    tracker_summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "gate_pass": bool(gate.get("hardware_prototyping_gate", {}).get("pass", False)),
        "n_blockers": int(len(blockers)),
        "n_assigned_owners": assigned,
        "estimated_low_cost_budget_usd": round(total_estimated_cost, 2),
        "recommended_actions_joined": action_join,
        "tracker_csv": os.path.relpath(OUT_CSV, C.ANALYSIS_DIR).replace("\\", "/"),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(tracker_summary, fh, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
