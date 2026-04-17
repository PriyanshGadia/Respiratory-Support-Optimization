# Phase 3 Original Valve - First Iteration Mechanical Dossier

This dossier is kept as a traceable record of the first iteration, including mistakes that directly informed the redesign.

Date: 2026-03-25  
Status: Research-stage engineering dossier for panel review (not manufacturing release, not clinical use)

## Problem statement

The original (single-path) adaptive expiratory valve iteration must satisfy five coupled engineering goals:

1. Provide sufficient expiratory flow modulation to reduce transient pressure spikes near cycling events.
2. Maintain a deterministic fail-safe opening tendency under adverse pressure rise.
3. Include an independent relief path sized for over-pressure venting.
4. Preserve manufacturable geometry and assembly consistency.
5. Produce traceable quantitative evidence with pass/fail outcomes.

The governing first-order flow relation is:

$$
Q = C_d A \sqrt{\frac{2\Delta p}{\rho}}
$$

where $Q$ is flow, $A$ is effective area, $\Delta p$ is pressure drop, $\rho$ is fluid density, and $C_d$ is discharge coefficient.

Baseline values used in this iteration:

- $\rho = 1.2\ \text{kg/m}^3$
- $C_d = 0.7$
- Bore diameter $d_{bore}=16\ \text{mm}$
- Maximum active lift $x_{max}=3\ \text{mm}$
- Relief set/max pressures: $30/35\ \text{cmH}_2\text{O}$
- Relief target flow: $2.29\ \text{L/s}$

Pressure unit conversion:

$$
1\ \text{cmH}_2\text{O}=98.0665\ \text{Pa}
$$

---

## Literature Survey

This first iteration uses established fluid, spring, and safety-engineering foundations:

1. Thin-orifice incompressible sizing for low Mach internal flow paths:

$$
Q=C_dA\sqrt{\frac{2\Delta p}{\rho}}
$$

2. Compression spring rate for round-wire helical spring:

$$
k = \frac{Gd_w^4}{8D_m^3N_a}
$$

where $G$ is shear modulus, $d_w$ wire diameter, $D_m$ mean coil diameter, and $N_a$ active coils.

3. Pressure force acting on exposed seat area:

$$
F_p=\Delta p\,A_{seat}
$$

4. Safety and risk control framing for ventilator subsystems from standards-aligned process workstreams:
- ISO 14971 risk management structure.
- IEC 60601-1 abnormal-operation/single-fault principles.
- ISO 80601-2-12 ventilator-specific performance and fault behavior themes.

5. Practical design-control approach from this repository: simulation gates are necessary but not sufficient for hardware release; process evidence and independent review are mandatory.

---

## Mechanism (How each component works)

This section maps each mechanical component to function in the original valve architecture.

1. Main body
- Provides axial bore and flow channel.
- Hosts right-side seat pocket, left-side flow path, vent port, and relief inlet.
- Provides mounting flange and sensor port.

2. Replaceable seat (conical seat ring)
- Forms the primary sealing interface with poppet tip.
- Seat profile controls contact line and local discharge geometry.
- Seat geometry was corrected to maintain manufacturable topology.

3. Active poppet (stem + tip + flange seat)
- Translates axially to modulate effective opening area.
- Tip closes against seat in closed state.
- Integrated flange creates a manufacturable spring seat (replacing invalid legacy stem-only shoulder concept).

4. Main compression spring
- Provides closed-state force bias.
- Supports fail-open safety posture by setting force target and restoring behavior.
- Installed between body recess and poppet recess floors.

5. Voice-coil/magnet actuation volume
- Supplies commanded motion for breath-by-breath lift modulation.
- Housing and magnet are geometrically arranged for sensor alignment and stroke control.

6. Relief valve subassembly
- Independent over-pressure vent path.
- Seat size is first-order matched to target emergency flow.
- Dynamic response depends on mass, damping, spring rate, preload, and max lift.

7. Dynamic seal placeholder (PTFE-style marker)
- Represents intended low-friction dynamic sealing direction.
- Current geometry is a placeholder for future supplier-qualified gland release.

8. Sensor bracket
- Supports position sensing architecture for disagreement detection and timing safety logic.

---

## Workflow (Findings from previous phase used in current phase + How this iteration was executed + calculations + derivations of boundary conditions + validation (report passes and failures))

