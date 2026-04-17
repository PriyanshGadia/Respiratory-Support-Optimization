# Phase 3 Component Freeze Plan

Document Version: 1.0
Date: March 20, 2026
Status: Template (not yet frozen)

---

## Purpose

Define supplier-qualified component decisions required to close hardware gate blockers.

---

## Component Matrix

| Subsystem | Placeholder Status | Target Supplier/Part Number | Key Specs to Freeze | Evidence Artifact | Owner | Status |
|---|---|---|---|---|---|---|
| Main spring | CAD-derived only | TBD | k, free length, solid height, preload tolerance, fatigue life | Datasheet + tolerance stack report |  | Open |
| Dynamic seal | PTFE-style placeholder | TBD | material grade, hardness, friction, leakage, gland dimensions | Supplier guide + gland calc + endurance plan |  | Open |
| Relief valve poppet/spring | Simulation envelope only | TBD | moving mass, damping mechanism, spring rate/preload, pressure rating | Supplier BOM + bench transient test report |  | Open |
| Voice coil actuator | Geometric placeholder | TBD | force-stroke curve, resistance, thermal rise, duty cycle, driver compatibility | Datasheet + electrical/thermal test report |  | Open |
| Hall sensors (redundant) | Concept class only | TBD | linearity, noise, drift, cross-talk, mounting tolerance | Datasheet + bench calibration report |  | Open |
| Watchdog/safety switch chain | Concept class only | TBD | timeout behavior, line cutoff behavior, fault coverage | Bench timing + fault injection report |  | Open |

---

## Freeze Rules

1. No component is considered frozen without supplier part number and datasheet archived.
2. Every frozen part requires at least one linked verification artifact in `analysis/logs/phase3_evidence_pack/`.
3. Any change to a frozen part triggers a new iteration entry in docs/PHASE3_ITERATION_LOG.md.

---

## Gate Linkage

Freeze completion must support these evidence flags in analysis/logs/phase3_hardware_evidence_status.json:

- relief_supplier_components_frozen
- relief_bench_transient_verified
- seal_supplier_qualified
- actuator_characterized
- cad_release_ready

---

## Notes

- This template supports research-to-engineering transition planning only.
- Hardware gate remains closed until all linked evidence and sign-offs are complete.
