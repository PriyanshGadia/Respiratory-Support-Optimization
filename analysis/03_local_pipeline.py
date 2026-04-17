#!/usr/bin/env python
# =============================================================================
# 03_local_pipeline.py  —  Steps 4 & 5: Local tailored pipeline
# Version: 1.0  |  2026-03-14
#
# Operates exclusively on the LOCAL TRAIN dataset (CCVW P01-P05).
# 1. Segment breaths
# 2. Detect t_cycle + extract event windows
# 3. Compute PL, features, binary labels
# 4. Run LOPO-CV with XGBoost (primary) and record metrics
# 5. Test against LOCAL TEST (P06-P07)
#
# All thresholds come from config.py (tailored to CCVW 200 Hz characteristics).
# Run: python REBOOT/analysis/03_local_pipeline.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import pickle
import numpy as np
import pandas as pd

import config as C
from lib.segmentation import segment_breaths
from lib.events       import process_breath
from lib.features     import build_feature_row, get_feature_columns
from lib.models       import (
    run_lopo_cv,
    train_final_model,
    predict,
    train_regression_pipeline,
    predict_with_uncertainty,
    compute_permutation_importance,
    lopo_splits,
    QuantileForestRegressor,
    HierarchicalBayesRegressor,
)
from lib.metrics      import regression_metrics, classification_metrics, bootstrap_ci
from lib.qc           import breath_quality_flags

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("03_local_pipeline")

