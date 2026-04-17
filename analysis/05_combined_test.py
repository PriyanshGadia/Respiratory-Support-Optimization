#!/usr/bin/env python
# =============================================================================
# 05_combined_test.py  —  Step 9: Combined single dataset test
# Version: 1.0  |  2026-03-14
#
# Loads both local and global models; tests on the combined full CCVW dataset
# (all 7 patients), then reports unified metrics and validates final gate.
# Run: python REBOOT/analysis/05_combined_test.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import pickle
import numpy as np
import pandas as pd

import config as C
from lib.metrics import regression_metrics, classification_metrics, bootstrap_ci

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("05_combined_test")

os.makedirs(C.LOGS_DIR, exist_ok=True)
MODELS_DIR = os.path.join(C.ANALYSIS_DIR, "models")


def load_model(fname):
    path = os.path.join(MODELS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model {path} not found.")
    with open(path, "rb") as fh:
        bundle = pickle.load(fh)
    return bundle["model"], bundle["feature_cols"]


def load_feature_csv(fname):
    path = os.path.join(C.LOGS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Feature file {path} not found. Run 03_local_pipeline.py first.")
    return pd.read_csv(path)


def evaluate_model_on_df(model, feature_cols, df, model_name="model") -> dict:
    avail = [c for c in feature_cols if c in df.columns]
    missing = set(feature_cols) - set(avail)
    if missing:
        for col in missing:
            df[col] = np.nan
        avail = feature_cols

    X = df[avail].values.astype(np.float64)
    y_true = df["y_regression"].values.astype(np.float64)
    y_pred = model.predict(X) if hasattr(model, "predict") else np.full(len(X), np.nan)

    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    metrics = regression_metrics(y_true[valid], y_pred[valid])

    log.info("  %s — n=%d | MAE=%.4f | RMSE=%.4f | R²=%.4f | CCC=%.4f",
             model_name, metrics.get("n", 0),
             metrics.get("mae", np.nan), metrics.get("rmse", np.nan),
             metrics.get("r2", np.nan),  metrics.get("ccc", np.nan))

    # Per-patient breakdown
    per_patient = []
    for pid, grp in df.groupby("patient_id"):
        Xp = grp[avail].values.astype(np.float64)
        yp_true = grp["y_regression"].values.astype(np.float64)
        yp_pred = model.predict(Xp)
        vm = np.isfinite(yp_true) & np.isfinite(yp_pred)
        pm = regression_metrics(yp_true[vm], yp_pred[vm])
        pm["patient_id"] = pid
        per_patient.append(pm)

    return {"overall": metrics, "per_patient": per_patient,
            "y_pred": y_pred, "y_true": y_true}


def main():
    log.info("Phase 2 — Step 9: Combined Dataset Test")

    # Load models
    local_model,  local_feat_cols  = load_model("local_xgb_regression.pkl")
    global_model, global_feat_cols = load_model("global_xgb_regression.pkl")

    # Load all feature data
    train_feat = load_feature_csv("local_train_features.csv")
    test_feat  = load_feature_csv("local_test_features.csv")

    # Combine into one full CCVW feature table
    combined = pd.concat([train_feat, test_feat], ignore_index=True)
    log.info("Combined CCVW dataset: %d breaths, %d patients",
             len(combined), combined["patient_id"].nunique())

    # --- Local model on combined ---
    log.info("Evaluating LOCAL model on combined CCVW...")
    local_res = evaluate_model_on_df(local_model, local_feat_cols, combined.copy(),
                                      model_name="local_model")

    # --- Global model on combined ---
    log.info("Evaluating GLOBAL model on combined CCVW...")
    global_res = evaluate_model_on_df(global_model, global_feat_cols, combined.copy(),
                                       model_name="global_model")

    # --- Bootstrap CIs ---
    for res_name, res in [("local", local_res), ("global", global_res)]:
        yt = res["y_true"]
        yp = res["y_pred"]
        vm = np.isfinite(yt) & np.isfinite(yp)
        ci_mae = bootstrap_ci(yt[vm], yp[vm],
                              metric_fn=lambda y, p: regression_metrics(y, p)["mae"],
                              seed=C.RANDOM_SEED)
        ci_r2  = bootstrap_ci(yt[vm], yp[vm],
                              metric_fn=lambda y, p: regression_metrics(y, p)["r2"],
                              seed=C.RANDOM_SEED)
        res["ci_mae"] = ci_mae
        res["ci_r2"]  = ci_r2
        log.info("  %s | MAE 95%%CI=[%.4f, %.4f] | R² 95%%CI=[%.4f, %.4f]",
                 res_name,
                 ci_mae.get("lo", np.nan), ci_mae.get("hi", np.nan),
                 ci_r2.get("lo", np.nan),  ci_r2.get("hi", np.nan))

    # --- Combined predictions file ---
    combined["local_pred"]  = local_res["y_pred"]
    combined["global_pred"] = global_res["y_pred"]
    combined.to_csv(os.path.join(C.LOGS_DIR, "combined_predictions.csv"), index=False)

    # Per-patient summary
    pp_rows = []
    for pid, grp in combined.groupby("patient_id"):
        pp_rows.append({
            "patient_id": pid,
            "n_breaths":  len(grp),
            "local_mae":  regression_metrics(
                grp["y_regression"].values,
                grp["local_pred"].values
            ).get("mae", np.nan),
            "global_mae": regression_metrics(
                grp["y_regression"].values,
                grp["global_pred"].values
            ).get("mae", np.nan),
        })
    df_pp = pd.DataFrame(pp_rows)
    df_pp.to_csv(os.path.join(C.LOGS_DIR, "combined_per_patient.csv"), index=False)
    log.info("Per-patient combined:\n%s", df_pp.to_string(index=False))

    # --- Validation gate ---
    local_mae  = local_res["overall"].get("mae", np.inf)
    global_mae = global_res["overall"].get("mae", np.inf)
    gate_pass  = (local_mae < 3.0) and (global_mae < 5.0)

    if gate_pass:
        log.info("COMBINED VALIDATION GATE: PASSED "
                 "(local_mae=%.3f, global_mae=%.3f)", local_mae, global_mae)
    else:
        log.warning("COMBINED VALIDATION GATE: FAILED "
                    "(local_mae=%.3f, global_mae=%.3f)", local_mae, global_mae)

    # Save summary
    summary = {
        "local_overall":       local_res["overall"],
        "global_overall":      global_res["overall"],
        "local_ci_mae":        local_res["ci_mae"],
        "global_ci_mae":       global_res["ci_mae"],
        "local_ci_r2":         local_res["ci_r2"],
        "global_ci_r2":        global_res["ci_r2"],
        "combined_gate_pass":  gate_pass,
        "n_total_breaths":     len(combined),
    }
    with open(os.path.join(C.LOGS_DIR, "combined_test_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    log.info("Step 9 complete → %s", C.LOGS_DIR)


if __name__ == "__main__":
    main()
