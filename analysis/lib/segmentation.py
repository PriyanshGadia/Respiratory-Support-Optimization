# =============================================================================
# lib/segmentation.py  —  Breath segmentation (Protocol Section 5)
# Version: 1.0  |  2026-03-14
# =============================================================================

import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def segment_breaths(df: pd.DataFrame, fs: float,
                    eps: float = 0.02,
                    insp_sustain_ms: float = 40.0,
                    insp_dur_min_s: float = 0.20,
                    insp_dur_max_s: float = 4.0,
                    flow_peak_min: float = 0.05,
                    paw_slope_thresh: float = 1.5) -> list:
    """
    Segment a continuous waveform DataFrame into individual breaths.
    Section 5 — primary (flow-based) with pressure-fallback.

    Parameters
    ----------
    df : DataFrame with unified columns (time, flow, paw, ...)
    fs : sampling rate in Hz

    Returns
    -------
    list of dicts, each describing one breath:
      {
        'insp_start_idx': int,
        'insp_end_idx':   int,   (last sample of inspiration)
        'breath_end_idx': int,   (start of next inspiration - 1)
        't_insp_start':   float, (seconds)
        'f_peak':         float, (L/s)
        'f_peak_idx':     int,
        'method':         str,   ('flow' | 'fallback')
        'exclude':        bool,
        'exclude_reason': str,
      }
    """
    time = df["time"].values
    flow = df["flow"].values

    insp_sustain_n = max(1, int(insp_sustain_ms / 1000.0 * fs))
    dt = 1.0 / fs

    breaths = []

    # -----------------------------------------------------------------------
    # Primary: flow-based segmentation with hysteresis
    #   Inspiratory: flow > +eps sustained for insp_sustain_n samples
    # -----------------------------------------------------------------------
    n = len(flow)
    insp_phase = flow > eps

    # Find raw rising crossings (non-insp → insp)
    raw_onsets = np.where(np.diff(insp_phase.astype(int)) == 1)[0] + 1

    confirmed_onsets = []
    for onset_idx in raw_onsets:
        end_check = min(onset_idx + insp_sustain_n, n)
        # I keep this sustain check to reject one-sample spikes that otherwise
        # look like real inspiratory starts.
        if np.all(insp_phase[onset_idx:end_check]):
            confirmed_onsets.append(onset_idx)

    if len(confirmed_onsets) < 2:
        log.warning("Fewer than 2 confirmed inspiratory onsets; trying fallback.")
        return _fallback_segmentation(
            df,
            fs,
            insp_dur_min_s,
            insp_dur_max_s,
            flow_peak_min,
            paw_slope_thresh,
        )

    for i, onset in enumerate(confirmed_onsets):
        next_onset = confirmed_onsets[i + 1] if i + 1 < len(confirmed_onsets) else n - 1

        # Find where flow drops back below -eps (expiratory onset)
        insp_end = onset
        for j in range(onset, next_onset):
            if flow[j] > eps:
                insp_end = j
            else:
                break

        # F_peak in inspiratory segment
        if insp_end > onset:
            fp_idx = onset + int(np.argmax(flow[onset:insp_end + 1]))
        else:
            fp_idx = onset
        f_peak = float(flow[fp_idx])

        insp_dur = (insp_end - onset) * dt

        # Exclusion checks
        exclude = False
        reason = ""
        if insp_dur < insp_dur_min_s:
            exclude, reason = True, f"short_insp:{insp_dur:.3f}s"
        elif insp_dur > insp_dur_max_s:
            exclude, reason = True, f"long_insp:{insp_dur:.3f}s"
        elif f_peak < flow_peak_min:
            exclude, reason = True, f"low_fpeak:{f_peak:.3f}"

        breaths.append({
            "insp_start_idx":  int(onset),
            "insp_end_idx":    int(insp_end),
            "breath_end_idx":  int(next_onset - 1),
            "t_insp_start":    float(time[onset]),
            "f_peak":          f_peak,
            "f_peak_idx":      int(fp_idx),
            "method":          "flow",
            "exclude":         exclude,
            "exclude_reason":  reason,
        })

    return breaths


def _fallback_segmentation(df, fs, insp_dur_min_s, insp_dur_max_s,
                            flow_peak_min, paw_slope_thresh):
    """
    Pressure-assisted fallback segmentation (Section 5.2).
    Returns same structure as segment_breaths, all flagged with method='fallback'.
    """
    time = df["time"].values
    flow = df["flow"].values
    paw_signal = df["paw"].values if "paw" in df.columns else np.zeros(len(time))
    dt = 1.0 / fs

    # Candidate onset: dPaw/dt > threshold AND flow >= 0
    dpaw = np.gradient(paw_signal, dt)
    candidate = (dpaw > paw_slope_thresh) & (flow >= 0)
    raw_onsets = np.where(np.diff(candidate.astype(int)) == 1)[0] + 1

    breaths = []
    n = len(flow)
    for i, onset in enumerate(raw_onsets):
        next_onset = raw_onsets[i + 1] if i + 1 < len(raw_onsets) else n - 1

        insp_end = onset
        for j in range(onset, next_onset):
            if flow[j] >= 0:
                insp_end = j
            else:
                break

        fp_idx = onset + int(np.argmax(flow[onset:insp_end + 1])) if insp_end > onset else onset
        f_peak = float(flow[fp_idx])
        insp_dur = (insp_end - onset) * dt

        exclude = False
        reason = ""
        if insp_dur < insp_dur_min_s:
            exclude, reason = True, f"short_insp:{insp_dur:.3f}s"
        elif insp_dur > insp_dur_max_s:
            exclude, reason = True, f"long_insp:{insp_dur:.3f}s"
        elif f_peak < flow_peak_min:
            exclude, reason = True, f"low_fpeak:{f_peak:.3f}"

        breaths.append({
            "insp_start_idx":  int(onset),
            "insp_end_idx":    int(insp_end),
            "breath_end_idx":  int(next_onset - 1),
            "t_insp_start":    float(time[onset]),
            "f_peak":          f_peak,
            "f_peak_idx":      int(fp_idx),
            "method":          "fallback",
            "exclude":         exclude,
            "exclude_reason":  reason,
        })

    return breaths
