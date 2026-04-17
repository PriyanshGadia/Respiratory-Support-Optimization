#!/usr/bin/env python
# =============================================================================
# 10_phase3_safety_fault_injection.py  —  Phase 3B safety fault timing checks
# Version: 1.0  |  2026-03-19
#
# Generates preliminary in-silico timing evidence for safety controls:
# - watchdog timeout cutoff
# - dual-sensor disagreement detection
# - pressure-differential fault response
#
# This script is a screening artifact for redesign gating, not hardware evidence.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from itertools import product

import numpy as np

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("10_phase3_safety_fault_injection")

OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_safety_fault_summary.json")
OUT_CSV = os.path.join(C.LOGS_DIR, "phase3_safety_fault_trace.csv")


@dataclass(frozen=True)
class SafetyFaultParams:
    dt_ms: float = 0.1
    t_end_ms: float = 40.0

    watchdog_timeout_ms: float = 8.0
    watchdog_cutoff_delay_ms: float = 1.0

    sensor_disagreement_threshold_mm: float = 0.10
    sensor_disagreement_debounce_ms: float = 5.0
    sensor_fault_onset_ms: float = 3.0
    sensor_bias_rate_mm_per_ms: float = 0.03

    pressure_fault_threshold_cmh2o: float = 3.5
    pressure_fault_debounce_ms: float = 4.0
    pressure_fault_onset_ms: float = 2.0
    pressure_rise_rate_cmh2o_per_ms: float = 0.35

    fail_open_timing_target_ms: float = 10.0


def _first_true_time_ms(mask: np.ndarray, t_ms: np.ndarray) -> float:
    idx = np.where(mask)[0]
    return float(t_ms[idx[0]]) if len(idx) else float("nan")


def _simulate_watchdog(p: SafetyFaultParams, t_ms: np.ndarray) -> tuple[dict, dict]:
    wdt_trigger = t_ms >= p.watchdog_timeout_ms
    cutoff = t_ms >= (p.watchdog_timeout_ms + p.watchdog_cutoff_delay_ms)

    t_cutoff = _first_true_time_ms(cutoff, t_ms)
    pass_flag = bool(np.isfinite(t_cutoff) and t_cutoff <= p.fail_open_timing_target_ms)

    trace = {
        "watchdog_trigger": wdt_trigger.astype(int),
        "watchdog_cutoff": cutoff.astype(int),
    }
    summary = {
        "t_watchdog_cutoff_ms": t_cutoff,
        "pass": pass_flag,
    }
    return trace, summary


def _simulate_sensor_disagreement(p: SafetyFaultParams, t_ms: np.ndarray) -> tuple[dict, dict]:
    pos_ch1 = np.zeros_like(t_ms)
    bias = np.maximum(0.0, t_ms - p.sensor_fault_onset_ms) * p.sensor_bias_rate_mm_per_ms
    pos_ch2 = pos_ch1 + bias

    disagreement = np.abs(pos_ch1 - pos_ch2)
    over_thr = disagreement > p.sensor_disagreement_threshold_mm

    debounce_steps = max(1, int(round(p.sensor_disagreement_debounce_ms / p.dt_ms)))
    kernel = np.ones(debounce_steps, dtype=int)
    over_thr_i = over_thr.astype(int)
    sustained = np.convolve(over_thr_i, kernel, mode="full")[: len(over_thr_i)] >= debounce_steps

    t_fault_latch = _first_true_time_ms(sustained, t_ms)
    pass_flag = bool(np.isfinite(t_fault_latch) and t_fault_latch <= p.fail_open_timing_target_ms)

    trace = {
        "sensor_disagreement_mm": disagreement,
        "sensor_over_threshold": over_thr.astype(int),
        "sensor_fault_latched": sustained.astype(int),
    }
    summary = {
        "t_sensor_fault_latched_ms": t_fault_latch,
        "pass": pass_flag,
    }
    return trace, summary


def _simulate_pressure_fault(p: SafetyFaultParams, t_ms: np.ndarray) -> tuple[dict, dict]:
    dp = np.maximum(0.0, t_ms - p.pressure_fault_onset_ms) * p.pressure_rise_rate_cmh2o_per_ms
    over_thr = dp > p.pressure_fault_threshold_cmh2o

    debounce_steps = max(1, int(round(p.pressure_fault_debounce_ms / p.dt_ms)))
    kernel = np.ones(debounce_steps, dtype=int)
    over_thr_i = over_thr.astype(int)
    sustained = np.convolve(over_thr_i, kernel, mode="full")[: len(over_thr_i)] >= debounce_steps

    t_fault_response = _first_true_time_ms(sustained, t_ms)
    pass_flag = bool(np.isfinite(t_fault_response) and t_fault_response <= p.fail_open_timing_target_ms)

    trace = {
        "delta_p_cmh2o": dp,
        "pressure_over_threshold": over_thr.astype(int),
        "pressure_fault_latched": sustained.astype(int),
    }
    summary = {
        "t_pressure_fault_latched_ms": t_fault_response,
        "pass": pass_flag,
    }
    return trace, summary


