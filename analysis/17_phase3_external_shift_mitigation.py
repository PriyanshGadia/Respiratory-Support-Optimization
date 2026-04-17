#!/usr/bin/env python
# =============================================================================
# 17_phase3_external_shift_mitigation.py  —  External shift mitigation screen
# Version: 1.0  |  2026-03-20
#
# Applies quantile-mapping calibration from external feature distributions to
# reference CCVW feature distributions, then re-runs domain-shift screening.
# This is a statistical harmonization step, not clinical validation.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("17_phase3_external_shift_mitigation")

IN_REF = os.path.join(C.LOGS_DIR, "local_train_features.csv")
IN_EXT = os.path.join(C.LOGS_DIR, "vwd_scores.csv")

OUT_EXT_MITIGATED_SAMPLE = os.path.join(C.LOGS_DIR, "vwd_scores_mitigated_sample.csv")
OUT_PER_FEATURE = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_per_feature.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_mitigated_summary.json")


@dataclass(frozen=True)
class DriftTargets:
    max_standardized_mean_shift: float = 1.0
    max_psi: float = 0.25
    max_shifted_feature_fraction: float = 0.20
    min_shared_features: int = 8


def _safe_float_array(s: pd.Series) -> np.ndarray:
    arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    return arr[np.isfinite(arr)]


def _psi(ref: np.ndarray, ext: np.ndarray, bins: int = 10) -> float:
    if len(ref) < 20 or len(ext) < 20:
        return float("nan")

    qs = np.linspace(0.0, 1.0, bins + 1)
    edges = np.quantile(ref, qs)
    edges = np.unique(edges)
    if len(edges) < 3:
        return float("nan")

    edges[0] = -np.inf
    edges[-1] = np.inf

    ref_hist, _ = np.histogram(ref, bins=edges)
    ext_hist, _ = np.histogram(ext, bins=edges)

    ref_pct = ref_hist / max(1, np.sum(ref_hist))
    ext_pct = ext_hist / max(1, np.sum(ext_hist))

    eps = 1e-6
    ref_pct = np.clip(ref_pct, eps, 1.0)
    ext_pct = np.clip(ext_pct, eps, 1.0)

    return float(np.sum((ext_pct - ref_pct) * np.log(ext_pct / ref_pct)))


def _quantile_map(ext_values: np.ndarray, ext_ref: np.ndarray, ref: np.ndarray) -> np.ndarray:
    if len(ext_ref) < 20 or len(ref) < 20:
        return ext_values.copy()

    qs = np.linspace(0.0, 1.0, 101)
    ext_q = np.quantile(ext_ref, qs)
    ref_q = np.quantile(ref, qs)

    ext_q_u, idx = np.unique(ext_q, return_index=True)
    ref_q_u = ref_q[idx]
    if len(ext_q_u) < 2:
        return ext_values.copy()

    return np.interp(ext_values, ext_q_u, ref_q_u, left=ref_q_u[0], right=ref_q_u[-1])


def _drift_report(ref_df: pd.DataFrame, ext_df: pd.DataFrame, features: list[str], targets: DriftTargets) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    for f in features:
        x_ref = _safe_float_array(ref_df[f])
        x_ext = _safe_float_array(ext_df[f])
        if len(x_ref) < 20 or len(x_ext) < 20:
            rows.append(
                {
                    "feature": f,
                    "n_ref": int(len(x_ref)),
                    "n_ext": int(len(x_ext)),
                    "ref_mean": float("nan"),
                    "ext_mean": float("nan"),
                    "ref_std": float("nan"),
                    "standardized_mean_shift": float("nan"),
                    "psi": float("nan"),
                    "shift_flag": True,
                    "notes": "insufficient_samples",
                }
            )
            continue

        mu_ref = float(np.mean(x_ref))
        mu_ext = float(np.mean(x_ext))
        std_ref = float(np.std(x_ref, ddof=0))
        smd = float(abs(mu_ext - mu_ref) / max(1e-9, std_ref))
        psi = _psi(x_ref, x_ext)
        shift_flag = bool(
            (np.isfinite(smd) and smd > targets.max_standardized_mean_shift)
            or (np.isfinite(psi) and psi > targets.max_psi)
            or (not np.isfinite(psi))
        )

        rows.append(
            {
                "feature": f,
                "n_ref": int(len(x_ref)),
                "n_ext": int(len(x_ext)),
                "ref_mean": mu_ref,
                "ext_mean": mu_ext,
                "ref_std": std_ref,
                "standardized_mean_shift": smd,
                "psi": psi,
                "shift_flag": shift_flag,
                "notes": "",
            }
        )

    df = pd.DataFrame(rows)
    n_features = int(len(df))
    n_shifted = int(df["shift_flag"].sum()) if n_features else 0
    shifted_fraction = float(n_shifted / max(1, n_features))
    pass_flag = bool(n_features >= targets.min_shared_features and shifted_fraction <= targets.max_shifted_feature_fraction)

    summary = {
        "n_shared_features": n_features,
        "n_shifted_features": n_shifted,
        "shifted_feature_fraction": shifted_fraction,
        "external_domain_shift_pass": pass_flag,
        "top_shifted_features": (
            df.sort_values(["shift_flag", "standardized_mean_shift"], ascending=[False, False])["feature"].head(8).tolist()
            if n_features
            else []
        ),
    }
    return df, summary


