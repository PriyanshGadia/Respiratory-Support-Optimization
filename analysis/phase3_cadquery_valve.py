#!/usr/bin/env python3
"""
Phase 3 Adaptive Expiratory Valve - Parametric CAD Generator (CadQuery)

Version: 3.1
Date: March 19, 2026
Status: Active redesign baseline (concept geometry, not manufacturing release)

This script generates simulation-ready STEP geometry for the adaptive expiratory
valve concept and its key subcomponents:
- Body
- Replaceable seat
- Poppet stem + optional FKM tip
- Spring (helical concept model with annulus fallback)
- Voice-coil magnet and housing
- Relief valve body/poppet/spring
- Sensor bracket
- Dynamic-seal placeholder (PTFE-style geometry marker)

Run:
  python REBOOT/analysis/phase3_cadquery_valve.py

Output:
  REBOOT/analysis/valve_export/*.step
  REBOOT/analysis/valve_export/valve_metadata.json
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi, radians, sqrt, tan
from pathlib import Path
from typing import Any, Dict, Tuple
import json
import os
import subprocess
import sys

try:
    import cadquery as cq
    CQ_AVAILABLE = True
    CADQUERY_IMPORT_ERROR = ""
except Exception as exc:
    cq = None  # type: ignore[assignment]
    CQ_AVAILABLE = False
    CADQUERY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class ValveParams:
    # Redesign baseline dimensions
    bore_dia: float = 16.0
    port_dia: float = 16.0
    body_od: float = 30.0
    body_length: float = 60.0
    seat_angle: float = 30.0
    lift_max: float = 3.0

    spring_wire: float = 0.58
    spring_od: float = 10.0
    spring_free_len: float = 6.8
    spring_coils: int = 4

    poppet_stem_dia: float = 10.0
    poppet_flange_od: float = 11.0
    poppet_flange_thickness: float = 1.5
    poppet_spring_recess_depth: float = 1.0
    body_spring_recess_depth: float = 0.2

    spring_target_k_n_per_mm: float = 0.30
    spring_force_closed_target_n: float = 1.0
    spring_shear_modulus_pa: float = 79e9

    # Dynamic seal baseline: PTFE-style ring placeholder (geometry marker for gland development).
    seal_inner_dia: float = 10.2
    seal_cross: float = 1.5
    seal_gland_depth: float = 1.5
    seal_gland_width: float = 2.0

    vcm_coil_od: float = 20.0
    vcm_magnet_od: float = 12.0
    vcm_length: float = 15.0

    relief_seat_dia: float = 12.1
    relief_lift: float = 3.0
    relief_set_pressure_cmh2o: float = 30.0
    relief_max_pressure_cmh2o: float = 35.0
    relief_flow_target_lps: float = 2.29
    relief_cd: float = 0.7

    magnet_dia: float = 3.0
    magnet_len: float = 3.0

    vent_port_dia: float = 8.0

    # Secondary design constants (kept explicit for transparency)
    left_port_depth: float = 15.0
    gland_step_depth: float = 5.0
    right_counterbore_depth: float = 3.0
    flange_od: float = 40.0
    flange_thickness: float = 5.0

    sensor_port_dia: float = 5.0
    spring_preload: float = 0.5


P = ValveParams()
ShapeT = Any
AssemblyT = Any
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def spring_id(params: ValveParams) -> float:
    return params.spring_od - 2.0 * params.spring_wire


def cmh2o_to_pa(v: float) -> float:
    return v * 98.0665


def spring_mean_dia(params: ValveParams) -> float:
    return params.spring_od - params.spring_wire


def spring_rate_n_per_mm(params: ValveParams) -> float:
    # Helical compression spring approximation with active coils.
    d = params.spring_wire / 1000.0
    D = spring_mean_dia(params) / 1000.0
    Na = float(params.spring_coils)
    if d <= 0 or D <= 0 or Na <= 0:
        return 0.0
    k_n_per_m = params.spring_shear_modulus_pa * d**4 / (8.0 * D**3 * Na)
    return k_n_per_m / 1000.0


def spring_solid_length_mm(params: ValveParams) -> float:
    # Approximate total coils = active + 2 closed ends.
    total_coils = params.spring_coils + 2
    return total_coils * params.spring_wire


def spring_force_closed_n(params: ValveParams) -> float:
    return max(0.0, spring_rate_n_per_mm(params) * (params.spring_free_len - spring_installed_length_closed(params)))


def spring_force_open_n(params: ValveParams) -> float:
    open_len = spring_installed_length_closed(params) + params.lift_max
    return max(0.0, spring_rate_n_per_mm(params) * (params.spring_free_len - open_len))


def spring_recommended_free_len_mm(params: ValveParams) -> float:
    k = max(1e-9, spring_rate_n_per_mm(params))
    return spring_installed_length_closed(params) + params.spring_force_closed_target_n / k


def relief_required_area_mm2(params: ValveParams, rho: float = 1.2) -> float:
    dp_pa = cmh2o_to_pa(params.relief_max_pressure_cmh2o - params.relief_set_pressure_cmh2o)
    denom = params.relief_cd * sqrt(max(1e-12, 2.0 * dp_pa / rho))
    area_m2 = (params.relief_flow_target_lps / 1000.0) / max(1e-12, denom)
    return area_m2 * 1e6


def relief_required_dia_mm(params: ValveParams) -> float:
    area_mm2 = relief_required_area_mm2(params)
    return sqrt(4.0 * area_mm2 / pi)


def seal_major_radius_installed(params: ValveParams) -> float:
    # Ring-path radius around the stem axis for PTFE placeholder geometry.
    return params.seal_inner_dia * 0.5 + params.seal_cross * 0.5


def validate_params(params: ValveParams) -> None:
    sid = spring_id(params)
    if sid <= 0:
        raise ValueError("Invalid spring dimensions: spring_id <= 0")
    if not (0 < params.seal_gland_depth <= params.seal_cross):
        raise ValueError("Seal gland depth must be >0 and <= seal_cross")
    if params.port_dia > params.body_od:
        raise ValueError("port_dia cannot exceed body_od")
    if params.poppet_flange_od <= params.spring_od:
        raise ValueError("poppet_flange_od must exceed spring_od for stable spring seating")
    if params.poppet_flange_od >= params.bore_dia:
        raise ValueError("poppet_flange_od must remain below bore_dia for radial clearance")
    if params.poppet_spring_recess_depth >= params.poppet_flange_thickness:
        raise ValueError("poppet_spring_recess_depth must be less than poppet_flange_thickness")
    if spring_solid_length_mm(params) >= spring_installed_length_closed(params):
        raise ValueError("Spring solid length exceeds/equal installed closed length")
    if params.relief_cd <= 0 or params.relief_cd > 1:
        raise ValueError("relief_cd must be in (0, 1]")


def seat_inner_r_left(params: ValveParams) -> float:
    return params.bore_dia / 2.0


def seat_inner_r_right(params: ValveParams) -> float:
    return seat_inner_r_left(params) + params.right_counterbore_depth * tan(radians(params.seat_angle))


def seat_outer_r(params: ValveParams) -> float:
    # Preserve nominal bore+2 shell where possible; enlarge only if needed to fit conical profile.
    nominal = (params.bore_dia + 2.0) / 2.0
    required = seat_inner_r_right(params) + 0.5
    return max(nominal, required)


def body_spring_seat_z(params: ValveParams) -> float:
    # Internal shoulder at seat-pocket entrance.
    return params.body_length - params.right_counterbore_depth


def poppet_closed_center_z(params: ValveParams) -> float:
    # Place poppet so tip apex touches seat entrance plane in closed position.
    seat_z = body_spring_seat_z(params)
    stem_len = params.body_length / 2.0
    return seat_z - (stem_len / 2.0 + params.lift_max)


def spring_installed_length_closed(params: ValveParams) -> float:
    # Spring installed length is measured between recess floors in closed position.
    poppet_floor = poppet_spring_floor_z_closed(params)
    body_floor = body_spring_floor_z(params)
    return max(0.5, body_floor - poppet_floor)


def poppet_spring_recess_center_z_closed(params: ValveParams) -> float:
    stem_len = params.body_length / 2.0
    return poppet_closed_center_z(params) + (stem_len / 2.0 - params.poppet_spring_recess_depth / 2.0)


def body_spring_recess_center_z(params: ValveParams) -> float:
    return body_spring_seat_z(params) - params.body_spring_recess_depth / 2.0


def poppet_spring_floor_z_closed(params: ValveParams) -> float:
    return poppet_tip_base_z_closed(params) - params.poppet_spring_recess_depth


def body_spring_floor_z(params: ValveParams) -> float:
    return body_spring_seat_z(params) - params.body_spring_recess_depth


def spring_length_fit_error_closed(params: ValveParams) -> float:
    # Positive means under-length spring; negative means over-length for floor-to-floor span.
    return spring_installed_length_closed(params) - (body_spring_floor_z(params) - poppet_spring_floor_z_closed(params))


def seat_contact_error_closed(params: ValveParams) -> float:
    # Zero means poppet tip apex is exactly on seat entrance plane in closed state.
    return poppet_tip_apex_z_closed(params) - body_spring_seat_z(params)


def poppet_tip_base_z_closed(params: ValveParams) -> float:
    stem_len = params.body_length / 2.0
    return poppet_closed_center_z(params) + stem_len / 2.0


def poppet_tip_apex_z_closed(params: ValveParams) -> float:
    return poppet_tip_base_z_closed(params) + params.lift_max


def poppet_right_end_z_closed(params: ValveParams) -> float:
    stem_len = params.body_length / 2.0
    return poppet_closed_center_z(params) - stem_len / 2.0


def magnet_center_z_closed(params: ValveParams) -> float:
    return poppet_right_end_z_closed(params) - params.vcm_length / 2.0


def magnet_center_z_midstroke(params: ValveParams) -> float:
    return magnet_center_z_closed(params) + params.lift_max / 2.0


def make_body(params: ValveParams) -> ShapeT:
    # Coordinate convention:
    # z=0 is the left (patient-side) end; z=body_length is the right actuator-side end.
    body = cq.Workplane("XY").circle(params.body_od / 2.0).extrude(params.body_length)

    # Optional right-end flange
    body = body.union(
        cq.Workplane("XY")
        .workplane(offset=params.body_length - params.flange_thickness)
        .circle(params.flange_od / 2.0)
        .extrude(params.flange_thickness)
    )

    # Base axial bore through full length (diameter = bore_dia)
    body = body.cut(
        cq.Workplane("XY")
        .circle(params.bore_dia / 2.0)
        .extrude(params.body_length)
    )

    # Left port section. This is only a distinct cut when port_dia differs from bore_dia.
    if abs(params.port_dia - params.bore_dia) > 1e-9:
        body = body.cut(
            cq.Workplane("XY")
            .circle(params.port_dia / 2.0)
            .extrude(params.left_port_depth)
        )

    # Stepped cavity after port: bore_dia + 2, depth 5 mm
    body = body.cut(
        cq.Workplane("XY")
        .workplane(offset=params.left_port_depth)
        .circle((params.bore_dia + 2.0) / 2.0)
        .extrude(params.gland_step_depth)
    )

    # Right counterbore for seat ring: bore_dia + 2, depth 3 mm
    body = body.cut(
        cq.Workplane("XY")
        .workplane(offset=params.body_length - params.right_counterbore_depth)
        .circle(seat_outer_r(params))
        .extrude(params.right_counterbore_depth)
    )

    # Dynamic-seal gland groove in bore wall, centered 5 mm from left end of main bore.
    # Main bore starts after left_port_depth + gland_step_depth
    bore_start = params.left_port_depth + params.gland_step_depth
    gland_center_z = bore_start + 5.0
    body = body.cut(
        cq.Workplane("XY")
        .workplane(offset=gland_center_z - params.seal_gland_width / 2.0)
        .circle((params.seal_inner_dia + 2.0 * params.seal_gland_depth) / 2.0)
        .extrude(params.seal_gland_width)
    )

    # Spring seat recess in body at the internal shoulder (z = body_length - right_counterbore_depth).
    spring_recess_z = body_spring_seat_z(params)
    spring_recess_dia = params.spring_od + 0.5
    body = body.cut(
        cq.Workplane("XY")
        .workplane(offset=spring_recess_z)
        .circle(spring_recess_dia / 2.0)
        .extrude(-params.body_spring_recess_depth)
    )

    # Side sensor port (true through-hole along X).
    body = body.cut(
        cq.Workplane("YZ")
        .workplane(offset=-params.body_od / 2.0)
        .center(0.0, params.body_length * 0.55)
        .circle(params.sensor_port_dia / 2.0)
        .extrude(params.body_od)
    )

    # Relief inlet path from body side into main bore (through-body along X).
    body = body.cut(
        cq.Workplane("YZ")
        .workplane(offset=-params.body_od / 2.0)
        .center(0.0, params.left_port_depth + 6.0)
        .circle(params.relief_seat_dia / 2.0)
        .extrude(params.body_od)
    )

    # Vent path (through-body along Y).
    body = body.cut(
        cq.Workplane("XZ")
        .workplane(offset=-params.body_od / 2.0)
        .center(0.0, params.left_port_depth + 12.0)
        .circle(params.vent_port_dia / 2.0)
        .extrude(params.body_od)
    )

    # Two mounting holes on flange for VCM/sensor bracket
    flange_z = params.body_length - params.flange_thickness / 2.0
    mount_pitch = 26.0
    hole_dia = 3.2
    for x in (-mount_pitch / 2.0, mount_pitch / 2.0):
        body = body.cut(
            cq.Workplane("XY")
            .center(x, 0.0)
            .workplane(offset=flange_z - params.flange_thickness / 2.0)
            .circle(hole_dia / 2.0)
            .extrude(params.flange_thickness + 0.2)
        )

    return body


def make_seat(params: ValveParams) -> ShapeT:
    seat_h = params.right_counterbore_depth

    r_in_l = seat_inner_r_left(params)
    r_in_r = seat_inner_r_right(params)
    r_out = seat_outer_r(params)

    # Build seat as an outer cylinder minus a conical inner bore.
    # This avoids degenerate OD topology that can appear with a single revolved ring profile.
    outer = cq.Workplane("XY").circle(r_out).extrude(seat_h)
    inner = (
        cq.Workplane("XZ")
        .polyline([
            (0.0, 0.0),
            (r_in_l, 0.0),
            (r_in_r, seat_h),
            (0.0, seat_h),
        ])
        .close()
        .revolve(360.0, (0, 0, 0), (0, 0, 1))
    )
    seat = outer.cut(inner)

    # Sealing edge chamfer at the inner entrance.
    # Some kernels fail on specific topologies; keep export robust if chamfer cannot be built.
    try:
        seat = seat.edges("|Z and <Z").chamfer(0.2)
    except Exception:
        pass
    return seat


def make_poppet(params: ValveParams) -> Tuple[ShapeT, ShapeT]:
    stem_len = params.body_length / 2.0

    stem = (
        cq.Workplane("XY")
        .circle(params.poppet_stem_dia / 2.0)
        .extrude(stem_len, both=True)
    )

    # Add a spring-seat flange at the tip-side shoulder.
    flange = (
        cq.Workplane("XY")
        .workplane(offset=stem_len / 2.0 - params.poppet_flange_thickness)
        .circle(params.poppet_flange_od / 2.0)
        .extrude(params.poppet_flange_thickness)
    )
    stem = stem.union(flange)

    # Conical tip extends beyond the stem, from z=+stem_len/2 to z=+stem_len/2+lift_max.
    tip = (
        cq.Workplane("XY")
        .workplane(offset=stem_len / 2.0)
        .circle(params.poppet_stem_dia / 2.0)
        .workplane(offset=params.lift_max)
        .circle(0.01)
        .loft(combine=True)
    )
    stem = stem.union(tip)

    # Magnet blind hole at non-sealing end.
    stem = stem.faces("<Z").workplane().hole(params.magnet_dia, depth=params.magnet_len)

    # Spring seat recess in flange near tip base (manufacturable geometry).
    spring_recess_dia = params.spring_od + 0.5
    stem = stem.cut(
        cq.Workplane("XY")
        .workplane(offset=stem_len / 2.0)
        .circle(spring_recess_dia / 2.0)
        .extrude(-params.poppet_spring_recess_depth)
    )

    # Optional separate FKM tip disk
    fkm_tip = cq.Workplane("XY").circle(params.poppet_stem_dia / 2.0).extrude(2.0)

    return stem, fkm_tip


def make_spring(params: ValveParams, length: float | None = None) -> ShapeT:
    sid = spring_id(params)
    spring_len = params.spring_free_len if length is None else max(0.5, length)
    annulus_fallback = (
        cq.Workplane("XY")
        .circle(params.spring_od / 2.0)
        .circle(sid / 2.0)
        .extrude(spring_len)
        .translate((0.0, 0.0, -spring_len / 2.0))
    )

    # Build explicit helical geometry for manufacturability and dynamic reviews.
    # Keep annulus fallback for kernels/interpreters that cannot robustly sweep coils.
    mean_radius = spring_mean_dia(params) / 2.0
    total_turns = max(2.0, float(params.spring_coils) + 2.0)
    pitch = max(params.spring_wire * 1.05, spring_len / total_turns)
    helix_height = max(params.spring_wire * 1.2, spring_len - params.spring_wire)

    try:
        helix = cq.Wire.makeHelix(
            pitch,
            helix_height,
            mean_radius,
            center=cq.Vector(0.0, 0.0, 0.0),
            dir=cq.Vector(0.0, 0.0, 1.0),
        )
        wire_profile = cq.Workplane("XZ").center(mean_radius, 0.0).circle(params.spring_wire / 2.0)
        spring = wire_profile.sweep(path=helix, isFrenet=True)
        return spring.translate((0.0, 0.0, -helix_height / 2.0))
    except Exception:
        return annulus_fallback


def make_voice_coil(params: ValveParams) -> Tuple[ShapeT, ShapeT]:
    magnet = cq.Workplane("XY").circle(params.vcm_magnet_od / 2.0).extrude(params.vcm_length)

    housing = (
        cq.Workplane("XY")
        .circle(params.vcm_coil_od / 2.0)
        .circle((params.vcm_magnet_od + 2.0) / 2.0)
        .extrude(params.vcm_length)
    )

    # Simple mounting flange and holes
    housing = housing.union(
        cq.Workplane("XY")
        .workplane(offset=params.vcm_length)
        .circle((params.vcm_coil_od + 8.0) / 2.0)
        .extrude(2.0)
    )

    for x in (-7.0, 7.0):
        housing = housing.cut(
            cq.Workplane("XY")
            .center(x, 0.0)
            .workplane(offset=params.vcm_length)
            .circle(1.6)
            .extrude(2.2)
        )

    return magnet, housing


def make_relief_valve(params: ValveParams) -> Tuple[ShapeT, ShapeT, ShapeT]:
    body = cq.Workplane("XY").box(20.0, 20.0, 10.0)

    # Through hole for flow path
    body = body.faces(">Z").workplane().hole(params.relief_seat_dia)

    # Counterbore pocket on top side
    body = body.faces(">Z").workplane().circle((params.relief_seat_dia + 4.0) / 2.0).cutBlind(-4.0)

    # Poppet and spring (simplified)
    relief_cone = (
        cq.Workplane("XY")
        .workplane(offset=2.0)
        .circle(params.relief_seat_dia / 2.0)
        .workplane(offset=3.0)
        .circle(0.2)
        .loft(combine=True)
    )
    poppet = (
        cq.Workplane("XY")
        .circle(params.relief_seat_dia / 2.0)
        .extrude(2.0)
        .union(relief_cone)
        .union(cq.Workplane("XY").workplane(offset=5.0).circle(2.0).extrude(4.0))
    )

    spring = (
        cq.Workplane("XY")
        .circle(2.5)
        .circle(1.5)
        .extrude(5.0)
    )

    return body, poppet, spring


def make_sensor_bracket() -> ShapeT:
    base = cq.Workplane("XY").box(10.0, 10.0, 2.0)
    upright = cq.Workplane("XY").workplane(offset=6.0).box(10.0, 2.0, 10.0)
    bracket = base.union(upright)

    # Hall sensor hole
    bracket = bracket.cut(
        cq.Workplane("XZ")
        .workplane(offset=0.0)
        .center(0.0, 6.0)
        .circle(1.5)
        .extrude(1.0, both=True)
    )

    # Mount holes
    for x in (-3.0, 3.0):
        bracket = bracket.cut(
            cq.Workplane("XY")
            .center(x, 0.0)
            .circle(1.1)
            .extrude(2.2)
        )

    return bracket


def make_dynamic_seal(params: ValveParams) -> ShapeT:
    # PTFE-style seal placeholder as torus marker for gland layout in concept CAD.
    major_r = seal_major_radius_installed(params)
    minor_r = params.seal_cross / 2.0
    torus = cq.Solid.makeTorus(major_r, minor_r)
    return cq.Workplane(obj=torus)


def make_assembly(params: ValveParams) -> AssemblyT:
    body = make_body(params)
    seat = make_seat(params)
    poppet, fkm_tip = make_poppet(params)
    spring = make_spring(params, length=spring_installed_length_closed(params))
    vcm_magnet, vcm_housing = make_voice_coil(params)
    relief_body, relief_poppet, relief_spring = make_relief_valve(params)
    sensor_bracket = make_sensor_bracket()
    dynamic_seal = make_dynamic_seal(params)

    asm = cq.Assembly(name="Valve_Assembly")

    asm.add(body, name="Body", color=cq.Color(0.7, 0.7, 0.75))

    seat_z = body_spring_seat_z(params)
    asm.add(
        seat,
        name="Seat",
        loc=cq.Location(cq.Vector(0, 0, seat_z)),
        color=cq.Color(0.8, 0.8, 0.8),
    )

    # Closed position: tip apex at seat entrance plane.
    poppet_z = poppet_closed_center_z(params)
    asm.add(
        poppet,
        name="Poppet",
        loc=cq.Location(cq.Vector(0, 0, poppet_z)),
        color=cq.Color(0.75, 0.75, 0.8),
    )

    asm.add(
        fkm_tip,
        name="FKM_Tip",
        # FKM tip (local z: 0..2) is placed with its bottom face at the poppet tip base.
        loc=cq.Location(cq.Vector(0, 0, poppet_tip_base_z_closed(params))),
        color=cq.Color(0.1, 0.1, 0.1),
    )

    # Spring connects poppet and body recess floors (closed state).
    poppet_spring_floor = poppet_spring_floor_z_closed(params)
    body_spring_floor = body_spring_floor_z(params)
    spring_len = spring_installed_length_closed(params)
    spring_z = (poppet_spring_floor + body_spring_floor) / 2.0
    asm.add(
        spring,
        name="Spring",
        loc=cq.Location(cq.Vector(0, 0, spring_z)),
        color=cq.Color(0.85, 0.85, 0.85),
    )

    asm.add(
        vcm_magnet,
        name="VCM_Magnet",
        # Attach magnet to poppet right end (actuator side): local z 0..vcm_length.
        loc=cq.Location(cq.Vector(0, 0, poppet_right_end_z_closed(params) - params.vcm_length)),
        color=cq.Color(0.6, 0.6, 0.65),
    )
    asm.add(
        vcm_housing,
        name="VCM_Housing",
        # Housing mounted from flange shoulder (z = body_length - flange_thickness) outward.
        loc=cq.Location(
            cq.Vector(0, 0, params.body_length - params.flange_thickness + params.vcm_length / 2.0)
        ),
        color=cq.Color(0.5, 0.5, 0.55),
    )

    asm.add(
        relief_body,
        name="Relief_Body",
        loc=cq.Location(cq.Vector(params.body_od / 2.0 + 7.0, 0, params.left_port_depth + 8.0)),
        color=cq.Color(0.8, 0.8, 0.82),
    )
    asm.add(
        relief_poppet,
        name="Relief_Poppet",
        loc=cq.Location(cq.Vector(params.body_od / 2.0 + 7.0, 0, params.left_port_depth + 8.5)),
        color=cq.Color(0.9, 0.85, 0.75),
    )
    asm.add(
        relief_spring,
        name="Relief_Spring",
        loc=cq.Location(cq.Vector(params.body_od / 2.0 + 7.0, 0, params.left_port_depth + 11.0)),
        color=cq.Color(0.9, 0.9, 0.9),
    )

    # Sensor bracket aligned with magnet center at poppet mid-stroke.
    sensor_z = magnet_center_z_midstroke(params)
    asm.add(
        sensor_bracket,
        name="Sensor_Bracket",
        loc=cq.Location(cq.Vector(0, -params.body_od / 2.0 - 4.0, sensor_z)),
        color=cq.Color(0.6, 0.65, 0.7),
    )

    # Dynamic seal placeholder placed at gland center.
    bore_start = params.left_port_depth + params.gland_step_depth
    gland_center_z = bore_start + 5.0
    asm.add(
        dynamic_seal,
        name="PTFE_Seal_Placeholder",
        loc=cq.Location(cq.Vector(0, 0, gland_center_z)),
        color=cq.Color(0.95, 0.95, 0.95),
    )

    return asm


def export_step(shape: ShapeT, path: Path) -> None:
    shape.val().exportStep(str(path))


def write_metadata(export_dir: Path, params: ValveParams) -> None:
    warnings = []
    if abs(params.relief_seat_dia - relief_required_dia_mm(params)) > 0.3:
        warnings.append("Relief seat diameter deviates from orifice-based sizing target by >0.3 mm.")
    if abs(seat_outer_r(params) - (params.bore_dia + 2.0) / 2.0) > 1e-9:
        warnings.append("Seat OD was increased above bore_dia+2 to satisfy seat-angle geometry with current thickness.")
    if spring_installed_length_closed(params) + 1e-6 < spring_solid_length_mm(params):
        warnings.append("Closed-position installed spring length is below solid height; geometry is mechanically invalid.")
    if spring_force_closed_n(params) <= 0:
        warnings.append("Closed spring force is non-positive; fail-safe opening bias is not guaranteed.")
    if abs(spring_force_closed_n(params) - params.spring_force_closed_target_n) > 0.2:
        warnings.append("Closed spring force deviates from target by >0.2 N; retune spring geometry.")
    if spring_force_open_n(params) > 0.6:
        warnings.append("Open-state spring force exceeds 0.6 N heuristic ceiling; verify actuator margin and opening dynamics.")
    if abs(seat_contact_error_closed(params)) > 1e-6:
        warnings.append("Closed-state seat contact mismatch detected: tip apex does not align with seat plane.")
    if abs(spring_length_fit_error_closed(params)) > 1e-6:
        warnings.append("Closed-state spring floor-to-floor mismatch detected: assembly spring fit is inconsistent.")
    warnings.append("Research-use model only: CAD output is concept geometry and is not a medical-device manufacturing release.")

    data: Dict[str, object] = {
        "version": "3.1",
        "date": "2026-03-19",
        "notes": [
            "Rebased to redesign baseline with 16 mm bore",
            "Poppet spring seat moved to dedicated flange geometry",
            "Dynamic seal updated to PTFE-style placeholder geometry",
            "Main spring exported as helical model when kernel supports sweep; annulus fallback retained for robustness",
            "Assembly is geometric reference, not mate-constrained dynamics",
            "Body coordinate system: left end z=0, right end z=body_length",
        ],
        "environment": {
            "python": sys.version,
            "cadquery_available": CQ_AVAILABLE,
            "cadquery_import_error": CADQUERY_IMPORT_ERROR if not CQ_AVAILABLE else "",
        },
        "warnings": warnings,
        "params": asdict(params),
        "derived": {
            "spring_id": spring_id(params),
            "spring_rate_n_per_mm": spring_rate_n_per_mm(params),
            "spring_solid_length_mm": spring_solid_length_mm(params),
            "spring_force_closed_n": spring_force_closed_n(params),
            "spring_force_open_n": spring_force_open_n(params),
            "spring_force_closed_target_n": params.spring_force_closed_target_n,
            "spring_recommended_free_len_mm": spring_recommended_free_len_mm(params),
            "spring_model": "helical_with_annulus_fallback",
            "seal_major_radius_installed": seal_major_radius_installed(params),
            "seat_inner_radius_left": seat_inner_r_left(params),
            "seat_inner_radius_right": seat_inner_r_right(params),
            "seat_outer_radius": seat_outer_r(params),
            "poppet_closed_center_z": poppet_closed_center_z(params),
            "poppet_tip_base_z_closed": poppet_tip_base_z_closed(params),
            "poppet_tip_apex_z_closed": poppet_tip_apex_z_closed(params),
            "poppet_right_end_z_closed": poppet_right_end_z_closed(params),
            "poppet_spring_recess_center_z_closed": poppet_spring_recess_center_z_closed(params),
            "body_spring_recess_center_z": body_spring_recess_center_z(params),
            "poppet_spring_floor_z_closed": poppet_spring_floor_z_closed(params),
            "body_spring_floor_z": body_spring_floor_z(params),
            "magnet_center_z_closed": magnet_center_z_closed(params),
            "magnet_center_z_midstroke": magnet_center_z_midstroke(params),
            "spring_installed_length_closed": spring_installed_length_closed(params),
            "seat_contact_error_closed": seat_contact_error_closed(params),
            "spring_length_fit_error_closed": spring_length_fit_error_closed(params),
            "relief_required_area_mm2": relief_required_area_mm2(params),
            "relief_required_dia_mm": relief_required_dia_mm(params),
            "conical_area_formula": "A(x)=pi*d_seat*x*sin(theta)",
        },
    }
    (export_dir / "valve_metadata.json").write_text(json.dumps(data, indent=2))


def main() -> int:
    validate_params(P)

    export_dir = Path(__file__).resolve().parent / "valve_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    if not CQ_AVAILABLE:
        # Auto-fallback to a known compatible interpreter unless explicitly disabled.
        # Set PHASE3_CQ_NO_AUTO_FALLBACK=1 to disable this behavior.
        fallback_py = PROJECT_ROOT / ".venv_cq313" / "Scripts" / "python.exe"
        no_auto = os.environ.get("PHASE3_CQ_NO_AUTO_FALLBACK", "0") == "1"
        same_interp = str(fallback_py).lower() == str(Path(sys.executable)).lower()
        if fallback_py.exists() and not no_auto and not same_interp:
            print(f"CadQuery import failed in current interpreter: {CADQUERY_IMPORT_ERROR}")
            print(f"Auto-fallback to compatible interpreter: {fallback_py}")
            # Replace current process with compatible interpreter so the caller gets
            # a single run without a parent process waiting on child termination.
            try:
                os.execv(str(fallback_py), [str(fallback_py), str(Path(__file__).resolve())])
            except Exception:
                # If execv is unavailable/fails, fall back to a normal child process.
                return subprocess.call([str(fallback_py), str(Path(__file__).resolve())])

        write_metadata(export_dir, P)
        (export_dir / "README_NO_CADQUERY.txt").write_text(
            "CadQuery is not installed in the active environment.\n"
            "No STEP files were generated.\n\n"
            f"Import error: {CADQUERY_IMPORT_ERROR}\n\n"
            "Likely cause: current Python version is incompatible with cadquery-ocp backend.\n"
            "Recommended: use Python 3.13 or 3.12 virtual environment for CAD export.\n"
            "Install: pip install cadquery\n"
            "Then rerun this script to export CAD geometry.\n"
            f"Example (if available): {fallback_py} {Path(__file__).resolve()}\n"
            "Set PHASE3_CQ_NO_AUTO_FALLBACK=1 to disable auto-reexec behavior.\n"
        )
        print("CadQuery unavailable. Wrote metadata and setup guidance only.")
        if CADQUERY_IMPORT_ERROR:
            print(f"Import error: {CADQUERY_IMPORT_ERROR}")
        if fallback_py.exists():
            print(f"Compatible interpreter detected: {fallback_py}")
            print("Run the script with that interpreter to generate STEP files.")
        print(f"Output: {export_dir}")
        return 0

    print("Generating adaptive expiratory valve CAD set...")

    body = make_body(P)
    seat = make_seat(P)
    poppet, fkm_tip = make_poppet(P)
    spring = make_spring(P)
    vcm_magnet, vcm_housing = make_voice_coil(P)
    relief_body, relief_poppet, relief_spring = make_relief_valve(P)
    sensor_bracket = make_sensor_bracket()
    dynamic_seal = make_dynamic_seal(P)

    export_step(body, export_dir / "Body.step")
    export_step(seat, export_dir / "Seat.step")
    export_step(poppet, export_dir / "Poppet.step")
    export_step(fkm_tip, export_dir / "FKM_Tip.step")
    export_step(spring, export_dir / "Spring.step")
    export_step(vcm_magnet, export_dir / "VCM_Magnet.step")
    export_step(vcm_housing, export_dir / "VCM_Housing.step")
    export_step(relief_body, export_dir / "Relief_Body.step")
    export_step(relief_poppet, export_dir / "Relief_Poppet.step")
    export_step(relief_spring, export_dir / "Relief_Spring.step")
    export_step(sensor_bracket, export_dir / "Sensor_Bracket.step")
    export_step(dynamic_seal, export_dir / "PTFE_Seal_Placeholder.step")

    assembly = make_assembly(P)
    assembly.save(str(export_dir / "Valve_Assembly.step"), "STEP")

    write_metadata(export_dir, P)

    print(f"Export complete: {export_dir}")
    print(f"Spring closed/open force (N): {spring_force_closed_n(P):.3f} / {spring_force_open_n(P):.3f}")
    print(f"Relief seat sizing target (mm): {relief_required_dia_mm(P):.2f}; configured: {P.relief_seat_dia:.2f}")
    print("Next: use Valve_Assembly.step for layout and component STEP files for CFD/FEA partitioning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
