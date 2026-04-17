# =============================================================================
# lib/qc.py  —  File-level and sample-level Quality Control
# Version: 1.0  |  2026-03-14
# Implements Section 4 of 02_ANALYSIS_PROTOCOL.md verbatim.
# =============================================================================

import logging
import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hampel filter (sample-level spike detector)
# ---------------------------------------------------------------------------

def hampel_mask(x: np.ndarray, window: int = 11, threshold: float = 6.0) -> np.ndarray:
    """
    Return boolean mask where True = flagged outlier.
    Uses rolling median absolute deviation (MAD) across a given window.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    half = window // 2
    flagged = np.zeros(n, dtype=bool)

    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        win = x[lo:hi]
        med = np.median(win)
        mad = np.median(np.abs(win - med))
        if mad == 0:
            continue
        if abs(x[i] - med) > threshold * 1.4826 * mad:
            flagged[i] = True

    return flagged


def hampel_replace(x: np.ndarray, window: int = 11, threshold: float = 6.0) -> np.ndarray:
    """Replace Hampel-flagged outliers with local median."""
    x = x.copy()
    flagged = hampel_mask(x, window=window, threshold=threshold)
    half = window // 2
    n = len(x)
    for i in np.where(flagged)[0]:
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        x[i] = np.median(x[lo:hi])
    return x


# ---------------------------------------------------------------------------
# Zero-phase low-pass filter
# ---------------------------------------------------------------------------

def lowpass_filter(x: np.ndarray, cutoff_hz: float, fs: float, order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth low-pass filter."""
    nyq = fs / 2.0
    if cutoff_hz >= nyq:
        return x  # already below Nyquist
    sos = butter(order, cutoff_hz / nyq, btype="low", output="sos")
    return sosfiltfilt(sos, x)


def antialias_filter(x: np.ndarray, target_fs: float, source_fs: float,
                     order: int = 8) -> np.ndarray:
    """Anti-aliasing LP filter before decimation. Cutoff = min(0.4*target_fs, 20 Hz)."""
    cutoff = min(0.4 * target_fs, 20.0)
    nyq = source_fs / 2.0
    if cutoff >= nyq:
        return x
    sos = butter(order, cutoff / nyq, btype="low", output="sos")
    return sosfiltfilt(sos, x)


# ---------------------------------------------------------------------------
# File-level inclusion gate    (Protocol Section 4.1)
# ---------------------------------------------------------------------------

def file_qc(df: pd.DataFrame, declared_fs: float,
            required_channels: list,
            fs_tol: float = 0.05,
            max_miss: float = 0.05,
            flatline_max_s: float = 2.0) -> dict:
    """
    Evaluate file-level QC gates.

    Returns
    -------
    dict with keys:
      'pass': bool  (True = file is included)
      'reasons': list[str]  (non-empty if failed)
      'fs_estimated': float
    """
    reasons = []

    # Gate 1 — required channels present
    for col in required_channels:
        if col not in df.columns:
            reasons.append(f"missing_channel:{col}")

    if reasons:  # can't continue without channels
        return {"pass": False, "reasons": reasons, "fs_estimated": np.nan}

    # Gate 2 — monotonic increasing time
    time = df["time"].values
    if np.any(np.diff(time) <= 0):
        reasons.append("time_not_monotonic")

    # Gate 3 — effective sampling rate within tolerance
    dt_series = np.diff(time)
    if len(dt_series) > 0:
        dt_median = float(np.median(dt_series))
        fs_est = 1.0 / dt_median if dt_median > 0 else np.nan
    else:
        dt_median = np.nan
        fs_est = np.nan

    if np.isfinite(fs_est):
        rel_err = abs(fs_est - declared_fs) / declared_fs
        if rel_err > fs_tol:
            reasons.append(
                f"fs_mismatch: estimated={fs_est:.1f} declared={declared_fs:.1f}"
            )
    else:
        reasons.append("fs_uncomputable")

    # Gate 4 — missingness per channel
    for col in required_channels:
        miss_frac = df[col].isna().mean()
        if miss_frac > max_miss:
            reasons.append(f"high_missingness:{col}={miss_frac:.3f}")

    # Gate 5 — no constant flatline > flatline_max_s in required channels
    if np.isfinite(dt_median) and dt_median > 0:
        flatline_samples = int(flatline_max_s / dt_median)
        for col in required_channels:
            arr = df[col].values
            max_run = _max_constant_run(arr)
            if max_run >= flatline_samples:
                reasons.append(f"flatline:{col}={max_run * dt_median:.1f}s")

    passed = len(reasons) == 0
    return {"pass": passed, "reasons": reasons, "fs_estimated": fs_est}


def _max_constant_run(arr: np.ndarray) -> int:
    """Return the longest run of identical consecutive values."""
    if len(arr) == 0:
        return 0
    diffs = np.diff(arr.astype(np.float64))
    max_run = 1
    current = 1
    for d in diffs:
        if d == 0:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 1
    return max_run


# ---------------------------------------------------------------------------
# Sample-level processing pipeline    (Protocol Section 4.2)
# ---------------------------------------------------------------------------

