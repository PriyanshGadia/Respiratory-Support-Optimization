#!/usr/bin/env python
# =============================================================================
# 18_phase3_external_controller_replay.py  —  External controller replay screen
# Version: 1.0  |  2026-03-20
#
# Replays the selected Phase 3 plant-aware controller configuration on external
# waveform-derived features (e.g., Puritan-Bennett artifacts) and evaluates the
# same plant-coupled surrogate gates used internally.
#
# This is proxy replay only (no Pes ground truth).
# =============================================================================

from __future__ import annotations

import argparse
import json
import logging
import os

import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("18_phase3_external_controller_replay")

IN_CONFIG = os.path.join(C.LOGS_DIR, "phase3_plant_aware_summary.json")
DEFAULT_INPUT = os.path.join(C.LOGS_DIR, "vwd_scores.csv")


def _paths(tag: str) -> tuple[str, str]:
    safe = "".join(ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in tag).lower()
    safe = safe or "external_raw"
    return (
        os.path.join(C.LOGS_DIR, f"phase3_external_controller_replay_{safe}_per_patient_severe.csv"),
        os.path.join(C.LOGS_DIR, f"phase3_external_controller_replay_{safe}_summary.json"),
    )


def _pick_baseline(df: pd.DataFrame) -> np.ndarray:
    for c in ["delta_paw_max", "delta_paw_baseline", "y_regression"]:
        if c in df.columns:
            x = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            if np.isfinite(x).any():
                return np.nan_to_num(x, nan=np.nanmedian(x[np.isfinite(x)]), posinf=np.nanmedian(x[np.isfinite(x)]), neginf=0.0)
    raise ValueError("No usable baseline proxy column found (expected one of delta_paw_max|delta_paw_baseline|y_regression).")


def _group_ids(df: pd.DataFrame) -> np.ndarray:
    if "patient_id" in df.columns:
        pid = df["patient_id"].astype(str).to_numpy()
        if len(np.unique(pid)) > 1:
            return pid
    if "source" in df.columns:
        return df["source"].astype(str).to_numpy()
    return np.array(["ext_all"] * len(df), dtype=object)


def _severity_bucket(baseline: np.ndarray, group_ids: np.ndarray) -> np.ndarray:
    per_group = {}
    for g in np.unique(group_ids):
        m = group_ids == g
        per_group[g] = float(np.nanmean(baseline[m]))
    means = np.array([per_group[g] for g in group_ids], dtype=float)
    q1 = float(np.nanquantile(list(per_group.values()), 0.33))
    q2 = float(np.nanquantile(list(per_group.values()), 0.66))
    return np.where(means <= q1, 0, np.where(means <= q2, 1, 2)).astype(int)


def _synthesize_external(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    baseline = _pick_baseline(out)
    group_ids = _group_ids(out)
    bucket = _severity_bucket(baseline, group_ids)

    open_base = np.where(bucket == 0, cfg["open_low_ms"], np.where(bucket == 1, cfg["open_mid_ms"], cfg["open_high_ms"]))
    set_base = np.where(bucket == 0, cfg["set_low"], np.where(bucket == 1, cfg["set_mid"], cfg["set_high"]))

    sev_local = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)
    open_cmd = np.clip(open_base + cfg.get("open_severity_gain_ms", 0.0) * sev_local, 20.0, 140.0)
    setpoint = np.clip(set_base - cfg.get("set_severity_gain", 0.0) * sev_local, 1.8, 5.0)

    open_ref = np.maximum(20.0, open_cmd)
    eff_est = np.clip(
        np.exp(-(cfg["deadtime_est_ms"] + cfg["latency_est_ms"]) / np.maximum(1.0, 0.6 * open_ref))
        * open_ref
        / (open_ref + cfg["tau_est_ms"]),
        cfg["eff_floor"],
        1.0,
    )

    req = np.maximum(0.0, baseline - setpoint)
    cmd_red = np.minimum(baseline, req / np.maximum(cfg["eff_floor"], eff_est))
    dpaw_target = np.maximum(0.0, baseline - cmd_red)
    min_dpaw = np.maximum(1.8, 2.2 - 0.2 * np.clip((baseline - 5.0) / 5.0, 0.0, 1.5))
    dpaw_target = np.maximum(dpaw_target, min_dpaw)

    out["patient_id"] = group_ids
    out["delta_paw_baseline_proxy"] = baseline
    out["open_time_ms"] = open_cmd
    out["delta_paw_external_target"] = dpaw_target
    return out