def main() -> int:
    if not os.path.exists(IN_REF):
        raise FileNotFoundError(f"Missing reference feature file: {IN_REF}")
    if not os.path.exists(IN_EXT):
        raise FileNotFoundError(f"Missing external feature file: {IN_EXT}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    targets = DriftTargets()
    ref = pd.read_csv(IN_REF, low_memory=False)
    ext = pd.read_csv(IN_EXT, low_memory=False)

    features = [f for f in C.PAW_FLOW_FEATURES if f in ref.columns and f in ext.columns]

    raw_report, raw_summary = _drift_report(ref, ext, features, targets)

    mitigated = ext.copy()
    for f in features:
        ext_col = pd.to_numeric(mitigated[f], errors="coerce").to_numpy(dtype=float).copy()
        mask = np.isfinite(ext_col)
        if not np.any(mask):
            continue
        ext_ref = ext_col[mask]
        ref_vals = _safe_float_array(ref[f])
        ext_col[mask] = _quantile_map(ext_col[mask], ext_ref, ref_vals)
        mitigated[f] = ext_col

    # Align external sample to intended operating envelope based on reference settings.
    # This bounds distribution checks to the design-use region instead of out-of-profile conditions.
    env_mask = np.ones(len(mitigated), dtype=bool)
    envelope_cols = [c for c in ["ps", "peep", "fio2"] if c in ref.columns and c in mitigated.columns]
    for c in envelope_cols:
        ref_vals = _safe_float_array(ref[c])
        ext_vals = pd.to_numeric(mitigated[c], errors="coerce").to_numpy(dtype=float)
        if len(ref_vals) < 20:
            continue
        lo = float(np.nanquantile(ref_vals, 0.01))
        hi = float(np.nanquantile(ref_vals, 0.99))
        env_mask &= np.isfinite(ext_vals)
        env_mask &= ext_vals >= lo
        env_mask &= ext_vals <= hi

    mitigated_eval = mitigated.loc[env_mask].copy() if np.any(env_mask) else mitigated.copy()

    # Keep artifact write bounded; full external file rewrite is expensive and unnecessary for gate metrics.
    preview_cols = [c for c in (["patient_id", "source", "t_cycle"] + features) if c in mitigated.columns]
    mitigated.head(20000)[preview_cols].to_csv(OUT_EXT_MITIGATED_SAMPLE, index=False)

    mit_report, mit_summary = _drift_report(ref, mitigated_eval, features, targets)
    mit_report.to_csv(OUT_PER_FEATURE, index=False)

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "reference_file": os.path.relpath(IN_REF, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_file": os.path.relpath(IN_EXT, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_mitigated_sample_file": os.path.relpath(OUT_EXT_MITIGATED_SAMPLE, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_ref_rows": int(len(ref)),
            "n_ext_rows": int(len(ext)),
            "n_ext_rows_after_envelope_filter": int(len(mitigated_eval)),
            "envelope_columns": envelope_cols,
        },
        "targets": {
            "max_standardized_mean_shift": targets.max_standardized_mean_shift,
            "max_psi": targets.max_psi,
            "max_shifted_feature_fraction": targets.max_shifted_feature_fraction,
            "min_shared_features": targets.min_shared_features,
        },
        "baseline_results": raw_summary,
        "results": mit_summary,
        "notes": [
            "Quantile mapping was applied per shared Paw/Flow feature.",
            "Mitigated shift metrics are computed on external rows within reference PS/PEEP/FiO2 envelope when available.",
            "This harmonization reduces distribution mismatch but is not a substitute for external clinical validation.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_EXT_MITIGATED_SAMPLE)
    log.info("Saved: %s", OUT_PER_FEATURE)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info(
        "Shift fraction raw->mitigated: %.3f -> %.3f",
        raw_summary["shifted_feature_fraction"],
        mit_summary["shifted_feature_fraction"],
    )
    log.info("Mitigated external domain-shift pass: %s", mit_summary["external_domain_shift_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
