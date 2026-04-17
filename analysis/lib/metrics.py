# =============================================================================
# lib/metrics.py  —  Performance metrics  (Protocol Section 11)
# Version: 1.0  |  2026-03-14
# =============================================================================

import logging
import numpy as np
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    f1_score, precision_score, recall_score,
    balanced_accuracy_score, brier_score_loss,
    mean_absolute_error, mean_squared_error, r2_score,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regression metrics  (Section 11.2)
# ---------------------------------------------------------------------------

def concordance_correlation(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Lin's concordance correlation coefficient."""
    mu_t, mu_p = np.mean(y_true), np.mean(y_pred)
    s_t = np.var(y_true, ddof=0)
    s_p = np.var(y_pred, ddof=0)
    s_tp = np.mean((y_true - mu_t) * (y_pred - mu_p))
    denom = s_t + s_p + (mu_t - mu_p) ** 2
    return float(2 * s_tp / denom) if denom > 0 else np.nan


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return {k: np.nan for k in ["mae", "rmse", "r2", "ccc"]}
    yt, yp = y_true[mask], y_pred[mask]
    return {
        "mae":  float(mean_absolute_error(yt, yp)),
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "r2":   float(r2_score(yt, yp)),
        "ccc":  concordance_correlation(yt, yp),
        "n":    int(mask.sum()),
    }


# ---------------------------------------------------------------------------
# Classification metrics  (Section 11.1)
# ---------------------------------------------------------------------------

def classification_metrics(y_true: np.ndarray, y_prob: np.ndarray,
                            threshold: float = 0.5) -> dict:
    mask = np.isfinite(y_true) & np.isfinite(y_prob)
    if mask.sum() < 2:
        return {k: np.nan for k in [
            "auroc", "auprc", "f1", "precision", "recall",
            "specificity", "npv", "balanced_acc", "brier",
        ]}
    yt = y_true[mask].astype(int)
    yp = y_prob[mask]
    yb = (yp >= threshold).astype(int)

    # Guard against single-class
    if len(np.unique(yt)) < 2:
        return {k: np.nan for k in [
            "auroc", "auprc", "f1", "precision", "recall",
            "specificity", "npv", "balanced_acc", "brier",
        ]}

    tn = int(((yt == 0) & (yb == 0)).sum())
    fp = int(((yt == 0) & (yb == 1)).sum())
    fn = int(((yt == 1) & (yb == 0)).sum())

    specificity = tn / (tn + fp) if (tn + fp) > 0 else np.nan
    npv_val = tn / (tn + fn) if (tn + fn) > 0 else np.nan

    return {
        "auroc":        float(roc_auc_score(yt, yp)),
        "auprc":        float(average_precision_score(yt, yp)),
        "f1":           float(f1_score(yt, yb, zero_division=0)),
        "precision":    float(precision_score(yt, yb, zero_division=0)),
        "recall":       float(recall_score(yt, yb, zero_division=0)),
        "specificity":  float(specificity),
        "npv":          float(npv_val),
        "balanced_acc": float(balanced_accuracy_score(yt, yb)),
        "brier":        float(brier_score_loss(yt, yp)),
        "n":            int(mask.sum()),
        "n_pos":        int(yt.sum()),
    }


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals  (Section 11.3)
# ---------------------------------------------------------------------------

def bootstrap_ci(y_true: np.ndarray, y_pred: np.ndarray,
                 metric_fn, n_boot: int = 1000,
                 ci: float = 0.95, seed: int = 42) -> dict:
    """
    Patient-level bootstrap (resample patients).
    Expects y_true and y_pred arrays of patient-aggregated metric values,
    OR per-sample arrays (simple bootstrap).
    """
    rng = np.random.default_rng(seed)
    n = len(y_true)
    boot_vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        metric_value = metric_fn(y_true[idx], y_pred[idx])
        if isinstance(metric_value, dict):
            boot_vals.append(metric_value)
        else:
            boot_vals.append(float(metric_value))

    alpha = (1 - ci) / 2
    if isinstance(boot_vals[0], dict):
        interval_bounds = {}
        for key in boot_vals[0]:
            finite_metric_values = [v[key] for v in boot_vals if np.isfinite(v[key])]
            if finite_metric_values:
                interval_bounds[f"{key}_lo"] = float(
                    np.quantile(finite_metric_values, alpha)
                )
                interval_bounds[f"{key}_hi"] = float(
                    np.quantile(finite_metric_values, 1 - alpha)
                )
        return interval_bounds
    else:
        finite_bootstrap_values = [value for value in boot_vals if np.isfinite(value)]
        if not finite_bootstrap_values:
            return {"lo": np.nan, "hi": np.nan}
        # I filter non-finite draws explicitly so extreme edge cases don't silently poison CI quantiles.
        return {
            "lo": float(np.quantile(finite_bootstrap_values, alpha)),
            "hi": float(np.quantile(finite_bootstrap_values, 1 - alpha)),
        }
