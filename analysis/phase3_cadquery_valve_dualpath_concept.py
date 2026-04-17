#!/usr/bin/env python3
"""
Phase 3 Adaptive Expiratory Valve - Dual-Path Concept CAD (CadQuery)

Version: 1.0
Date: March 20, 2026
Status: Research concept only (not manufacturing release, not clinical use)

Purpose:
- Explore a novel but buildable dual-path expiratory valve architecture.
- Keep a deterministic safety posture: normally open, passive bypass present,
  and no claim of hardware readiness.

Concept summary:
- Path A: Active central poppet for breath-by-breath modulation.
- Path B: Passive annular bypass path with a low-inertia fuse ring that opens
  under excessive differential pressure if Path A is delayed/failed.
- Cost-aware geometry with metadata output for area, volume, and rough cost.

Run:
  python REBOOT/analysis/phase3_cadquery_valve_dualpath_concept.py

Output:
  REBOOT/analysis/valve_export_dualpath_concept/*.step
  REBOOT/analysis/valve_export_dualpath_concept/dualpath_metadata.json
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi, sqrt
from pathlib import Path
from typing import Any
import json

try:
    import cadquery as cq

    CQ_AVAILABLE = True
    CADQUERY_IMPORT_ERROR = ""
except Exception as exc:
    cq = None  # type: ignore[assignment]
    CQ_AVAILABLE = False
    CADQUERY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class DualPathParams:
    # Main valve geometry
    bore_dia_mm: float = 16.0
    body_od_mm: float = 32.0
    body_len_mm: float = 64.0
    active_lift_max_mm: float = 3.0

    # Passive annular bypass ring
    bypass_inner_dia_mm: float = 18.0
    bypass_outer_dia_mm: float = 24.0
    bypass_axial_len_mm: float = 8.0
    bypass_slot_count: int = 12
    bypass_slot_w_mm: float = 1.2
    bypass_slot_h_mm: float = 3.0

    # Fuse ring (thin flex ring that vents in over-pressure events)
    fuse_ring_thickness_mm: float = 0.45
    fuse_ring_width_mm: float = 2.5
    fuse_open_dp_cmh2o_nominal: float = 14.0

    # Active poppet
    poppet_stem_dia_mm: float = 9.0
    poppet_head_dia_mm: float = 13.0
    poppet_head_thk_mm: float = 1.8

    # Material density assumptions for rough mass/cost estimates
    density_body_kg_m3: float = 8000.0   # 316L-like estimate
    density_poppet_kg_m3: float = 7800.0
    density_ring_kg_m3: float = 2150.0   # PTFE/PEEK-class placeholder

    # Very rough cost assumptions (research budgeting only)
    cost_body_usd_per_kg: float = 18.0
    cost_poppet_usd_per_kg: float = 22.0
    cost_ring_usd_per_kg: float = 60.0
    machining_factor: float = 2.2


ShapeT = Any
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "REBOOT" / "analysis" / "valve_export_dualpath_concept"


def cmh2o_to_pa(v: float) -> float:
    return v * 98.0665


def annulus_area_mm2(d_in: float, d_out: float) -> float:
    return 0.25 * pi * (d_out * d_out - d_in * d_in)


def active_curtain_area_mm2(d_seat: float, lift_mm: float) -> float:
    return pi * d_seat * max(0.0, lift_mm)


def bypass_slot_total_area_mm2(params: DualPathParams) -> float:
    return float(params.bypass_slot_count) * params.bypass_slot_w_mm * params.bypass_slot_h_mm


def estimated_fuse_force_n(params: DualPathParams) -> float:
    # First-order estimate: pressure force on annular differential area.
    area_m2 = annulus_area_mm2(params.bypass_inner_dia_mm, params.bypass_outer_dia_mm) * 1e-6
    return cmh2o_to_pa(params.fuse_open_dp_cmh2o_nominal) * area_m2


def make_body(params: DualPathParams) -> ShapeT:
    body = cq.Workplane("XY").circle(params.body_od_mm / 2.0).extrude(params.body_len_mm)

    # Main central bore
    body = body.cut(cq.Workplane("XY").circle(params.bore_dia_mm / 2.0).extrude(params.body_len_mm))

    # Annular bypass tunnel (coaxial ring volume)
    bypass_outer = cq.Workplane("XY").circle(params.bypass_outer_dia_mm / 2.0).extrude(params.bypass_axial_len_mm)
    bypass_inner = cq.Workplane("XY").circle(params.bypass_inner_dia_mm / 2.0).extrude(params.bypass_axial_len_mm)
    bypass_ring = bypass_outer.cut(bypass_inner).translate((0, 0, params.body_len_mm * 0.5 - params.bypass_axial_len_mm * 0.5))
    body = body.cut(bypass_ring)

    # Bypass feed slots distributed circumferentially.
    slot_r = (params.bypass_inner_dia_mm + params.bypass_outer_dia_mm) * 0.25
    z0 = params.body_len_mm * 0.5
    for i in range(params.bypass_slot_count):
        angle_deg = 360.0 * i / float(params.bypass_slot_count)
        slot = (
            cq.Workplane("XY")
            .center(slot_r, 0.0)
            .rect(params.bypass_slot_w_mm, params.bypass_slot_h_mm)
            .extrude(params.bypass_axial_len_mm + 0.5)
            .translate((0.0, 0.0, z0 - params.bypass_axial_len_mm * 0.5 - 0.25))
            .rotate((0, 0, 0), (0, 0, 1), angle_deg)
        )
        body = body.cut(slot)

    # Light mount flange for low-cost bracket attachment.
    flange = (
        cq.Workplane("XY")
        .workplane(offset=params.body_len_mm - 4.0)
        .circle((params.body_od_mm + 10.0) / 2.0)
        .circle((params.body_od_mm - 2.0) / 2.0)
        .extrude(4.0)
    )
    body = body.union(flange)

    return body


def make_active_poppet(params: DualPathParams) -> ShapeT:
    stem_len = params.body_len_mm * 0.52
    stem = cq.Workplane("XY").circle(params.poppet_stem_dia_mm / 2.0).extrude(stem_len, both=True)
    head = (
        cq.Workplane("XY")
        .workplane(offset=stem_len / 2.0 - params.poppet_head_thk_mm)
        .circle(params.poppet_head_dia_mm / 2.0)
        .extrude(params.poppet_head_thk_mm)
    )
    return stem.union(head)


def make_fuse_ring(params: DualPathParams) -> ShapeT:
    # Thin ring that can deflect/open under over-pressure differential.
    ring_od = params.bypass_outer_dia_mm - 0.6
    ring_id = ring_od - 2.0 * params.fuse_ring_width_mm

    ring = (
        cq.Workplane("XY")
        .circle(ring_od / 2.0)
        .circle(ring_id / 2.0)
        .extrude(params.fuse_ring_thickness_mm)
    )

    # Introduce periodic compliance slots so opening pressure can be tuned.
    slot_len = params.fuse_ring_width_mm * 0.9
    slot_w = 0.35
    slot_r = (ring_od + ring_id) * 0.25
    for i in range(8):
        a = 360.0 * i / 8.0
        slot = (
            cq.Workplane("XY")
            .center(slot_r, 0.0)
            .rect(slot_len, slot_w)
            .extrude(params.fuse_ring_thickness_mm + 0.2)
            .translate((0.0, 0.0, -0.1))
            .rotate((0, 0, 0), (0, 0, 1), a)
        )
        ring = ring.cut(slot)

    return ring


def make_sensor_bridge(params: DualPathParams) -> ShapeT:
    # Symmetric bridge to support two low-cost Hall sensors for redundancy.
    z = params.body_len_mm - 2.0
    bridge = cq.Workplane("XY").workplane(offset=z).rect(28.0, 6.0).extrude(2.0)

    for x in (-8.0, 8.0):
        pocket = cq.Workplane("XY").workplane(offset=z + 0.6).center(x, 0.0).rect(5.2, 4.2).extrude(1.6)
        bridge = bridge.cut(pocket)

    return bridge


def build_concept(params: DualPathParams) -> tuple[ShapeT, ShapeT, ShapeT, ShapeT]:
    body = make_body(params)
    poppet = make_active_poppet(params)
    ring = make_fuse_ring(params)
    bridge = make_sensor_bridge(params)

    # Position internal parts in closed-state layout for packaging checks.
    poppet = poppet.translate((0, 0, params.body_len_mm * 0.22))
    ring = ring.translate((0, 0, params.body_len_mm * 0.5))

    return body, poppet, ring, bridge


def rough_component_costs(params: DualPathParams, body_v_mm3: float, poppet_v_mm3: float, ring_v_mm3: float) -> dict[str, float]:
    # Convert mm^3 to m^3 then to kg.
    body_kg = body_v_mm3 * 1e-9 * params.density_body_kg_m3
    poppet_kg = poppet_v_mm3 * 1e-9 * params.density_poppet_kg_m3
    ring_kg = ring_v_mm3 * 1e-9 * params.density_ring_kg_m3

    body_cost = body_kg * params.cost_body_usd_per_kg
    poppet_cost = poppet_kg * params.cost_poppet_usd_per_kg
    ring_cost = ring_kg * params.cost_ring_usd_per_kg
    raw = body_cost + poppet_cost + ring_cost

    return {
        "material_cost_usd": round(raw, 4),
        "estimated_piece_cost_usd": round(raw * params.machining_factor, 4),
    }


def analytical_fallback_metadata(params: DualPathParams) -> dict[str, float]:
    # Fallback when CadQuery is unavailable.
    body_v = pi * (params.body_od_mm * 0.5) ** 2 * params.body_len_mm
    bore_v = pi * (params.bore_dia_mm * 0.5) ** 2 * params.body_len_mm
    body_net = max(0.0, body_v - bore_v)

    poppet_v = pi * (params.poppet_stem_dia_mm * 0.5) ** 2 * (params.body_len_mm * 0.52)
    poppet_v += pi * (params.poppet_head_dia_mm * 0.5) ** 2 * params.poppet_head_thk_mm

    ring_od = params.bypass_outer_dia_mm - 0.6
    ring_id = ring_od - 2.0 * params.fuse_ring_width_mm
    ring_v = annulus_area_mm2(ring_id, ring_od) * params.fuse_ring_thickness_mm

    return {
        "body_volume_mm3": round(body_net, 3),
        "poppet_volume_mm3": round(poppet_v, 3),
        "ring_volume_mm3": round(max(0.0, ring_v), 3),
    }


def main() -> int:
    params = DualPathParams()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    area_active = active_curtain_area_mm2(params.bore_dia_mm, params.active_lift_max_mm)
    area_bypass_slots = bypass_slot_total_area_mm2(params)
    area_bypass_annulus = annulus_area_mm2(params.bypass_inner_dia_mm, params.bypass_outer_dia_mm)

    metadata: dict[str, Any] = {
        "version": "1.0",
        "date": "2026-03-20",
        "status": "research_concept_only",
        "concept": "dual_path_active_plus_passive_bypass",
        "cadquery_available": CQ_AVAILABLE,
        "cadquery_import_error": CADQUERY_IMPORT_ERROR,
        "params": asdict(params),
        "physics_summary": {
            "active_curtain_area_mm2": round(area_active, 3),
            "bypass_slot_total_area_mm2": round(area_bypass_slots, 3),
            "bypass_annulus_area_mm2": round(area_bypass_annulus, 3),
            "bypass_to_active_area_ratio": round(area_bypass_slots / max(1e-9, area_active), 4),
            "estimated_fuse_open_force_n": round(estimated_fuse_force_n(params), 4),
        },
        "notes": [
            "Concept is for CAD/physics exploration only; not manufacturing release.",
            "Fuse-ring opening pressure is a first-order estimate and requires bench validation.",
            "No hardware or clinical safety claim is made by this script.",
        ],
    }

    if CQ_AVAILABLE:
        body, poppet, ring, bridge = build_concept(params)

        cq.exporters.export(body, str(OUT_DIR / "dualpath_body.step"))
        cq.exporters.export(poppet, str(OUT_DIR / "dualpath_poppet.step"))
        cq.exporters.export(ring, str(OUT_DIR / "dualpath_fuse_ring.step"))
        cq.exporters.export(bridge, str(OUT_DIR / "dualpath_sensor_bridge.step"))

        body_v = float(body.val().Volume())
        poppet_v = float(poppet.val().Volume())
        ring_v = float(ring.val().Volume())

        metadata["volumes_mm3"] = {
            "body_volume_mm3": round(body_v, 3),
            "poppet_volume_mm3": round(poppet_v, 3),
            "ring_volume_mm3": round(ring_v, 3),
        }
        metadata["cost_estimate"] = rough_component_costs(params, body_v, poppet_v, ring_v)
    else:
        vols = analytical_fallback_metadata(params)
        metadata["volumes_mm3"] = vols
        metadata["cost_estimate"] = rough_component_costs(
            params,
            vols["body_volume_mm3"],
            vols["poppet_volume_mm3"],
            vols["ring_volume_mm3"],
        )

    with open(OUT_DIR / "dualpath_metadata.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    print("Saved concept metadata:", OUT_DIR / "dualpath_metadata.json")
    if not CQ_AVAILABLE:
        print("CadQuery unavailable; exported metadata only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
