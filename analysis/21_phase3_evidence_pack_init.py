#!/usr/bin/env python
# =============================================================================
# 21_phase3_evidence_pack_init.py  —  Evidence pack scaffold generator
# Version: 1.0  |  2026-03-20
#
# Generates structured evidence-pack templates for each open hardware-gate
# blocker so closure work is explicit and auditable.
# =============================================================================

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import pandas as pd

import config as C

IN_TRACKER = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv")
OUT_DIR = os.path.join(C.LOGS_DIR, "phase3_evidence_pack")
OUT_INDEX = os.path.join(OUT_DIR, "index.json")


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def main() -> int:
    if not os.path.exists(IN_TRACKER):
        raise FileNotFoundError(f"Missing blocker tracker: {IN_TRACKER}")

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(IN_TRACKER)

    entries = []
    generated = 0
    for _, r in df.iterrows():
        blocker = str(r.get("blocker", "")).strip()
        domain = str(r.get("domain", "")).strip()
        required = str(r.get("required_evidence", "")).strip()
        closure = str(r.get("closure_check", "")).strip()

        slug = _slug(blocker)
        path = os.path.join(OUT_DIR, f"{slug}.json")

        if not os.path.exists(path):
            payload = {
                "version": "1.0",
                "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "blocker": blocker,
                "domain": domain,
                "status": "open",
                "required_evidence": required,
                "closure_check": closure,
                "owner": "",
                "target_date": "",
                "evidence_artifacts": [],
                "verification_notes": "",
                "review_signoff": {
                    "reviewer": "",
                    "date": "",
                    "approved": False,
                    "comments": ""
                }
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            generated += 1

        entries.append(
            {
                "blocker": blocker,
                "domain": domain,
                "status": str(r.get("status", "open")),
                "evidence_file": os.path.relpath(path, C.ANALYSIS_DIR).replace("\\", "/"),
            }
        )

    index_payload = {
        "version": "1.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_tracker": os.path.relpath(IN_TRACKER, C.ANALYSIS_DIR).replace("\\", "/"),
        "n_blockers": int(len(entries)),
        "n_new_files": int(generated),
        "entries": entries,
    }
    with open(OUT_INDEX, "w", encoding="utf-8") as fh:
        json.dump(index_payload, fh, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
