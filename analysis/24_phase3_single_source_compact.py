#!/usr/bin/env python
# =============================================================================
# 24_phase3_single_source_compact.py  —  Phase 3 single-source compactor
# Version: 1.0  |  2026-03-20
#
# Produces a compact, navigable single source of truth for current Phase 3
# status and optionally removes redundant run-log text artifacts.
# =============================================================================

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import config as C

OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_single_source_of_truth.json")
OUT_MD = os.path.join(C.LOGS_DIR, "phase3_single_source_of_truth.md")


def _load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact_meta(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {
            "exists": False,
            "relpath": os.path.relpath(path, C.ANALYSIS_DIR).replace("\\", "/"),
        }
    return {
        "exists": True,
        "relpath": os.path.relpath(path, C.ANALYSIS_DIR).replace("\\", "/"),
        "bytes": os.path.getsize(path),
        "sha256": _sha256(path),
    }


def _tracker_snapshot(path: str, limit: int = 40) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, r in enumerate(reader):
            if i >= limit:
                break
            rows.append(
                {
                    "blocker": str(r.get("blocker", "")),
                    "domain": str(r.get("domain", "")),
                    "owner": str(r.get("owner", "")),
                    "target_date": str(r.get("target_date", "")),
                    "status": str(r.get("status", "")),
                    "evidence_artifact": str(r.get("evidence_artifact", "")),
                }
            )
    return rows


def _extract_key_state() -> dict[str, Any]:
    readiness = _load_json(os.path.join(C.LOGS_DIR, "phase3_readiness_packet.json"))
    gate = _load_json(os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json"))
    closure = _load_json(os.path.join(C.LOGS_DIR, "phase3_closure_plan.json"))
    tracker = _load_json(os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.json"))
    evidence = _load_json(os.path.join(C.LOGS_DIR, "phase3_hardware_evidence_status.json"))
    shift_mit = _load_json(os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_summary.json"))
    replay_mit = _load_json(os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_mitigated_summary.json"))

    hp = gate.get("hardware_prototyping_gate", {}) if isinstance(gate, dict) else {}
    shift_results = shift_mit.get("results", {}) if isinstance(shift_mit, dict) else {}
    replay_results = replay_mit.get("results", {}) if isinstance(replay_mit, dict) else {}

    return {
        "readiness_generated_utc": readiness.get("date", ""),
        "readiness_executions_ok": readiness.get("executions_ok", False),
        "hardware_gate_pass": hp.get("pass", False),
        "n_blockers": len(hp.get("blockers", []) or []),
        "external_mode": (evidence.get("external_validation", {}) or {}).get("external_shift_mode", "unknown"),
        "mitigated_shift_pass": shift_results.get("external_domain_shift_pass", False),
        "mitigated_shift_fraction": shift_results.get("shifted_feature_fraction", None),
        "mitigated_replay_pass": replay_results.get("plant_coupled_gate_met", False),
        "estimated_budget_usd": closure.get("estimated_low_cost_budget_usd", None),
        "assigned_owners": closure.get("n_assigned_owners", None),
        "target_dates_set": closure.get("n_target_dates_set", None),
        "tracker_n_blockers": tracker.get("n_blockers", None),
    }


def _cleanup_run_logs() -> list[str]:
    removed: list[str] = []
    patterns = [
        os.path.join(C.LOGS_DIR, "run*.txt"),
    ]
    for p in patterns:
        for f in glob.glob(p):
            try:
                os.remove(f)
                removed.append(os.path.relpath(f, C.ANALYSIS_DIR).replace("\\", "/"))
            except OSError:
                continue
    return sorted(removed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate compact Phase 3 single source of truth")
    parser.add_argument("--cleanup-run-logs", action="store_true", help="Delete redundant run*.txt logs from analysis/logs")
    args = parser.parse_args()

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    tracked_files = [
        os.path.join(C.LOGS_DIR, "phase3_readiness_packet.json"),
        os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_hardware_evidence_status.json"),
        os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv"),
        os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.json"),
        os.path.join(C.LOGS_DIR, "phase3_closure_plan.csv"),
        os.path.join(C.LOGS_DIR, "phase3_closure_plan.json"),
        os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_external_controller_replay_external_mitigated_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_plant_coupled_plant_aware_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_relief_transient_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_safety_fault_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_dualpath_comparison_summary.json"),
        os.path.join(C.LOGS_DIR, "phase3_dualpath_comparison_per_patient.csv"),
        os.path.join(C.LOGS_DIR, "phase3_parallel_runner_summary.json"),
    ]

    removed_logs: list[str] = []
    if args.cleanup_run_logs:
        removed_logs = _cleanup_run_logs()

    artifact_index = [_artifact_meta(p) for p in tracked_files]
    key_state = _extract_key_state()
    tracker_rows = _tracker_snapshot(os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv"), limit=50)

    out = {
        "version": "2.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": "compact_phase3_single_source_of_truth",
        "key_state": key_state,
        "artifact_index": artifact_index,
        "tracker_snapshot": tracker_rows,
        "docs_index": [
            "../docs/04_PHASE3_MECHANICAL_DESIGN.md",
            "../docs/05_PHASE3_RISK_REGISTER.md",
            "../docs/06_PHASE3_SAFETY_ARCHITECTURE.md",
            "../docs/PHASE3_ITERATION_LOG.md",
            "../docs/PHASE3_COMPONENT_FREEZE_PLAN.md",
            "../docs/PHASE3_LOW_COST_HARDWARE_VERIFICATION_PLAN.md",
        ],
        "housekeeping": {
            "cleanup_run_logs_enabled": bool(args.cleanup_run_logs),
            "removed_run_logs": removed_logs,
        },
        "non_use_statement": "Research-stage only. Not approved for clinical or animal use.",
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    md_lines = [
        "# Phase 3 Single Source of Truth",
        "",
        f"- Generated: {out['generated_utc']}",
        f"- Hardware gate pass: {key_state.get('hardware_gate_pass', False)}",
        f"- Open blockers: {key_state.get('n_blockers', 'n/a')}",
        f"- External mode: {key_state.get('external_mode', 'unknown')}",
        f"- Mitigated shift pass: {key_state.get('mitigated_shift_pass', False)}",
        f"- Mitigated replay pass: {key_state.get('mitigated_replay_pass', False)}",
        f"- Estimated budget (USD): {key_state.get('estimated_budget_usd', 'n/a')}",
        "",
        "## Core Artifacts",
    ]

    for m in artifact_index:
        if m.get("exists"):
            md_lines.append(f"- {m['relpath']} ({m.get('bytes', 0)} bytes)")
        else:
            md_lines.append(f"- {m['relpath']} (missing)")

    md_lines.extend(["", "## Blocker Snapshot"])
    for r in tracker_rows:
        md_lines.append(
            f"- {r['blocker']} | domain={r['domain']} | status={r['status']} | owner={r['owner']} | target={r['target_date']}"
        )

    if removed_logs:
        md_lines.extend(["", "## Housekeeping"])
        for p in removed_logs:
            md_lines.append(f"- Removed redundant log: {p}")

    md_lines.extend(["", "## Non-Use Statement", "- Research-stage only. Not approved for clinical or animal use."])

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")

    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_MD}")
    if removed_logs:
        print(f"Removed run logs: {len(removed_logs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