os.makedirs(C.LOGS_DIR, exist_ok=True)
PREPROCESSED_DIR = os.path.join(C.ANALYSIS_DIR, "preprocessed")
MODELS_DIR       = os.path.join(C.ANALYSIS_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

EXPLORATORY_EXTRA_FEATURES = [
    "paw_flow_loop_area",
    "paw_flow_corr",
    "d2Paw_dt2_max",
    "paw_spectral_centroid_hz",
    "flow_time_product",
    "paw_stress_index",
]


def load_split(fname):
    path = os.path.join(C.SPLITS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found. Run 01_preprocess.py and 02_split.py first.")
    with open(path, "rb") as fh:
        return pickle.load(fh)


# ---------------------------------------------------------------------------
# Process a single CCVW patient record → list of event feature rows
# ---------------------------------------------------------------------------

def process_ccvw_patient(pid: str, df: pd.DataFrame, fs: float = None):
    """
    Full processing pipeline for one CCVW patient.
    Returns list of feature dicts (one per valid breath).
    """
    if fs is None:
        dts = np.diff(df["time"].values)
        fs  = 1.0 / float(np.median(dts)) if len(dts) > 0 else C.CCVW_FS

    # ETS from patient metadata
    ets_frac = float(df["ets"].iloc[0]) if "ets" in df.columns and not pd.isna(df["ets"].iloc[0]) else None
    ets_defaulted = False
    if ets_frac is None:
        ets_frac = C.ETS_DEFAULT
        ets_defaulted = True

    # Breath segmentation
    breaths = segment_breaths(
        df, fs,
        eps=C.FLOW_EPS,
        insp_sustain_ms=C.INSP_SUSTAIN_MS,
        insp_dur_min_s=C.INSP_DUR_MIN_S,
        insp_dur_max_s=C.INSP_DUR_MAX_S,
        flow_peak_min=C.FLOW_PEAK_MIN,
    )

    feature_rows = []
    n_excluded = 0
    n_cycle_undef = 0
    n_incomplete = 0
    n_low_quality_flow = 0
    n_low_quality_paw = 0
    n_low_quality_pes = 0

    for breath in breaths:
        if breath["exclude"]:
            n_excluded += 1
            continue

        # Slip per-breath clinical metadata onto df for process_breath
        event_dict = process_breath(
            breath_info=breath,
            df=df,
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

        if event_dict.get("cycle_undefined"):
            n_cycle_undef += 1
            continue
        if event_dict.get("incomplete_window"):
            n_incomplete += 1
            continue

        # Breath-level quality flags
        start = breath["insp_start_idx"]
        end   = breath["breath_end_idx"]
        breath_df = df.iloc[start:end + 1]
        flags = breath_quality_flags(
            breath_df, fs,
            hampel_window=C.HAMPEL_WINDOW,
            hampel_thresh=C.HAMPEL_THRESHOLD,
            bad_frac=C.HAMPEL_BREATH_FRAC,
            flatline_ms=C.FLATLINE_BREATH_MS,
            pre_ms=C.PRE_WIN_MS,
            post_ms=C.POST_WIN_MS,
            t_cycle=event_dict.get("t_cycle"),
            apply_hampel=False,
        )

        # Primary analysis excludes any breath with required-channel quality flag
        # (Protocol §4.3: Pes is a required channel for CCVW-ICU)
        low_flow = bool(flags.get("low_quality_flow"))
        low_paw = bool(flags.get("low_quality_paw"))
        low_pes = bool(flags.get("low_quality_pes"))
        if low_flow:
            n_low_quality_flow += 1
        if low_paw:
            n_low_quality_paw += 1
        if low_pes:
            n_low_quality_pes += 1

        if low_flow or low_paw or low_pes:
            continue

        # Build feature row (use full [-pre, +post] window)
        t_cycle = event_dict["t_cycle"]
        time = df["time"].values
        full_mask = (time >= t_cycle - C.PRE_WIN_MS / 1000.0) & \
                    (time <= t_cycle + C.POST_WIN_MS / 1000.0)
        full_win_df = df[full_mask]

        # Attach clinical metadata to event dict
        for col in ["ps", "peep", "fio2", "ets"]:
            if col in df.columns:
                event_dict[col] = float(df[col].iloc[0]) if not pd.isna(df[col].iloc[0]) else np.nan

        row = build_feature_row(event_dict, full_win_df, fs, include_clinical=True)
        row["patient_id"] = pid
        row["low_quality_pes"] = flags.get("low_quality_pes", False)
        feature_rows.append(row)

    n_segmented = len(breaths)
    n_quality_excluded = n_low_quality_flow + n_low_quality_paw + n_low_quality_pes
    stats = {
        "patient_id": pid,
        "n_segmented": int(n_segmented),
        "n_excluded_segmentation": int(n_excluded),
        "n_cycle_undefined": int(n_cycle_undef),
        "n_incomplete_window": int(n_incomplete),
        "n_low_quality_flow": int(n_low_quality_flow),
        "n_low_quality_paw": int(n_low_quality_paw),
        "n_low_quality_pes": int(n_low_quality_pes),
        "n_quality_excluded_total": int(n_quality_excluded),
        "n_valid": int(len(feature_rows)),
        "retained_rate": float(len(feature_rows) / n_segmented) if n_segmented else np.nan,
    }

    log.info("  %s: segmented=%d, seg_excl=%d, cycle_undef=%d, incomplete=%d, quality_excl=%d, valid=%d",
             pid, n_segmented, n_excluded, n_cycle_undef, n_incomplete,
             n_quality_excluded, len(feature_rows))
    return feature_rows, stats


# ---------------------------------------------------------------------------
# Build full feature table from a dict of patients
# ---------------------------------------------------------------------------

def build_features_table(patient_dict: dict, fs: float = None,
                          label: str = "dataset"):
    all_rows = []
    stats_rows = []
    for pid, df in sorted(patient_dict.items()):
        rows, stats = process_ccvw_patient(pid, df, fs)
        all_rows.extend(rows)
        stats_rows.append(stats)

    if not all_rows:
        log.error("No valid breaths found in %s!", label)
        return pd.DataFrame(), pd.DataFrame(stats_rows)

    features_df = pd.DataFrame(all_rows)
    log.info("%s: %d total valid breaths in feature table", label, len(features_df))

    # Log event label balance
    if "event_positive" in features_df.columns:
        pos = features_df["event_positive"].sum()
        total = features_df["event_positive"].notna().sum()
        log.info("  Event label balance: %d pos / %d total (%.1f%%)",
                 pos, total, 100 * pos / total if total else 0)

    # Log Delta PL distribution
    if "delta_pl_max" in features_df.columns:
        vals = features_df["delta_pl_max"].dropna()
        if len(vals):
            log.info("  delta_pl_max: mean=%.3f ± %.3f cmH2O (n=%d)",
                     vals.mean(), vals.std(), len(vals))

    stats_df = pd.DataFrame(stats_rows)
    if not stats_df.empty:
        totals = {
            "n_segmented": int(stats_df["n_segmented"].sum()),
            "n_valid": int(stats_df["n_valid"].sum()),
            "n_excluded_segmentation": int(stats_df["n_excluded_segmentation"].sum()),
            "n_cycle_undefined": int(stats_df["n_cycle_undefined"].sum()),
            "n_incomplete_window": int(stats_df["n_incomplete_window"].sum()),
            "n_quality_excluded_total": int(stats_df["n_quality_excluded_total"].sum()),
        }
        rate = (totals["n_valid"] / totals["n_segmented"]) if totals["n_segmented"] else np.nan
        log.info("%s exclusions: segmented=%d, valid=%d, retained=%.1f%%, quality_excluded=%d",
                 label, totals["n_segmented"], totals["n_valid"], 100 * rate if np.isfinite(rate) else np.nan,
                 totals["n_quality_excluded_total"])

    return features_df, stats_df


# ---------------------------------------------------------------------------
# LOPO-CV  (local train only)
# ---------------------------------------------------------------------------

def run_local_lopo(features_df: pd.DataFrame) -> dict:
    log.info("Running LOPO-CV on local train set...")
    all_cols = get_feature_columns(features_df)
    # Explicit allowlist: only features derivable from Paw + Flow (no Pes-derived quantities).
    # tf, pl_base, pl_at_cycle, dPL_dt_max etc. are EXCLUDED even if present.
    feature_cols_noPS = [c for c in all_cols if c in C.PAW_FLOW_FEATURES]
    log.info("  Features (Paw+Flow only): %d of %d available | Excluded (Pes-derived/other): %d",
             len(feature_cols_noPS), len(all_cols), len(all_cols) - len(feature_cols_noPS))

    # Regression primary (δPL_max as label, but features are Paw+Flow)
    results_reg = run_lopo_cv(
        features_df,
        feature_cols=feature_cols_noPS,
        target_col="y_regression",
        task="regression",
        param_grid=C.XGB_PARAM_GRID,
        seed=C.RANDOM_SEED,
        log_dir=C.LOGS_DIR,
    )

    if len(results_reg) == 0:
        log.error("LOPO-CV produced no results!")
        return {}

    # Per-fold metrics
    fold_metrics = []
    for fold_id, grp in results_reg.groupby("fold"):
        yt = grp["y_true"].values
        yp = grp["y_pred"].values
        valid = np.isfinite(yt) & np.isfinite(yp)
        m = regression_metrics(yt[valid], yp[valid])
        m["fold"] = fold_id
        fold_metrics.append(m)

    df_fold = pd.DataFrame(fold_metrics)
    df_fold.to_csv(os.path.join(C.LOGS_DIR, "lopo_cv_fold_metrics.csv"), index=False)

    # Overall metrics
    all_yt = results_reg["y_true"].values
    all_yp = results_reg["y_pred"].values
    valid  = np.isfinite(all_yt) & np.isfinite(all_yp)
    overall = regression_metrics(all_yt[valid], all_yp[valid])
    log.info("  LOPO-CV overall: MAE=%.4f, RMSE=%.4f, R²=%.4f, CCC=%.4f",
             overall.get("mae", np.nan), overall.get("rmse", np.nan),
             overall.get("r2", np.nan),  overall.get("ccc", np.nan))

    # Bootstrap CI
    ci = bootstrap_ci(all_yt[valid], all_yp[valid],
                      metric_fn=lambda y, p: regression_metrics(y, p)["mae"],
                      seed=C.RANDOM_SEED)
    overall["mae_ci"] = ci

    results_reg.to_csv(os.path.join(C.LOGS_DIR, "lopo_cv_predictions.csv"), index=False)
    return {"overall": overall, "fold_metrics": df_fold, "predictions": results_reg,
            "feature_cols": feature_cols_noPS}


def get_exploratory_feature_cols(features_df: pd.DataFrame,
                                 primary_feature_cols: list) -> list:
    cols = list(primary_feature_cols)
    available = set(get_feature_columns(features_df))
    for feat in EXPLORATORY_EXTRA_FEATURES:
        if feat in available and feat not in cols:
            cols.append(feat)
    return cols


def run_regression_benchmarks(train_features: pd.DataFrame,
                              test_features: pd.DataFrame,
                              primary_feature_cols: list,
                              exploratory_feature_cols: list) -> dict:
    """
    Benchmark a suite of regressors on LOPO and held-out local test.
    Adds hierarchical Bayesian random-effects and quantile forest uncertainty.
    """
    benchmark_specs = [
        {"label": "mean_baseline", "model_name": "mean", "feature_cols": primary_feature_cols},
        {"label": "ridge_baseline", "model_name": "ridge", "feature_cols": primary_feature_cols},
        {"label": "gaussian_process", "model_name": "gaussian_process", "feature_cols": primary_feature_cols},
        {"label": "quantile_forest", "model_name": "quantile_forest", "feature_cols": primary_feature_cols},
        {"label": "hierarchical_bayes", "model_name": "hierarchical_bayes", "feature_cols": primary_feature_cols},
        {"label": "xgboost_primary", "model_name": "xgboost", "feature_cols": primary_feature_cols},
        {"label": "xgboost_exploratory", "model_name": "xgboost", "feature_cols": exploratory_feature_cols},
    ]

    lopo_rows = []
    for spec in benchmark_specs:
        label = spec["label"]
        model_name = spec["model_name"]
        feature_cols = spec["feature_cols"]
        log.info("Benchmark LOPO: %s (%d features)", label, len(feature_cols))
        for pid, train_idx, test_idx in lopo_splits(train_features, patient_col="patient_id"):
            X_train = train_features.iloc[train_idx][feature_cols].values.astype(np.float64)
            y_train = train_features.iloc[train_idx]["y_regression"].values.astype(np.float64)
            groups = train_features.iloc[train_idx]["patient_id"].values
            X_test = train_features.iloc[test_idx][feature_cols].values.astype(np.float64)
            y_test = train_features.iloc[test_idx]["y_regression"].values.astype(np.float64)
            pid_test = train_features.iloc[test_idx]["patient_id"].values

            valid_train = np.isfinite(y_train)
            if valid_train.sum() < 5:
                continue

            model = train_regression_pipeline(
                model_name,
                X_train[valid_train],
                y_train[valid_train],
                groups_train=groups[valid_train],
                param_grid=C.XGB_PARAM_GRID,
                seed=C.RANDOM_SEED,
            )

            y_std = None
            y_lo = None
            y_hi = None
            if isinstance(model, HierarchicalBayesRegressor):
                y_pred, y_std = model.predict(X_test, patient_ids=pid_test, return_std=True)
                y_lo = y_pred - 1.96 * y_std
                y_hi = y_pred + 1.96 * y_std
            elif isinstance(model, QuantileForestRegressor):
                y_pred, y_std, y_lo, y_hi = model.predict_with_uncertainty(X_test)
            else:
                y_pred, y_std = predict_with_uncertainty(model, X_test)
                if y_std is not None:
                    y_lo = y_pred - 1.96 * y_std
                    y_hi = y_pred + 1.96 * y_std

            for i in range(len(y_test)):
                lopo_rows.append({
                    "model": label,
                    "fold": pid,
                    "patient_id": train_features.iloc[test_idx[i]]["patient_id"],
                    "y_true": float(y_test[i]),
                    "y_pred": float(y_pred[i]),
                    "y_std": float(y_std[i]) if y_std is not None else np.nan,
                    "y_lo": float(y_lo[i]) if y_lo is not None else np.nan,
                    "y_hi": float(y_hi[i]) if y_hi is not None else np.nan,
                })

    df_lopo = pd.DataFrame(lopo_rows)
    df_lopo.to_csv(os.path.join(C.LOGS_DIR, "local_benchmark_lopo_predictions.csv"), index=False)

    lopo_metrics_rows = []
    for model_name, grp in df_lopo.groupby("model"):
        valid = np.isfinite(grp["y_true"].values) & np.isfinite(grp["y_pred"].values)
        metrics = regression_metrics(grp["y_true"].values[valid], grp["y_pred"].values[valid])
        metrics["model"] = model_name
        metrics["split"] = "lopo_cv"
        if {"y_lo", "y_hi"}.issubset(grp.columns):
            cov_mask = valid & np.isfinite(grp["y_lo"].values) & np.isfinite(grp["y_hi"].values)
            metrics["pi95_coverage"] = float(np.mean((grp["y_true"].values[cov_mask] >= grp["y_lo"].values[cov_mask]) &
                                                     (grp["y_true"].values[cov_mask] <= grp["y_hi"].values[cov_mask]))) if cov_mask.any() else np.nan
        lopo_metrics_rows.append(metrics)

    test_rows = []
    test_metrics_rows = []
    uncertainty_summary = {}
    posterior_rows = []
    for spec in benchmark_specs:
        label = spec["label"]
        model_name = spec["model_name"]
        feature_cols = spec["feature_cols"]
        X_train = train_features[feature_cols].values.astype(np.float64)
        y_train = train_features["y_regression"].values.astype(np.float64)
        groups = train_features["patient_id"].values
        X_test = test_features[feature_cols].values.astype(np.float64)
        y_test = test_features["y_regression"].values.astype(np.float64)
        pid_test = test_features["patient_id"].values

        valid_train = np.isfinite(y_train)
        model = train_regression_pipeline(
            model_name,
            X_train[valid_train],
            y_train[valid_train],
            groups_train=groups[valid_train],
            param_grid=C.XGB_PARAM_GRID,
            seed=C.RANDOM_SEED,
        )

        y_std = None
        y_lo = None
        y_hi = None
        if isinstance(model, HierarchicalBayesRegressor):
            y_pred, y_std = model.predict(X_test, patient_ids=pid_test, return_std=True)
            y_lo = y_pred - 1.96 * y_std
            y_hi = y_pred + 1.96 * y_std
            post = model.posterior_summary()
            if not post.empty:
                post["model"] = label
                posterior_rows.append(post)
        elif isinstance(model, QuantileForestRegressor):
            y_pred, y_std, y_lo, y_hi = model.predict_with_uncertainty(X_test)
        else:
            y_pred, y_std = predict_with_uncertainty(model, X_test)
            if y_std is not None:
                y_lo = y_pred - 1.96 * y_std
                y_hi = y_pred + 1.96 * y_std

        valid = np.isfinite(y_test) & np.isfinite(y_pred)
        metrics = regression_metrics(y_test[valid], y_pred[valid])
        metrics["model"] = label
        metrics["split"] = "local_test"

        if y_lo is not None and y_hi is not None:
            cov_mask = valid & np.isfinite(y_lo) & np.isfinite(y_hi)
            coverage = float(np.mean((y_test[cov_mask] >= y_lo[cov_mask]) & (y_test[cov_mask] <= y_hi[cov_mask]))) if cov_mask.any() else np.nan
            metrics["pi95_coverage"] = coverage
            uncertainty_summary[label] = {
                "mean_pred_std": float(np.nanmean(y_std)) if y_std is not None else np.nan,
                "median_pred_std": float(np.nanmedian(y_std)) if y_std is not None else np.nan,
                "pi95_coverage": coverage,
            }

        test_metrics_rows.append(metrics)

        for i in range(len(y_test)):
            test_rows.append({
                "model": label,
                "patient_id": test_features.iloc[i]["patient_id"],
                "y_true": float(y_test[i]),
                "y_pred": float(y_pred[i]),
                "y_std": float(y_std[i]) if y_std is not None else np.nan,
                "y_lo": float(y_lo[i]) if y_lo is not None else np.nan,
                "y_hi": float(y_hi[i]) if y_hi is not None else np.nan,
            })

    df_test = pd.DataFrame(test_rows)
    df_test.to_csv(os.path.join(C.LOGS_DIR, "local_benchmark_test_predictions.csv"), index=False)

    metrics_df = pd.DataFrame(lopo_metrics_rows + test_metrics_rows)
    metrics_df.to_csv(os.path.join(C.LOGS_DIR, "local_model_benchmarks.csv"), index=False)

    posterior_df = pd.concat(posterior_rows, ignore_index=True) if posterior_rows else pd.DataFrame()
    posterior_df.to_csv(os.path.join(C.LOGS_DIR, "hierarchical_bayes_posterior.csv"), index=False)

    return {
        "metrics": metrics_df,
        "lopo_predictions": df_lopo,
        "test_predictions": df_test,
        "uncertainty": uncertainty_summary,
        "posterior": posterior_df,
    }


def export_primary_feature_importance(train_features: pd.DataFrame,
                                      primary_feature_cols: list):
    X_train = train_features[primary_feature_cols].values.astype(np.float64)
    y_train = train_features["y_regression"].values.astype(np.float64)
    groups = train_features["patient_id"].values
    valid = np.isfinite(y_train)
    model = train_regression_pipeline(
        "xgboost",
        X_train[valid],
        y_train[valid],
        groups_train=groups[valid],
        param_grid=C.XGB_PARAM_GRID,
        seed=C.RANDOM_SEED,
    )
    imp_df = compute_permutation_importance(
        model,
        X_train[valid],
        y_train[valid],
        primary_feature_cols,
        seed=C.RANDOM_SEED,
        n_repeats=25,
    )
    imp_df.to_csv(os.path.join(C.LOGS_DIR, "local_feature_importance.csv"), index=False)
    return imp_df


# ---------------------------------------------------------------------------
# Train final local model + test on local_test
# ---------------------------------------------------------------------------

def run_patient_specific_fine_tuning_demo(train_features: pd.DataFrame,
                                           test_features: pd.DataFrame,
                                           feature_cols: list) -> tuple[pd.DataFrame, dict]:
    """
    Demonstrate patient adaptation by calibrating a per-patient offset using
    the first k breaths of each held-out test patient.
    """
    if test_features.empty:
        return pd.DataFrame(), {}

    base_model, _ = train_final_model(
        train_features,
        feature_cols=feature_cols,
        target_col="y_regression",
        task="regression",
        param_grid=C.XGB_PARAM_GRID,
        seed=C.RANDOM_SEED,
    )

    rows = []
    for pid, grp in test_features.groupby("patient_id"):
        grp = grp.reset_index(drop=True)
        n = len(grp)
        if n < 6:
            continue

        k = max(3, min(10, int(round(0.2 * n))))
        if (n - k) < 3:
            k = n - 3
        if k <= 0:
            continue

        adapt = grp.iloc[:k]
        eval_df = grp.iloc[k:]

        X_adapt = adapt[feature_cols].values.astype(np.float64)
        y_adapt = adapt["y_regression"].values.astype(np.float64)
        X_eval = eval_df[feature_cols].values.astype(np.float64)
        y_eval = eval_df["y_regression"].values.astype(np.float64)

        pred_adapt = predict(base_model, X_adapt, task="regression")
        pred_eval = predict(base_model, X_eval, task="regression")
        offset = float(np.nanmean(y_adapt - pred_adapt)) if len(y_adapt) else 0.0
        pred_eval_tuned = pred_eval + offset

        m_base = regression_metrics(y_eval, pred_eval)
        m_tuned = regression_metrics(y_eval, pred_eval_tuned)
        rows.append({
            "patient_id": pid,
            "n_total": int(n),
            "n_adapt": int(k),
            "n_eval": int(n - k),
            "offset_cmH2O": offset,
            "mae_before": float(m_base.get("mae", np.nan)),
            "mae_after": float(m_tuned.get("mae", np.nan)),
            "mae_gain": float(m_base.get("mae", np.nan) - m_tuned.get("mae", np.nan)),
            "rmse_before": float(m_base.get("rmse", np.nan)),
            "rmse_after": float(m_tuned.get("rmse", np.nan)),
            "r2_before": float(m_base.get("r2", np.nan)),
            "r2_after": float(m_tuned.get("r2", np.nan)),
        })

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.LOGS_DIR, "patient_specific_fine_tuning.csv"), index=False)

    if df.empty:
        return df, {}

    summary = {
        "n_patients_evaluated": int(df["patient_id"].nunique()),
        "mean_mae_before": float(df["mae_before"].mean()),
        "mean_mae_after": float(df["mae_after"].mean()),
        "mean_mae_gain": float(df["mae_gain"].mean()),
        "median_mae_gain": float(df["mae_gain"].median()),
        "patients_improved": int((df["mae_gain"] > 0).sum()),
    }
    return df, summary


def train_and_test_local(train_features: pd.DataFrame,
                          test_features: pd.DataFrame,
                          feature_cols: list) -> dict:
    log.info("Training final local model (P01-P05) and testing on local test (P06-P07)...")

    # Train
    model, _ = train_final_model(
        train_features,
        feature_cols=feature_cols,
        target_col="y_regression",
        task="regression",
        param_grid=C.XGB_PARAM_GRID,
        seed=C.RANDOM_SEED,
    )

    # Save model
    model_path = os.path.join(MODELS_DIR, "local_xgb_regression.pkl")
    with open(model_path, "wb") as fh:
        pickle.dump({"model": model, "feature_cols": feature_cols}, fh)
    log.info("  Saved local model → %s", model_path)

    # Test
    X_test   = test_features[feature_cols].values.astype(np.float64)
    y_test   = test_features["y_regression"].values.astype(np.float64)
    y_pred   = predict(model, X_test, task="regression")

    valid = np.isfinite(y_test) & np.isfinite(y_pred)
    metrics = regression_metrics(y_test[valid], y_pred[valid])
    log.info("  Local test metrics: MAE=%.4f, RMSE=%.4f, R²=%.4f, CCC=%.4f",
             metrics.get("mae", np.nan), metrics.get("rmse", np.nan),
             metrics.get("r2", np.nan),  metrics.get("ccc", np.nan))

    # Log per-patient test metrics
    per_patient = []
    for pid, grp in test_features.groupby("patient_id"):
        Xp = grp[feature_cols].values.astype(np.float64)
        yp_true = grp["y_regression"].values.astype(np.float64)
        yp_pred = predict(model, Xp, task="regression")
        vm = np.isfinite(yp_true) & np.isfinite(yp_pred)
        pm = regression_metrics(yp_true[vm], yp_pred[vm])
        pm["patient_id"] = pid
        per_patient.append(pm)

    df_pp = pd.DataFrame(per_patient)
    df_pp.to_csv(os.path.join(C.LOGS_DIR, "local_test_per_patient.csv"), index=False)

    test_preds = pd.DataFrame({
        "patient_id": test_features["patient_id"].values,
        "y_true": y_test,
        "y_pred": y_pred,
    })
    test_preds.to_csv(os.path.join(C.LOGS_DIR, "local_test_predictions.csv"), index=False)

    return metrics


# ---------------------------------------------------------------------------
# Validation check: pass/fail gate
# ---------------------------------------------------------------------------

def validate_local_results(lopo_metrics: dict, local_test_metrics: dict) -> bool:
    """
    Protocol validation gate before proceeding to global pipeline.
    Checks that:
      - LOPO-CV MAE < 3.0 cmH2O (sanity bound)
      - Local test R² > -1.0 (model does better than mean predictor)
    """
    passes = True
    mae = lopo_metrics.get("mae", np.inf)
    r2  = local_test_metrics.get("r2", -np.inf)

    if mae > 3.0:
        log.warning("VALIDATION GATE: LOPO-CV MAE=%.3f exceeds 3.0 cmH2O threshold", mae)
        passes = False
    if r2 < -1.0:
        log.warning("VALIDATION GATE: Local test R²=%.3f < -1.0", r2)
        passes = False

    if passes:
        log.info("VALIDATION GATE: LOCAL PASSED (MAE=%.3f, R²=%.3f)", mae, r2)
    else:
        log.warning("VALIDATION GATE: LOCAL FAILED — review results before proceeding")

    return passes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Steps 4 & 5: Local Pipeline")

    local_train = load_split("local_train.pkl")
    local_test  = load_split("local_test.pkl")

    # Build feature tables
    log.info("Building feature table for local train (P01-P05)...")
    train_features, train_exclusion = build_features_table(local_train, label="LOCAL_TRAIN")

    log.info("Building feature table for local test (P06-P07)...")
    test_features, test_exclusion  = build_features_table(local_test, label="LOCAL_TEST")

    if train_features.empty:
        log.error("Empty training features — aborting.")
        sys.exit(1)

    # Save feature tables
    train_features.to_csv(os.path.join(C.LOGS_DIR, "local_train_features.csv"), index=False)
    test_features.to_csv(os.path.join(C.LOGS_DIR,  "local_test_features.csv"),  index=False)
    train_exclusion["split"] = "local_train"
    test_exclusion["split"] = "local_test"
    exclusion_df = pd.concat([train_exclusion, test_exclusion], ignore_index=True)
    exclusion_df.to_csv(os.path.join(C.LOGS_DIR, "breath_exclusion_summary.csv"), index=False)

    # LOPO-CV
    lopo_res = run_local_lopo(train_features)
    feature_cols = lopo_res.get("feature_cols", get_feature_columns(train_features))
    exploratory_feature_cols = get_exploratory_feature_cols(train_features, feature_cols)

    # Filter test features to same columns
    test_cols = [c for c in feature_cols if c in test_features.columns]
    missing_in_test = set(feature_cols) - set(test_cols)
    if missing_in_test:
        log.warning("Missing feature cols in local test: %s — padding with NaN", missing_in_test)
        for col in missing_in_test:
            test_features[col] = np.nan
        test_cols = feature_cols

    # Train final + test
    local_test_metrics = train_and_test_local(train_features, test_features, feature_cols)

    # Benchmark suite + interpretability
    benchmark_res = run_regression_benchmarks(
        train_features,
        test_features,
        feature_cols,
        exploratory_feature_cols,
    )
    importance_df = export_primary_feature_importance(train_features, feature_cols)
    fine_tune_df, fine_tune_summary = run_patient_specific_fine_tuning_demo(
        train_features,
        test_features,
        feature_cols,
    )

    # Validation gate
    passed = validate_local_results(lopo_res.get("overall", {}), local_test_metrics)

    # Save combined summary
    summary = {
        "lopo_cv": lopo_res.get("overall", {}),
        "local_test": local_test_metrics,
        "validation_pass": passed,
        "n_train_breaths": len(train_features),
        "n_test_breaths":  len(test_features),
        "exclusion_summary": {
            "n_segmented": int(exclusion_df["n_segmented"].sum()) if not exclusion_df.empty else 0,
            "n_valid": int(exclusion_df["n_valid"].sum()) if not exclusion_df.empty else 0,
            "n_quality_excluded_total": int(exclusion_df["n_quality_excluded_total"].sum()) if not exclusion_df.empty else 0,
            "retained_rate": float(exclusion_df["n_valid"].sum() / exclusion_df["n_segmented"].sum()) if (not exclusion_df.empty and exclusion_df["n_segmented"].sum() > 0) else np.nan,
        },
        "benchmark_models": benchmark_res["metrics"].to_dict(orient="records"),
        "uncertainty": benchmark_res.get("uncertainty", {}),
        "gp_uncertainty": benchmark_res.get("uncertainty", {}).get("gaussian_process", {}),
        "hierarchical_posterior": benchmark_res.get("posterior", pd.DataFrame()).to_dict(orient="records"),
        "patient_specific_fine_tuning": fine_tune_summary,
        "top_features": importance_df.head(10).to_dict(orient="records"),
    }
    for key in summary:
        if isinstance(summary[key], np.generic):
            summary[key] = float(summary[key])

    with open(os.path.join(C.LOGS_DIR, "local_pipeline_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    if not passed:
        log.warning("Local validation failed. Review results; global pipeline may be unreliable.")
    log.info("Step 4/5 complete. Results → %s", C.LOGS_DIR)
