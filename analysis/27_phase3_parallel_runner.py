#!/usr/bin/env python
# =============================================================================
# 27_phase3_parallel_runner.py  —  Phase 3 dependency-aware parallel runner
# Version: 1.0  |  2026-03-20
#
# Runs the core Phase 3 simulation chain with dependency-aware parallelization.
# Research-stage workflow utility only.
# =============================================================================

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import config as C

OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_parallel_runner_summary.json")
OUT_MD = os.path.join(C.LOGS_DIR, "phase3_parallel_runner_summary.md")


def _run(cmd: list[str], timeout_s: int = 3600) -> dict[str, Any]:
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    dt = time.time() - t0
    return {
        "cmd": cmd,
        "exit_code": int(proc.returncode),
        "duration_s": round(dt, 3),
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _run_parallel(commands: list[list[str]], timeout_s: int, max_workers: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_run, c, timeout_s): c for c in commands}
        for fut in as_completed(futs):
            results.append(fut.result())
    return results


def _ok(results: list[dict[str, Any]]) -> bool:
    return all(r.get("exit_code", 1) == 0 for r in results)


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    py = sys.executable

    # Stage 1: produce baseline predictions once.
    stage1 = [
        [py, os.path.join(C.ANALYSIS_DIR, "08_phase3_adaptive_rule_sim.py")],
    ]

    # Stage 2: independent jobs after baseline exists.
    stage2 = [
        [py, os.path.join(C.ANALYSIS_DIR, "09_relief_valve_transient_check.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "10_phase3_safety_fault_injection.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "11_phase3_adaptive_robustness_check.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "13_phase3_model_based_controller_eval.py")],
        [py, os.path.join(C.ANALYSIS_DIR, "14_phase3_plant_aware_controller_eval.py")],
    ]

    # Stage 3: plant-coupled checks after 14 exists.
    stage3 = [
        [py, os.path.join(C.ANALYSIS_DIR, "12_phase3_adaptive_plant_coupled_check.py")],
        [
            py,
            os.path.join(C.ANALYSIS_DIR, "12_phase3_adaptive_plant_coupled_check.py"),
            "--input",
            os.path.join(C.LOGS_DIR, "phase3_plant_aware_predictions.csv"),
            "--output-tag",
            "plant_aware",
        ],
    ]

    all_results: dict[str, list[dict[str, Any]]] = {}

    t_all = time.time()

    s1_results = [_run(c, timeout_s=3600) for c in stage1]
    all_results["stage1"] = s1_results
    if not _ok(s1_results):
        status = "failed_stage1"
    else:
        s2_results = _run_parallel(stage2, timeout_s=3600, max_workers=min(5, os.cpu_count() or 2))
        all_results["stage2"] = s2_results
        if not _ok(s2_results):
            status = "failed_stage2"
        else:
            s3_results = _run_parallel(stage3, timeout_s=3600, max_workers=2)
            all_results["stage3"] = s3_results
            status = "ok" if _ok(s3_results) else "failed_stage3"

    total_s = round(time.time() - t_all, 3)

    out = {
        "version": "1.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "total_duration_s": total_s,
        "results": all_results,
        "notes": [
            "Parallelization is dependency-aware and limited to independent scripts.",
            "This runner generates simulation artifacts only; hardware gate closure still requires real evidence.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    lines = [
        "# Phase 3 Parallel Runner Summary",
        "",
        f"- Generated: {out['generated_utc']}",
        f"- Status: {status}",
        f"- Total duration (s): {total_s}",
        "",
    ]

    for stage in ["stage1", "stage2", "stage3"]:
        if stage not in all_results:
            continue
        lines.append(f"## {stage}")
        for r in all_results[stage]:
            lines.append(
                f"- exit={r['exit_code']} | {r['duration_s']}s | {' '.join(r['cmd'])}"
            )
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"Saved: {OUT_SUMMARY}")
    print(f"Saved: {OUT_MD}")
    print(f"status={status}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