### Step 0: Previous-phase findings that were explicitly carried into this iteration

The following Phase 2 and redesign-baseline findings were used as hard inputs:

1. Clinical waveform envelope (from cohort boundary summaries)
- $\Delta P_{aw,max}$ mean $6.34\ \text{cmH}_2\text{O}$, p95 $11.36\ \text{cmH}_2\text{O}$.
- $dP_{aw}/dt$ p95 $260.04\ \text{cmH}_2\text{O/s}$.
- $f_{peak}$ p95 $0.957\ \text{L/s}$.

2. Mechanical baseline correction decisions
- Bore resized to $16\ \text{mm}$ from corrected orifice math.
- Closed spring-force target fixed near $1.0\ \text{N}$ (not legacy overstated values).
- Relief seat anchored near $12.07\ \text{mm}$ equivalent diameter requirement.

3. Gate definitions used during this iteration
- Control objective gate: breath-level $\Delta P_{aw}\le5\ \text{cmH}_2\text{O}$ with pass-rate thresholding.
- Relief transient gates: response-time and flow-capacity checks.
- Safety timing gate: fail-open/fault-path latching within $\le10\ \text{ms}$.

These carried findings define the numeric envelope and pass/fail criteria used below.

### Step 1: Parameter freeze for original-valve baseline

From the original valve metadata:

- Bore diameter: $16\ \text{mm}$
- Lift max: $3\ \text{mm}$
- Spring: wire $0.58\ \text{mm}$, OD $10\ \text{mm}$, free length $6.8\ \text{mm}$, active coils $4$
- Relief seat diameter: $12.1\ \text{mm}$
- Relief pressure window: $30\to35\ \text{cmH}_2\text{O}$
- Relief target: $2.29\ \text{L/s}$

### Step 2: Core calculations (with derivations and substitutions)

#### 2.1 Bore area and pressure opening force

Seat/bore projected area:

$$
A_{bore}=\frac{\pi d_{bore}^2}{4}
$$

$$
A_{bore}=\frac{\pi(16\times10^{-3})^2}{4}=2.0106\times10^{-4}\ \text{m}^2=201.06\ \text{mm}^2
$$

Pressure opening force at $25\ \text{cmH}_2\text{O}$:

$$
\Delta p = 25\times 98.0665 = 2451.6625\ \text{Pa}
$$

$$
F_{p,25}=\Delta p\,A_{bore}=2451.6625\cdot 2.0106\times10^{-4}=0.4929\ \text{N}
$$

Interpretation: pressure-only opening tendency is about $0.49\ \text{N}$, so a closed-force target around $1.0\ \text{N}$ provides margin without excessive actuator burden.

#### 2.2 Active-path flow area at full lift

Two area models are useful in this iteration:

1. Axial curtain approximation:

$$
A_{curtain}=\pi d x
$$

$$
A_{curtain,max}=\pi(16)(3)=150.80\ \text{mm}^2
$$

2. Seat-angle-adjusted local area (metadata formula, $\theta=30^\circ$):

$$
A_{cone}=\pi d x\sin\theta
$$

$$
A_{cone,max}=\pi(16)(3)\sin 30^\circ=75.40\ \text{mm}^2
$$

Reasoning for panel:
- $A_{curtain}$ is used as the practical first-order area in previous sizing checks.
- $A_{cone}$ is a stricter local projection and indicates the need for CFD-calibrated $C_d$ and seat-flow mapping in next iteration.

#### 2.3 Spring rate and force derivation

Given:

- $G=79\times10^9\ \text{Pa}$
- $d_w=0.58\ \text{mm}=5.8\times10^{-4}\ \text{m}$
- Mean diameter $D_m=(10.0-0.58)\ \text{mm}=9.42\times10^{-3}\ \text{m}$
- Active coils $N_a=4$

Spring rate:

$$
k=\frac{Gd_w^4}{8D_m^3N_a}
$$

$$
k=\frac{79\times10^9(5.8\times10^{-4})^4}{8(9.42\times10^{-3})^3(4)}=334.223\ \text{N/m}=0.3342\ \text{N/mm}
$$

Closed installed length from metadata: $L_{inst,closed}=3.8\ \text{mm}$  
Free length: $L_f=6.8\ \text{mm}$  
Deflection at closed state:

$$
\delta_{closed}=L_f-L_{inst,closed}=3.0\ \text{mm}
$$

Closed spring force:

$$
F_{s,closed}=k\delta_{closed}=0.3342\times3.0=1.0027\ \text{N}
$$

Open-state installed length (full lift):

$$
L_{inst,open}=L_{inst,closed}+x_{max}=3.8+3.0=6.8\ \text{mm}
$$

$$
F_{s,open}=k(L_f-L_{inst,open})\approx0\ \text{N}
$$

Interpretation:
- Closed target $1.0\ \text{N}$ is achieved ($1.0027\ \text{N}$ actual).
- Near-zero open force reduces re-closing bias and actuator load at max stroke.

#### 2.4 Relief path sizing derivation

Pressure window for relief sizing:

$$
\Delta p_{relief}=(35-30)\times98.0665=490.3325\ \text{Pa}
$$

Required area for $Q_{target}=2.29\times10^{-3}\ \text{m}^3/\text{s}$:

$$
A_{req}=\frac{Q_{target}}{C_d\sqrt{2\Delta p_{relief}/\rho}}
$$

$$
A_{req}=\frac{2.29\times10^{-3}}{0.7\sqrt{2(490.3325)/1.2}}=1.14437\times10^{-4}\ \text{m}^2=114.44\ \text{mm}^2
$$

Equivalent diameter:

$$
d_{req}=\sqrt{\frac{4A_{req}}{\pi}}=12.0709\ \text{mm}
$$

Configured relief seat area ($d=12.1\ \text{mm}$):

$$
A_{seat,relief}=\frac{\pi(12.1)^2}{4}=114.99\ \text{mm}^2
$$

Area ratio:

$$
\frac{A_{seat,relief}}{A_{req}}=1.0048
$$

Interpretation: relief seat geometry matches first-order orifice requirement with about $0.48\%$ positive area margin.

#### 2.5 Geometric integrity checks (assembly consistency)

From metadata:

- $\text{seat_contact_error_closed}=0.0$
- $\text{spring_length_fit_error_closed}=0.0$

Meaning:
- Closed-state poppet tip apex aligns with seat plane.
- Spring floor-to-floor fit is internally consistent.

### Step 3: Derivation of boundary conditions

Boundary conditions are derived from intended physics, geometry limits, and observed patient-side data envelopes.

#### 3.1 Fluid governing equations

Primary valve flow:

$$
Q_v(t)=C_{d,v}A_v(x(t))\sqrt{\frac{2\Delta p(t)}{\rho}}
$$

Relief flow:

$$
Q_r(t)=C_{d,r}A_r(y(t))\sqrt{\frac{2\Delta p_r(t)}{\rho}}
$$

Total exhaust path:

$$
Q_{tot}(t)=Q_v(t)+Q_r(t)
$$

#### 3.2 Area-state relations

For active poppet lift $x$:

$$
A_v(x)=\pi d_{seat}x\quad\text{(first-order curtain model)}
$$

with kinematic bound:

$$
0\le x(t)\le x_{max}=3\ \text{mm}
$$

For relief poppet lift $y$ (simplified):

$$
A_r(y)=\pi d_{relief}y,
\quad 0\le y(t)\le y_{max}=3\ \text{mm}\ \text{(or 3.2 mm in candidate)}
$$

#### 3.3 Pressure boundary conditions

Use gauge reference at outlet:

$$
p_{out}=0\ \text{cmH}_2\text{O}
$$

Inlet/upstream boundary is patient-ventilator waveform side:

$$
p_{in}(t)=p_{aw}(t)
$$

Hence:

$$
\Delta p(t)=p_{in}(t)-p_{out}(t)
$$

First-iteration envelope values are anchored to observed data and design checks:

- Baseline waveform envelope from dataset summaries:
  - $\Delta p_{aw,max}$ mean $6.34\ \text{cmH}_2\text{O}$
  - $\Delta p_{aw,max}$ p95 $11.36\ \text{cmH}_2\text{O}$
- Relief stress window:
  - set at $30\ \text{cmH}_2\text{O}$, evaluate up to $35\ \text{cmH}_2\text{O}$

Recommended simulation tiers from this derivation:

