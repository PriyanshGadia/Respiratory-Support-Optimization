#!/usr/bin/env python
# =============================================================================
# 13_phase3_model_based_controller_eval.py  —  Delay-compensated controller eval
# Version: 1.0  |  2026-03-20
#
# Builds a simple model-based, delay-compensated breath-level controller that
# pre-compensates for actuator lag/deadtime and evaluates it under both
# perturbation and plant-coupled stress scenarios.
#
# This is a simulation benchmark, not a deployable controller.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("13_phase3_model_based_controller_eval")

IN_FILE = os.path.join(C.LOGS_DIR, "phase3_adaptive_rule_predictions.csv")
OUT_PRED = os.path.join(C.LOGS_DIR, "phase3_model_based_predictions.csv")
OUT_PATIENT = os.path.join(C.LOGS_DIR, "phase3_model_based_per_patient.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_model_based_summary.json")


@dataclass(frozen=True)
class ModelConfig:
    low_setpoint: float
    mid_setpoint: float
    high_setpoint: float
    tau_est_ms: float
    deadtime_est_ms: float
    latency_est_ms: float
    eff_floor: float


def _validate_input(df: pd.DataFrame) -> None:
    required = {
        "patient_id",
        "delta_paw_baseline",
        "delta_paw_adaptive",
        "delta_pl_baseline",
        "open_time_ms",
        "tf",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in input: {missing}")


def _plant_pass_rates(dpaw_cmd: np.ndarray, baseline: np.ndarray, open_ms: np.ndarray, threshold: float) -> dict:
    def _pass_rate(tau: float, dead: float, lat: float, sigma: float, seed: int) -> float:
        rng = np.random.default_rng(seed)
        open_ref = np.maximum(20.0, open_ms)
        eff = np.clip(
            np.exp(-(dead + lat) / np.maximum(1.0, 0.6 * open_ref)) * open_ref / (open_ref + tau),
            0.20,
            1.0,
        )
        req = np.maximum(0.0, baseline - dpaw_cmd)
        achieved = eff * req
        sev = np.clip((baseline - threshold) / 5.0, 0.0, 1.5)
        coupling_penalty = (1.0 - eff) * 0.25 * sev
        y = np.maximum(0.0, baseline - achieved + coupling_penalty + rng.normal(0.0, sigma, size=len(baseline)))
        return float(np.mean(y <= threshold))

    nominal = _pass_rate(2.0, 1.0, 1.0, 0.08, 200)
    moderate = _pass_rate(6.0, 4.0, 4.0, 0.18, 201)
    severe = _pass_rate(12.0, 8.0, 9.0, 0.30, 202)

    return {
        "plant_nominal_pass_rate": nominal,
        "plant_moderate_pass_rate": moderate,
        "plant_severe_pass_rate": severe,
        "plant_gate_met": float(moderate >= 0.90 and severe >= 0.80),
    }


def _perturbation_pass_rates(dpaw_cmd: np.ndarray, baseline: np.ndarray, threshold: float) -> dict:
    scenarios = {
        "sensor_noise_light": (0.15, 0.0, 0.0, 43),
        "sensor_noise_moderate": (0.30, 0.0, 0.0, 44),
        "timing_jitter_moderate": (0.00, 4.0, 0.0, 45),
        "actuator_lag_moderate": (0.00, 0.0, 3.0, 46),
        "combined_moderate": (0.25, 5.0, 4.0, 47),
        "combined_severe": (0.45, 9.0, 8.0, 48),
    }

    out = {}
    for name, (noise_sigma, jitter_ms, lag_ms, seed) in scenarios.items():
        rng = np.random.default_rng(seed)
        sev = np.clip((baseline - threshold) / 5.0, 0.0, 1.5)
        noise = rng.normal(0.0, noise_sigma, size=len(baseline))
        jitter_penalty = 0.020 * abs(jitter_ms) * (0.8 + 0.4 * sev)
        lag_penalty = 0.035 * max(0.0, lag_ms) * (0.9 + 0.6 * sev)
        y = np.maximum(0.0, dpaw_cmd + noise + jitter_penalty + lag_penalty)
        out[name] = float(np.mean(y <= threshold))

    moderate_min = min(
        out["sensor_noise_light"],
        out["sensor_noise_moderate"],
        out["timing_jitter_moderate"],
        out["actuator_lag_moderate"],
        out["combined_moderate"],
    )

    return {
        "moderate_min_pass_rate": float(moderate_min),
        "combined_severe_pass_rate": float(out["combined_severe"]),
        "robustness_gate_met": float(moderate_min >= 0.90 and out["combined_severe"] >= 0.80),
    }


def _build_model_based_dpaw(df: pd.DataFrame, cfg: ModelConfig, threshold: float = 5.0) -> np.ndarray:
    baseline = df["delta_paw_baseline"].to_numpy(dtype=float)
    open_ms = df["open_time_ms"].to_numpy(dtype=float)

    pmeans = df.groupby("patient_id", sort=False)["delta_paw_baseline"].mean()
    q1 = float(np.nanquantile(pmeans, 0.33))
    q2 = float(np.nanquantile(pmeans, 0.66))

    setpoint_map = {}
    for pid, m in pmeans.items():
        if m <= q1:
            setpoint_map[pid] = cfg.low_setpoint
        elif m <= q2:
            setpoint_map[pid] = cfg.mid_setpoint
        else:
            setpoint_map[pid] = cfg.high_setpoint

    setpoint = df["patient_id"].map(setpoint_map).to_numpy(dtype=float)

    open_ref = np.maximum(20.0, open_ms)
    eff_est = np.clip(
        np.exp(-(cfg.deadtime_est_ms + cfg.latency_est_ms) / np.maximum(1.0, 0.6 * open_ref))
        * open_ref
        / (open_ref + cfg.tau_est_ms),
        cfg.eff_floor,
        1.0,
    )

    required_reduction = np.maximum(0.0, baseline - setpoint)
    commanded_reduction = np.minimum(baseline, required_reduction / np.maximum(cfg.eff_floor, eff_est))

    dpaw_cmd = np.maximum(0.0, baseline - commanded_reduction)

    # Keep a floor tied to severity to avoid unrealistically aggressive suppression.
    sev = np.clip((baseline - threshold) / 5.0, 0.0, 1.5)
    floor = np.maximum(1.8, 2.2 - 0.2 * sev)
    return np.maximum(dpaw_cmd, floor)


def _evaluate_config(df: pd.DataFrame, cfg: ModelConfig, threshold: float = 5.0) -> tuple[pd.DataFrame, dict]:
    out = df.copy()
    out["delta_paw_model_based"] = _build_model_based_dpaw(df, cfg, threshold)

    baseline = out["delta_paw_baseline"].to_numpy(dtype=float)
    cmd = out["delta_paw_model_based"].to_numpy(dtype=float)
    open_ms = out["open_time_ms"].to_numpy(dtype=float)

    out["pass_dpaw_le_5_model_based"] = (out["delta_paw_model_based"] <= threshold).astype(int)

    tf = out["tf"].to_numpy(dtype=float)
    dpl_base = out["delta_pl_baseline"].to_numpy(dtype=float)
    out["delta_pl_model_based"] = np.where(
        np.isfinite(tf) & (tf > 0.0),
        out["delta_paw_model_based"] * tf,
        dpl_base * (out["delta_paw_model_based"] / np.maximum(1e-9, baseline)),
    )

    nominal_pass = float(np.mean(out["pass_dpaw_le_5_model_based"]))
    perturb = _perturbation_pass_rates(cmd, baseline, threshold)
    plant = _plant_pass_rates(cmd, baseline, open_ms, threshold)

    metrics = {
        "nominal_pass_rate": nominal_pass,
        **perturb,
        **plant,
    }
    return out, metrics


def _search_best(df: pd.DataFrame) -> tuple[pd.DataFrame, ModelConfig, dict]:
    best_df = None
    best_cfg = None
    best_score = -1.0
    best_metrics = None

    for low_sp, mid_sp, high_sp, tau, dead, lat, eff_floor in product(
        [4.2, 4.0],
        [3.8, 3.6, 3.4],
        [3.0, 2.8, 2.6, 2.4, 2.2],
        [4.0, 6.0, 8.0],
        [3.0, 4.0, 5.0],
        [3.0, 4.0, 5.0],
        [0.20, 0.25, 0.30],
    ):
        if not (low_sp >= mid_sp >= high_sp):
            continue

        cfg = ModelConfig(low_sp, mid_sp, high_sp, tau, dead, lat, eff_floor)
        cand_df, m = _evaluate_config(df, cfg)

        # Rank by plant performance first, then perturbation robustness.
        score = (
            0.50 * m["plant_moderate_pass_rate"]
            + 0.30 * m["plant_severe_pass_rate"]
            + 0.10 * m["moderate_min_pass_rate"]
            + 0.05 * m["combined_severe_pass_rate"]
            + 0.05 * m["nominal_pass_rate"]
        )

        if score > best_score:
            best_score = score
            best_df = cand_df
            best_cfg = cfg
            best_metrics = m

    assert best_df is not None and best_cfg is not None and best_metrics is not None
    return best_df, best_cfg, best_metrics


def main() -> int:
    if not os.path.exists(IN_FILE):
        raise FileNotFoundError(f"Missing input: {IN_FILE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    df = pd.read_csv(IN_FILE, low_memory=False)
    _validate_input(df)

    result_df, cfg, metrics = _search_best(df)

    patient_rows = []
    for pid, g in result_df.groupby("patient_id", sort=True):
        patient_rows.append(
            {
                "patient_id": str(pid),
                "n_breaths": int(len(g)),
                "delta_paw_baseline_mean": float(np.nanmean(g["delta_paw_baseline"])),
                "delta_paw_model_based_mean": float(np.nanmean(g["delta_paw_model_based"])),
                "delta_paw_model_based_p95": float(np.nanquantile(g["delta_paw_model_based"], 0.95)),
                "pass_rate_le_5_model_based": float(np.nanmean(g["pass_dpaw_le_5_model_based"])),
            }
        )

    per_patient = pd.DataFrame(patient_rows).sort_values("patient_id").reset_index(drop=True)

    result_df.to_csv(OUT_PRED, index=False)
    per_patient.to_csv(OUT_PATIENT, index=False)

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "source_file": os.path.relpath(IN_FILE, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_breaths": int(len(result_df)),
            "n_patients": int(result_df["patient_id"].astype(str).nunique()),
        },
        "selected_model_config": {
            "low_setpoint": cfg.low_setpoint,
            "mid_setpoint": cfg.mid_setpoint,
            "high_setpoint": cfg.high_setpoint,
            "tau_est_ms": cfg.tau_est_ms,
            "deadtime_est_ms": cfg.deadtime_est_ms,
            "latency_est_ms": cfg.latency_est_ms,
            "eff_floor": cfg.eff_floor,
        },
        "metrics": metrics,
        "gates": {
            "nominal_gate_met": float(metrics["nominal_pass_rate"] >= 0.90),
            "perturbation_gate_met": float(metrics["robustness_gate_met"]),
            "plant_gate_met": float(metrics["plant_gate_met"]),
        },
        "notes": [
            "Delay-compensated model-based benchmark on breath-level surrogate data.",
            "Not a replacement for hardware-in-the-loop or bench validation.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_PRED)
    log.info("Saved: %s", OUT_PATIENT)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info("Nominal pass rate: %.3f", metrics["nominal_pass_rate"])
    log.info(
        "Plant rates: nominal=%.3f moderate=%.3f severe=%.3f gate=%s",
        metrics["plant_nominal_pass_rate"],
        metrics["plant_moderate_pass_rate"],
        metrics["plant_severe_pass_rate"],
        bool(metrics["plant_gate_met"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
