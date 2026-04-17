#!/usr/bin/env python
# =============================================================================
# 11_phase3_adaptive_robustness_check.py  —  Phase 3A robustness stress checks
# Version: 1.0  |  2026-03-20
#
# Stress-tests adaptive controller outputs against bounded perturbations:
# - sensor noise on estimated DeltaPaw
# - command timing jitter
# - actuator lag sensitivity
#
# This is simulation-only robustness screening, not clinical validation.
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
log = logging.getLogger("11_phase3_adaptive_robustness_check")

IN_FILE = os.path.join(C.LOGS_DIR, "phase3_adaptive_rule_predictions.csv")
OUT_SCENARIO = os.path.join(C.LOGS_DIR, "phase3_adaptive_robustness_scenarios.csv")
OUT_PATIENT = os.path.join(C.LOGS_DIR, "phase3_adaptive_robustness_per_patient.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_adaptive_robustness_summary.json")


@dataclass(frozen=True)
class Scenario:
    name: str
    sensor_noise_sigma: float
    timing_jitter_ms: float
    actuator_lag_ms: float


def _scenario_table() -> list[Scenario]:
    return [
        Scenario("nominal_replay", 0.00, 0.0, 0.0),
        Scenario("sensor_noise_light", 0.15, 0.0, 0.0),
        Scenario("sensor_noise_moderate", 0.30, 0.0, 0.0),
        Scenario("timing_jitter_moderate", 0.00, 4.0, 0.0),
        Scenario("actuator_lag_moderate", 0.00, 0.0, 3.0),
        Scenario("combined_moderate", 0.25, 5.0, 4.0),
        Scenario("combined_severe", 0.45, 9.0, 8.0),
    ]


def _apply_scenario(df: pd.DataFrame, s: Scenario, seed: int = 42) -> pd.DataFrame:
    out = df.copy()

    rng = np.random.default_rng(seed)

    dpaw_base = out["delta_paw_adaptive"].to_numpy(dtype=float)
    baseline = out["delta_paw_baseline"].to_numpy(dtype=float)

    # Severity proxy from baseline burden (bounded 0..1.5)
    sev = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)

    noise = rng.normal(0.0, s.sensor_noise_sigma, size=len(out))
    jitter_penalty = 0.020 * abs(s.timing_jitter_ms) * (0.8 + 0.4 * sev)
    lag_penalty = 0.035 * max(0.0, s.actuator_lag_ms) * (0.9 + 0.6 * sev)

    dpaw_stress = np.maximum(0.0, dpaw_base + noise + jitter_penalty + lag_penalty)

    tf = out["tf"].to_numpy(dtype=float)
    dpl_base = out["delta_pl_baseline"].to_numpy(dtype=float)
    dpl_stress = np.where(
        np.isfinite(tf) & (tf > 0.0),
        dpaw_stress * tf,
        dpl_base * (dpaw_stress / np.maximum(1e-9, baseline)),
    )

    out["scenario"] = s.name
    out["delta_paw_stress"] = dpaw_stress
    out["delta_pl_stress"] = np.maximum(0.0, dpl_stress)
    out["pass_dpaw_le_5_stress"] = (out["delta_paw_stress"] <= 5.0).astype(int)
    out["noise_sigma"] = s.sensor_noise_sigma
    out["timing_jitter_ms"] = s.timing_jitter_ms
    out["actuator_lag_ms"] = s.actuator_lag_ms

    return out


def _scenario_stats(stress_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, g in stress_df.groupby("scenario", sort=False):
        rows.append(
            {
                "scenario": name,
                "n_breaths": int(len(g)),
                "dpaw_mean": float(np.nanmean(g["delta_paw_stress"])),
                "dpaw_p95": float(np.nanquantile(g["delta_paw_stress"], 0.95)),
                "pass_rate_le_5": float(np.nanmean(g["pass_dpaw_le_5_stress"])),
            }
        )
    return pd.DataFrame(rows)


def _patient_stats(stress_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, pid), g in stress_df.groupby(["scenario", "patient_id"], sort=False):
        rows.append(
            {
                "scenario": scenario,
                "patient_id": str(pid),
                "n_breaths": int(len(g)),
                "dpaw_mean": float(np.nanmean(g["delta_paw_stress"])),
                "dpaw_p95": float(np.nanquantile(g["delta_paw_stress"], 0.95)),
                "pass_rate_le_5": float(np.nanmean(g["pass_dpaw_le_5_stress"])),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    if not os.path.exists(IN_FILE):
        raise FileNotFoundError(f"Missing input: {IN_FILE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    df = pd.read_csv(IN_FILE, low_memory=False)
    needed = {"patient_id", "delta_paw_baseline", "delta_paw_adaptive", "delta_pl_baseline", "tf"}
    missing = sorted(needed - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in adaptive predictions: {missing}")

    scenario_frames = []
    for i, s in enumerate(_scenario_table()):
        scenario_frames.append(_apply_scenario(df, s, seed=42 + i))

    stress_df = pd.concat(scenario_frames, ignore_index=True)
    scenario_df = _scenario_stats(stress_df)
    patient_df = _patient_stats(stress_df)

    scenario_df.to_csv(OUT_SCENARIO, index=False)
    patient_df.to_csv(OUT_PATIENT, index=False)

    moderate_names = {
        "sensor_noise_light",
        "sensor_noise_moderate",
        "timing_jitter_moderate",
        "actuator_lag_moderate",
        "combined_moderate",
    }

    pass_map = dict(zip(scenario_df["scenario"], scenario_df["pass_rate_le_5"]))

    moderate_min = min(pass_map[k] for k in moderate_names)
    severe_pass = pass_map["combined_severe"]

    robustness_gate = bool(moderate_min >= 0.90 and severe_pass >= 0.80)

    worst_patient = patient_df.sort_values("pass_rate_le_5", ascending=True).iloc[0]

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "source_file": os.path.relpath(IN_FILE, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_breaths": int(len(df)),
            "n_patients": int(df["patient_id"].astype(str).nunique()),
            "n_scenarios": int(len(scenario_df)),
        },
        "targets": {
            "threshold_cmH2O": 5.0,
            "moderate_scenario_min_pass_rate": 0.90,
            "combined_severe_min_pass_rate": 0.80,
        },
        "results": {
            "nominal_pass_rate": float(pass_map["nominal_replay"]),
            "moderate_min_pass_rate": float(moderate_min),
            "combined_severe_pass_rate": float(severe_pass),
            "robustness_gate_met": float(robustness_gate),
            "worst_case_patient": {
                "scenario": str(worst_patient["scenario"]),
                "patient_id": str(worst_patient["patient_id"]),
                "pass_rate_le_5": float(worst_patient["pass_rate_le_5"]),
                "dpaw_p95": float(worst_patient["dpaw_p95"]),
            },
        },
        "notes": [
            "Perturbations are bounded synthetic stressors for screening only.",
            "This does not replace external-dataset validation or plant-coupled simulation.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_SCENARIO)
    log.info("Saved: %s", OUT_PATIENT)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info("Robustness gate met: %s", robustness_gate)
    log.info("Moderate min pass rate: %.3f", moderate_min)
    log.info("Combined severe pass rate: %.3f", severe_pass)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
