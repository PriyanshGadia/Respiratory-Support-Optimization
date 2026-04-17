#!/usr/bin/env python
# =============================================================================
# 12_phase3_adaptive_plant_coupled_check.py  —  Plant-coupled robustness screen
# Version: 1.0  |  2026-03-20
#
# Evaluates adaptive outputs under a simplified plant-coupled surrogate:
# actuator lag + command deadtime + control latency + sensor noise.
#
# This is still simulation-level screening and not a replacement for HIL/bench.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("12_phase3_adaptive_plant_coupled_check")

DEFAULT_IN_FILE = os.path.join(C.LOGS_DIR, "phase3_adaptive_rule_predictions.csv")
DEFAULT_OUT_TAG = "adaptive"


def _output_paths(tag: str) -> tuple[str, str, str]:
    safe_tag = "".join(ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in str(tag).strip())
    safe_tag = safe_tag.lower() or DEFAULT_OUT_TAG
    return (
        os.path.join(C.LOGS_DIR, f"phase3_plant_coupled_{safe_tag}_scenarios.csv"),
        os.path.join(C.LOGS_DIR, f"phase3_plant_coupled_{safe_tag}_per_patient.csv"),
        os.path.join(C.LOGS_DIR, f"phase3_plant_coupled_{safe_tag}_summary.json"),
    )


@dataclass(frozen=True)
class PlantScenario:
    name: str
    actuator_tau_ms: float
    command_deadtime_ms: float
    control_latency_ms: float
    sensor_noise_sigma: float


def _scenarios() -> list[PlantScenario]:
    return [
        PlantScenario("plant_nominal", 2.0, 1.0, 1.0, 0.08),
        PlantScenario("plant_moderate", 6.0, 4.0, 4.0, 0.18),
        PlantScenario("plant_severe", 12.0, 8.0, 9.0, 0.30),
    ]


def _apply_plant_scenario(df: pd.DataFrame, s: PlantScenario, seed: int) -> pd.DataFrame:
    out = df.copy()
    rng = np.random.default_rng(seed)

    baseline = out["delta_paw_baseline"].to_numpy(dtype=float)
    target = out["delta_paw_target"].to_numpy(dtype=float)
    open_ms = out["open_time_ms"].to_numpy(dtype=float)

    # Requested control benefit from adaptive strategy.
    requested_reduction = np.maximum(0.0, baseline - target)

    # Surrogate coupling: usable actuation fraction shrinks with lag and delay budget.
    total_delay = s.command_deadtime_ms + s.control_latency_ms
    open_ref = np.maximum(20.0, open_ms)

    delay_factor = np.exp(-total_delay / np.maximum(1.0, 0.6 * open_ref))
    lag_factor = open_ref / (open_ref + s.actuator_tau_ms)

    effectiveness = np.clip(delay_factor * lag_factor, 0.20, 1.0)
    achieved_reduction = effectiveness * requested_reduction

    # Residual coupling error is stronger for higher baseline burden.
    sev = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)
    coupling_penalty = (1.0 - effectiveness) * 0.25 * sev

    sensor_noise = rng.normal(0.0, s.sensor_noise_sigma, size=len(out))

    dpaw_plant = np.maximum(0.0, baseline - achieved_reduction + coupling_penalty + sensor_noise)

    tf = out["tf"].to_numpy(dtype=float)
    dpl_base = out["delta_pl_baseline"].to_numpy(dtype=float)
    dpl_plant = np.where(
        np.isfinite(tf) & (tf > 0.0),
        dpaw_plant * tf,
        dpl_base * (dpaw_plant / np.maximum(1e-9, baseline)),
    )

    out["scenario"] = s.name
    out["delta_paw_plant"] = dpaw_plant
    out["delta_pl_plant"] = np.maximum(0.0, dpl_plant)
    out["pass_dpaw_le_5_plant"] = (out["delta_paw_plant"] <= 5.0).astype(int)
    out["actuator_tau_ms"] = s.actuator_tau_ms
    out["command_deadtime_ms"] = s.command_deadtime_ms
    out["control_latency_ms"] = s.control_latency_ms
    out["sensor_noise_sigma"] = s.sensor_noise_sigma

    return out


