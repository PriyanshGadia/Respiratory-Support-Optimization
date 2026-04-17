# =============================================================================
# lib/events.py  —  t_cycle detection + event window extraction
# Version: 1.0  |  2026-03-14
# Implements Protocol Sections 6 and 7.
# =============================================================================

import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# t_cycle detection    (Section 6.1)
# ---------------------------------------------------------------------------

def detect_tcycle(flow: np.ndarray, fp_idx: int, ets_frac: float,
                  confirm_n: int = 3) -> int:
    """
    Deterministic t_cycle detection.
    Starting from F_peak index, scan forward for 3 consecutive samples
    where flow <= ets_frac * F_peak.

    Returns
    -------
    Index of t_cycle, or -1 if no such sample found (flags cycle_undefined).
    """
    n = len(flow)
    f_peak = flow[fp_idx]
    f_ets = ets_frac * f_peak

    # I require consecutive samples here because single-point threshold
    # crossings were too noisy in clinical traces.
    count = 0
    candidate = -1
    for j in range(fp_idx, n):
        if flow[j] <= f_ets:
            if count == 0:
                candidate = j
            count += 1
            if count >= confirm_n:
                return candidate
        else:
            count = 0
            candidate = -1

    return -1  # cycle_undefined


# ---------------------------------------------------------------------------
# Event window extraction    (Section 6.2)
# ---------------------------------------------------------------------------

def extract_event_window(df: pd.DataFrame, t_cycle: float,
                         pre_ms: float = 150.0, post_ms: float = 350.0) -> dict:
    """
    Extract signal windows around t_cycle.

    Returns
    -------
    dict: {
        'pre_slice': DataFrame ([-pre_ms, 0] relative to t_cycle),
        'post_slice': DataFrame ([0, +post_ms]),
        'full_slice': DataFrame ([-pre_ms, +post_ms]),
        'complete': bool (both slices fully populated),
    }
    """
    time = df["time"].values
    pre_start = t_cycle - pre_ms / 1000.0
    post_end = t_cycle + post_ms / 1000.0

    pre_mask = (time >= pre_start) & (time <= t_cycle)
    post_mask = (time >= t_cycle) & (time <= post_end)
    full_mask = (time >= pre_start) & (time <= post_end)

    pre_df = df[pre_mask].copy()
    post_df = df[post_mask].copy()
    full_df = df[full_mask].copy()

    # Offset time so t_cycle = 0
    for d in [pre_df, post_df, full_df]:
        d["time_rel"] = d["time"] - t_cycle

    complete = (len(pre_df) > 0) and (len(post_df) > 0)

    return {
        "pre_slice": pre_df,
        "post_slice": post_df,
        "full_slice": full_df,
        "complete": complete,
    }


# ---------------------------------------------------------------------------
# Continuous event magnitudes    (Section 6.3)
# ---------------------------------------------------------------------------

