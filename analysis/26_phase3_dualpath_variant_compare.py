#!/usr/bin/env python
# =============================================================================
# 26_phase3_dualpath_variant_compare.py  —  Dual-path variant comparison
# Version: 1.0  |  2026-03-20
#
# Compares baseline plant-aware predictions against an exploratory dual-path
# passive-assist variant under the same surrogate plant scenarios.
#
# Research-use only: this is not firmware logic and not a safety claim.
# =============================================================================

from __future__ import annotations

import argparse
import json
import logging
import os
from itertools import product

import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("26_phase3_dualpath_variant_compare")

IN_ACTIVE = os.path.join(C.LOGS_DIR, "phase3_plant_aware_predictions.csv")
IN_DUAL_META = os.path.join(C.ANALYSIS_DIR, "valve_export_dualpath_concept", "dualpath_metadata.json")

OUT_PRED = os.path.join(C.LOGS_DIR, "phase3_dualpath_predictions.csv")
OUT_PER_PATIENT = os.path.join(C.LOGS_DIR, "phase3_dualpath_comparison_per_patient.csv")
OUT_SUMMARY = os.path.join(C.LOGS_DIR, "phase3_dualpath_comparison_summary.json")
OUT_SWEEP = os.path.join(C.LOGS_DIR, "phase3_dualpath_sweep.csv")