def preprocess_signal(df: pd.DataFrame, fs: float,
                      hampel_window: int = 11, hampel_thresh: float = 6.0,
                      flow_lp_hz: float = 12.0, pres_lp_hz: float = 20.0,
                      target_fs: float = None,
                      apply_hampel: bool = True) -> pd.DataFrame:
    """
    Apply full sample-level processing pipeline in protocol order:
      1. Hampel outlier replacement (spikes only)
      2. Zero-phase low-pass denoising (flow + pressure)
      3. Anti-aliasing + optional resampling to target_fs

    Returns processed DataFrame (same length unless resampled).
    """
    df = df.copy()

    # Step 1 — Hampel spike replacement on flow and pressure channels
    if apply_hampel and hampel_window > 1:
        for col in ["flow", "paw", "pes"]:
            if col in df.columns:
                arr = df[col].values.astype(np.float64)
                valid = np.isfinite(arr)
                if valid.sum() > hampel_window:
                    arr[valid] = hampel_replace(arr[valid], hampel_window, hampel_thresh)
                    df[col] = arr

    # Step 2 — Zero-phase low-pass denoising
    if "flow" in df.columns:
        arr = df["flow"].values.astype(np.float64)
        finite_mask = np.isfinite(arr)
        if finite_mask.sum() > 10:
            interpolated_signal = arr.copy()
            # I interpolate only the missing points before filtering to avoid edge ringing from NaN gaps.
            interpolated_signal[~finite_mask] = np.interp(
                np.where(~finite_mask)[0],
                np.where(finite_mask)[0],
                arr[finite_mask],
            )
            df["flow"] = lowpass_filter(interpolated_signal, flow_lp_hz, fs)

    for col in ["paw", "pes"]:
        if col in df.columns:
            arr = df[col].values.astype(np.float64)
            finite_mask = np.isfinite(arr)
            if finite_mask.sum() > 10:
                interpolated_signal = arr.copy()
                interpolated_signal[~finite_mask] = np.interp(
                    np.where(~finite_mask)[0],
                    np.where(finite_mask)[0],
                    arr[finite_mask],
                )
                df[col] = lowpass_filter(interpolated_signal, pres_lp_hz, fs)

    # Step 3 — Anti-aliasing + resampling (if requested)
    if target_fs is not None and abs(target_fs - fs) / fs > 0.02:
        df = resample_df(df, fs, target_fs)

    return df


def resample_df(df: pd.DataFrame, source_fs: float, target_fs: float) -> pd.DataFrame:
    """
    Anti-alias then linearly resample the DataFrame to target_fs.
    Preserves constant columns (patient_id, source, etc.).
    """
    t_orig = df["time"].values.astype(np.float64)
    duration = t_orig[-1] - t_orig[0]
    n_new = int(round(duration * target_fs)) + 1
    t_new = np.linspace(t_orig[0], t_orig[-1], n_new)

    numeric_cols = ["flow", "paw", "pes"]
    resampled_columns = {}
    for col in numeric_cols:
        if col in df.columns:
            arr = df[col].values.astype(np.float64)
            arr_aa = antialias_filter(arr, target_fs, source_fs)
            resampled_columns[col] = np.interp(t_new, t_orig, arr_aa)

    resampled_columns["time"] = t_new

    # Copy constant non-signal columns
    for col in df.columns:
        if col not in resampled_columns:
            unique_values = df[col].unique()
            resampled_columns[col] = (
                unique_values[0] if len(unique_values) == 1 else df[col].values[0]
            )

    return pd.DataFrame(resampled_columns)


# ---------------------------------------------------------------------------
# Breath-level quality flags    (Protocol Section 4.3)
# ---------------------------------------------------------------------------

def breath_quality_flags(breath_df: pd.DataFrame, fs: float,
                         hampel_window: int = 11, hampel_thresh: float = 6.0,
                         bad_frac: float = 0.05,
                         flatline_ms: float = 200.0,
                         pre_ms: float = 150.0, post_ms: float = 350.0,
                         t_cycle: float = None,
                         apply_hampel: bool = True) -> dict:
    """
    Compute per-breath quality flags.

    Returns
    -------
    dict: {
        'low_quality_flow': bool,
        'low_quality_paw': bool,
        'low_quality_pes': bool,
        'incomplete_window': bool,
    }
    """
    dt = 1.0 / fs
    flatline_samples = int(flatline_ms / 1000.0 / dt)
    flags = {}

    for col, flag_name in [("flow", "low_quality_flow"),
                           ("paw", "low_quality_paw"),
                           ("pes", "low_quality_pes")]:
        if col not in breath_df.columns:
            flags[flag_name] = True
            continue
        arr = breath_df[col].values.astype(np.float64)
        if np.all(np.isnan(arr)):
            flags[flag_name] = (col in ("flow", "paw"))  # pes NaN is OK if no Pes available
            continue

        valid = np.isfinite(arr)
        # Criterion 1: Hampel outlier fraction
        if apply_hampel and valid.sum() >= hampel_window:
            outlier_mask = hampel_mask(arr[valid], hampel_window, hampel_thresh)
            frac_bad = outlier_mask.sum() / len(arr)
        else:
            frac_bad = 0.0

        # Criterion 2: flatline
        max_flat = _max_constant_run(arr[valid]) if valid.sum() > 0 else 0

        flags[flag_name] = (frac_bad > bad_frac) or (max_flat >= flatline_samples)

    # incomplete_window: is the [-pre_ms, +post_ms] window available?
    if t_cycle is not None:
        time = breath_df["time"].values
        t_start = t_cycle - pre_ms / 1000.0
        t_end = t_cycle + post_ms / 1000.0
        flags["incomplete_window"] = (time[0] > t_start) or (time[-1] < t_end)
    else:
        flags["incomplete_window"] = False

    return flags