def compute_event_magnitudes(pre_df: pd.DataFrame,
                              post_df: pd.DataFrame,
                              fs: float) -> dict:
    """
    Compute primary continuous event features:
      - Delta Paw max, Delta PL max
      - max |dPaw/dt|, max |dPL/dt|
    Uses pre-window medians as baselines.

    Returns
    -------
    dict of float values, or NaN where Pes is unavailable.
    """
    dt = 1.0 / fs
    event_magnitudes = {}

    if len(pre_df) == 0 or len(post_df) == 0:
        return {k: np.nan for k in [
            "paw_base", "pes_base", "pl_base",
            "delta_paw_max", "delta_pl_max",
            "dPaw_dt_max", "dPL_dt_max",
            "pl_at_cycle",
        ]}

    # Baselines (median in pre-window)
    paw_base = float(np.nanmedian(pre_df["paw"].values))
    has_pes = ("pes" in pre_df.columns) and (not np.all(np.isnan(pre_df["pes"].values)))
    pes_base = float(np.nanmedian(pre_df["pes"].values)) if has_pes else np.nan
    pl_base = (paw_base - pes_base) if has_pes else np.nan

    event_magnitudes["paw_base"] = paw_base
    event_magnitudes["pes_base"] = pes_base
    event_magnitudes["pl_base"] = pl_base

    # PL at t_cycle = first post-window sample
    paw_at_cycle = float(post_df["paw"].values[0])
    pes_at_cycle = float(post_df["pes"].values[0]) if has_pes else np.nan
    event_magnitudes["pl_at_cycle"] = (paw_at_cycle - pes_at_cycle) if has_pes else np.nan

    # Delta Paw max
    paw_post = post_df["paw"].values
    event_magnitudes["delta_paw_max"] = float(np.max(np.abs(paw_post - paw_base)))

    # Delta PL max (requires Pes)
    if has_pes:
        pes_post = post_df["pes"].values
        pl_post = paw_post - pes_post
        event_magnitudes["delta_pl_max"] = float(np.max(np.abs(pl_post - pl_base)))
    else:
        event_magnitudes["delta_pl_max"] = np.nan

    # Slope terms: max |dX/dt| in post-window
    if len(paw_post) >= 2:
        dpaw = np.gradient(paw_post, dt)
        event_magnitudes["dPaw_dt_max"] = float(np.max(np.abs(dpaw)))
    else:
        event_magnitudes["dPaw_dt_max"] = np.nan

    if has_pes and len(post_df["pes"].values) >= 2:
        pes_post = post_df["pes"].values
        pl_post = paw_post - pes_post
        dpl = np.gradient(pl_post, dt)
        event_magnitudes["dPL_dt_max"] = float(np.max(np.abs(dpl)))
    else:
        event_magnitudes["dPL_dt_max"] = np.nan

    return event_magnitudes


# ---------------------------------------------------------------------------
# Transmission fraction    (Section 7.2)
# ---------------------------------------------------------------------------

def compute_tf(delta_paw_max: float, delta_pl_max: float,
               guard: float = 0.2) -> float:
    """
    TF = delta_PL_max / delta_Paw_max, only if delta Paw > guard.
    Returns NaN otherwise.
    """
    if np.isnan(delta_paw_max) or np.isnan(delta_pl_max):
        return np.nan
    if delta_paw_max <= guard:
        return np.nan
    return delta_pl_max / delta_paw_max


# ---------------------------------------------------------------------------
# Binary event label    (Section 6.4)
# ---------------------------------------------------------------------------

def compute_event_label(post_df: pd.DataFrame, pl_base: float,
                        t_cycle: float, fs: float,
                        dpl_min: float = 1.0,
                        slope_min: float = 8.0,
                        peak_max_ms: float = 200.0) -> dict:
    """
    Derive binary event_positive label.

    Returns
    -------
    dict: {
        'event_positive': bool or None (None if Pes required data missing),
        'delta_pl_max': float,
        'dpl_dt_max': float,
        'peak_latency_ms': float,
    }
    """
    has_pes = ("pes" in post_df.columns) and not np.all(np.isnan(post_df["pes"].values))
    if not has_pes:
        return {
            "event_positive": None,
            "delta_pl_max": np.nan,
            "dpl_dt_max": np.nan,
            "peak_latency_ms": np.nan,
        }

    dt = 1.0 / fs
    paw = post_df["paw"].values
    pes = post_df["pes"].values
    time = post_df["time"].values

    pl = paw - pes
    # Baseline is passed in as pl_base
    delta_pl = np.abs(pl - pl_base)

    # peak within peak_max_ms
    peak_window_n = int(peak_max_ms / 1000.0 * fs) + 1
    peak_window_n = min(peak_window_n, len(delta_pl))
    peak_in_window_idx = int(np.argmax(delta_pl[:peak_window_n]))
    delta_pl_max = float(delta_pl[peak_in_window_idx])
    peak_latency_ms = float((time[peak_in_window_idx] - t_cycle) * 1000.0)

    # Slope
    if len(pl) >= 2:
        dpl = np.gradient(pl, dt)
        dpl_dt_max = float(np.max(np.abs(dpl[:peak_window_n])))
    else:
        dpl_dt_max = 0.0

    event_pos = (
        delta_pl_max >= dpl_min
        and dpl_dt_max >= slope_min
        and peak_latency_ms <= peak_max_ms
    )

    return {
        "event_positive": bool(event_pos),
        "delta_pl_max": delta_pl_max,
        "dpl_dt_max": dpl_dt_max,
        "peak_latency_ms": peak_latency_ms,
    }


