#!/usr/bin/env python
# =============================================================================
# 15_phase3_hardware_gate_check.py  —  Phase 3 hardware transition gate
# Version: 1.0  |  2026-03-20
#
# Enforces a strict multi-domain gate before hardware prototyping can be
# considered. Combines simulation artifacts with explicit hardware/process
# evidence flags.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("15_phase3_hardware_gate_check")

IN_CONTROLLER = os.path.join(C.LOGS_DIR, "phase3_plant_coupled_plant_aware_summary.json")
IN_RELIEF = os.path.join(C.LOGS_DIR, "phase3_relief_transient_summary.json")
IN_SAFETY = os.path.join(C.LOGS_DIR, "phase3_safety_fault_summary.json")
IN_EVIDENCE = os.path.join(C.LOGS_DIR, "phase3_hardware_evidence_status.json")
IN_EXTERNAL_SHIFT_RAW = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_summary.json")
IN_EXTERNAL_SHIFT_MITIGATED = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_summary.json")
IN_EXTERNAL_REPLAY = os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_raw_summary.json")

OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json")


@dataclass(frozen=True)
class GateTargets:
    controller_moderate_min: float = 0.90
    controller_severe_min: float = 0.80
    controller_patient_moderate_min: float = 0.90
    controller_patient_severe_min: float = 0.80
    safety_timing_max_ms: float = 10.0


def _load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing required input JSON: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _bool(v: Any) -> bool:
    return bool(v)


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _evaluate_controller(controller: dict[str, Any], t: GateTargets) -> tuple[bool, dict[str, Any], list[str]]:
    r = controller.get("results", {})
    moderate = _num(r.get("plant_moderate_pass_rate"))
    severe = _num(r.get("plant_severe_pass_rate"))
    pmod = _num(r.get("plant_moderate_min_patient_pass_rate"))
    psev = _num(r.get("plant_severe_min_patient_pass_rate"))

    pass_flag = bool(
        moderate >= t.controller_moderate_min
        and severe >= t.controller_severe_min
        and pmod >= t.controller_patient_moderate_min
        and psev >= t.controller_patient_severe_min
        and _bool(r.get("plant_coupled_gate_met"))
    )

    blockers: list[str] = []
    if not pass_flag:
        blockers.append("controller_strict_gate_not_met")

    return pass_flag, {
        "plant_moderate_pass_rate": moderate,
        "plant_severe_pass_rate": severe,
        "plant_moderate_min_patient_pass_rate": pmod,
        "plant_severe_min_patient_pass_rate": psev,
        "strict_gate": _bool(r.get("plant_coupled_gate_met")),
    }, blockers


