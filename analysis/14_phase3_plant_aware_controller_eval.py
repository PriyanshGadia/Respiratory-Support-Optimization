#!/usr/bin/env python
# =============================================================================
# 14_phase3_plant_aware_controller_eval.py  —  Plant-aware control benchmark
# Version: 1.0  |  2026-03-20
#
# Benchmarks a plant-aware controller that jointly selects:
# - per-severity opening-time command
# - delay-compensated DeltaPaw target
#
# This is an exploratory simulation benchmark, not deployable firmware logic.
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
log = logging.getLogger("14_phase3_plant_aware_controller_eval")

IN_FILE = os.path.join(C.LOGS_DIR, "phase3_adaptive_rule_predictions.csv")
OUT_PRED = os.path.join(C.LOGS_DIR, "phase3_plant_aware_predictions.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_plant_aware_summary.json")


@dataclass(frozen=True)
class PlantAwareConfig:
    open_low_ms: float
    open_mid_ms: float
    open_high_ms: float
    set_low: float
    set_mid: float
    set_high: float
    open_severity_gain_ms: float
    set_severity_gain: float
    tau_est_ms: float
    deadtime_est_ms: float
    latency_est_ms: float
    eff_floor: float


def _severity_bucket(df: pd.DataFrame) -> np.ndarray:
    pmean = df.groupby("patient_id", sort=False)["delta_paw_baseline"].mean()
    q1 = float(np.nanquantile(pmean, 0.33))
    q2 = float(np.nanquantile(pmean, 0.66))

    bucket = []
    for pid in df["patient_id"].astype(str):
        m = pmean[pid]
        if m <= q1:
            bucket.append(0)
        elif m <= q2:
            bucket.append(1)
        else:
            bucket.append(2)
    return np.array(bucket, dtype=int)


def _synthesize(df: pd.DataFrame, cfg: PlantAwareConfig, bucket: np.ndarray) -> pd.DataFrame:
    synthesized_df = df.copy()

    baseline = synthesized_df["delta_paw_baseline"].to_numpy(dtype=float)

    open_base = np.where(bucket == 0, cfg.open_low_ms, np.where(bucket == 1, cfg.open_mid_ms, cfg.open_high_ms)).astype(float)
    set_base = np.where(bucket == 0, cfg.set_low, np.where(bucket == 1, cfg.set_mid, cfg.set_high)).astype(float)

    # Breath-level severity adaptation over the per-patient bucket baseline.
    sev_local = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)
    open_cmd = np.clip(open_base + cfg.open_severity_gain_ms * sev_local, 20.0, 140.0)
    setpoint = np.clip(set_base - cfg.set_severity_gain * sev_local, 1.8, 5.0)

    # Inverse compensation based on estimated plant to reach setpoint under delay/lag.
    open_ref = np.maximum(20.0, open_cmd)
    eff_est = np.clip(
        np.exp(-(cfg.deadtime_est_ms + cfg.latency_est_ms) / np.maximum(1.0, 0.6 * open_ref))
        * open_ref
        / (open_ref + cfg.tau_est_ms),
        cfg.eff_floor,
        1.0,
    )

    required_reduction = np.maximum(0.0, baseline - setpoint)
    commanded_reduction = np.minimum(baseline, required_reduction / np.maximum(cfg.eff_floor, eff_est))

    dpaw_target = np.maximum(0.0, baseline - commanded_reduction)

    # Conservative lower bound to avoid collapsing transients unrealistically.
    sev = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)
    min_dpaw = np.maximum(1.8, 2.2 - 0.2 * sev)
    dpaw_target = np.maximum(dpaw_target, min_dpaw)

    synthesized_df["open_time_ms"] = open_cmd
    synthesized_df["delta_paw_plant_aware"] = dpaw_target
    synthesized_df["pass_dpaw_le_5_plant_aware"] = (dpaw_target <= 5.0).astype(int)

    tf = synthesized_df["tf"].to_numpy(dtype=float)
    dpl_base = synthesized_df["delta_pl_baseline"].to_numpy(dtype=float)
    synthesized_df["delta_pl_plant_aware"] = np.where(
        np.isfinite(tf) & (tf > 0.0),
        synthesized_df["delta_paw_plant_aware"] * tf,
        dpl_base * (synthesized_df["delta_paw_plant_aware"] / np.maximum(1e-9, baseline)),
    )

    return synthesized_df


