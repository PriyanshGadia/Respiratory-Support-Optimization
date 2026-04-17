#!/usr/bin/env python
# =============================================================================
# 02_split.py  —  Step 3: Split into 4 sub-datasets
# Version: 1.0  |  2026-03-14
#
# Creates four canonical splits:
#   local_train  — CCVW P01–P05 (primary model development, Pes available)
#   local_test   — CCVW P06–P07 (held-out local validation)
#   global_train — Simulation dataset (pre-training + generalization)
#   global_test  — VWD external (domain-shift characterization, no Pes)
#
# Saves indices / keys to splits/ so downstream scripts always use the same split.
# Run: python REBOOT/analysis/02_split.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import pickle
import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("02_split")

os.makedirs(C.SPLITS_DIR, exist_ok=True)
PREPROCESSED_DIR = os.path.join(C.ANALYSIS_DIR, "preprocessed")


def load_preprocessed(fname):
    path = os.path.join(PREPROCESSED_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run 01_preprocess.py first."
        )
    with open(path, "rb") as fh:
        return pickle.load(fh)


def main():
    log.info("Phase 2 — Step 3: Dataset Splitting")

    # Load preprocessed
    ccvw_clean = load_preprocessed("ccvw_clean.pkl")
    sim_clean  = load_preprocessed("simulation_clean.pkl")

    # -----------------------------------------------------------------------
    # CCVW splits
    # -----------------------------------------------------------------------
    all_ccvw_pids = sorted(ccvw_clean.keys())
    local_train_pids = [p for p in C.LOCAL_TRAIN_PATIENTS if p in all_ccvw_pids]
    local_test_pids  = [p for p in C.LOCAL_TEST_PATIENTS  if p in all_ccvw_pids]

    missing_train = set(C.LOCAL_TRAIN_PATIENTS) - set(all_ccvw_pids)
    missing_test  = set(C.LOCAL_TEST_PATIENTS)  - set(all_ccvw_pids)

    if missing_train:
        log.warning("Local train patients missing from cleaned data: %s", missing_train)
    if missing_test:
        log.warning("Local test patients missing from cleaned data: %s", missing_test)

    # Save local splits
    local_train_data = {p: ccvw_clean[p] for p in local_train_pids}
    local_test_data  = {p: ccvw_clean[p] for p in local_test_pids}

    with open(os.path.join(C.SPLITS_DIR, "local_train.pkl"), "wb") as fh:
        pickle.dump(local_train_data, fh)
    with open(os.path.join(C.SPLITS_DIR, "local_test.pkl"), "wb") as fh:
        pickle.dump(local_test_data, fh)

    # -----------------------------------------------------------------------
    # Global train = all simulation runs
    # -----------------------------------------------------------------------
    global_train_ids = sorted(sim_clean.keys())

    with open(os.path.join(C.SPLITS_DIR, "global_train.pkl"), "wb") as fh:
        pickle.dump(sim_clean, fh)

    # -----------------------------------------------------------------------
    # Global test = all VWD records
    # -----------------------------------------------------------------------
    vwd_meta = {
        "split_type": "vwd_pointer",
        "preprocessed_path": os.path.join(PREPROCESSED_DIR, "vwd_clean.pkl"),
        "vwd_dir": C.VWD_DIR,
        "declared_fs": C.VWD_FS_DECLARED,
        "flow_scale": C.VWD_FLOW_SCALE,
    }

    n_vwd_files = np.nan
    vwd_audit_path = os.path.join(C.LOGS_DIR, "preprocess_audit_vwd.csv")
    if os.path.exists(vwd_audit_path):
        vwd_audit = pd.read_csv(vwd_audit_path)
        if "qc_pass" in vwd_audit.columns:
            n_vwd_files = int(vwd_audit["qc_pass"].sum())
        else:
            n_vwd_files = int(len(vwd_audit))

    with open(os.path.join(C.SPLITS_DIR, "global_test.pkl"), "wb") as fh:
        pickle.dump(vwd_meta, fh)

    # -----------------------------------------------------------------------
    # Save split manifest
    # -----------------------------------------------------------------------
    manifest = {
        "local_train": {
            "patients":  local_train_pids,
            "n_patients": len(local_train_pids),
            "n_samples":  sum(len(local_train_data[p]) for p in local_train_pids),
            "note":      "CCVW-ICU PSV+Pes, 200 Hz, for LOPO-CV model development",
        },
        "local_test": {
            "patients":  local_test_pids,
            "n_patients": len(local_test_pids),
            "n_samples":  sum(len(local_test_data[p]) for p in local_test_pids),
            "note":      "CCVW-ICU PSV+Pes, 200 Hz, held-out local test",
        },
        "global_train": {
            "n_runs":    len(global_train_ids),
            "run_ids_sample": global_train_ids[:5],
            "note":      "Simulation PSV 1405 runs, with ground-truth t_cycle (tem)",
        },
        "global_test": {
            "n_files":   int(n_vwd_files) if np.isfinite(n_vwd_files) else None,
            "note":      "VWD Puritan Bennett, ~50 Hz, no Pes — domain shift only",
        },
    }

    manifest_path = os.path.join(C.SPLITS_DIR, "split_manifest.json")
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    log.info("Split manifest saved → %s", manifest_path)
    for split_name, info in manifest.items():
        log.info("  %-16s: %s", split_name, {k: v for k, v in info.items() if k != "run_ids_sample"})

    log.info("Step 3 complete. All splits saved to %s", C.SPLITS_DIR)


if __name__ == "__main__":
    main()