def _scenario_pass(df: pd.DataFrame, tau: float, dead: float, lat: float, sigma: float, seed: int) -> np.ndarray:
    baseline = df["delta_paw_baseline_proxy"].to_numpy(dtype=float)
    target = df["delta_paw_external_target"].to_numpy(dtype=float)
    open_ms = df["open_time_ms"].to_numpy(dtype=float)

    rng = np.random.default_rng(seed)
    open_ref = np.maximum(20.0, open_ms)
    eff = np.clip(np.exp(-(dead + lat) / np.maximum(1.0, 0.6 * open_ref)) * open_ref / (open_ref + tau), 0.20, 1.0)
    req = np.maximum(0.0, baseline - target)
    ach = eff * req
    sev = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)
    penalty = (1.0 - eff) * 0.25 * sev
    y = np.maximum(0.0, baseline - ach + penalty + rng.normal(0.0, sigma, size=len(df)))
    return (y <= 5.0).astype(float)


def _stats(df: pd.DataFrame, passed: np.ndarray) -> tuple[float, float, str, pd.DataFrame]:
    g = df[["patient_id"]].copy()
    g["passed"] = passed
    gp = g.groupby("patient_id", sort=False)["passed"].mean().reset_index()
    gp = gp.rename(columns={"passed": "pass_rate_le_5"})
    overall = float(np.mean(passed))
    worst_row = gp.sort_values("pass_rate_le_5", ascending=True).iloc[0]
    return overall, float(worst_row["pass_rate_le_5"]), str(worst_row["patient_id"]), gp


def main() -> int:
    parser = argparse.ArgumentParser(description="External replay of Phase 3 plant-aware controller")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="External feature CSV (default: logs/vwd_scores.csv)")
    parser.add_argument("--tag", default="external_raw", help="Tag for output files")
    args = parser.parse_args()

    if not os.path.exists(IN_CONFIG):
        raise FileNotFoundError(f"Missing controller config summary: {IN_CONFIG}")
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Missing external input: {args.input}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)
    out_patient, out_summary = _paths(args.tag)

    with open(IN_CONFIG, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)["selected_config"]

    ext = pd.read_csv(args.input, low_memory=False)
    sim = _synthesize_external(ext, cfg)

    p_nom = _scenario_pass(sim, 2.0, 1.0, 1.0, 0.08, seed=900)
    p_mod = _scenario_pass(sim, 6.0, 4.0, 4.0, 0.18, seed=901)
    p_sev = _scenario_pass(sim, 12.0, 8.0, 9.0, 0.30, seed=902)

    nom, nom_min, nom_worst, _ = _stats(sim, p_nom)
    mod, mod_min, mod_worst, _ = _stats(sim, p_mod)
    sev, sev_min, sev_worst, sev_gp = _stats(sim, p_sev)

    sev_gp.to_csv(out_patient, index=False)

    aggregate_gate = bool(mod >= 0.90 and sev >= 0.80)
    patient_gate = bool(mod_min >= 0.90 and sev_min >= 0.80)
    strict_gate = bool(aggregate_gate and patient_gate)

    out = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "external_file": os.path.relpath(args.input, C.ANALYSIS_DIR).replace("\\", "/") if os.path.isabs(args.input) else args.input.replace("\\", "/"),
            "n_rows": int(len(sim)),
            "n_groups": int(sim["patient_id"].astype(str).nunique()),
            "controller_config_source": os.path.relpath(IN_CONFIG, C.ANALYSIS_DIR).replace("\\", "/"),
        },
        "targets": {
            "plant_moderate_min_pass_rate": 0.90,
            "plant_severe_min_pass_rate": 0.80,
            "plant_moderate_min_patient_pass_rate": 0.90,
            "plant_severe_min_patient_pass_rate": 0.80,
        },
        "results": {
            "plant_nominal_pass_rate": nom,
            "plant_moderate_pass_rate": mod,
            "plant_severe_pass_rate": sev,
            "plant_moderate_min_patient_pass_rate": mod_min,
            "plant_severe_min_patient_pass_rate": sev_min,
            "plant_moderate_worst_group_id": mod_worst,
            "plant_severe_worst_group_id": sev_worst,
            "plant_coupled_gate_met_aggregate": float(aggregate_gate),
            "plant_coupled_gate_met_patient_level": float(patient_gate),
            "plant_coupled_gate_met": float(strict_gate),
        },
        "limitations": [
            "Uses external feature-derived baseline proxy, not Pes-ground-truth outcomes.",
            "This is a surrogate replay screen and not a substitute for HIL/clinical validation.",
        ],
    }

    with open(out_summary, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    log.info("Saved: %s", out_patient)
    log.info("Saved: %s", out_summary)
    log.info("External replay strict gate: %s", strict_gate)
    log.info("Moderate/severe aggregate: %.3f / %.3f", mod, sev)
    log.info("Moderate/severe min-group: %.3f / %.3f", mod_min, sev_min)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
