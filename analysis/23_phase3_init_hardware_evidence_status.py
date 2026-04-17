#!/usr/bin/env python
# =============================================================================
# 23_phase3_init_hardware_evidence_status.py  —  Evidence status initializer
# Version: 1.0  |  2026-03-20
#
# Creates or repairs phase3_hardware_evidence_status.json with conservative
# defaults. Existing true flags are preserved.
# =============================================================================

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import config as C

OUT = os.path.join(C.LOGS_DIR, "phase3_hardware_evidence_status.json")

DEFAULT = {
    "version": "1.0",
    "date": "2026-03-20",
    "hardware_validation": {
        "safety_timing_verified_on_hardware": False,
        "relief_supplier_components_frozen": False,
        "relief_bench_transient_verified": False,
    },
    "cad_and_procurement": {
        "cad_release_ready": False,
        "seal_supplier_qualified": False,
        "actuator_characterized": False,
    },
    "external_validation": {
        "external_dataset_validation_complete": False,
        "external_shift_review_signed": False,
        "external_replay_review_signed": False,
        "external_shift_mode": "mitigated",
        "dataset_notes": "Run external shift/replay validation and archive reviewed mode decision before enabling flags.",
    },
    "standards_and_quality": {
        "iso14971_file_complete": False,
        "iec60601_1_prelim_complete": False,
        "independent_review_signed": False,
    },
    "design_control": {
        "iteration_log_current": False,
        "component_freeze_plan_current": False,
    },
    "notes": [
        "Set each flag to true only after evidence is archived and reviewed.",
        "This file is intentionally conservative and should gate hardware transition decisions.",
    ],
}


def _merge(base: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, val in base.items():
        if key not in current:
            continue
        cur = current[key]
        if isinstance(val, dict) and isinstance(cur, dict):
            for k2, v2 in val.items():
                if k2 in cur:
                    out[key][k2] = cur[k2]
        else:
            out[key] = cur
    # Force conservative reviewed default mode unless explicitly set to raw/mitigated.
    mode = str(out.get("external_validation", {}).get("external_shift_mode", "mitigated")).strip().lower()
    if mode not in {"raw", "mitigated"}:
        out["external_validation"]["external_shift_mode"] = "mitigated"
    return out


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    if os.path.exists(OUT):
        with open(OUT, "r", encoding="utf-8") as fh:
            cur = json.load(fh)
    else:
        cur = {}

    merged = _merge(DEFAULT, cur if isinstance(cur, dict) else {})

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)

    print(f"Saved: {OUT}")
    print(f"external_shift_mode={merged['external_validation']['external_shift_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