def _plant_rates(df: pd.DataFrame, target_col: str, threshold: float = 5.0) -> dict:
    baseline = df["delta_paw_baseline"].to_numpy(dtype=float)
    target = df[target_col].to_numpy(dtype=float)
    open_ms = df["open_time_ms"].to_numpy(dtype=float)
    patient_ids = df["patient_id"].astype(str).to_numpy()

    def _simulate(tau: float, dead: float, lat: float, sigma: float, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        open_ref = np.maximum(20.0, open_ms)
        eff = np.clip(
            np.exp(-(dead + lat) / np.maximum(1.0, 0.6 * open_ref)) * open_ref / (open_ref + tau),
            0.20,
            1.0,
        )
        req = np.maximum(0.0, baseline - target)
        ach = eff * req
        sev = np.clip((baseline - threshold) / 5.0, 0.0, 1.5)
        penalty = (1.0 - eff) * 0.25 * sev
        return np.maximum(0.0, baseline - ach + penalty + rng.normal(0.0, sigma, size=len(df)))

    def _scenario_stats(y: np.ndarray) -> dict:
        passed = (y <= threshold).astype(float)
        overall = float(np.mean(passed))

        per_patient_rates: dict[str, float] = {}
        for pid in np.unique(patient_ids):
            m = patient_ids == pid
            per_patient_rates[pid] = float(np.mean(passed[m]))

        worst_pid, worst_rate = min(per_patient_rates.items(), key=lambda kv: kv[1])
        return {
            "overall": overall,
            "per_patient_rates": per_patient_rates,
            "worst_pid": str(worst_pid),
            "worst_rate": float(worst_rate),
        }

    nominal = _scenario_stats(_simulate(2.0, 1.0, 1.0, 0.08, 200))
    moderate = _scenario_stats(_simulate(6.0, 4.0, 4.0, 0.18, 201))
    severe = _scenario_stats(_simulate(12.0, 8.0, 9.0, 0.30, 202))

    moderate_gate = float(moderate["overall"] >= 0.90)
    severe_gate = float(severe["overall"] >= 0.80)
    patient_level_gate = float(moderate["worst_rate"] >= 0.90 and severe["worst_rate"] >= 0.80)

    return {
        "plant_nominal_pass_rate": nominal["overall"],
        "plant_moderate_pass_rate": moderate["overall"],
        "plant_severe_pass_rate": severe["overall"],
        "plant_gate_met_aggregate": float(moderate_gate and severe_gate),
        "plant_moderate_min_patient_pass_rate": moderate["worst_rate"],
        "plant_severe_min_patient_pass_rate": severe["worst_rate"],
        "plant_moderate_worst_patient_id": moderate["worst_pid"],
        "plant_severe_worst_patient_id": severe["worst_pid"],
        "patient_level_gate_met": patient_level_gate,
        "plant_gate_met": float(moderate_gate and severe_gate and patient_level_gate),
    }


def _search(df: pd.DataFrame) -> tuple[pd.DataFrame, PlantAwareConfig, dict]:
    best_feasible_score = None
    best_feasible_df = None
    best_feasible_cfg = None
    best_feasible_metrics = None

    best_fallback_score = None
    best_fallback_df = None
    best_fallback_cfg = None
    best_fallback_metrics = None

    bucket = _severity_bucket(df)

    for o0, o1, o2, s0, s1, s2, go, gs, tau, dead, lat, eff_floor in product(
        [50.0, 70.0],
        [70.0, 95.0],
        [100.0, 130.0],
        [4.2, 3.8],
        [3.6, 3.2],
        [2.8, 2.0],
        [0.0, 24.0],
        [0.0, 0.3],
        [12.0],
        [8.0],
        [9.0],
        [0.20],
    ):
        if not (o0 <= o1 <= o2):
            continue
        if not (s0 >= s1 >= s2):
            continue

        cfg = PlantAwareConfig(o0, o1, o2, s0, s1, s2, go, gs, tau, dead, lat, eff_floor)
        cand = _synthesize(df, cfg, bucket)
        rates = _plant_rates(cand, "delta_paw_plant_aware")

        nominal = float(np.mean(cand["pass_dpaw_le_5_plant_aware"]))
        # Lexicographic max-min objective: worst severe patient first, then worst moderate patient,
        # then aggregate severe/moderate, then nominal replay.
        lex_score = (
            rates["plant_severe_min_patient_pass_rate"],
            rates["plant_moderate_min_patient_pass_rate"],
            rates["plant_severe_pass_rate"],
            rates["plant_moderate_pass_rate"],
            nominal,
        )

        metrics = {"nominal_pass_rate": nominal, **rates}

        if best_fallback_score is None or lex_score > best_fallback_score:
            best_fallback_score = lex_score
            best_fallback_df = cand
            best_fallback_cfg = cfg
            best_fallback_metrics = metrics

        if not bool(rates["plant_gate_met"]):
            continue

        if best_feasible_score is None or lex_score > best_feasible_score:
            best_feasible_score = lex_score
            best_feasible_df = cand
            best_feasible_cfg = cfg
            best_feasible_metrics = metrics

    if best_feasible_df is not None:
        best_feasible_metrics["search_outcome"] = "feasible_patient_level_gate"
        best_feasible_metrics["objective"] = "lexicographic_maximin"
        return best_feasible_df, best_feasible_cfg, best_feasible_metrics

    assert best_fallback_df is not None and best_fallback_cfg is not None and best_fallback_metrics is not None
    best_fallback_metrics["search_outcome"] = "fallback_best_effort_patient_level_gate_not_met"
    best_fallback_metrics["objective"] = "lexicographic_maximin"
    return best_fallback_df, best_fallback_cfg, best_fallback_metrics


def main() -> int:
    if not os.path.exists(IN_FILE):
        raise FileNotFoundError(f"Missing input: {IN_FILE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    df = pd.read_csv(IN_FILE, low_memory=False)
    required = {"patient_id", "delta_paw_baseline", "delta_pl_baseline", "open_time_ms", "tf"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    plant_aware_df, cfg, metrics = _search(df)
    plant_aware_df.to_csv(OUT_PRED, index=False)

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "source_file": os.path.relpath(IN_FILE, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_breaths": int(len(plant_aware_df)),
            "n_patients": int(plant_aware_df["patient_id"].astype(str).nunique()),
        },
        "selected_config": {
            "open_low_ms": cfg.open_low_ms,
            "open_mid_ms": cfg.open_mid_ms,
            "open_high_ms": cfg.open_high_ms,
            "set_low": cfg.set_low,
            "set_mid": cfg.set_mid,
            "set_high": cfg.set_high,
            "open_severity_gain_ms": cfg.open_severity_gain_ms,
            "set_severity_gain": cfg.set_severity_gain,
            "tau_est_ms": cfg.tau_est_ms,
            "deadtime_est_ms": cfg.deadtime_est_ms,
            "latency_est_ms": cfg.latency_est_ms,
            "eff_floor": cfg.eff_floor,
        },
        "metrics": metrics,
        "targets": {
            "aggregate": {
                "plant_moderate_min_pass_rate": 0.90,
                "plant_severe_min_pass_rate": 0.80,
            },
            "patient_level": {
                "plant_moderate_min_patient_pass_rate": 0.90,
                "plant_severe_min_patient_pass_rate": 0.80,
            },
        },
        "notes": [
            "Exploratory plant-aware benchmark; not deployment-ready control logic.",
            "Uses the same plant surrogate form as script 12 for comparability.",
            "Search uses lexicographic max-min objective (worst severe patient first).",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_PRED)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info("Nominal pass: %.3f", metrics["nominal_pass_rate"])
    log.info("Plant moderate/severe (aggregate): %.3f / %.3f", metrics["plant_moderate_pass_rate"], metrics["plant_severe_pass_rate"])
    log.info(
        "Plant moderate/severe (min patient): %.3f / %.3f",
        metrics["plant_moderate_min_patient_pass_rate"],
        metrics["plant_severe_min_patient_pass_rate"],
    )
    log.info("Plant gate met (aggregate+patient-level): %s", bool(metrics["plant_gate_met"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
