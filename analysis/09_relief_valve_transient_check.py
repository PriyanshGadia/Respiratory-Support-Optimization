#!/usr/bin/env python
# =============================================================================
# 09_relief_valve_transient_check.py  —  Relief valve transient response check
# Version: 1.0  |  2026-03-19
#
# Concept-level dynamic check for the relief-valve branch using a lumped
# spring-mass-damper model and orifice flow relation.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from itertools import product

import numpy as np

import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("09_relief_valve_transient_check")

OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_relief_transient_summary.json")
OUT_CSV = os.path.join(C.LOGS_DIR, "phase3_relief_transient_trace.csv")


@dataclass(frozen=True)
class ReliefParams:
    # Pressure/flow requirements
    set_pressure_cmh2o: float = 30.0
    max_pressure_cmh2o: float = 35.0
    flow_target_lps: float = 2.29
    cd: float = 0.7
    rho: float = 1.2

    # Geometry
    seat_dia_mm: float = 12.1
    max_lift_mm: float = 3.0

    # Dynamics (concept placeholders; to be replaced by measured values)
    poppet_mass_kg: float = 0.0020
    damping_n_s_per_m: float = 0.08
    spring_rate_n_per_m: float = 120.0
    spring_preload_n: float = 0.35

    # Simulation setup
    dt_s: float = 1e-4
    t_end_s: float = 0.080


@dataclass(frozen=True)
class HardwareFeasibilityEnvelope:
    # Conservative first-pass ranges for catalog-like medical valve hardware.
    min_mass_kg: float = 0.0015
    max_mass_kg: float = 0.0035
    min_damping_n_s_per_m: float = 0.06
    max_damping_n_s_per_m: float = 0.20
    min_spring_rate_n_per_m: float = 80.0
    max_spring_rate_n_per_m: float = 220.0
    min_preload_n: float = 0.15
    max_preload_n: float = 0.60
    min_max_lift_mm: float = 2.8
    max_max_lift_mm: float = 4.0


def cmh2o_to_pa(v: float) -> float:
    return v * 98.0665


def seat_area_m2(p: ReliefParams) -> float:
    d = p.seat_dia_mm / 1000.0
    return np.pi * d * d / 4.0


def req_orifice_area_m2(p: ReliefParams) -> float:
    dp = cmh2o_to_pa(p.max_pressure_cmh2o - p.set_pressure_cmh2o)
    v = np.sqrt(max(1e-12, 2.0 * dp / p.rho))
    q = p.flow_target_lps / 1000.0
    return q / max(1e-12, p.cd * v)


def effective_orifice_area_m2(p: ReliefParams, x_m: float) -> float:
    # Curtain area approximation for poppet + cap by seat area.
    d = p.seat_dia_mm / 1000.0
    curtain = np.pi * d * max(0.0, x_m)
    return min(curtain, seat_area_m2(p))


def required_lift_mm(p: ReliefParams) -> float:
    d = p.seat_dia_mm / 1000.0
    a_req = req_orifice_area_m2(p)
    x_req = a_req / max(1e-12, np.pi * d)
    return x_req * 1000.0


def simulate_step_response(p: ReliefParams) -> dict:
    p_set = cmh2o_to_pa(p.set_pressure_cmh2o)
    p_max = cmh2o_to_pa(p.max_pressure_cmh2o)

    n = int(p.t_end_s / p.dt_s) + 1
    t = np.linspace(0.0, p.t_end_s, n)

    x = np.zeros(n)  # lift (m)
    v = np.zeros(n)  # velocity (m/s)
    q = np.zeros(n)  # flow (m^3/s)

    max_lift_m = p.max_lift_mm / 1000.0

    for i in range(1, n):
        # Worst-case overpressure step to p_max.
        f_pressure = p_max * seat_area_m2(p)
        f_spring = p.spring_preload_n + p.spring_rate_n_per_m * x[i - 1]
        f_damp = p.damping_n_s_per_m * v[i - 1]

        f_net = f_pressure - f_spring - f_damp
        a = f_net / p.poppet_mass_kg

        v_i = v[i - 1] + a * p.dt_s
        x_i = x[i - 1] + v_i * p.dt_s

        # Clamp physical limits.
        if x_i < 0.0:
            x_i = 0.0
            v_i = 0.0
        elif x_i > max_lift_m:
            x_i = max_lift_m
            v_i = 0.0

        x[i] = x_i
        v[i] = v_i

        a_eff = effective_orifice_area_m2(p, x_i)
        q[i] = p.cd * a_eff * np.sqrt(max(0.0, 2.0 * (p_max - p_set) / p.rho))

    x_req_m = required_lift_mm(p) / 1000.0
    idx_req = np.where(x >= x_req_m)[0]
    t_to_req_ms = float(t[idx_req[0]] * 1000.0) if len(idx_req) > 0 else np.nan

    idx_90 = np.where(x >= 0.9 * max_lift_m)[0]
    t_to_90_ms = float(t[idx_90[0]] * 1000.0) if len(idx_90) > 0 else np.nan

    q_target = p.flow_target_lps / 1000.0
    idx_q = np.where(q >= q_target)[0]
    t_to_flow_ms = float(t[idx_q[0]] * 1000.0) if len(idx_q) > 0 else np.nan

    trace = np.column_stack([t, x * 1000.0, v, q * 1000.0])

    return {
        "trace": trace,
        "summary": {
            "required_lift_mm": float(required_lift_mm(p)),
            "max_lift_mm": float(np.max(x) * 1000.0),
            "peak_flow_lps": float(np.max(q) * 1000.0),
            "flow_target_lps": p.flow_target_lps,
            "t_to_required_lift_ms": t_to_req_ms,
            "t_to_90pct_lift_ms": t_to_90_ms,
            "t_to_target_flow_ms": t_to_flow_ms,
            "response_time_target_ms": 20.0,
            "response_time_pass": bool(np.isfinite(t_to_flow_ms) and t_to_flow_ms <= 20.0),
            "flow_capacity_pass": bool(np.max(q) * 1000.0 >= p.flow_target_lps),
        },
    }