1. Nominal tier: $\Delta p\in[2,12]\ \text{cmH}_2\text{O}$ (patient-like envelope)
2. Stress tier: $\Delta p\in[12,25]\ \text{cmH}_2\text{O}$ (high transient envelope)
3. Relief tier: $\Delta p\in[30,35]\ \text{cmH}_2\text{O}$ (over-pressure vent verification)

#### 3.4 Mechanical boundary conditions

Main poppet one-DOF model:

$$
m_v\ddot x + c_v\dot x + k_v x = F_{act}(t)-\Delta p(t)A_{bore}-F_{contact}(x)
$$

Constraints:

- Closed stop: $x=0$ (non-penetration seat contact)
- Open stop: $x=x_{max}$
- Closed-state preload condition:

$$
F_{s,closed}\approx1.0\ \text{N}
$$

Relief poppet one-DOF model:

$$
m_r\ddot y + c_r\dot y + k_r y = \Delta p_r(t)A_{seat,relief}-F_{preload,r}
$$

with bounds:

$$
0\le y(t)\le y_{max}
$$

Nominal transient parameters used in current iteration validation:

- $m_r=0.002\ \text{kg}$
- $c_r=0.08\ \text{N·s/m}$
- $k_r=120\ \text{N/m}$
- $F_{preload,r}=0.35\ \text{N}$

Candidate hardware-feasible passing set (from search):

- $m_r=0.0015\ \text{kg}$
- $c_r=0.08\ \text{N·s/m}$
- $k_r=80\ \text{N/m}$
- $F_{preload,r}=0.2\ \text{N}$
- $y_{max}=3.2\ \text{mm}$

#### 3.5 Initial conditions

For conservative transient replay:

$$
x(0)=0,\ \dot x(0)=0,\ y(0)=0,\ \dot y(0)=0
$$

and pressure history initialized from waveform-derived baseline:

$$
\Delta p(0)\in[2,5]\ \text{cmH}_2\text{O}
$$

with stress/relief runs swept over the tiered ranges above.

### Step 4: Validation report (passes and failures)

#### 4.0 Judge-facing validation matrix

| Check block | Metric / gate | Baseline result | Candidate / tuned result | Status interpretation |
|---|---|---:|---:|---|
| CAD geometry integrity | Seat contact error (closed) | $0.0$ | N/A | Pass |
| CAD geometry integrity | Spring-fit error (closed) | $0.0$ | N/A | Pass |
| Main spring target | $F_{closed}\approx1.0\ \text{N}$ | $1.0027\ \text{N}$ | N/A | Pass |
| Relief static sizing | $d_{req}=12.0709\ \text{mm}$ | $d_{cfg}=12.1\ \text{mm}$ | N/A | Pass |
| Relief transient | Response + flow gates | Fail | Pass (hardware-feasible candidate) | Baseline fail, tunable pass |
| Safety timing | All fault paths $\le10\ \text{ms}$ | Fail | Pass (candidate timing set) | Baseline fail, tunable pass |
| Controller surrogate | $\Delta P_{aw}\le5$ pass-rate target | Pass in latest surrogate run | Pass | Surrogate pass |
| Plant-coupled strict gate | Aggregate + patient-level severe criteria | Fail | Separate plant-aware benchmark can pass | Blocker in current hardware-gate path |
| Hardware prototyping gate | Multi-evidence closure | Fail | N/A | Blocked |

#### 4.1 Mechanical/CAD integrity checks

Passes:

- Closed seat contact alignment: pass ($0.0$ error).
- Closed spring floor-fit consistency: pass ($0.0$ error).
- Spring force target tracking: pass ($1.0027\ \text{N}$ vs $1.0\ \text{N}$ target).
- Relief seat first-order sizing: pass ($12.1\ \text{mm}$ configured vs $12.0709\ \text{mm}$ required).

Open issues:

- Seat OD had to be increased to satisfy seat-angle geometry; indicates geometry coupling still needs manufacturability refinement.
- CAD remains concept release only.

#### 4.2 Relief transient validation

Baseline nominal dynamic set:

- Response-time pass: fail
- Flow-capacity pass: fail
- Peak flow: $0.502\ \text{L/s}$ vs $2.29\ \text{L/s}$ target

Candidate search outcomes:

- Unconstrained best candidate: pass (but not hardware-feasible envelope).
- Hardware-feasible-envelope best candidate: pass
  - $t_{to\ target\ flow}\approx8.7\ \text{ms}$
  - response time target ($\le20\ \text{ms}$): pass
  - flow target: pass

Interpretation: geometry is adequate; dynamic parameterization is the limiting factor.

#### 4.3 Fault-response timing validation

Baseline timing simulation:

- Watchdog cutoff: $9.0\ \text{ms}$ (pass)
- Sensor disagreement latch: $11.3\ \text{ms}$ (fail)
- Pressure fault latch: $16.0\ \text{ms}$ (fail)
- Overall: fail

Candidate timing set:

- Watchdog cutoff: $6.5\ \text{ms}$ (pass)
- Sensor disagreement latch: $8.3\ \text{ms}$ (pass)
- Pressure fault latch: $9.3\ \text{ms}$ (pass)
- Overall: pass (simulation only)

Interpretation: software timing can be tuned to pass; hardware verification is still missing.

#### 4.4 Control-coupled performance status relevant to mechanical readiness

Surrogate adaptive replay:

- Cohort $\Delta P_{aw}\le5\ \text{cmH}_2\text{O}$ pass rate: 100.0% (pass)

Plant-coupled strict check (same iteration family):

- Moderate aggregate: pass
- Severe aggregate: fail in latest hardware-gate input set
- Severe worst-patient minimum: fail in latest hardware-gate input set

Hardware prototyping gate:

- Overall: fail
- Blockers include controller strict gate, missing hardware timing verification, unresolved process/compliance evidence, and external-domain-shift gate not met.

Final validation interpretation for this first iteration:

- Mechanical geometry and static sizing logic: partially validated and internally consistent.
- Dynamic relief and safety timing: tunable to pass in simulation, baseline still fails.
- Transition to hardware: blocked by evidence and strict gate closures.

---

## Conclusions (mistakes that were planned to be fixed in next iteration and future plans)

### A. Mistakes/limitations identified in this first iteration

1. Legacy geometry assumptions required corrective redesign actions (spring seat manufacturability, seat profile coupling).
2. Baseline relief transient parameters were under-capable despite correct first-order seat sizing.
3. Baseline fault timing failed two of three timing channels.
4. Simulation success was not enough to clear strict plant-level and hardware-evidence gates.
5. External domain shift remains a major transfer-risk blocker.

### B. Planned fixes for next iteration

1. Replace nominal relief dynamics with hardware-feasible parameter set, then verify on bench transient tests.
2. Freeze supplier candidates for relief spring/poppet/seal and bind models to catalog tolerances.
3. Convert timing pass from simulation-only to HIL/bench-verified evidence with traceable logs.
4. Refine seat-flow model with lift-dependent $C_d$ and CFD calibration to reconcile curtain/conical area interpretations.
5. Complete process evidence flags (CAD release readiness, actuator characterization, standards files, independent review).

### C. Future plan

1. Move from first-order static equations to calibrated transient digital twin (fluid + actuator + seal friction).
2. Execute strict patient-level plant-coupled replay on finalized controller/mechanics set.
3. Close external validation/shift mitigation with signed review artifacts.
4. Re-run hardware gate with complete evidence package before any prototyping transition.

---

## References

1. White, F. M., Fluid Mechanics, McGraw-Hill. (Orifice-flow and internal-flow fundamentals)
2. Budynas, R. G., Nisbett, J. K., Shigley’s Mechanical Engineering Design, McGraw-Hill. (Helical spring equations and design practice)
3. ISO 14971, Medical devices - Application of risk management to medical devices.
4. IEC 60601-1, Medical electrical equipment - General requirements for basic safety and essential performance.
5. ISO 80601-2-12, Particular requirements for basic safety and essential performance of critical care ventilators.
6. Project source artifacts:
   - REBOOT/analysis/phase3_cadquery_valve.py
   - REBOOT/analysis/valve_export/valve_metadata.json
   - REBOOT/analysis/logs/phase3_relief_transient_summary.json
   - REBOOT/analysis/logs/phase3_safety_fault_summary.json
   - REBOOT/analysis/logs/phase3_hardware_gate_summary.json
   - REBOOT/analysis/logs/boundary_conditions.csv
