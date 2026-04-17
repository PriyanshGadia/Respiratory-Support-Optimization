#!/usr/bin/env python
# =============================================================================
# 28_phase3_assign_closure_defaults.py  —  Closure assignment bootstrap
# Version: 1.0  |  2026-03-20
#
# Populates owner/target_date/status placeholders for open blockers to accelerate
# execution planning. Does not change any evidence flags.
# =============================================================================

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

import pandas as pd

import config as C

TRACKER = os.path.join(C.LOGS_DIR, "phase3_blocker_tracker.csv")
OUT = TRACKER


def _role_owner(role: str) -> str:
    role = (role or "").strip().lower()
    mapping = {
        "firmware": "owner_firmware",
        "mechanical": "owner_mechanical",
        "electrical": "owner_electrical",
        "test": "owner_test",
        "ml": "owner_ml",
        "quality": "owner_quality",
        "systems": "owner_systems",
    }
    return mapping.get(role, "owner_unassigned")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign default owner/date placeholders for blocker closure")
    parser.add_argument("--all", action="store_true", help="Apply to all open blockers (default: P1 only)")
    args = parser.parse_args()

    if not os.path.exists(TRACKER):
        raise FileNotFoundError(f"Missing tracker: {TRACKER}")

    df = pd.read_csv(TRACKER)

    if "owner" not in df.columns:
        df["owner"] = ""
    if "target_date" not in df.columns:
        df["target_date"] = ""
    if "status" not in df.columns:
        df["status"] = "open"
    if "notes" not in df.columns:
        df["notes"] = ""

    # Normalize text fields to string dtype for safe in-place updates.
    for col in ["owner", "target_date", "status", "notes", "domain", "suggested_owner_role"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    p1_domains = {"safety", "relief", "mechanical", "electromechanical"}

    today = date.today()
    n_assigned = 0

    for i in range(len(df)):
        status = str(df.at[i, "status"]).strip().lower()
        if status == "closed":
            continue

        domain = str(df.at[i, "domain"]).strip().lower()
        if not args.all and domain not in p1_domains:
            continue

        owner = str(df.at[i, "owner"]).strip()
        tdate = str(df.at[i, "target_date"]).strip()

        if not owner:
            role = str(df.at[i, "suggested_owner_role"]).strip()
            df.at[i, "owner"] = _role_owner(role)
            owner = str(df.at[i, "owner"]).strip()

        if not tdate:
            # Stagger by domain urgency for quick scheduling.
            if domain == "safety":
                due = today + timedelta(days=5)
            elif domain in {"relief", "mechanical", "electromechanical"}:
                due = today + timedelta(days=10)
            else:
                due = today + timedelta(days=14)
            df.at[i, "target_date"] = due.isoformat()

        if not str(df.at[i, "status"]).strip():
            df.at[i, "status"] = "open"

        note = str(df.at[i, "notes"]).strip()
        if "auto-assigned" not in note.lower():
            suffix = "auto-assigned owner/date placeholder"
            df.at[i, "notes"] = f"{note}; {suffix}".strip("; ")

        if owner:
            n_assigned += 1

    df.to_csv(OUT, index=False)
    print(f"Saved: {OUT}")
    print(f"assigned_rows={n_assigned}")
    print(f"mode={'all_open' if args.all else 'p1_only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
