#!/usr/bin/env python
# =============================================================================
# 04_global_pipeline.py  —  Steps 6, 7 & 8: Generalized global pipeline
# Version: 1.0  |  2026-03-14
#
# Step 6: Re-write pipeline using smart header retrieval (operates on any dataset).
# Step 7: Test generalized model on global_train (simulation — known labels).
# Step 8: Domain-shift characterization on global_test (VWD — no Pes).
#
# Run: python REBOOT/analysis/04_global_pipeline.py
# =============================================================================

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import pickle
import numpy as np
import pandas as pd

import config as C
from lib.io           import load_vwd
from lib.segmentation import segment_breaths
from lib.events       import process_breath, detect_tcycle
from lib.features     import build_feature_row, get_feature_columns
from lib.models       import train_final_model, predict
from lib.metrics      import regression_metrics, bootstrap_ci
from lib.qc           import file_qc, preprocess_signal, breath_quality_flags

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("04_global_pipeline")

os.makedirs(C.LOGS_DIR, exist_ok=True)
MODELS_DIR = os.path.join(C.ANALYSIS_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# STEP 6: Generic header-adaptive dataset loader wrapper
# ---------------------------------------------------------------------------
#
# The process_generic_waveform() function operates on any DataFrame that
# provides the columns: time, flow, paw  (pes optional).
# It introspects the declared sampling rate from the time vector,
# selects the right ETS from dataset-level metadata when available,
# and runs the full protocol pipeline.
# ---------------------------------------------------------------------------

def detect_fs(df: pd.DataFrame) -> float:
    """Estimate fs from median time step."""
    dts = np.diff(df["time"].values)
    if len(dts) == 0:
        return 100.0
    dt = float(np.median(dts[dts > 0]))
    return 1.0 / dt


def resolve_ets(metadata: dict) -> tuple:
    """
    ETS hierarchy (Protocol Section 6.1 step 3):
      breath-level > session-level > patient-level > default
    Returns (ets_frac, ets_defaulted).
    """
    for key in ["ets_breath", "ets_session", "ets_patient", "ets"]:
        if key in metadata and metadata[key] is not None:
                        ets_candidate = metadata[key]
                        if np.isfinite(ets_candidate) and 0.05 < ets_candidate < 1.0:
                                return float(ets_candidate), False
    return C.ETS_DEFAULT, True


def process_generic_waveform(df: pd.DataFrame,
                              metadata: dict,
                              source_id: str,
                              source_tag: str) -> list:
    """
    Generalized breath processing for any waveform DataFrame.
    Performs header detection, QC, segmentation, event extraction & features.

    Parameters
    ----------
    df        : unified DataFrame (time, flow, paw, pes)
    metadata  : dict with optional keys: ets, ps, peep, fio2
    source_id : record identifier
    source_tag: dataset label string

    Returns
    -------
    list of feature row dicts
    """
    fs = detect_fs(df)

    # Required channels depend on source
    has_pes = ("pes" in df.columns) and (not df["pes"].isna().all())
    required = ["time", "flow", "paw"] + (["pes"] if has_pes else [])

    qc_check = file_qc(df, fs, required_channels=required, fs_tol=C.FS_TOLERANCE * 2)
    if not qc_check["pass"]:
        log.debug("Skipping %s (QC fail): %s", source_id, qc_check["reasons"])
        return []

    # Preprocessing
    df_clean = preprocess_signal(
        df, fs=fs,
        hampel_window=C.HAMPEL_WINDOW,
        hampel_thresh=C.HAMPEL_THRESHOLD,
        flow_lp_hz=C.FLOW_LOWPASS_HZ,
        pres_lp_hz=C.PRES_LOWPASS_HZ,
        apply_hampel=False,
    )

    ets_frac, ets_defaulted = resolve_ets(metadata)

    breaths = segment_breaths(
        df_clean, fs,
        eps=C.FLOW_EPS,
        insp_sustain_ms=C.INSP_SUSTAIN_MS,
        insp_dur_min_s=C.INSP_DUR_MIN_S,
        insp_dur_max_s=C.INSP_DUR_MAX_S,
        flow_peak_min=C.FLOW_PEAK_MIN,
    )

    feature_rows = []
    for breath in breaths:
        if breath["exclude"]:
            continue

        breath_event = process_breath(
            breath_info=breath,
            df=df_clean,
            fs=fs,
            ets_frac=ets_frac,
            ets_defaulted=ets_defaulted,
            pre_ms=C.PRE_WIN_MS,
            post_ms=C.POST_WIN_MS,
            confirm_n=C.TCYCLE_CONFIRM_N,
            tf_guard=C.TF_PAW_GUARD,
            event_dpl_min=C.EVENT_LABEL_DPL_MIN,
            event_slope_min=C.EVENT_LABEL_SLOPE_MIN,
            event_peak_ms=C.EVENT_PEAK_MAX_MS,
        )

        if breath_event.get("cycle_undefined") or breath_event.get("incomplete_window"):
            continue

        # Attach metadata
        for key in ["ps", "peep", "fio2", "ets"]:
            if key in metadata:
                breath_event[key] = metadata[key]

        breath_event["patient_id"] = source_id
        breath_event["source"] = source_tag

        t_cycle = breath_event["t_cycle"]
        time = df_clean["time"].values
        full_mask = (time >= t_cycle - C.PRE_WIN_MS / 1000.0) & \
                    (time <= t_cycle + C.POST_WIN_MS / 1000.0)
        waveform_window_df = df_clean[full_mask]

        include_clinical = any(k in metadata for k in ["ps", "peep", "fio2"])
        feature_row = build_feature_row(
            breath_event,
            waveform_window_df,
            fs,
            include_clinical=include_clinical,
        )
        feature_rows.append(feature_row)

    return feature_rows


# ---------------------------------------------------------------------------
# STEP 7: Global train — simulation dataset evaluation
# ---------------------------------------------------------------------------

def load_split(fname):
    path = os.path.join(C.SPLITS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found.")
    with open(path, "rb") as fh:
        return pickle.load(fh)


def process_simulation_runs(sim_clean: dict,
                             run_limit: int = None) -> pd.DataFrame:
    """
    Process all simulation runs using generic pipeline.
    Attaches ground-truth t_cycle from mechanical reference (tem column).
    """
    log.info("Processing simulation runs through generic pipeline...")
    all_rows = []
    run_ids = sorted(sim_clean.keys())
    if run_limit:
        run_ids = run_ids[:run_limit]

    for i, run_id in enumerate(run_ids):
        rec = sim_clean[run_id]
        df  = rec["waveform"]
        mec = rec.get("mech_ref", pd.DataFrame())
        st  = rec.get("settings", {})

        # Build metadata
        metadata = {
            "ps":   float(st.get("PipPEEP", np.nan)) if st.get("PipPEEP") else np.nan,
            "peep": float(st.get("PEEP", np.nan))    if st.get("PEEP")    else np.nan,
        }

        run_feature_rows = process_generic_waveform(df, metadata, run_id, "simulation")

        # Attach ground-truth t_cycle from mechanical reference
        # For each detected breath, find matching tem (cycle end time)
        if len(run_feature_rows) > 0 and len(mec) > 0:
            tem_vals = mec[C.SIM_MECH_TEM_COL].values if C.SIM_MECH_TEM_COL in mec.columns else np.array([])
            for feature_row in run_feature_rows:
                tc = feature_row.get("t_cycle", np.nan)
                if np.isfinite(tc) and len(tem_vals) > 0:
                    diffs = np.abs(tem_vals - tc)
                    nearest_idx = int(np.argmin(diffs))
                    feature_row["t_cycle_gt"] = float(tem_vals[nearest_idx])
                    feature_row["t_cycle_error_ms"] = float(diffs[nearest_idx] * 1000.0)
                else:
                    feature_row["t_cycle_gt"] = np.nan
                    feature_row["t_cycle_error_ms"] = np.nan

        all_rows.extend(run_feature_rows)

        if (i + 1) % 100 == 0:
            log.info("  Processed %d / %d simulation runs", i + 1, len(run_ids))

    if not all_rows:
        log.error("No valid simulation breaths processed!")
        return pd.DataFrame()

    df_out = pd.DataFrame(all_rows)
    log.info("Simulation feature table: %d breaths", len(df_out))
    return df_out


# ---------------------------------------------------------------------------
# STEP 7: Simulation Appendix C audit before pre-training
# ---------------------------------------------------------------------------

def run_simulation_audit(sim_features: pd.DataFrame,
                          mismatch_ms_threshold: float = C.SIM_TCYCLE_MISMATCH_MS,
                          mismatch_rate_max: float = C.SIM_MISMATCH_RATE_THRESHOLD) -> dict:
    """
    Appendix C: Stratified audit of 200 simulation breaths.
    Checks t_cycle agreement between provided label (tem) and protocol detector.
    """
    log.info("Running Simulation Label-Mapping Audit (Appendix C)...")

    if "t_cycle_error_ms" not in sim_features.columns:
        log.warning("t_cycle_error_ms not available; skipping audit.")
        return {"audit_skipped": True}

    valid = sim_features["t_cycle_error_ms"].notna()
    n_valid = valid.sum()

    if n_valid < 20:
        log.warning("Too few valid t_cycle comparisons (%d) for audit.", n_valid)
        return {"audit_skipped": True, "n_valid": int(n_valid)}

    n_audit = min(C.SIM_AUDIT_N, n_valid)
    audit_sample = sim_features[valid].sample(n=n_audit, random_state=C.RANDOM_SEED)

    # Mismatch criterion 1: |t_cycle_error_ms| > threshold
    mismatch_mask = audit_sample["t_cycle_error_ms"] > mismatch_ms_threshold
    mismatch_rate = float(mismatch_mask.mean())

    ci_lo = float(mismatch_rate - 1.96 * np.sqrt(mismatch_rate * (1 - mismatch_rate) / n_audit))
    ci_hi = float(mismatch_rate + 1.96 * np.sqrt(mismatch_rate * (1 - mismatch_rate) / n_audit))

    sim_pretrain_enabled = mismatch_rate <= mismatch_rate_max

    audit_summary = {
        "n_audited":          int(n_audit),
        "mismatch_rate":      round(mismatch_rate, 4),
        "mismatch_ci_95":     [round(ci_lo, 4), round(ci_hi, 4)],
        "threshold_ms":       mismatch_ms_threshold,
        "max_allowed_rate":   mismatch_rate_max,
        "pretrain_enabled":   sim_pretrain_enabled,
    }

    log.info("  Appendix C audit: mismatch_rate=%.3f (95%%CI %.3f–%.3f) | pre-train=%s",
             mismatch_rate, ci_lo, ci_hi, "ENABLED" if sim_pretrain_enabled else "DISABLED")

    audit_path = os.path.join(C.LOGS_DIR, "simulation_audit_results.json")
    with open(audit_path, "w") as fh:
        json.dump(audit_summary, fh, indent=2)

    return audit_summary


# ---------------------------------------------------------------------------
# STEP 7: Train generalized model on simulation, evaluate
# ---------------------------------------------------------------------------

def train_global_model(sim_features: pd.DataFrame,
                       local_model_feature_cols: list) -> tuple:
    """
    Train XGBoost on simulation data using the same feature set as the local model.
    Returns (model, feature_cols).
    """
    log.info("Training global model on simulation dataset...")

    # Use features available in simulation (no Pes in deployment features)
    available_cols = [c for c in local_model_feature_cols if c in sim_features.columns]
    missing = set(local_model_feature_cols) - set(available_cols)
    if missing:
        log.warning("Features not in simulation data (will pad NaN): %s", missing)
        for col in missing:
            sim_features[col] = np.nan
        available_cols = local_model_feature_cols

    # Use delta_paw_max as regression target when delta_pl_max is unavailable
    # (simulation has pmus → PL is computable)
    target_col = "y_regression" if "y_regression" in sim_features.columns else "delta_paw_max"
    valid_y = sim_features[target_col].notna().sum()
    log.info("  Simulation regression target '%s': %d valid samples", target_col, valid_y)

    if valid_y < 10:
        log.error("Insufficient valid targets for global training.")
        return None, available_cols

    model, cols = train_final_model(
        sim_features,
        feature_cols=available_cols,
        target_col=target_col,
        task="regression",
        param_grid=C.XGB_PARAM_GRID,
        seed=C.RANDOM_SEED,
    )

    model_path = os.path.join(MODELS_DIR, "global_xgb_regression.pkl")
    with open(model_path, "wb") as fh:
        pickle.dump({"model": model, "feature_cols": cols}, fh)
    log.info("  Saved global model → %s", model_path)

    return model, cols


# ---------------------------------------------------------------------------
# STEP 8: Domain-shift characterization on VWD
# ---------------------------------------------------------------------------

VWD_BATCH_SIZE = 20   # files per batch — limits peak memory usage


def process_vwd_records(vwd_data, model, feature_cols: list) -> dict:
    """
    Memory-efficient streaming VWD processing.
    Processes files in batches of VWD_BATCH_SIZE, scores each batch with
    `model`, and appends scored rows to the CSV incrementally.
    Returns score statistics dict (no in-memory DataFrame retained).
    """
    log.info("Processing VWD records (domain shift characterization) — "
             "batch size %d files...", VWD_BATCH_SIZE)

    if isinstance(vwd_data, dict) and vwd_data.get("split_type") == "vwd_pointer":
        vwd_clean = load_vwd(
            vwd_data.get("vwd_dir", C.VWD_DIR),
            declared_fs=vwd_data.get("declared_fs", C.VWD_FS_DECLARED),
            flow_scale=vwd_data.get("flow_scale", C.VWD_FLOW_SCALE),
            max_files=C.VWD_MAX_FILES,
        )
        log.info("Loaded %d VWD files (VWD_MAX_FILES=%s) for domain-shift run",
                 len(vwd_clean), C.VWD_MAX_FILES)
    else:
        vwd_clean = vwd_data

    vwd_scores_path = os.path.join(C.LOGS_DIR, "vwd_scores.csv")
    first_write = True
    n_ok = n_total_breaths = 0

    for batch_start in range(0, len(vwd_clean), VWD_BATCH_SIZE):
        vwd_batch = vwd_clean[batch_start: batch_start + VWD_BATCH_SIZE]
        batch_rows = []
        for record in vwd_batch:
            record_feature_rows = process_generic_waveform(
                record["df"], {},
                source_id=record["patient_id"],
                source_tag="vwd",
            )
            batch_rows.extend(record_feature_rows)
            if record_feature_rows:
                n_ok += 1

        if not batch_rows:
            continue

        batch_df = pd.DataFrame(batch_rows)

        # Score with global model
        avail = [c for c in feature_cols if c in batch_df.columns]
        for col in set(feature_cols) - set(avail):
            batch_df[col] = np.nan
        X_batch = batch_df[feature_cols].values.astype(np.float64)
        batch_df["model_score"] = predict(model, X_batch, task="regression")
        n_total_breaths += len(batch_df)

        # Append to CSV
        batch_df.to_csv(vwd_scores_path,
                        mode="w" if first_write else "a",
                        header=first_write,
                        index=False)
        first_write = False
        log.info("  Batch %d/%d done: %d breaths so far",
                 batch_start // VWD_BATCH_SIZE + 1,
                 (len(vwd_clean) + VWD_BATCH_SIZE - 1) // VWD_BATCH_SIZE,
                 n_total_breaths)

    if n_total_breaths == 0:
        log.warning("No valid VWD breaths processed.")
        return {"domain_shift": "no_data"}

    # Compute summary stats from saved CSV
    scores_df = pd.read_csv(vwd_scores_path, usecols=["model_score"])
    valid = scores_df["model_score"].dropna().values
    score_stats = {
        "n_breaths":     int(len(valid)),
        "mean":          float(np.mean(valid)),
        "std":           float(np.std(valid)),
        "p5":            float(np.percentile(valid, 5)),
        "p25":           float(np.percentile(valid, 25)),
        "median":        float(np.median(valid)),
        "p75":           float(np.percentile(valid, 75)),
        "p95":           float(np.percentile(valid, 95)),
        "n_high_score":  int((valid >= C.EVENT_LABEL_DPL_MIN).sum()),
    }
    log.info("  VWD domain shift: %d breaths from %d/%d files, "
             "mean_score=%.3f±%.3f",
             score_stats["n_breaths"], n_ok, len(vwd_clean),
             score_stats["mean"], score_stats["std"])

    return {"domain_shift_scores": score_stats}


def domain_shift_analysis(model, vwd_features: pd.DataFrame,
                           feature_cols: list) -> dict:
    """
    Protocol Section 10.2 — legacy single-call path (not used when process_vwd_records
    is called in streaming mode). Kept for compatibility.
    """
    if len(vwd_features) == 0:
        return {"domain_shift": "no_data"}

    available = [c for c in feature_cols if c in vwd_features.columns]
    for col in set(feature_cols) - set(available):
        vwd_features[col] = np.nan
    available = feature_cols

    X_vwd = vwd_features[available].values.astype(np.float64)
    scores = predict(model, X_vwd, task="regression")

    # Score distribution
    valid = np.isfinite(scores)
    score_stats = {
        "n_breaths":     int(valid.sum()),
        "mean":          float(np.mean(scores[valid])),
        "std":           float(np.std(scores[valid])),
        "p5":            float(np.percentile(scores[valid], 5)),
        "p25":           float(np.percentile(scores[valid], 25)),
        "median":        float(np.median(scores[valid])),
        "p75":           float(np.percentile(scores[valid], 75)),
        "p95":           float(np.percentile(scores[valid], 95)),
        "n_high_score":  int((scores[valid] >= C.EVENT_LABEL_DPL_MIN).sum()),
    }

    vwd_features["model_score"] = scores
    vwd_features.to_csv(os.path.join(C.LOGS_DIR, "vwd_scores.csv"), index=False)
    log.info("  VWD domain shift: %d breaths, mean_score=%.3f±%.3f",
             score_stats["n_breaths"], score_stats["mean"], score_stats["std"])

    return {"domain_shift_scores": score_stats}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Steps 6, 7 & 8: Global Pipeline")

    sim_clean  = load_split("global_train.pkl")
    vwd_data   = load_split("global_test.pkl")

    # Load local model feature cols
    local_model_path = os.path.join(MODELS_DIR, "local_xgb_regression.pkl")
    if not os.path.exists(local_model_path):
        raise FileNotFoundError("Local model not found. Run 03_local_pipeline.py first.")
    with open(local_model_path, "rb") as fh:
        local_bundle = pickle.load(fh)
    local_feature_cols = local_bundle["feature_cols"]

    simulation_features_path = os.path.join(C.LOGS_DIR, "simulation_features.csv")
    global_model_path = os.path.join(MODELS_DIR, "global_xgb_regression.pkl")

    # --- Step 7: Simulation processing & audit ---
    if os.path.exists(simulation_features_path):
        sim_features = pd.read_csv(simulation_features_path)
        log.info("Loaded cached simulation features: %d breaths", len(sim_features))
        audit = None
        audit_path = os.path.join(C.LOGS_DIR, "simulation_audit.json")
        if os.path.exists(audit_path):
            with open(audit_path, "r") as fh:
                audit = json.load(fh)
        else:
            audit = run_simulation_audit(sim_features)
            with open(audit_path, "w") as fh:
                json.dump(audit, fh, indent=2)
    else:
        sim_features = process_simulation_runs(sim_clean)

        if len(sim_features) == 0:
            log.error("No simulation features; cannot proceed to global training.")
            sys.exit(1)

        sim_features.to_csv(simulation_features_path, index=False)
        audit = run_simulation_audit(sim_features)
        with open(os.path.join(C.LOGS_DIR, "simulation_audit.json"), "w") as fh:
            json.dump(audit, fh, indent=2)

    if not audit.get("pretrain_enabled", True) and not audit.get("audit_skipped", False):
        log.warning("Simulation pre-training DISABLED (mismatch rate > %.0f%%). "
                    "Augmentation-only strategy per Protocol Section 13.2.",
                    C.SIM_MISMATCH_RATE_THRESHOLD * 100)

    # --- Step 7: Train or load global model ---
    if os.path.exists(global_model_path):
        with open(global_model_path, "rb") as fh:
            global_bundle = pickle.load(fh)
        global_model = global_bundle["model"]
        global_feature_cols = global_bundle["feature_cols"]
        log.info("Loaded cached global model from %s", global_model_path)
    else:
        global_model, global_feature_cols = train_global_model(sim_features, local_feature_cols)

        if global_model is None:
            log.error("Global model training failed.")
            sys.exit(1)

    # Evaluate global model on simulation itself (internal check)
    available = [c for c in global_feature_cols if c in sim_features.columns]
    target_col = "y_regression" if "y_regression" in sim_features.columns else "delta_paw_max"
    X_sim = sim_features[available].fillna(0).values
    y_sim = sim_features[target_col].values
    y_pred_sim = predict(global_model, X_sim, task="regression")
    valid = np.isfinite(y_sim) & np.isfinite(y_pred_sim)
    sim_train_metrics = regression_metrics(y_sim[valid], y_pred_sim[valid])
    log.info("  Global model on simulation (train) metrics: MAE=%.4f, R²=%.4f",
             sim_train_metrics.get("mae", np.nan), sim_train_metrics.get("r2", np.nan))

    # I stream this stage in batches so large external files don't force a
    # full in-memory frame during exploratory replay.
    # --- Step 8: Domain shift on VWD (streaming, memory-efficient) ---
    # process_vwd_records now handles loading, scoring each batch, and writing to CSV.
    # Returns a score statistics dict rather than a full in-memory DataFrame.
    domain_result = process_vwd_records(vwd_data, global_model, global_feature_cols)
    n_vwd_breaths = domain_result.get("domain_shift_scores", {}).get("n_breaths", 0)

    # Combined summary
    summary = {
        "simulation_audit": audit,
        "simulation_train_metrics": sim_train_metrics,
        "vwd_domain_shift": domain_result,
        "n_sim_breaths": len(sim_features),
        "n_vwd_breaths": n_vwd_breaths,
    }
    with open(os.path.join(C.LOGS_DIR, "global_pipeline_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    log.info("Steps 6–8 complete. Results → %s", C.LOGS_DIR)
