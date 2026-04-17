#!/usr/bin/env python
# =============================================================================
# 19_phase3_readiness_packet.py  —  Phase 3 readiness packet orchestrator
# Version: 1.0  |  2026-03-20
#
# Runs the current Phase 3 validation chain and writes a consolidated readiness
# packet for rapid review.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("19_phase3_readiness_packet")


def _run(cmd: list[str], timeout_s: int = 600) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()
    return {
        "cmd": cmd,
        "exit_code": int(proc.returncode),
        "stdout_tail": stdout_text[-2000:],
        "stderr_tail": stderr_text[-2000:],
    }


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _ok(executions: list[dict[str, Any]]) -> bool:
    return all(e["exit_code"] == 0 for e in executions)


def _required_gate_inputs() -> list[dict[str, str]]:
    return [
        {
            "path": os.path.join(C.LOGS_DIR, "phase3_plant_coupled_plant_aware_summary.json"),
            "producer": "12_phase3_adaptive_plant_coupled_check.py (run with --output-tag plant_aware)",
            "purpose": "controller strict plant-coupled summary",
        },
        {
            "path": os.path.join(C.LOGS_DIR, "phase3_relief_transient_summary.json"),
            "producer": "09_relief_valve_transient_check.py",
            "purpose": "relief transient feasibility summary",
        },
        {
            "path": os.path.join(C.LOGS_DIR, "phase3_safety_fault_summary.json"),
            "producer": "10_phase3_safety_fault_injection.py",
            "purpose": "safety fault timing summary",
        },
    ]


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    out_json = os.path.join(C.LOGS_DIR, "phase3_readiness_packet.json")
    out_md = os.path.join(C.LOGS_DIR, "phase3_readiness_packet.md")

    missing_inputs: list[dict[str, str]] = []
    for item in _required_gate_inputs():
        if not os.path.exists(item["path"]):
            missing_inputs.append(item)

    if missing_inputs:
        packet = {
            "version": "1.0",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "executions_ok": False,
            "preflight": {
                "pass": False,
                "missing_required_inputs": [
                    {
                        "path": os.path.relpath(m["path"], C.ANALYSIS_DIR).replace("\\", "/"),
                        "producer": m["producer"],
                        "purpose": m["purpose"],
                    }
                    for m in missing_inputs
                ],
            },
            "executions": [],
        }

        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(packet, fh, indent=2)

        md_lines = [
            "# Phase 3 Readiness Packet",
            "",
            f"- Generated: {packet['date']}",
            "- Pipeline executions ok: False",
            "- Preflight pass: False",
            "",
            "## Missing Required Inputs",
        ]
        for m in packet["preflight"]["missing_required_inputs"]:
            md_lines.append(f"- {m['path']} ({m['purpose']})")
            md_lines.append(f"  Producer: {m['producer']}")

        md_lines.extend([
            "",
            "## Action",
            "- Generate missing simulation summaries before running readiness packet again.",
        ])
        _write_text(out_md, "\n".join(md_lines) + "\n")

        log.warning("Preflight failed: missing required gate inputs.")
        for m in packet["preflight"]["missing_required_inputs"]:
            log.warning("Missing: %s | producer: %s", m["path"], m["producer"])
        log.info("Saved: %s", out_json)
        log.info("Saved: %s", out_md)
        return 2

    py = sys.executable
    steps = [
        [py, os.path.join(C.ANALYSIS_DIR, "23_phase3_init_hardware_evidence_status.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "16_phase3_external_domain_shift_check.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "17_phase3_external_shift_mitigation.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "18_phase3_external_controller_replay.py"), "--input", os.path.join(C.LOGS_DIR, "vwd_scores.csv"), "--tag", "external_raw"],
        [py, os.path.join(C.ANALYSIS_DIR, "18_phase3_external_controller_replay.py"), "--input", os.path.join(C.LOGS_DIR, "vwd_scores_mitigated_sample.csv"), "--tag", "external_mitigated"],
        [py, os.path.join(C.ANALYSIS_DIR, "15_phase3_hardware_gate_check.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "20_phase3_blocker_tracker.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "21_phase3_evidence_pack_init.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "22_phase3_closure_plan.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "24_phase3_single_source_compact.py"), "--cleanup-run-logs"],
        [py, os.path.join(C.ANALYSIS_DIR, "25_phase3_markdown_compact.py"), "--cleanup-generated-markdown"],
    ]

    executions: list[dict[str, Any]] = []
    for s in steps:
        log.info("Running: %s", " ".join(s))
        executions.append(_run(s, timeout_s=900))

    # Artifact paths
    shift_raw_p = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_summary.json")
    shift_mit_p = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_summary.json")
    rep_raw_p = os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_raw_summary.json")
    rep_mit_p = os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_mitigated_summary.json")
    gate_p = os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json")
    tracker_p = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.json")
    evidence_index_p = os.path.join(C.LOGS_DIR, "phase3_evidence_pack", "index.json")
    closure_p = os.path.join(C.LOGS_DIR, "phase3_closure_plan.json")
    ssot_p = os.path.join(C.LOGS_DIR, "phase3_single_source_of_truth.json")
    md_compendium_p = os.path.join(C.LOGS_DIR, "phase3_markdown_compendium.md")
    md_index_p = os.path.join(C.LOGS_DIR, "phase3_markdown_index.json")

    packet = {
        "version": "1.0",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "executions_ok": _ok(executions),
        "executions": executions,
        "artifacts": {
            "external_shift_raw": os.path.relpath(shift_raw_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_shift_mitigated": os.path.relpath(shift_mit_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_replay_raw": os.path.relpath(rep_raw_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_replay_mitigated": os.path.relpath(rep_mit_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "hardware_gate": os.path.relpath(gate_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "blocker_tracker": os.path.relpath(tracker_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "evidence_pack_index": os.path.relpath(evidence_index_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "closure_plan": os.path.relpath(closure_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "single_source_of_truth": os.path.relpath(ssot_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "markdown_compendium": os.path.relpath(md_compendium_p, C.ANALYSIS_DIR).replace("\\", "/"),
            "markdown_index": os.path.relpath(md_index_p, C.ANALYSIS_DIR).replace("\\", "/"),
        },
    }

    # Best-effort load summaries.
    summaries: dict[str, Any] = {}
    for key, p in [
        ("shift_raw", shift_raw_p),
        ("shift_mitigated", shift_mit_p),
        ("replay_raw", rep_raw_p),
        ("replay_mitigated", rep_mit_p),
        ("hardware_gate", gate_p),
        ("blocker_tracker", tracker_p),
        ("evidence_pack_index", evidence_index_p),
        ("closure_plan", closure_p),
        ("single_source_of_truth", ssot_p),
        ("markdown_index", md_index_p),
    ]:
        if os.path.exists(p):
            summaries[key] = _read_json(p)
    packet["summaries"] = summaries

    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(packet, fh, indent=2)

    gate = summaries.get("hardware_gate", {})
    hp = gate.get("hardware_prototyping_gate", {}) if isinstance(gate, dict) else {}
    blockers = hp.get("blockers", []) if isinstance(hp, dict) else []
    actions = hp.get("recommended_actions", []) if isinstance(hp, dict) else []

    md_lines = [
        "# Phase 3 Readiness Packet",
        "",
        f"- Generated: {packet['date']}",
        f"- Pipeline executions ok: {packet['executions_ok']}",
        f"- Hardware prototyping gate pass: {hp.get('pass', False)}",
        "",
        "## Snapshot",
        f"- Raw external shift pass: {summaries.get('shift_raw', {}).get('results', {}).get('external_domain_shift_pass', False)}",
        f"- Mitigated external shift pass: {summaries.get('shift_mitigated', {}).get('results', {}).get('external_domain_shift_pass', False)}",
        f"- Raw external replay strict gate: {summaries.get('replay_raw', {}).get('results', {}).get('plant_coupled_gate_met', False)}",
        f"- Mitigated external replay strict gate: {summaries.get('replay_mitigated', {}).get('results', {}).get('plant_coupled_gate_met', False)}",
        "",
        "## Blockers",
    ]
    if blockers:
        md_lines.extend([f"- {b}" for b in blockers])
    else:
        md_lines.append("- none")

    md_lines.extend(["", "## Recommended Actions"])
    if actions:
        md_lines.extend([f"- {a}" for a in actions])
    else:
        md_lines.append("- none")

    _write_text(out_md, "\n".join(md_lines) + "\n")

    log.info("Saved: %s", out_json)
    log.info("Saved: %s", out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