def _scenario_stats(stress_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, g in stress_df.groupby("scenario", sort=False):
        rows.append(
            {
                "scenario": name,
                "n_breaths": int(len(g)),
                "dpaw_mean": float(np.nanmean(g["delta_paw_plant"])),
                "dpaw_p95": float(np.nanquantile(g["delta_paw_plant"], 0.95)),
                "pass_rate_le_5": float(np.nanmean(g["pass_dpaw_le_5_plant"])),
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
                "dpaw_mean": float(np.nanmean(g["delta_paw_plant"])),
                "dpaw_p95": float(np.nanquantile(g["delta_paw_plant"], 0.95)),
                "pass_rate_le_5": float(np.nanmean(g["pass_dpaw_le_5_plant"])),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plant-coupled adaptive robustness screening")
    parser.add_argument(
        "--input",
        default=DEFAULT_IN_FILE,
        help="Path to predictions CSV (default: phase3_adaptive_rule_predictions.csv)",
    )
    parser.add_argument(
        "--target-column",
        default="delta_paw_adaptive",
        help="Column name representing adaptive command target DeltaPaw",
    )
    parser.add_argument(
        "--output-tag",
        default=DEFAULT_OUT_TAG,
        help="Artifact tag for output filenames (default: adaptive)",
    )
    args = parser.parse_args()

    in_file = args.input

    if not os.path.exists(in_file):
        raise FileNotFoundError(f"Missing input: {in_file}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)
    out_scenario, out_patient, out_summary = _output_paths(args.output_tag)

    df = pd.read_csv(in_file, low_memory=False)
    target_col = args.target_column

    needed = {"patient_id", "delta_paw_baseline", target_col, "delta_pl_baseline", "tf", "open_time_ms"}
    missing = sorted(needed - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in adaptive predictions: {missing}")

    if target_col != "delta_paw_target":
        df = df.copy()
        df["delta_paw_target"] = df[target_col].astype(float)

    frames = []
    for i, s in enumerate(_scenarios()):
        frames.append(_apply_plant_scenario(df, s, seed=200 + i))

    stress_df = pd.concat(frames, ignore_index=True)
    scenario_df = _scenario_stats(stress_df)
    patient_df = _patient_stats(stress_df)

    scenario_df.to_csv(out_scenario, index=False)
    patient_df.to_csv(out_patient, index=False)

    pass_map = dict(zip(scenario_df["scenario"], scenario_df["pass_rate_le_5"]))
    moderate = float(pass_map["plant_moderate"])
    severe = float(pass_map["plant_severe"])

    aggregate_gate = bool(moderate >= 0.90 and severe >= 0.80)

    worst = patient_df.sort_values("pass_rate_le_5", ascending=True).iloc[0]
    severe_rows = patient_df[patient_df["scenario"] == "plant_severe"].copy()
    moderate_rows = patient_df[patient_df["scenario"] == "plant_moderate"].copy()

    worst_severe = severe_rows.sort_values("pass_rate_le_5", ascending=True).iloc[0]
    worst_moderate = moderate_rows.sort_values("pass_rate_le_5", ascending=True).iloc[0]

    patient_level_gate = bool(
        float(worst_moderate["pass_rate_le_5"]) >= 0.90
        and float(worst_severe["pass_rate_le_5"]) >= 0.80
    )

    strict_gate = bool(aggregate_gate and patient_level_gate)

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "source_file": os.path.relpath(in_file, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_breaths": int(len(df)),
            "n_patients": int(df["patient_id"].astype(str).nunique()),
            "n_scenarios": int(len(scenario_df)),
        },
        "targets": {
            "threshold_cmH2O": 5.0,
            "plant_moderate_min_pass_rate": 0.90,
            "plant_severe_min_pass_rate": 0.80,
            "plant_moderate_min_patient_pass_rate": 0.90,
            "plant_severe_min_patient_pass_rate": 0.80,
        },
        "results": {
            "plant_nominal_pass_rate": float(pass_map["plant_nominal"]),
            "plant_moderate_pass_rate": moderate,
            "plant_severe_pass_rate": severe,
            "plant_coupled_gate_met_aggregate": float(aggregate_gate),
            "plant_moderate_min_patient_pass_rate": float(worst_moderate["pass_rate_le_5"]),
            "plant_severe_min_patient_pass_rate": float(worst_severe["pass_rate_le_5"]),
            "plant_coupled_gate_met_patient_level": float(patient_level_gate),
            "plant_coupled_gate_met": float(strict_gate),
            "worst_case_patient": {
                "scenario": str(worst["scenario"]),
                "patient_id": str(worst["patient_id"]),
                "pass_rate_le_5": float(worst["pass_rate_le_5"]),
                "dpaw_p95": float(worst["dpaw_p95"]),
            },
            "worst_case_patient_moderate": {
                "scenario": str(worst_moderate["scenario"]),
                "patient_id": str(worst_moderate["patient_id"]),
                "pass_rate_le_5": float(worst_moderate["pass_rate_le_5"]),
                "dpaw_p95": float(worst_moderate["dpaw_p95"]),
            },
            "worst_case_patient_severe": {
                "scenario": str(worst_severe["scenario"]),
                "patient_id": str(worst_severe["patient_id"]),
                "pass_rate_le_5": float(worst_severe["pass_rate_le_5"]),
                "dpaw_p95": float(worst_severe["dpaw_p95"]),
            },
        },
        "limitations": [
            "Uses simplified first-order actuator and delay surrogate; not HIL/bench evidence.",
            "External replay is not computed here because current combined predictions contain CCVW-only rows.",
        ],
    }

    with open(out_summary, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", out_scenario)
    log.info("Saved: %s", out_patient)
    log.info("Saved: %s", out_summary)
    log.info("Plant-coupled gate met (aggregate): %s", aggregate_gate)
    log.info("Plant-coupled gate met (patient-level): %s", patient_level_gate)
    log.info("Plant-coupled gate met (strict): %s", strict_gate)
    log.info("Plant moderate pass rate: %.3f", moderate)
    log.info("Plant severe pass rate: %.3f", severe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
