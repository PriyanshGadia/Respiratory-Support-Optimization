#!/usr/bin/env python
# =============================================================================
# 22_phase3_closure_plan.py  —  Phase 3 hardware-gate closure planner
# Version: 1.0  |  2026-03-20
#
# Converts current open blockers into prioritized closure work packages with
# dependencies, deliverables, and acceptance checks.
# =============================================================================

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import config as C

IN_TRACKER = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv")
IN_GATE = os.path.join(C.LOGS_DIR, "phase3_hardware_gate_summary.json")
OUT_CSV = os.path.join(C.LOGS_DIR, "phase3_closure_plan.csv")
OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_closure_plan.json")
OUT_MD = os.path.join(C.LOGS_DIR, "phase3_closure_plan.md")


def _clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"", "nan", "none", "nat"}:
        return ""
    return s


def _pkg_meta(blocker: str) -> dict[str, Any]:
    if blocker == "safety_timing_not_hardware_verified":
        return {
            "workstream": "Safety Hardware Verification",
            "priority": 1,
            "depends_on": "",
            "deliverables": "HIL timing traces; watchdog/sensor/pressure latch report",
            "acceptance": "All latch paths <=10 ms on target hardware",
        }

    if blocker in {"external_domain_shift_gate_not_met", "external_replay_gate_not_met"}:
        return {
            "workstream": "External Validation Reconciliation",
            "priority": 2,
            "depends_on": "",
            "deliverables": "External shift and replay review packet with approved replay mode policy",
            "acceptance": "External shift/replay checks pass on approved mode and reviews are signed",
        }

    if blocker.startswith("process_evidence_missing:"):
        k = blocker.split(":", 1)[1]
        if k in {"relief_supplier_components_frozen", "relief_bench_transient_verified"}:
            return {
                "workstream": "Relief Hardware Qualification",
                "priority": 1,
                "depends_on": "",
                "deliverables": "Supplier-qualified relief BOM; bench transient report",
                "acceptance": "Supplier freeze and bench transient verification complete",
            }
        if k in {"cad_release_ready", "seal_supplier_qualified", "actuator_characterized"}:
            return {
                "workstream": "Mechanical Release Package",
                "priority": 1,
                "depends_on": "",
                "deliverables": "Manufacturing CAD release, seal qualification, actuator characterization",
                "acceptance": "CAD/procurement flags set true with linked artifacts",
            }
        if k in {"iso14971_file_complete", "iec60601_1_prelim_complete", "independent_review_signed"}:
            return {
                "workstream": "Regulatory and Independent Review",
                "priority": 2,
                "depends_on": "",
                "deliverables": "ISO 14971 file, IEC 60601-1 preliminary package, signed independent review",
                "acceptance": "All regulatory/review flags set true with references",
            }
        if k in {"iteration_log_current", "component_freeze_plan_current"}:
            return {
                "workstream": "Design Control Traceability",
                "priority": 2,
                "depends_on": "",
                "deliverables": "Current iteration log and component freeze plan linked to blocker evidence",
                "acceptance": "Design-control flags true with reviewer-confirmed links",
            }
        if k in {"external_dataset_validation_complete", "external_shift_review_signed", "external_replay_review_signed"}:
            return {
                "workstream": "External Validation Governance",
                "priority": 2,
                "depends_on": "",
                "deliverables": "Signed external shift/replay reviews and dataset validation decision",
                "acceptance": "External validation flags all true",
            }

    return {
        "workstream": "Unmapped",
        "priority": 3,
        "depends_on": "",
        "deliverables": "Manual closure package",
        "acceptance": "Manual review closure",
    }


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    if not os.path.exists(IN_TRACKER):
        raise FileNotFoundError(f"Missing tracker: {IN_TRACKER}")
    if not os.path.exists(IN_GATE):
        raise FileNotFoundError(f"Missing gate summary: {IN_GATE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    tracker = pd.read_csv(IN_TRACKER)
    gate = _read_json(IN_GATE)
    blockers = gate.get("hardware_prototyping_gate", {}).get("blockers", [])

    closure_rows = []
    for b in blockers:
        base_row = tracker[tracker["blocker"] == b]
        required_evidence = ""
        closure_check = ""
        low_cost_action = ""
        evidence_artifact = ""
        estimated_cost_usd = 0.0
        suggested_owner_role = ""
        owner = ""
        target_date = ""
        status = "open"
        notes = ""
        if len(base_row):
            required_evidence = _clean_text(base_row.iloc[0].get("required_evidence", ""))
            closure_check = _clean_text(base_row.iloc[0].get("closure_check", ""))
            low_cost_action = _clean_text(base_row.iloc[0].get("low_cost_action", ""))
            evidence_artifact = _clean_text(base_row.iloc[0].get("evidence_artifact", ""))
            suggested_owner_role = _clean_text(base_row.iloc[0].get("suggested_owner_role", ""))
            owner = _clean_text(base_row.iloc[0].get("owner", ""))
            target_date = _clean_text(base_row.iloc[0].get("target_date", ""))
            status = _clean_text(base_row.iloc[0].get("status", "open")) or "open"
            notes = _clean_text(base_row.iloc[0].get("notes", ""))
            try:
                estimated_cost_usd = float(base_row.iloc[0].get("estimated_cost_usd", 0.0))
            except Exception:
                estimated_cost_usd = 0.0

        m = _pkg_meta(b)
        closure_rows.append(
            {
                "blocker": b,
                "priority": int(m["priority"]),
                "workstream": m["workstream"],
                "depends_on": m["depends_on"],
                "required_evidence": required_evidence,
                "closure_check": closure_check,
                "low_cost_action": low_cost_action,
                "evidence_artifact": evidence_artifact,
                "estimated_cost_usd": round(estimated_cost_usd, 2),
                "suggested_owner_role": suggested_owner_role,
                "deliverables": m["deliverables"],
                "acceptance": m["acceptance"],
                "owner": owner,
                "target_date": target_date,
                "status": status,
                "notes": notes,
            }
        )

    closure_plan_df = pd.DataFrame(closure_rows).sort_values(["priority", "workstream", "blocker"], ascending=[True, True, True])
    closure_plan_df.to_csv(OUT_CSV, index=False)

    workstream_rollup = (
        closure_plan_df.groupby(["priority", "workstream"], as_index=False)
        .agg(n_blockers=("blocker", "count"), estimated_cost_usd=("estimated_cost_usd", "sum"))
        .sort_values(["priority", "workstream"])
    )

    total_cost = float(closure_plan_df["estimated_cost_usd"].sum()) if len(closure_plan_df) else 0.0
    assigned_owners = int((closure_plan_df["owner"].apply(_clean_text) != "").sum()) if len(closure_plan_df) else 0
    with_dates = int((closure_plan_df["target_date"].apply(_clean_text) != "").sum()) if len(closure_plan_df) else 0

    closure_summary = {
        "version": "1.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hardware_gate_pass": bool(gate.get("hardware_prototyping_gate", {}).get("pass", False)),
        "n_blockers": int(len(closure_plan_df)),
        "estimated_low_cost_budget_usd": round(total_cost, 2),
        "n_assigned_owners": assigned_owners,
        "n_target_dates_set": with_dates,
        "artifacts": {
            "source_tracker": os.path.relpath(IN_TRACKER, C.ANALYSIS_DIR).replace("\\", "/"),
            "source_gate": os.path.relpath(IN_GATE, C.ANALYSIS_DIR).replace("\\", "/"),
            "closure_plan_csv": os.path.relpath(OUT_CSV, C.ANALYSIS_DIR).replace("\\", "/"),
        },
        "workstream_rollup": workstream_rollup.to_dict(orient="records"),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(closure_summary, fh, indent=2)

    md_lines = [
        "# Phase 3 Hardware Gate Closure Plan",
        "",
        f"- Generated: {closure_summary['generated_utc']}",
        f"- Hardware gate pass: {closure_summary['hardware_gate_pass']}",
        f"- Open blockers: {closure_summary['n_blockers']}",
        f"- Estimated low-cost budget: ${closure_summary['estimated_low_cost_budget_usd']:.2f}",
        f"- Assigned owners: {closure_summary['n_assigned_owners']}/{closure_summary['n_blockers']}",
        f"- Target dates set: {closure_summary['n_target_dates_set']}/{closure_summary['n_blockers']}",
        "",
        "## Workstream Rollup",
    ]
    for r in closure_summary["workstream_rollup"]:
        md_lines.append(
            f"- P{r['priority']} | {r['workstream']} | blockers: {r['n_blockers']} | estimated cost: ${float(r['estimated_cost_usd']):.2f}"
        )

    md_lines.extend(["", "## Priority Execution Order"])
    for _, r in closure_plan_df.iterrows():
        md_lines.append(
            f"- P{int(r['priority'])} | {r['workstream']} | {r['blocker']} | owner-role: {r['suggested_owner_role']} | est cost: ${float(r['estimated_cost_usd']):.2f}"
        )

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