def _evaluate_relief(relief: dict[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    base = relief.get("results", {})
    cs = relief.get("candidate_search", {})
    feasible = cs.get("best_hardware_feasible")
    feasible_pass = _bool(cs.get("hardware_feasible_pass_found"))

    details = {
        "baseline_response_time_pass": _bool(base.get("response_time_pass")),
        "baseline_flow_capacity_pass": _bool(base.get("flow_capacity_pass")),
        "hardware_feasible_pass_found": feasible_pass,
        "best_hardware_feasible": feasible,
    }

    blockers: list[str] = []
    if not feasible_pass:
        blockers.append("relief_no_hardware_feasible_sim_pass")

    return feasible_pass, details, blockers


def _evaluate_safety_timing(safety: dict[str, Any], evidence: dict[str, Any], t: GateTargets) -> tuple[bool, dict[str, Any], list[str]]:
    baseline = safety.get("results", {})
    cand = safety.get("candidate_search", {}).get("results", {})

    hw = evidence.get("hardware_validation", {})
    hw_verified = _bool(hw.get("safety_timing_verified_on_hardware"))

    details = {
        "baseline_overall_pass": _bool(baseline.get("overall_pass")),
        "candidate_overall_pass": _bool(cand.get("overall_pass")),
        "baseline_watchdog_ms": _num(baseline.get("watchdog", {}).get("t_watchdog_cutoff_ms"), default=float("nan")),
        "baseline_sensor_ms": _num(baseline.get("sensor_disagreement", {}).get("t_sensor_fault_latched_ms"), default=float("nan")),
        "baseline_pressure_ms": _num(baseline.get("pressure_fault", {}).get("t_pressure_fault_latched_ms"), default=float("nan")),
        "timing_target_ms": t.safety_timing_max_ms,
        "safety_timing_verified_on_hardware": hw_verified,
    }

    blockers: list[str] = []
    # Gate requires hardware validation even if candidate simulation passes.
    if not hw_verified:
        blockers.append("safety_timing_not_hardware_verified")

    return hw_verified, details, blockers


def _evaluate_process_evidence(evidence: dict[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    hw = evidence.get("hardware_validation", {})
    cad = evidence.get("cad_and_procurement", {})
    ext = evidence.get("external_validation", {})
    std = evidence.get("standards_and_quality", {})
    dctl = evidence.get("design_control", {})

    checks = {
        "relief_supplier_components_frozen": _bool(hw.get("relief_supplier_components_frozen")),
        "relief_bench_transient_verified": _bool(hw.get("relief_bench_transient_verified")),
        "cad_release_ready": _bool(cad.get("cad_release_ready")),
        "seal_supplier_qualified": _bool(cad.get("seal_supplier_qualified")),
        "actuator_characterized": _bool(cad.get("actuator_characterized")),
        "external_dataset_validation_complete": _bool(ext.get("external_dataset_validation_complete")),
        "external_shift_review_signed": _bool(ext.get("external_shift_review_signed")),
        "external_replay_review_signed": _bool(ext.get("external_replay_review_signed")),
        "iso14971_file_complete": _bool(std.get("iso14971_file_complete")),
        "iec60601_1_prelim_complete": _bool(std.get("iec60601_1_prelim_complete")),
        "independent_review_signed": _bool(std.get("independent_review_signed")),
        "iteration_log_current": _bool(dctl.get("iteration_log_current")),
        "component_freeze_plan_current": _bool(dctl.get("component_freeze_plan_current")),
    }

    blockers = [f"process_evidence_missing:{k}" for k, v in checks.items() if not v]
    pass_flag = len(blockers) == 0
    return pass_flag, checks, blockers


def _evaluate_external_shift_summary(path: str, mode: str) -> tuple[bool, dict[str, Any], list[str]]:
    if not os.path.exists(path):
        return False, {"summary_present": False, "selected_mode": mode}, ["external_domain_shift_summary_missing"]

    ext_shift = _load_json(path)
    r = ext_shift.get("results", {})
    pass_flag = _bool(r.get("external_domain_shift_pass"))
    details = {
        "summary_present": True,
        "selected_mode": mode,
        "external_domain_shift_pass": pass_flag,
        "n_shared_features": _num(r.get("n_shared_features")),
        "n_shifted_features": _num(r.get("n_shifted_features")),
        "shifted_feature_fraction": _num(r.get("shifted_feature_fraction")),
        "top_shifted_features": r.get("top_shifted_features", []),
    }

    blockers: list[str] = []
    if not pass_flag:
        blockers.append("external_domain_shift_gate_not_met")
    return pass_flag, details, blockers


def _evaluate_external_replay_summary(path: str) -> tuple[bool, dict[str, Any], list[str]]:
    if not os.path.exists(path):
        return False, {"summary_present": False}, ["external_replay_summary_missing"]

    rep = _load_json(path)
    r = rep.get("results", {})
    strict = _bool(r.get("plant_coupled_gate_met"))
    details = {
        "summary_present": True,
        "plant_moderate_pass_rate": _num(r.get("plant_moderate_pass_rate")),
        "plant_severe_pass_rate": _num(r.get("plant_severe_pass_rate")),
        "plant_moderate_min_patient_pass_rate": _num(r.get("plant_moderate_min_patient_pass_rate")),
        "plant_severe_min_patient_pass_rate": _num(r.get("plant_severe_min_patient_pass_rate")),
        "strict_gate": strict,
    }
    blockers: list[str] = []
    if not strict:
        blockers.append("external_replay_gate_not_met")
    return strict, details, blockers


def _recommended_actions(blockers: list[str]) -> list[str]:
    actions: list[str] = []
    for b in blockers:
        if b == "controller_strict_gate_not_met":
            actions.append("Re-run plant-aware optimization and plant-coupled replay until strict patient-level controller gate is met.")
        elif b == "relief_no_hardware_feasible_sim_pass":
            actions.append("Expand relief design search with supplier-constrained parameter bounds and re-run transient simulation.")
        elif b == "safety_timing_not_hardware_verified":
            actions.append("Execute HIL timing test and archive watchdog/sensor/pressure latch evidence (<=10 ms each).")
        elif b == "external_domain_shift_summary_missing":
            actions.append("Run external domain-shift scripts (16/17) to generate required shift summary artifacts.")
        elif b == "external_domain_shift_gate_not_met":
            actions.append("Mitigate external domain shift (feature harmonization and operating-envelope review), then re-run gate in reviewed mode.")
        elif b == "external_replay_summary_missing":
            actions.append("Run external controller replay script (18) for the selected external mode and archive summary artifacts.")
        elif b == "external_replay_gate_not_met":
            actions.append("Retune replay calibration and controller mapping for external data, then re-run external replay until strict replay gate is met.")
        elif b.startswith("process_evidence_missing:"):
            key = b.split(":", 1)[1]
            if key == "iteration_log_current":
                actions.append("Update PHASE3_ITERATION_LOG.md with latest versioned design changes and linked verification artifacts.")
            elif key == "component_freeze_plan_current":
                actions.append("Update PHASE3_COMPONENT_FREEZE_PLAN.md with owners, target dates, and supplier evidence links.")
            else:
                actions.append(f"Complete and document evidence item: {key}.")

    # Preserve order while removing duplicates.
    dedup = []
    seen = set()
    for a in actions:
        if a in seen:
            continue
        seen.add(a)
        dedup.append(a)
    return dedup


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    targets = GateTargets()

    controller = _load_json(IN_CONTROLLER)
    relief = _load_json(IN_RELIEF)
    safety = _load_json(IN_SAFETY)
    evidence = _load_json(IN_EVIDENCE)

    ext_mode = str(evidence.get("external_validation", {}).get("external_shift_mode", "raw")).strip().lower()
    if ext_mode == "mitigated":
        ext_shift_path = IN_EXTERNAL_SHIFT_MITIGATED
        ext_replay_path = os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_mitigated_summary.json")
    else:
        ext_mode = "raw"
        ext_shift_path = IN_EXTERNAL_SHIFT_RAW
        ext_replay_path = IN_EXTERNAL_REPLAY

    c_pass, c_details, c_block = _evaluate_controller(controller, targets)
    r_pass, r_details, r_block = _evaluate_relief(relief)
    s_pass, s_details, s_block = _evaluate_safety_timing(safety, evidence, targets)
    p_pass, p_details, p_block = _evaluate_process_evidence(evidence)
    x_pass, x_details, x_block = _evaluate_external_shift_summary(ext_shift_path, ext_mode)
    xr_pass, xr_details, xr_block = _evaluate_external_replay_summary(ext_replay_path)

    blockers = c_block + r_block + s_block + p_block + x_block + xr_block
    hardware_ready = bool(c_pass and r_pass and s_pass and p_pass and x_pass and xr_pass)

    out = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "controller_summary": os.path.relpath(IN_CONTROLLER, C.ANALYSIS_DIR).replace("\\", "/"),
            "relief_summary": os.path.relpath(IN_RELIEF, C.ANALYSIS_DIR).replace("\\", "/"),
            "safety_summary": os.path.relpath(IN_SAFETY, C.ANALYSIS_DIR).replace("\\", "/"),
            "evidence_status": os.path.relpath(IN_EVIDENCE, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_shift_summary": os.path.relpath(ext_shift_path, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_replay_summary": os.path.relpath(ext_replay_path, C.ANALYSIS_DIR).replace("\\", "/"),
        },
        "targets": {
            "controller_moderate_min": targets.controller_moderate_min,
            "controller_severe_min": targets.controller_severe_min,
            "controller_patient_moderate_min": targets.controller_patient_moderate_min,
            "controller_patient_severe_min": targets.controller_patient_severe_min,
            "safety_timing_max_ms": targets.safety_timing_max_ms,
        },
        "checks": {
            "controller": {"pass": c_pass, "details": c_details},
            "relief": {"pass": r_pass, "details": r_details},
            "safety_timing": {"pass": s_pass, "details": s_details},
            "external_domain_shift": {"pass": x_pass, "details": x_details},
            "external_controller_replay": {"pass": xr_pass, "details": xr_details},
            "process_and_compliance": {"pass": p_pass, "details": p_details},
        },
        "hardware_prototyping_gate": {
            "pass": hardware_ready,
            "blockers": blockers,
            "recommended_actions": _recommended_actions(blockers),
        },
        "notes": [
            "Controller and relief simulation passes are necessary but not sufficient.",
            "Hardware gate requires explicit hardware/process evidence flags in phase3_hardware_evidence_status.json.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    log.info("Saved: %s", OUT_SUMMARY)
    log.info("Hardware prototyping gate pass: %s", hardware_ready)
    if blockers:
        log.info("Blockers: %s", ", ".join(blockers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