# ---------------------------------------------------------------------------
# Full per-breath event processing pipeline
# ---------------------------------------------------------------------------

def process_breath(breath_info: dict, df: pd.DataFrame,
                   fs: float,
                   ets_frac: float,
                   ets_defaulted: bool = False,
                   pre_ms: float = 150.0,
                   post_ms: float = 350.0,
                   confirm_n: int = 3,
                   tf_guard: float = 0.2,
                   event_dpl_min: float = 1.0,
                   event_slope_min: float = 8.0,
                   event_peak_ms: float = 200.0) -> dict:
    """
    Full event pipeline for one already-segmented breath dict.

    Returns
    -------
    dict with all event-level features + flags.
    """
    fp_idx = breath_info["f_peak_idx"]
    flow = df["flow"].values

    # --- t_cycle detection ---
    tc_idx = detect_tcycle(flow, fp_idx, ets_frac, confirm_n)

    breath_event = {
        "patient_id": df["patient_id"].iloc[0] if "patient_id" in df.columns else "",
        "source": df["source"].iloc[0] if "source" in df.columns else "",
        "t_insp_start": breath_info["t_insp_start"],
        "f_peak": breath_info["f_peak"],
        "ets_frac": ets_frac,
        "ets_defaulted": ets_defaulted,
        "seg_method": breath_info["method"],
        "t_cycle": np.nan,
        "cycle_undefined": True,
    }

    if tc_idx < 0:
        breath_event["cycle_undefined"] = True
        breath_event.update({k: np.nan for k in [
            "paw_base", "pes_base", "pl_base", "pl_at_cycle",
            "delta_paw_max", "delta_pl_max", "dPaw_dt_max", "dPL_dt_max",
            "tf", "event_positive", "dpl_dt_max", "peak_latency_ms",
            "insp_dur_s", "exp_dur_s",
        ]})
        return breath_event

    t_cycle = float(df["time"].iloc[tc_idx])
    breath_event["t_cycle"] = t_cycle
    breath_event["cycle_undefined"] = False

    # Inspiration / expiration durations
    breath_event["insp_dur_s"] = float(t_cycle - breath_info["t_insp_start"])
    breath_end_t = float(df["time"].iloc[breath_info["breath_end_idx"]])
    breath_event["exp_dur_s"] = float(breath_end_t - t_cycle)

    # Event window
    windows = extract_event_window(df, t_cycle, pre_ms=pre_ms, post_ms=post_ms)
    if not windows["complete"]:
        # I keep this explicit early return so partial windows never leak into model training.
        breath_event["incomplete_window"] = True
        breath_event.update({k: np.nan for k in [
            "paw_base", "pes_base", "pl_base", "pl_at_cycle",
            "delta_paw_max", "delta_pl_max", "dPaw_dt_max", "dPL_dt_max",
            "tf", "event_positive", "dpl_dt_max", "peak_latency_ms",
        ]})
        return breath_event

    breath_event["incomplete_window"] = False

    # Continuous magnitudes
    magnitude_features = compute_event_magnitudes(windows["pre_slice"], windows["post_slice"], fs)
    breath_event.update(magnitude_features)

    # TF
    breath_event["tf"] = compute_tf(
        magnitude_features["delta_paw_max"], magnitude_features["delta_pl_max"], guard=tf_guard
    )

    # Binary label
    label = compute_event_label(
        windows["post_slice"], magnitude_features["pl_base"], t_cycle, fs,
        dpl_min=event_dpl_min, slope_min=event_slope_min,
        peak_max_ms=event_peak_ms,
    )
    breath_event.update(label)

    return breath_event
