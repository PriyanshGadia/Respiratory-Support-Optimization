#!/usr/bin/env python
"""
Standalone dataset tester core.

This module reuses the existing REBOOT analysis library to run a single-file
analysis on arbitrary imported datasets through a simple unified schema.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse existing project analysis code without modifying the original pipeline.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REBOOT_DIR = os.path.dirname(_THIS_DIR)
_ANALYSIS_DIR = os.path.join(_REBOOT_DIR, "analysis")

if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)

import config as C  # type: ignore
from lib.events import process_breath  # type: ignore
from lib.features import build_feature_row  # type: ignore
from lib.qc import breath_quality_flags, file_qc, preprocess_signal  # type: ignore
from lib.segmentation import segment_breaths  # type: ignore


@dataclass
class RunConfig:
    file_path: str
    time_col: Optional[str]
    flow_col: str
    paw_col: str
    pes_col: Optional[str]
    patient_id: str
    source_tag: str
    fs_hz: Optional[float]
    ets_frac: Optional[float]
    ps: Optional[float]
    peep: Optional[float]
    fio2: Optional[float]


@dataclass
class AnalysisResult:
    summary: Dict[str, object]
    features_df: pd.DataFrame
    unified_df: pd.DataFrame


@dataclass
class BatchAnalysisResult:
    results: list[AnalysisResult]
    combined_features_df: pd.DataFrame
    combined_unified_df: pd.DataFrame
    batch_summary: Dict[str, object]


def read_input_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file extension: {ext}. Use CSV or Excel.")


def list_columns(path: str) -> Tuple[list[str], pd.DataFrame]:
    preview_df = read_input_file(path)
    column_names = [str(col_name) for col_name in preview_df.columns]
    return column_names, preview_df.head(10)


def _as_float_series(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").values.astype(np.float64)


def _estimate_fs_from_time(time_arr: np.ndarray) -> Optional[float]:
    finite_mask = np.isfinite(time_arr)
    finite_time = time_arr[finite_mask]
    if len(finite_time) < 3:
        return None
    dts = np.diff(finite_time)
    dts = dts[dts > 0]
    if len(dts) == 0:
        return None
    dt = float(np.median(dts))
    if dt <= 0:
        return None
    return 1.0 / dt


def build_unified_df(raw_df: pd.DataFrame, cfg: RunConfig) -> Tuple[pd.DataFrame, float]:
    if not cfg.flow_col or not cfg.paw_col:
        raise ValueError("Flow and Paw columns are required.")

    flow = _as_float_series(raw_df[cfg.flow_col])
    paw = _as_float_series(raw_df[cfg.paw_col])

    if cfg.pes_col:
        pes = _as_float_series(raw_df[cfg.pes_col])
    else:
        pes = np.full(len(raw_df), np.nan, dtype=np.float64)

    if cfg.time_col:
        time = _as_float_series(raw_df[cfg.time_col])
        fs_est = _estimate_fs_from_time(time)
        fs = cfg.fs_hz if cfg.fs_hz and cfg.fs_hz > 0 else fs_est
        if fs is None:
            raise ValueError("Could not infer sampling rate from time; provide fs manually.")
    else:
        if not cfg.fs_hz or cfg.fs_hz <= 0:
            raise ValueError("When time column is not provided, fs must be set.")
        fs = float(cfg.fs_hz)
        time = np.arange(len(raw_df), dtype=np.float64) / fs

    unified = pd.DataFrame(
        {
            "time": time,
            "flow": flow,
            "paw": paw,
            "pes": pes,
            "patient_id": cfg.patient_id,
            "source": cfg.source_tag,
        }
    )

    # Attach optional metadata so downstream feature builder can include it.
    unified["ps"] = np.nan if cfg.ps is None else float(cfg.ps)
    unified["peep"] = np.nan if cfg.peep is None else float(cfg.peep)
    unified["fio2"] = np.nan if cfg.fio2 is None else float(cfg.fio2)
    unified["ets"] = np.nan if cfg.ets_frac is None else float(cfg.ets_frac)

    # Drop rows where both key channels are missing.
    keep = np.isfinite(unified["flow"].values) | np.isfinite(unified["paw"].values)
    unified = unified.loc[keep].reset_index(drop=True)

    return unified, float(fs)


def _safe_stats(arr: np.ndarray) -> Dict[str, float]:
    finite_values = arr[np.isfinite(arr)]
    if len(finite_values) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "std": np.nan,
            "min": np.nan,
            "p5": np.nan,
            "p50": np.nan,
            "p95": np.nan,
            "max": np.nan,
        }
    return {
        "n": int(len(finite_values)),
        "mean": float(np.mean(finite_values)),
        "std": float(np.std(finite_values)),
        "min": float(np.min(finite_values)),
        "p5": float(np.percentile(finite_values, 5)),
        "p50": float(np.percentile(finite_values, 50)),
        "p95": float(np.percentile(finite_values, 95)),
        "max": float(np.max(finite_values)),
    }


def run_analysis(cfg: RunConfig) -> AnalysisResult:
    raw_df = read_input_file(cfg.file_path)
    unified_df, fs = build_unified_df(raw_df, cfg)

    has_pes = bool((~pd.isna(unified_df["pes"]).values).any())

    qc_required = ["time", "flow", "paw"]
    # I keep this QC gate up front because downstream breath segmentation
    # fails noisily when time/flow integrity is off.
    qc = file_qc(
        unified_df,
        declared_fs=fs,
        required_channels=qc_required,
        fs_tol=C.FS_TOLERANCE * 2,
        max_miss=C.MAX_MISSINGNESS,
        flatline_max_s=C.FLATLINE_MAX_S,
    )

    if not qc["pass"]:
        summary = {
            "status": "qc_failed",
            "qc_pass": False,
            "qc_reasons": qc["reasons"],
            "fs_used_hz": fs,
            "n_samples": int(len(unified_df)),
            "duration_s": (
                float(unified_df["time"].iloc[-1] - unified_df["time"].iloc[0])
                if len(unified_df) > 1
                else 0.0
            ),
            "has_pes": has_pes,
        }
        return AnalysisResult(
            summary=summary,
            features_df=pd.DataFrame(),
            unified_df=unified_df,
        )

    df_clean = preprocess_signal(
        unified_df,
        fs=fs,
        hampel_window=C.HAMPEL_WINDOW,
        hampel_thresh=C.HAMPEL_THRESHOLD,
        flow_lp_hz=C.FLOW_LOWPASS_HZ,
        pres_lp_hz=C.PRES_LOWPASS_HZ,
        apply_hampel=False,
    )

    ets_frac = float(cfg.ets_frac) if cfg.ets_frac is not None else C.ETS_DEFAULT
    ets_defaulted = cfg.ets_frac is None

    breaths = segment_breaths(
        df_clean,
        fs,
        eps=C.FLOW_EPS,
        insp_sustain_ms=C.INSP_SUSTAIN_MS,
        insp_dur_min_s=C.INSP_DUR_MIN_S,
        insp_dur_max_s=C.INSP_DUR_MAX_S,
        flow_peak_min=C.FLOW_PEAK_MIN,
    )

    feature_rows: list[dict] = []
    n_excluded_seg = 0
    n_cycle_undef = 0
    n_incomplete = 0
    n_quality_excluded = 0

    for breath in breaths:
        if breath.get("exclude", False):
            n_excluded_seg += 1
            continue

        breath_event_features = process_breath(
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

        if breath_event_features.get("cycle_undefined"):
            n_cycle_undef += 1
            continue
        if breath_event_features.get("incomplete_window"):
            n_incomplete += 1
            continue

        start = int(breath["insp_start_idx"])
        end = int(breath["breath_end_idx"])
        breath_df = df_clean.iloc[start : end + 1]
        flags = breath_quality_flags(
            breath_df,
            fs,
            hampel_window=C.HAMPEL_WINDOW,
            hampel_thresh=C.HAMPEL_THRESHOLD,
            bad_frac=C.HAMPEL_BREATH_FRAC,
            flatline_ms=C.FLATLINE_BREATH_MS,
            pre_ms=C.PRE_WIN_MS,
            post_ms=C.POST_WIN_MS,
            t_cycle=breath_event_features.get("t_cycle"),
            apply_hampel=False,
        )

        low_quality = bool(flags.get("low_quality_flow", False)) or bool(
            flags.get("low_quality_paw", False)
        )
        if has_pes:
            low_quality = low_quality or bool(flags.get("low_quality_pes", False))

        if low_quality:
            n_quality_excluded += 1
            continue

        t_cycle = float(breath_event_features["t_cycle"])
        time = df_clean["time"].values
        # I re-slice around the detected cycle marker so every feature row
        # is built from the exact same window definition.
        full_mask = (time >= t_cycle - C.PRE_WIN_MS / 1000.0) & (
            time <= t_cycle + C.POST_WIN_MS / 1000.0
        )
        waveform_window_df = df_clean[full_mask]

        for key in ["ps", "peep", "fio2", "ets"]:
            if key in df_clean.columns:
                metadata_value = df_clean[key].iloc[0]
                breath_event_features[key] = (
                    float(metadata_value) if pd.notna(metadata_value) else np.nan
                )

        feature_row = build_feature_row(
            breath_event_features,
            waveform_window_df,
            fs,
            include_clinical=True,
        )
        feature_row["patient_id"] = cfg.patient_id
        feature_row["source"] = cfg.source_tag
        feature_row["fs_hz"] = fs
        feature_rows.append(feature_row)

    features_df = pd.DataFrame(feature_rows)

    duration_s = float(df_clean["time"].iloc[-1] - df_clean["time"].iloc[0]) if len(df_clean) > 1 else 0.0
    n_segmented = len(breaths)
    n_valid = len(features_df)
    retained_rate = float(n_valid / n_segmented) if n_segmented else np.nan

    stats = {
        "delta_paw_max": (
            _safe_stats(features_df["delta_paw_max"].values)
            if "delta_paw_max" in features_df
            else _safe_stats(np.array([]))
        ),
        "dPaw_dt_max": (
            _safe_stats(features_df["dPaw_dt_max"].values)
            if "dPaw_dt_max" in features_df
            else _safe_stats(np.array([]))
        ),
        "f_peak": (
            _safe_stats(features_df["f_peak"].values)
            if "f_peak" in features_df
            else _safe_stats(np.array([]))
        ),
    }

    if "delta_pl_max" in features_df:
        stats["delta_pl_max"] = _safe_stats(features_df["delta_pl_max"].values)

    event_rate = np.nan
    if "event_positive" in features_df.columns:
        ep = features_df["event_positive"].dropna().astype(float)
        if len(ep):
            event_rate = float(ep.mean())

    summary = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": cfg.file_path,
        "patient_id": cfg.patient_id,
        "source": cfg.source_tag,
        "has_pes": has_pes,
        "fs_used_hz": fs,
        "n_samples": int(len(df_clean)),
        "duration_s": duration_s,
        "qc_pass": True,
        "qc_reasons": [],
        "n_segmented": int(n_segmented),
        "n_excluded_segmentation": int(n_excluded_seg),
        "n_cycle_undefined": int(n_cycle_undef),
        "n_incomplete_window": int(n_incomplete),
        "n_quality_excluded": int(n_quality_excluded),
        "n_valid_breaths": int(n_valid),
        "retained_rate": retained_rate,
        "event_positive_rate": event_rate,
        "stats": stats,
    }

    return AnalysisResult(summary=summary, features_df=features_df, unified_df=df_clean)


def run_batch_analysis(base_cfg: RunConfig, file_paths: list[str]) -> BatchAnalysisResult:
    if not file_paths:
        raise ValueError("No files were provided for batch analysis.")

    results: list[AnalysisResult] = []
    feature_tables: list[pd.DataFrame] = []
    unified_tables: list[pd.DataFrame] = []
    per_file_rows: list[dict] = []

    for idx, path in enumerate(file_paths, start=1):
        cfg = deepcopy(base_cfg)
        cfg.file_path = path

        # For multi-file runs, make patient IDs unique while preserving user prefix.
        if len(file_paths) > 1:
            stem = os.path.splitext(os.path.basename(path))[0]
            base_pid = (base_cfg.patient_id or "EXT").strip()
            cfg.patient_id = f"{base_pid}_{idx:03d}_{stem}"

        file_analysis = run_analysis(cfg)
        results.append(file_analysis)

        features = file_analysis.features_df.copy()
        if not features.empty:
            features["input_file"] = path
            feature_tables.append(features)

        unified = file_analysis.unified_df.copy()
        if not unified.empty:
            unified["input_file"] = path
            unified_tables.append(unified)

        per_file_summary = {
            "input_file": path,
            "status": file_analysis.summary.get("status"),
            "qc_pass": file_analysis.summary.get("qc_pass"),
            "has_pes": file_analysis.summary.get("has_pes"),
            "fs_used_hz": file_analysis.summary.get("fs_used_hz"),
            "n_samples": file_analysis.summary.get("n_samples"),
            "n_segmented": file_analysis.summary.get("n_segmented"),
            "n_valid_breaths": file_analysis.summary.get("n_valid_breaths"),
            "retained_rate": file_analysis.summary.get("retained_rate"),
            "event_positive_rate": file_analysis.summary.get("event_positive_rate"),
        }
        per_file_rows.append(per_file_summary)

    combined_features_df = pd.concat(feature_tables, ignore_index=True) if feature_tables else pd.DataFrame()
    combined_unified_df = pd.concat(unified_tables, ignore_index=True) if unified_tables else pd.DataFrame()
    per_file_df = pd.DataFrame(per_file_rows)

    n_total = len(results)
    n_ok = int((per_file_df["status"] == "ok").sum()) if not per_file_df.empty else 0
    n_qc_pass = (
        int(per_file_df["qc_pass"].fillna(False).astype(bool).sum())
        if not per_file_df.empty
        else 0
    )
    n_valid_breaths = int(combined_features_df.shape[0])

    batch_summary: Dict[str, object] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_files_total": n_total,
        "n_files_ok": n_ok,
        "n_files_qc_pass": n_qc_pass,
        "n_valid_breaths_total": n_valid_breaths,
        "input_files": file_paths,
        "per_file": per_file_rows,
    }

    if not combined_features_df.empty:
        if "delta_paw_max" in combined_features_df.columns:
            batch_summary["delta_paw_max"] = _safe_stats(
                combined_features_df["delta_paw_max"].values.astype(np.float64)
            )
        if "delta_pl_max" in combined_features_df.columns:
            batch_summary["delta_pl_max"] = _safe_stats(
                combined_features_df["delta_pl_max"].values.astype(np.float64)
            )

    return BatchAnalysisResult(
        results=results,
        combined_features_df=combined_features_df,
        combined_unified_df=combined_unified_df,
        batch_summary=batch_summary,
    )


def _summary_rows(summary: Dict[str, object]) -> pd.DataFrame:
    rows = []
    for key in [
        "status",
        "patient_id",
        "source",
        "has_pes",
        "fs_used_hz",
        "n_samples",
        "duration_s",
        "qc_pass",
        "n_segmented",
        "n_excluded_segmentation",
        "n_cycle_undefined",
        "n_incomplete_window",
        "n_quality_excluded",
        "n_valid_breaths",
        "retained_rate",
        "event_positive_rate",
    ]:
        rows.append({"metric": key, "value": summary.get(key)})
    return pd.DataFrame(rows)


def export_report(result: AnalysisResult, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    summary_path = os.path.join(out_dir, "analysis_summary.json")
    features_path = os.path.join(out_dir, "breath_features.csv")
    cleaned_path = os.path.join(out_dir, "cleaned_unified_waveform.csv")
    metrics_path = os.path.join(out_dir, "summary_metrics.csv")
    report_md_path = os.path.join(out_dir, "report.md")

    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(result.summary, fh, indent=2, default=str)

    result.features_df.to_csv(features_path, index=False)
    result.unified_df.to_csv(cleaned_path, index=False)
    _summary_rows(result.summary).to_csv(metrics_path, index=False)

    md_lines = [
        "# Standalone Dataset Test Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Run Summary",
        "",
    ]

    for _, metric_row in _summary_rows(result.summary).iterrows():
        md_lines.append(f"- {metric_row['metric']}: {metric_row['value']}")

    md_lines.extend([
        "",
        "## Signal Statistics",
        "",
    ])

    stats = result.summary.get("stats", {}) if isinstance(result.summary, dict) else {}
    if isinstance(stats, dict):
        for signal, stat_dict in stats.items():
            md_lines.append(f"### {signal}")
            if isinstance(stat_dict, dict):
                for k in ["n", "mean", "std", "min", "p5", "p50", "p95", "max"]:
                    md_lines.append(f"- {k}: {stat_dict.get(k)}")
            md_lines.append("")

    with open(report_md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines).strip() + "\n")

    return {
        "summary_json": summary_path,
        "features_csv": features_path,
        "cleaned_csv": cleaned_path,
        "summary_csv": metrics_path,
        "report_md": report_md_path,
    }


def export_batch_report(batch: BatchAnalysisResult, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    summary_path = os.path.join(out_dir, "batch_summary.json")
    per_file_path = os.path.join(out_dir, "batch_per_file_summary.csv")
    features_path = os.path.join(out_dir, "batch_combined_breath_features.csv")
    cleaned_path = os.path.join(out_dir, "batch_combined_cleaned_waveform.csv")
    report_md_path = os.path.join(out_dir, "batch_report.md")

    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(batch.batch_summary, fh, indent=2, default=str)

    per_file_df = pd.DataFrame(batch.batch_summary.get("per_file", []))
    per_file_df.to_csv(per_file_path, index=False)
    batch.combined_features_df.to_csv(features_path, index=False)
    batch.combined_unified_df.to_csv(cleaned_path, index=False)

    md = [
        "# Standalone Batch Dataset Test Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Batch Summary",
        "",
        f"- n_files_total: {batch.batch_summary.get('n_files_total')}",
        f"- n_files_ok: {batch.batch_summary.get('n_files_ok')}",
        f"- n_files_qc_pass: {batch.batch_summary.get('n_files_qc_pass')}",
        f"- n_valid_breaths_total: {batch.batch_summary.get('n_valid_breaths_total')}",
        "",
        "## Per-file Results",
        "",
    ]

    if per_file_df.empty:
        md.append("No per-file records.")
    else:
        for _, file_row in per_file_df.iterrows():
            file_path = file_row.get("input_file")
            status = file_row.get("status")
            qc_pass = file_row.get("qc_pass")
            valid_breaths = file_row.get("n_valid_breaths")
            md.append(
                f"- {file_path}: status={status}, "
                f"qc_pass={qc_pass}, n_valid_breaths={valid_breaths}"
            )

    with open(report_md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md).strip() + "\n")

    return {
        "batch_summary_json": summary_path,
        "batch_per_file_csv": per_file_path,
        "batch_features_csv": features_path,
        "batch_cleaned_csv": cleaned_path,
        "batch_report_md": report_md_path,
    }
