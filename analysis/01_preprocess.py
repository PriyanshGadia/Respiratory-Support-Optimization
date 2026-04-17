#!/usr/bin/env python
# =============================================================================
# 01_preprocess.py  —  Steps 1 & 2: Preprocessing + cleaning all datasets
# Version: 1.0  |  2026-03-14
# Applies Protocol Section 4 QC and preprocessing; saves cleaned files.
# Run: python REBOOT/analysis/01_preprocess.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import glob
import json
import logging
import pickle
import numpy as np
import pandas as pd

import config as C
from lib.io import load_ccvw, load_simulation, load_vwd
from lib.qc import file_qc, preprocess_signal, breath_quality_flags

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("01_preprocess")

os.makedirs(C.LOGS_DIR,   exist_ok=True)
PREPROCESSED_DIR = os.path.join(C.ANALYSIS_DIR, "preprocessed")
os.makedirs(PREPROCESSED_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# CCVW preprocessing
# ---------------------------------------------------------------------------

def preprocess_ccvw() -> dict:
    log.info("Preprocessing CCVW-ICU dataset...")
    records = load_ccvw(C.CCVW_WAVEFORM_DIR, C.CCVW_MV_FILE)
    audit = []
    clean_records = {}

    for pid, df in sorted(records.items()):
        # File-level QC gate
        qc_res = file_qc(
            df, C.CCVW_FS,
            required_channels=["time", "flow", "paw", "pes"],
            fs_tol=C.FS_TOLERANCE,
            max_miss=C.MAX_MISSINGNESS,
            flatline_max_s=C.FLATLINE_MAX_S,
        )

        audit_row = {
            "patient_id": pid,
            "source":     "ccvw",
            "n_raw":      len(df),
            "qc_pass":    qc_res["pass"],
            "qc_reasons": "; ".join(qc_res["reasons"]),
            "fs_est":     qc_res["fs_estimated"],
        }

        if not qc_res["pass"]:
            log.warning("CCVW %s EXCLUDED: %s", pid, qc_res["reasons"])
            audit.append(audit_row)
            continue

        # Sample-level processing
        df_clean = preprocess_signal(
            df, fs=C.CCVW_FS,
            hampel_window=C.HAMPEL_WINDOW,
            hampel_thresh=C.HAMPEL_THRESHOLD,
            flow_lp_hz=C.FLOW_LOWPASS_HZ,
            pres_lp_hz=C.PRES_LOWPASS_HZ,
        )

        audit_row["n_clean"] = len(df_clean)
        audit.append(audit_row)
        clean_records[pid] = df_clean
        log.info("  CCVW %s: %d → %d samples (PASS)", pid, len(df), len(df_clean))

    # Save
    out_path = os.path.join(PREPROCESSED_DIR, "ccvw_clean.pkl")
    with open(out_path, "wb") as fh:
        pickle.dump(clean_records, fh)
    log.info("Saved CCVW clean records → %s", out_path)

    pd.DataFrame(audit).to_csv(
        os.path.join(C.LOGS_DIR, "preprocess_audit_ccvw.csv"), index=False
    )
    return clean_records


# ---------------------------------------------------------------------------
# Simulation preprocessing
# ---------------------------------------------------------------------------

def preprocess_simulation(max_runs: int = None) -> dict:
    log.info("Preprocessing simulation dataset...")
    sim_recs = load_simulation(
        C.SIM_WAVEFORMS_DIR, C.SIM_MECH_REF_DIR,
        C.SIM_PAT_REF_DIR,   C.SIM_SETTINGS_FILE
    )
    audit = []
    clean_records = {}

    ids = sorted(sim_recs.keys())
    if max_runs:
        ids = ids[:max_runs]

    for run_id in ids:
        rec = sim_recs[run_id]
        df  = rec["waveform"]

        # Estimate fs from time vector
        dts = np.diff(df["time"].values)
        dt  = float(np.median(dts)) if len(dts) > 0 else 0.01
        fs  = 1.0 / dt

        qc_res = file_qc(
            df, declared_fs=fs,
            required_channels=["time", "flow", "paw"],
            fs_tol=0.10,   # sim files may vary slightly
        )

        audit_row = {
            "run_id":   run_id,
            "source":   "simulation",
            "n_raw":    len(df),
            "fs_est":   fs,
            "qc_pass":  qc_res["pass"],
            "qc_reasons": "; ".join(qc_res["reasons"]),
        }

        if not qc_res["pass"]:
            audit.append(audit_row)
            continue

        df_clean = preprocess_signal(
            df, fs=fs,
            hampel_window=C.HAMPEL_WINDOW,
            hampel_thresh=C.HAMPEL_THRESHOLD,
            flow_lp_hz=C.FLOW_LOWPASS_HZ,
            pres_lp_hz=C.PRES_LOWPASS_HZ,
            apply_hampel=False,
        )

        audit_row["n_clean"] = len(df_clean)
        audit.append(audit_row)
        clean_records[run_id] = {
            "waveform": df_clean,
            "mech_ref": rec["mech_ref"],
            "pat_ref":  rec["pat_ref"],
            "settings": rec["settings"],
        }

    n_pass = sum(1 for r in audit if r["qc_pass"])
    log.info("  Simulation: %d / %d runs passed QC", n_pass, len(ids))

    out_path = os.path.join(PREPROCESSED_DIR, "simulation_clean.pkl")
    with open(out_path, "wb") as fh:
        pickle.dump(clean_records, fh)
    log.info("Saved simulation clean records → %s", out_path)

    pd.DataFrame(audit).to_csv(
        os.path.join(C.LOGS_DIR, "preprocess_audit_simulation.csv"), index=False
    )
    return clean_records


# ---------------------------------------------------------------------------
# VWD preprocessing
# ---------------------------------------------------------------------------

def preprocess_vwd() -> list:
    log.info("Preprocessing VWD (external) dataset...")
    recs = load_vwd(C.VWD_DIR, declared_fs=C.VWD_FS_DECLARED,
                   flow_scale=C.VWD_FLOW_SCALE)
    audit = []
    clean_recs = []

    for rec in recs:
        df = rec["df"]
        qc_res = file_qc(
            df, C.VWD_FS_DECLARED,
            required_channels=["time", "flow", "paw"],
            fs_tol=0.30,
        )

        audit_row = {
            "filename":  rec["filename"][:60],
            "patient_id": rec["patient_id"],
            "n_raw":     len(df),
            "qc_pass":   qc_res["pass"],
            "qc_reasons": "; ".join(qc_res["reasons"]),
        }

        if not qc_res["pass"]:
            audit.append(audit_row)
            continue

        df_clean = preprocess_signal(
            df, fs=C.VWD_FS_DECLARED,
            hampel_window=C.HAMPEL_WINDOW,
            hampel_thresh=C.HAMPEL_THRESHOLD,
            flow_lp_hz=C.FLOW_LOWPASS_HZ,
            pres_lp_hz=C.PRES_LOWPASS_HZ,
            apply_hampel=False,
        )
        audit_row["n_clean"] = len(df_clean)
        audit.append(audit_row)
        rec_out = dict(rec)
        rec_out["df"] = df_clean
        clean_recs.append(rec_out)

    n_pass = sum(1 for r in audit if r["qc_pass"])
    log.info("  VWD: %d / %d files passed QC", n_pass, len(recs))

    out_path = os.path.join(PREPROCESSED_DIR, "vwd_clean.pkl")
    with open(out_path, "wb") as fh:
        pickle.dump(clean_recs, fh)
    log.info("Saved VWD clean records → %s", out_path)

    pd.DataFrame(audit).to_csv(
        os.path.join(C.LOGS_DIR, "preprocess_audit_vwd.csv"), index=False
    )
    return clean_recs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Steps 1 & 2: Preprocessing")

    ccvw_clean = preprocess_ccvw()
    sim_clean  = preprocess_simulation()
    vwd_clean  = preprocess_vwd()

    summary = {
        "ccvw_n_clean":       len(ccvw_clean),
        "simulation_n_clean": len(sim_clean),
        "vwd_n_clean":        len(vwd_clean),
    }
    with open(os.path.join(C.LOGS_DIR, "preprocess_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Preprocessing complete: %s", summary)
