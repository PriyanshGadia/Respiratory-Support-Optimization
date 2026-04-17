#!/usr/bin/env python
# =============================================================================
# 16_phase3_external_domain_shift_check.py  —  External domain-shift screening
# Version: 1.0  |  2026-03-20
#
# Compares Paw/Flow-derived feature distributions between CCVW reference data
# and Puritan Bennett external artifact data using standardized mean shift and
# PSI. This is not clinical-outcome validation; it is a data-shift screen.
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
log = logging.getLogger("16_phase3_external_domain_shift_check")

IN_REF = os.path.join(C.LOGS_DIR, "local_train_features.csv")
IN_EXT = os.path.join(C.LOGS_DIR, "vwd_scores.csv")

OUT_PER_FEATURE = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_per_feature.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_external_domain_shift_summary.json")


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

    # Extend edges to ensure inclusion.
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


def main() -> int:
    if not os.path.exists(IN_REF):
        raise FileNotFoundError(f"Missing reference feature file: {IN_REF}")
    if not os.path.exists(IN_EXT):
        raise FileNotFoundError(f"Missing external feature file: {IN_EXT}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    targets = DriftTargets()
    ref = pd.read_csv(IN_REF, low_memory=False)
    ext = pd.read_csv(IN_EXT, low_memory=False)

    candidate_features = [f for f in C.PAW_FLOW_FEATURES if f in ref.columns and f in ext.columns]

    rows: list[dict] = []
    for f in candidate_features:
        x_ref = _safe_float_array(ref[f])
        x_ext = _safe_float_array(ext[f])
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
        psi = _psi(x_ref, x_ext, bins=10)

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

    per_feature = pd.DataFrame(rows)
    per_feature.to_csv(OUT_PER_FEATURE, index=False)

    n_features = int(len(per_feature))
    n_shifted = int(per_feature["shift_flag"].sum()) if n_features else 0
    shifted_fraction = float(n_shifted / max(1, n_features))

    pass_flag = bool(
        n_features >= targets.min_shared_features
        and shifted_fraction <= targets.max_shifted_feature_fraction
    )

    top_shifted = (
        per_feature.sort_values(["shift_flag", "standardized_mean_shift"], ascending=[False, False])["feature"].head(8).tolist()
        if n_features
        else []
    )

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "reference_file": os.path.relpath(IN_REF, C.ANALYSIS_DIR).replace("\\", "/"),
            "external_file": os.path.relpath(IN_EXT, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_ref_rows": int(len(ref)),
            "n_ext_rows": int(len(ext)),
        },
        "targets": {
            "max_standardized_mean_shift": targets.max_standardized_mean_shift,
            "max_psi": targets.max_psi,
            "max_shifted_feature_fraction": targets.max_shifted_feature_fraction,
            "min_shared_features": targets.min_shared_features,
        },
        "results": {
            "n_shared_features": n_features,
            "n_shifted_features": n_shifted,
            "shifted_feature_fraction": shifted_fraction,
            "external_domain_shift_pass": pass_flag,
            "top_shifted_features": top_shifted,
        },
        "notes": [
            "This is a distribution-shift screen on Paw/Flow-derived features.",
            "Passing this screen does not establish clinical safety or efficacy.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_PER_FEATURE)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info("Shared features: %d | Shifted: %d | Fraction: %.3f", n_features, n_shifted, shifted_fraction)
    log.info("External domain-shift pass: %s", pass_flag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
