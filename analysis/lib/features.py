# =============================================================================
# lib/features.py  —  Feature extraction for ML (Protocol Section 8)
# Version: 1.0  |  2026-03-14
# =============================================================================

import logging
import numpy as np
import pandas as pd
from scipy.signal import welch

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-breath feature set  (Section 8.1)
# ---------------------------------------------------------------------------

SCALAR_FEATURES = [
    # Kinematic
    "f_peak", "insp_dur_s", "exp_dur_s",
    # Baselines
    "paw_base", "pes_base", "pl_base", "pl_at_cycle",
    # Event magnitudes
    "delta_paw_max", "delta_pl_max", "dPaw_dt_max", "dPL_dt_max",
    # Derived
    "tf",
    # Metadata
    "ets_frac",
]

CLINICAL_FEATURES = ["ps", "peep", "fio2"]   # from metadata; may be NaN


def extract_waveform_features(event_dict: dict,
                               full_window_df: pd.DataFrame,
                               fs: float) -> dict:
    """
    Augment an event dict with waveform-shape features
    (compliance/resistance surrogates, spectral energy, etc.)

    These are exploratory features appended to the scalar set.
    """
    feats = {}

    if full_window_df is None or len(full_window_df) < 10:
        return feats

    flow = full_window_df["flow"].values.astype(np.float64)
    paw  = full_window_df["paw"].values.astype(np.float64)
    dt   = 1.0 / fs

    # Flow deceleration slope (linear fit during late inspiration)
    # Use from F_peak onwards (positive flow region)
    pos_mask = flow > 0
    if pos_mask.sum() >= 4:
        t_rel = np.arange(len(flow)) * dt
        # Linear fit on late-inspiratory flow (from mid-inspiration)
        n_pos = pos_mask.sum()
        half = n_pos // 2
        idx_pos = np.where(pos_mask)[0]
        if half < len(idx_pos):
            late_idx = idx_pos[half:]
            slope = np.polyfit(t_rel[late_idx], flow[late_idx], 1)[0]
            feats["flow_decel_slope"] = float(slope)

    # Peak-to-end pressure ratio (Paw shape proxy)
    if len(paw) > 2:
        feats["paw_ratio_peak_end"] = float(np.max(paw) / (np.mean(paw[-3:]) + 1e-6))

    # Integral of absolute flow (work proxy)
    feats["flow_integral_abs"] = float(np.trapezoid(np.abs(flow), dx=dt))

    # Paw-flow phase-plane loop area (shape / hysteresis proxy)
    if len(flow) > 2 and len(paw) > 2:
        feats["paw_flow_loop_area"] = float(np.abs(np.trapezoid(paw, flow)))

    # Correlation between Paw and Flow around cycling
    if len(flow) > 3 and np.std(flow) > 1e-9 and np.std(paw) > 1e-9:
        feats["paw_flow_corr"] = float(np.corrcoef(paw, flow)[0, 1])

    # Rise time to peak flow (ms)
    if pos_mask.sum() > 0:
        peak_idx = int(np.argmax(flow))
        feats["flow_rise_time_ms"] = float(peak_idx * dt * 1000.0)

    # Higher-order pressure dynamics (acceleration / jerk proxy)
    if len(paw) >= 5:
        dpaw_dt = np.gradient(paw, dt)
        d2paw_dt2 = np.gradient(dpaw_dt, dt)
        feats["d2Paw_dt2_max"] = float(np.nanmax(np.abs(d2paw_dt2)))

    # Spectral energy ratio (low vs high freq in Paw)
    if len(paw) >= 32:
        nperseg = min(len(paw), 64)
        freqs, psd = welch(paw, fs=fs, nperseg=nperseg)
        low_mask  = freqs <= 5.0
        high_mask = freqs >  5.0
        e_low  = np.trapezoid(psd[low_mask],  freqs[low_mask])  if low_mask.sum() > 1 else 0.0
        e_high = np.trapezoid(psd[high_mask], freqs[high_mask]) if high_mask.sum() > 1 else 0.0
        feats["paw_spectral_ratio"] = float(e_high / (e_low + 1e-12))
        if np.sum(psd) > 0:
            feats["paw_spectral_centroid_hz"] = float(np.sum(freqs * psd) / np.sum(psd))

    return feats


def build_feature_row(event_dict: dict,
                      full_window_df: pd.DataFrame,
                      fs: float,
                      include_clinical: bool = True) -> dict:
    """
    Build a single-row feature dict ready for ML:
      - scalar protocol features
      - clinical metadata (ps, peep, fio2) if available
      - computed waveform shape features

    Parameters
    ----------
    event_dict : output from events.process_breath()
    full_window_df : [-150ms, +350ms] window around t_cycle (or None)
    include_clinical : whether to include ps/peep/fio2 features
    """
    row = {}

    for feat in SCALAR_FEATURES:
        row[feat] = event_dict.get(feat, np.nan)

    if include_clinical:
        for feat in CLINICAL_FEATURES:
            row[feat] = event_dict.get(feat, np.nan)

    row["ets_defaulted_flag"] = int(event_dict.get("ets_defaulted", False))

    # Simple interaction features (domain-driven, Paw+Flow only)
    if np.isfinite(row.get("f_peak", np.nan)) and np.isfinite(row.get("insp_dur_s", np.nan)):
        row["flow_time_product"] = float(row["f_peak"] * row["insp_dur_s"])
    if np.isfinite(row.get("delta_paw_max", np.nan)) and np.isfinite(row.get("dPaw_dt_max", np.nan)):
        row["paw_stress_index"] = float(row["delta_paw_max"] * row["dPaw_dt_max"])

    # Waveform shape features
    shape_feats = extract_waveform_features(event_dict, full_window_df, fs)
    row.update(shape_feats)

    # Targets
    row["y_regression"]  = event_dict.get("delta_pl_max", np.nan)
    row["y_class"]       = event_dict.get("event_positive", np.nan)

    # Identifiers (not used as ML features; dropped before training)
    row["patient_id"]    = event_dict.get("patient_id", "")
    row["source"]        = event_dict.get("source", "")
    row["t_cycle"]       = event_dict.get("t_cycle", np.nan)

    return row


def get_feature_columns(df: pd.DataFrame) -> list:
    """
    Return the list of actual feature columns (excludes target and ID columns).
    Drops columns that are all-NaN.
    """
    exclude = {"y_regression", "y_class", "patient_id", "source", "t_cycle"}
    candidates = [c for c in df.columns if c not in exclude]
    # Drop all-NaN columns
    return [c for c in candidates if df[c].notna().any()]