def _num(v: object, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _load_meta() -> tuple[float, float]:
    ratio = 0.25
    fuse_open_cmh2o = 14.0
    if os.path.exists(IN_DUAL_META):
        with open(IN_DUAL_META, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        ratio = _num((data.get("physics_summary", {}) or {}).get("bypass_to_active_area_ratio"), ratio)
        fuse_open_cmh2o = _num((data.get("params", {}) or {}).get("fuse_open_dp_cmh2o_nominal"), fuse_open_cmh2o)
    return ratio, fuse_open_cmh2o


def _apply_dualpath_variant(
    df: pd.DataFrame,
    bypass_ratio: float,
    fuse_open_cmh2o: float,
    trigger_scale: float,
    base_gain: float,
    base_cap: float,
    fuse_gain: float,
    fuse_cap: float,
    max_total_assist: float,
) -> pd.DataFrame:
    out = df.copy()

    baseline = out["delta_paw_baseline"].to_numpy(dtype=float)
    active = out["delta_paw_plant_aware"].to_numpy(dtype=float)

    required_reduction = np.maximum(0.0, baseline - active)
    sev = np.clip((baseline - 5.0) / 5.0, 0.0, 1.5)

    # Passive-assist model:
    # - scales with bypass area ratio
    # - activates more strongly with severity
    # - adds fuse assist when baseline transients exceed conservative trigger
    trigger = float(np.clip(trigger_scale * fuse_open_cmh2o, 6.0, 12.0))
    fuse_engaged = baseline >= trigger

    base_assist = np.clip(base_gain * bypass_ratio * sev, 0.0, base_cap)
    fuse_assist = np.where(fuse_engaged, np.clip(fuse_gain * bypass_ratio, 0.0, fuse_cap), 0.0)
    total_assist = np.clip(base_assist + fuse_assist, 0.0, max_total_assist)

    dual_reduction = np.minimum(baseline, required_reduction * (1.0 + total_assist))
    dual_dpaw = np.maximum(0.0, baseline - dual_reduction)

    # Conservative floor to avoid unrealistic collapse in surrogate space.
    floor = np.maximum(1.6, 2.1 - 0.2 * sev)
    dual_dpaw = np.maximum(dual_dpaw, floor)

    out["delta_paw_dualpath"] = dual_dpaw
    out["pass_dpaw_le_5_dualpath"] = (dual_dpaw <= 5.0).astype(int)
    out["dualpath_assist_factor"] = total_assist
    out["dualpath_fuse_engaged"] = fuse_engaged.astype(int)

    tf = out["tf"].to_numpy(dtype=float)
    dpl_base = out["delta_pl_baseline"].to_numpy(dtype=float)
    out["delta_pl_dualpath"] = np.where(
        np.isfinite(tf) & (tf > 0.0),
        out["delta_paw_dualpath"] * tf,
        dpl_base * (out["delta_paw_dualpath"] / np.maximum(1e-9, baseline)),
    )

    return out


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

    return {
        "plant_nominal_pass_rate": nominal["overall"],
        "plant_moderate_pass_rate": moderate["overall"],
        "plant_severe_pass_rate": severe["overall"],
        "plant_moderate_min_patient_pass_rate": moderate["worst_rate"],
        "plant_severe_min_patient_pass_rate": severe["worst_rate"],
        "plant_moderate_worst_patient_id": moderate["worst_pid"],
        "plant_severe_worst_patient_id": severe["worst_pid"],
        "moderate_per_patient": moderate["per_patient_rates"],
        "severe_per_patient": severe["per_patient_rates"],
    }


def _sweep_best(df: pd.DataFrame, bypass_ratio: float, fuse_open: float, active_rates: dict) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    rows = []
    best_score = None
    best_out = None
    best_cfg = None
    best_rates = None

    for trigger_scale, base_gain, base_cap, fuse_gain, fuse_cap, max_total_assist in product(
        [0.4, 0.5, 0.6],
        [0.18, 0.25, 0.35],
        [0.12, 0.15, 0.20],
        [0.08, 0.14, 0.22],
        [0.05, 0.08, 0.12],
        [0.20, 0.28, 0.35],
    ):
        out = _apply_dualpath_variant(
            df,
            bypass_ratio=bypass_ratio,
            fuse_open_cmh2o=fuse_open,
            trigger_scale=trigger_scale,
            base_gain=base_gain,
            base_cap=base_cap,
            fuse_gain=fuse_gain,
            fuse_cap=fuse_cap,
            max_total_assist=max_total_assist,
        )
        rates = _plant_rates(out, "delta_paw_dualpath")

        # Lexicographic improvement objective: severe worst patient first.
        score = (
            rates["plant_severe_min_patient_pass_rate"],
            rates["plant_severe_pass_rate"],
            rates["plant_moderate_min_patient_pass_rate"],
            rates["plant_moderate_pass_rate"],
        )

        rows.append(
            {
                "trigger_scale": trigger_scale,
                "base_gain": base_gain,
                "base_cap": base_cap,
                "fuse_gain": fuse_gain,
                "fuse_cap": fuse_cap,
                "max_total_assist": max_total_assist,
                "plant_moderate_pass_rate": rates["plant_moderate_pass_rate"],
                "plant_severe_pass_rate": rates["plant_severe_pass_rate"],
                "plant_moderate_min_patient_pass_rate": rates["plant_moderate_min_patient_pass_rate"],
                "plant_severe_min_patient_pass_rate": rates["plant_severe_min_patient_pass_rate"],
                "delta_moderate_min_patient": rates["plant_moderate_min_patient_pass_rate"] - active_rates["plant_moderate_min_patient_pass_rate"],
                "delta_severe_min_patient": rates["plant_severe_min_patient_pass_rate"] - active_rates["plant_severe_min_patient_pass_rate"],
            }
        )

        if best_score is None or score > best_score:
            best_score = score
            best_out = out
            best_cfg = {
                "trigger_scale": trigger_scale,
                "base_gain": base_gain,
                "base_cap": base_cap,
                "fuse_gain": fuse_gain,
                "fuse_cap": fuse_cap,
                "max_total_assist": max_total_assist,
            }
            best_rates = rates

    assert best_out is not None and best_cfg is not None and best_rates is not None
    sweep_df = pd.DataFrame(rows).sort_values(
        ["plant_severe_min_patient_pass_rate", "plant_severe_pass_rate", "plant_moderate_min_patient_pass_rate", "plant_moderate_pass_rate"],
        ascending=[False, False, False, False],
    )
    return best_out, {"config": best_cfg, "rates": best_rates}, sweep_df


def main() -> int:
    parser = argparse.ArgumentParser(description="Dual-path exploratory comparison")
    parser.add_argument("--no-sweep", action="store_true", help="Disable parameter sweep and run single-point surrogate")
    args = parser.parse_args()

    if not os.path.exists(IN_ACTIVE):
        raise FileNotFoundError(f"Missing input: {IN_ACTIVE}")

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    df = pd.read_csv(IN_ACTIVE, low_memory=False)
    required = {"patient_id", "delta_paw_baseline", "delta_pl_baseline", "open_time_ms", "tf", "delta_paw_plant_aware"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    bypass_ratio, fuse_open = _load_meta()
    active_rates = _plant_rates(df, "delta_paw_plant_aware")

    sweep_used = not args.no_sweep
    if sweep_used:
        out, best, sweep_df = _sweep_best(df, bypass_ratio=bypass_ratio, fuse_open=fuse_open, active_rates=active_rates)
        sweep_df.to_csv(OUT_SWEEP, index=False)
        best_cfg = best["config"]
        dual_rates = best["rates"]
    else:
        best_cfg = {
            "trigger_scale": 0.5,
            "base_gain": 0.18,
            "base_cap": 0.15,
            "fuse_gain": 0.08,
            "fuse_cap": 0.06,
            "max_total_assist": 0.20,
        }
        out = _apply_dualpath_variant(
            df,
            bypass_ratio=bypass_ratio,
            fuse_open_cmh2o=fuse_open,
            trigger_scale=best_cfg["trigger_scale"],
            base_gain=best_cfg["base_gain"],
            base_cap=best_cfg["base_cap"],
            fuse_gain=best_cfg["fuse_gain"],
            fuse_cap=best_cfg["fuse_cap"],
            max_total_assist=best_cfg["max_total_assist"],
        )
        dual_rates = _plant_rates(out, "delta_paw_dualpath")

    out.to_csv(OUT_PRED, index=False)

    pids = sorted(out["patient_id"].astype(str).unique())
    rows = []
    for pid in pids:
        rows.append(
            {
                "patient_id": pid,
                "moderate_pass_active": active_rates["moderate_per_patient"].get(pid, np.nan),
                "moderate_pass_dualpath": dual_rates["moderate_per_patient"].get(pid, np.nan),
                "moderate_delta": dual_rates["moderate_per_patient"].get(pid, np.nan) - active_rates["moderate_per_patient"].get(pid, np.nan),
                "severe_pass_active": active_rates["severe_per_patient"].get(pid, np.nan),
                "severe_pass_dualpath": dual_rates["severe_per_patient"].get(pid, np.nan),
                "severe_delta": dual_rates["severe_per_patient"].get(pid, np.nan) - active_rates["severe_per_patient"].get(pid, np.nan),
            }
        )
    pd.DataFrame(rows).to_csv(OUT_PER_PATIENT, index=False)

    summary = {
        "version": "1.0",
        "date": "2026-03-20",
        "inputs": {
            "active_predictions": os.path.relpath(IN_ACTIVE, C.ANALYSIS_DIR).replace("\\", "/"),
            "dualpath_metadata": os.path.relpath(IN_DUAL_META, C.ANALYSIS_DIR).replace("\\", "/"),
            "n_breaths": int(len(out)),
            "n_patients": int(out["patient_id"].astype(str).nunique()),
        },
        "dualpath_surrogate_parameters": {
            "bypass_to_active_area_ratio": float(bypass_ratio),
            "fuse_open_dp_cmh2o_nominal": float(fuse_open),
            "fuse_trigger_cmh2o_used": float(np.clip(best_cfg["trigger_scale"] * fuse_open, 6.0, 12.0)),
            "trigger_scale": float(best_cfg["trigger_scale"]),
            "base_gain": float(best_cfg["base_gain"]),
            "base_cap": float(best_cfg["base_cap"]),
            "fuse_gain": float(best_cfg["fuse_gain"]),
            "fuse_cap": float(best_cfg["fuse_cap"]),
            "max_total_assist_factor": float(best_cfg["max_total_assist"]),
            "sweep_used": bool(sweep_used),
        },
        "aggregate_comparison": {
            "active": {
                "plant_moderate_pass_rate": active_rates["plant_moderate_pass_rate"],
                "plant_severe_pass_rate": active_rates["plant_severe_pass_rate"],
                "plant_moderate_min_patient_pass_rate": active_rates["plant_moderate_min_patient_pass_rate"],
                "plant_severe_min_patient_pass_rate": active_rates["plant_severe_min_patient_pass_rate"],
            },
            "dualpath": {
                "plant_moderate_pass_rate": dual_rates["plant_moderate_pass_rate"],
                "plant_severe_pass_rate": dual_rates["plant_severe_pass_rate"],
                "plant_moderate_min_patient_pass_rate": dual_rates["plant_moderate_min_patient_pass_rate"],
                "plant_severe_min_patient_pass_rate": dual_rates["plant_severe_min_patient_pass_rate"],
            },
            "delta_dualpath_minus_active": {
                "plant_moderate_pass_rate": dual_rates["plant_moderate_pass_rate"] - active_rates["plant_moderate_pass_rate"],
                "plant_severe_pass_rate": dual_rates["plant_severe_pass_rate"] - active_rates["plant_severe_pass_rate"],
                "plant_moderate_min_patient_pass_rate": dual_rates["plant_moderate_min_patient_pass_rate"] - active_rates["plant_moderate_min_patient_pass_rate"],
                "plant_severe_min_patient_pass_rate": dual_rates["plant_severe_min_patient_pass_rate"] - active_rates["plant_severe_min_patient_pass_rate"],
            },
        },
        "outputs": {
            "dualpath_predictions": os.path.relpath(OUT_PRED, C.ANALYSIS_DIR).replace("\\", "/"),
            "per_patient_comparison": os.path.relpath(OUT_PER_PATIENT, C.ANALYSIS_DIR).replace("\\", "/"),
            "sweep_results": os.path.relpath(OUT_SWEEP, C.ANALYSIS_DIR).replace("\\", "/") if sweep_used else None,
        },
        "notes": [
            "Exploratory surrogate comparison only. Not a hardware validation result.",
            "Dual-path assist model is a first-order abstraction tied to CAD area ratio metadata.",
            "Use this output to decide whether dual-path warrants dedicated gate/evidence branch.",
        ],
    }

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    log.info("Saved: %s", OUT_PRED)
    log.info("Saved: %s", OUT_PER_PATIENT)
    log.info("Saved: %s", OUT_SUMMARY)
    log.info(
        "Severe min-patient pass rate active -> dualpath: %.3f -> %.3f",
        active_rates["plant_severe_min_patient_pass_rate"],
        dual_rates["plant_severe_min_patient_pass_rate"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