def _in_hardware_envelope(p: ReliefParams, env: HardwareFeasibilityEnvelope) -> bool:
    return (
        env.min_mass_kg <= p.poppet_mass_kg <= env.max_mass_kg
        and env.min_damping_n_s_per_m <= p.damping_n_s_per_m <= env.max_damping_n_s_per_m
        and env.min_spring_rate_n_per_m <= p.spring_rate_n_per_m <= env.max_spring_rate_n_per_m
        and env.min_preload_n <= p.spring_preload_n <= env.max_preload_n
        and env.min_max_lift_mm <= p.max_lift_mm <= env.max_max_lift_mm
    )


def search_relief_candidates(base: ReliefParams, env: HardwareFeasibilityEnvelope) -> dict:
    best = None
    best_feasible = None
    best_score = -1e9
    best_feasible_score = -1e9

    tested = 0
    feasible_tested = 0

    for mass, damp, k, preload, max_lift in product(
        [0.0008, 0.0010, 0.0015, 0.0020],
        [0.03, 0.05, 0.08],
        [40.0, 60.0, 80.0, 120.0],
        [0.05, 0.10, 0.20, 0.35],
        [3.2, 3.5, 4.0],
    ):
        tested += 1
        p = ReliefParams(
            set_pressure_cmh2o=base.set_pressure_cmh2o,
            max_pressure_cmh2o=base.max_pressure_cmh2o,
            flow_target_lps=base.flow_target_lps,
            cd=base.cd,
            rho=base.rho,
            seat_dia_mm=base.seat_dia_mm,
            max_lift_mm=max_lift,
            poppet_mass_kg=mass,
            damping_n_s_per_m=damp,
            spring_rate_n_per_m=k,
            spring_preload_n=preload,
            dt_s=base.dt_s,
            t_end_s=base.t_end_s,
        )
        sim = simulate_step_response(p)
        s = sim["summary"]

        t_flow = s["t_to_target_flow_ms"]
        t_penalty = 100.0 if not np.isfinite(t_flow) else max(0.0, t_flow - 20.0)
        flow_margin = s["peak_flow_lps"] - p.flow_target_lps
        score = flow_margin * 40.0 - t_penalty

        if score > best_score:
            best_score = score
            best = {
                "params": asdict(p),
                "results": s,
                "score": float(score),
                "hardware_feasible": bool(_in_hardware_envelope(p, env)),
            }

        is_feasible = _in_hardware_envelope(p, env)
        if is_feasible:
            feasible_tested += 1
            if score > best_feasible_score:
                best_feasible_score = score
                best_feasible = {
                    "params": asdict(p),
                    "results": s,
                    "score": float(score),
                    "hardware_feasible": True,
                }

    assert best is not None
    return {
        "tested_candidates": int(tested),
        "tested_hardware_feasible_candidates": int(feasible_tested),
        "best_unconstrained": best,
        "best_hardware_feasible": best_feasible,
        "hardware_feasible_pass_found": bool(
            best_feasible is not None
            and best_feasible["results"]["response_time_pass"]
            and best_feasible["results"]["flow_capacity_pass"]
        ),
    }


def main() -> int:
    os.makedirs(C.LOGS_DIR, exist_ok=True)

    params = ReliefParams()
    envelope = HardwareFeasibilityEnvelope()
    result = simulate_step_response(params)
    best = search_relief_candidates(params, envelope)

    np.savetxt(
        OUT_CSV,
        result["trace"],
        delimiter=",",
        header="time_s,lift_mm,velocity_m_s,flow_lps",
        comments="",
    )

    out = {
        "version": "1.0",
        "date": "2026-03-19",
        "params": asdict(params),
        "derived": {
            "seat_area_mm2": float(seat_area_m2(params) * 1e6),
            "required_orifice_area_mm2": float(req_orifice_area_m2(params) * 1e6),
        },
        "hardware_feasibility_envelope": asdict(envelope),
        "results": result["summary"],
        "candidate_search": best,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    log.info("Saved: %s", OUT_CSV)
    log.info("Saved: %s", OUT_JSON)
    log.info("Relief response pass (<=20 ms): %s", out["results"]["response_time_pass"])
    log.info("Relief flow capacity pass: %s", out["results"]["flow_capacity_pass"])
    uncon = best["best_unconstrained"]
    log.info(
        "Best unconstrained candidate pass pair: time=%s, flow=%s",
        uncon["results"]["response_time_pass"],
        uncon["results"]["flow_capacity_pass"],
    )
    log.info("Hardware-feasible candidate pass found: %s", best["hardware_feasible_pass_found"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
