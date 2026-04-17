#!/usr/bin/env python
# =============================================================================
# 00_dataset_analysis.py  —  Step 0 & 1: Comprehensive dataset profiling
# Version: 1.0  |  2026-03-14
# Analyzes all four datasets; outputs reports to logs/.
# Run: python REBOOT/analysis/00_dataset_analysis.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import numpy as np
import pandas as pd

import config as C
from lib.io import load_ccvw, load_simulation, load_vwd, load_cpap
from lib.qc import file_qc

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("00_dataset_analysis")

os.makedirs(C.LOGS_DIR,    exist_ok=True)
os.makedirs(C.FIGURES_DIR, exist_ok=True)
os.makedirs(C.SPLITS_DIR,  exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def describe_df(df: pd.DataFrame, name: str) -> dict:
    numeric = df.select_dtypes(include=np.number)
    stats = {}
    for col in numeric.columns:
        arr = numeric[col].dropna().values
        if len(arr) == 0:
            continue
        stats[col] = {
            "n":      int(len(arr)),
            "n_nan":  int(numeric[col].isna().sum()),
            "mean":   float(np.mean(arr)),
            "std":    float(np.std(arr)),
            "min":    float(np.min(arr)),
            "p5":     float(np.percentile(arr, 5)),
            "p25":    float(np.percentile(arr, 25)),
            "median": float(np.median(arr)),
            "p75":    float(np.percentile(arr, 75)),
            "p95":    float(np.percentile(arr, 95)),
            "max":    float(np.max(arr)),
        }
    log.info("  %s — %d rows x %d cols", name, len(df), len(df.columns))
    return stats


# ---------------------------------------------------------------------------
# 1. CCVW-ICU (Primary clinical dataset)
# ---------------------------------------------------------------------------

def analyze_ccvw():
    log.info("=" * 60)
    log.info("CCVW-ICU Analysis")
    log.info("=" * 60)

    records = load_ccvw(C.CCVW_WAVEFORM_DIR, C.CCVW_MV_FILE)
    report = {}

    all_stats = []
    for pid, df in sorted(records.items()):
        dt = float(np.median(np.diff(df["time"].values)))
        fs_est = 1.0 / dt if dt > 0 else np.nan
        dur_s  = float(df["time"].values[-1] - df["time"].values[0])

        res = file_qc(
            df, C.CCVW_FS,
            required_channels=["time", "flow", "paw", "pes"],
            fs_tol=C.FS_TOLERANCE,
            max_miss=C.MAX_MISSINGNESS,
            flatline_max_s=C.FLATLINE_MAX_S,
        )

        row = {
            "patient_id":   pid,
            "n_samples":    len(df),
            "duration_s":   dur_s,
            "fs_estimated": fs_est,
            "qc_pass":      res["pass"],
            "qc_reasons":   "; ".join(res["reasons"]),
            "ps":           float(df["ps"].iloc[0]) if "ps" in df.columns else np.nan,
            "peep":         float(df["peep"].iloc[0]) if "peep" in df.columns else np.nan,
            "fio2":         float(df["fio2"].iloc[0]) if "fio2" in df.columns else np.nan,
            "ets":          float(df["ets"].iloc[0]) if "ets" in df.columns else np.nan,
        }

        for col in ["flow", "paw", "pes"]:
            arr = df[col].dropna().values
            if len(arr):
                row[f"{col}_mean"] = float(np.mean(arr))
                row[f"{col}_std"]  = float(np.std(arr))
                row[f"{col}_min"]  = float(np.min(arr))
                row[f"{col}_max"]  = float(np.max(arr))

        all_stats.append(row)
        log.info("  %s: %d samples, %.1f s, fs~%.1f Hz, QC=%s",
                 pid, len(df), dur_s, fs_est, "PASS" if res["pass"] else "FAIL")

    df_out = pd.DataFrame(all_stats)
    df_out.to_csv(os.path.join(C.LOGS_DIR, "ccvw_dataset_summary.csv"), index=False)
    log.info("Saved CCVW summary → logs/ccvw_dataset_summary.csv")
    return df_out


# ---------------------------------------------------------------------------
# 2. Simulation dataset
# ---------------------------------------------------------------------------

def analyze_simulation():
    log.info("=" * 60)
    log.info("Simulation Dataset Analysis")
    log.info("=" * 60)

    sim_recs = load_simulation(
        C.SIM_WAVEFORMS_DIR, C.SIM_MECH_REF_DIR,
        C.SIM_PAT_REF_DIR,   C.SIM_SETTINGS_FILE
    )

    all_stats = []
    n_pass = 0
    settings_sample = []

    for run_id, rec in sorted(sim_recs.items()):
        df  = rec["waveform"]
        mec = rec["mech_ref"]
        pat = rec["pat_ref"]
        st  = rec["settings"]

        dt = float(np.median(np.diff(df["time"].values))) if len(df) > 1 else np.nan
        fs_est = 1.0 / dt if dt and dt > 0 else np.nan
        dur_s  = float(df["time"].values[-1] - df["time"].values[0]) if len(df) > 1 else 0.0
        n_mech = len(mec)
        n_pat  = len(pat)

        res = file_qc(
            df, declared_fs=100.0,
            required_channels=["time", "flow", "paw"],
            fs_tol=C.FS_TOLERANCE,
        )
        if res["pass"]:
            n_pass += 1

        row = {
            "run_id":       run_id,
            "n_samples":    len(df),
            "duration_s":   dur_s,
            "fs_estimated": fs_est,
            "n_mech_cycles": n_mech,
            "n_pat_breaths": n_pat,
            "qc_pass":      res["pass"],
            "patient_type": st.get("patient_type", ""),
            "PS":           st.get("PipPEEP", np.nan),
            "PEEP":         st.get("PEEP", np.nan),
            "PmusA":        st.get("PmusA", np.nan),
        }
        all_stats.append(row)

        if len(settings_sample) < 5:
            settings_sample.append(st)

    log.info("  Total runs: %d | QC pass: %d", len(sim_recs), n_pass)

    df_out = pd.DataFrame(all_stats)
    df_out.to_csv(os.path.join(C.LOGS_DIR, "simulation_dataset_summary.csv"), index=False)
    log.info("Saved simulation summary → logs/simulation_dataset_summary.csv")

    # Settings distribution
    settings_df = pd.read_csv(C.SIM_SETTINGS_FILE)
    settings_df.describe().to_csv(
        os.path.join(C.LOGS_DIR, "simulation_settings_stats.csv")
    )
    log.info("Patient types: %s", settings_df["patient_type"].value_counts().to_dict()
             if "patient_type" in settings_df.columns else "N/A")

    return df_out


# ---------------------------------------------------------------------------
# 3. VWD (Puritan Bennett external validation)
# ---------------------------------------------------------------------------

def analyze_vwd():
    log.info("=" * 60)
    log.info("Ventilator Waveform Data (External) Analysis")
    log.info("=" * 60)

    recs = load_vwd(C.VWD_DIR, declared_fs=C.VWD_FS_DECLARED,
                   flow_scale=C.VWD_FLOW_SCALE)

    all_stats = []
    for rec in recs:
        df = rec["df"]
        n = len(df)
        dur_s = float(df["time"].values[-1]) if n > 0 else 0.0

        res = file_qc(
            df, C.VWD_FS_DECLARED,
            required_channels=["time", "flow", "paw"],
            fs_tol=0.30,   # looser tolerance; VWD fs not precisely declared
        )

        all_stats.append({
            "filename":      rec["filename"][:50],
            "patient_id":    rec["patient_id"],
            "n_samples":     n,
            "duration_s":    dur_s,
            "declared_n":    rec.get("declared_n"),
            "qc_pass":       res["pass"],
            "qc_reasons":    "; ".join(res["reasons"]),
            "flow_min":      float(df["flow"].min()) if n else np.nan,
            "flow_max":      float(df["flow"].max()) if n else np.nan,
            "paw_min":       float(df["paw"].min())  if n else np.nan,
            "paw_max":       float(df["paw"].max())  if n else np.nan,
        })

    df_out = pd.DataFrame(all_stats)
    n_pass = df_out["qc_pass"].sum()
    log.info("  Total files: %d | QC pass: %d", len(df_out), n_pass)
    df_out.to_csv(os.path.join(C.LOGS_DIR, "vwd_dataset_summary.csv"), index=False)
    log.info("Saved VWD summary → logs/vwd_dataset_summary.csv")
    return df_out


# ---------------------------------------------------------------------------
# 4. CPAP dataset (contextual)
# ---------------------------------------------------------------------------

def analyze_cpap():
    log.info("=" * 60)
    log.info("CPAP Dataset Analysis (contextual)")
    log.info("=" * 60)

    records = load_cpap(C.CPAP_DIR)
    all_stats = []
    for sid, df in sorted(records.items()):
        dt   = float(np.median(np.diff(df["time"].values))) if len(df) > 1 else np.nan
        fs   = 1.0 / dt if dt and dt > 0 else np.nan
        dur_s = float(df["time"].values[-1] - df["time"].values[0]) if len(df) > 1 else 0.0

        res = file_qc(df, C.CPAP_FS,
                      required_channels=["time", "flow", "paw"],
                      fs_tol=C.FS_TOLERANCE)

        all_stats.append({
            "subject_id":   sid,
            "n_samples":    len(df),
            "duration_s":   dur_s,
            "fs_estimated": fs,
            "qc_pass":      res["pass"],
        })

    df_out = pd.DataFrame(all_stats)
    n_pass = df_out["qc_pass"].sum()
    log.info("  Total subjects: %d | QC pass: %d", len(df_out), n_pass)
    df_out.to_csv(os.path.join(C.LOGS_DIR, "cpap_dataset_summary.csv"), index=False)
    return df_out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Step 0/1: Dataset Analysis")

    df_ccvw = analyze_ccvw()
    df_sim  = analyze_simulation()
    df_vwd  = analyze_vwd()
    df_cpap = analyze_cpap()

    # Master summary
    master = {
        "ccvw": {
            "n_patients":    len(df_ccvw),
            "n_qc_pass":     int(df_ccvw["qc_pass"].sum()),
            "total_samples": int(df_ccvw["n_samples"].sum()),
        },
        "simulation": {
            "n_runs":       len(df_sim),
            "n_qc_pass":    int(df_sim["qc_pass"].sum()),
        },
        "vwd": {
            "n_files":      len(df_vwd),
            "n_qc_pass":    int(df_vwd["qc_pass"].sum()),
        },
        "cpap": {
            "n_subjects":   len(df_cpap),
            "n_qc_pass":    int(df_cpap["qc_pass"].sum()),
        },
    }

    out_path = os.path.join(C.LOGS_DIR, "dataset_master_summary.json")
    with open(out_path, "w") as fh:
        json.dump(master, fh, indent=2)

    log.info("=" * 60)
    log.info("Dataset Analysis Complete. Summary:")
    for ds, stats in master.items():
        log.info("  %s: %s", ds, stats)
    log.info("All reports → %s", C.LOGS_DIR)