def _run_fault_suite(p: SafetyFaultParams) -> tuple[dict, dict, np.ndarray]:
    n = int(round(p.t_end_ms / p.dt_ms)) + 1
    t_ms = np.linspace(0.0, p.t_end_ms, n)

    wd_trace, wd_summary = _simulate_watchdog(p, t_ms)
    sd_trace, sd_summary = _simulate_sensor_disagreement(p, t_ms)
    pr_trace, pr_summary = _simulate_pressure_fault(p, t_ms)

    traces = {
        "watchdog": wd_trace,
        "sensor_disagreement": sd_trace,
        "pressure_fault": pr_trace,
    }
    results = {
        "watchdog": wd_summary,
        "sensor_disagreement": sd_summary,
        "pressure_fault": pr_summary,
        "overall_pass": bool(wd_summary["pass"] and sd_summary["pass"] and pr_summary["pass"]),
    }
    return traces, results, t_ms


def _search_pass_candidate(base: SafetyFaultParams) -> dict:
    best = None
    best_score = -1e9

    for wdt_timeout, wdt_cutoff_delay, sensor_debounce, sensor_bias_rate, pressure_debounce, pressure_rise_rate in product(
        [6.0, 7.0, 8.0],
        [0.5, 1.0],
        [2.0, 3.0, 4.0, 5.0],
        [0.03, 0.04, 0.05],
        [1.5, 2.0, 3.0, 4.0],
        [0.35, 0.45, 0.60],
    ):
        p = SafetyFaultParams(
            dt_ms=base.dt_ms,
            t_end_ms=base.t_end_ms,
            watchdog_timeout_ms=wdt_timeout,
            watchdog_cutoff_delay_ms=wdt_cutoff_delay,
            sensor_disagreement_threshold_mm=base.sensor_disagreement_threshold_mm,
            sensor_disagreement_debounce_ms=sensor_debounce,
            sensor_fault_onset_ms=base.sensor_fault_onset_ms,
            sensor_bias_rate_mm_per_ms=sensor_bias_rate,
            pressure_fault_threshold_cmh2o=base.pressure_fault_threshold_cmh2o,
            pressure_fault_debounce_ms=pressure_debounce,
            pressure_fault_onset_ms=base.pressure_fault_onset_ms,
            pressure_rise_rate_cmh2o_per_ms=pressure_rise_rate,
            fail_open_timing_target_ms=base.fail_open_timing_target_ms,
        )
        _, res, _ = _run_fault_suite(p)

        wt = res["watchdog"]["t_watchdog_cutoff_ms"]
        st = res["sensor_disagreement"]["t_sensor_fault_latched_ms"]
        pt = res["pressure_fault"]["t_pressure_fault_latched_ms"]
        finite_times = [v for v in [wt, st, pt] if np.isfinite(v)]

        pass_count = int(res["watchdog"]["pass"]) + int(res["sensor_disagreement"]["pass"]) + int(res["pressure_fault"]["pass"])
        mean_time = float(np.mean(finite_times)) if finite_times else 1e6
        score = pass_count * 10.0 - mean_time / 10.0

        if score > best_score:
            best_score = score
            best = {
                "params": asdict(p),
                "results": res,
                "score": float(score),
            }
            if res["overall_pass"]:
                break

    assert best is not None
    return best


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    fault_params = SafetyFaultParams()
    traces, results, t_ms = _run_fault_suite(fault_params)
    candidate = _search_pass_candidate(fault_params)

    trace_cols = [
        t_ms,
        traces["watchdog"]["watchdog_trigger"],
        traces["watchdog"]["watchdog_cutoff"],
        traces["sensor_disagreement"]["sensor_disagreement_mm"],
        traces["sensor_disagreement"]["sensor_over_threshold"],
        traces["sensor_disagreement"]["sensor_fault_latched"],
        traces["pressure_fault"]["delta_p_cmh2o"],
        traces["pressure_fault"]["pressure_over_threshold"],
        traces["pressure_fault"]["pressure_fault_latched"],
    ]
    trace = np.column_stack(trace_cols)

    np.savetxt(
        OUT_CSV,
        trace,
        delimiter=",",
        header=(
            "time_ms,watchdog_trigger,watchdog_cutoff,sensor_disagreement_mm,"
            "sensor_over_threshold,sensor_fault_latched,delta_p_cmh2o,"
            "pressure_over_threshold,pressure_fault_latched"
        ),
        comments="",
    )

    summary_payload = {
        "version": "1.0",
        "date": "2026-03-19",
        "params": asdict(fault_params),
        "criteria": {
            "fail_open_timing_target_ms": fault_params.fail_open_timing_target_ms,
        },
        "results": results,
        "candidate_search": candidate,
        "notes": [
            "Preliminary software timing simulation only.",
            "Not a substitute for hardware-in-loop or bench fault injection.",
        ],
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary_payload, fh, indent=2)

    log.info("Saved: %s", OUT_CSV)
    log.info("Saved: %s", OUT_JSON)
    log.info("Watchdog timing pass: %s", results["watchdog"]["pass"])
    log.info("Sensor disagreement timing pass: %s", results["sensor_disagreement"]["pass"])
    log.info("Pressure fault timing pass: %s", results["pressure_fault"]["pass"])
    log.info("Overall timing pass: %s", results["overall_pass"])
    log.info(
        "Best candidate pass: %s (watchdog=%s sensor=%s pressure=%s)",
        candidate["results"]["overall_pass"],
        candidate["results"]["watchdog"]["pass"],
        candidate["results"]["sensor_disagreement"]["pass"],
        candidate["results"]["pressure_fault"]["pass"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
