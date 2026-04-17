# Medical Problem Statement and Literature Review
## Dynamic Flow-Termination Transients in Pressure Support Ventilation: An Unsolved Problem at the Intersection of Respiratory Physiology, Machine Learning, and Mechanical Engineering

> **Author working note:** I wrote this as the anchor document I kept coming back to whenever implementation decisions drifted from the clinical question.
>
> **What this means in practice:** If a later script or model choice looks odd, this file is the reason trail for why I chose it.

> **Phase 3 status note (2026-03-19):** Mechanical implementation status is tracked in `04_PHASE3_MECHANICAL_DESIGN.md` (active redesign, safety-gated). This document remains the biomedical foundation.

**Document Version:** 4.2  
**Date:** March 14, 2026 (v4.2 papers-folder verification revision)  
**Status:** Active — foundational document for the three-phase research program; expert-reviewed and citation-updated  
**Scope:** Interdisciplinary; primary orientation is biomedical and clinical, with ML and engineering domains introduced only where they contribute uniquely to solving the clinical problem.

---

## Table of Contents

1. [The Clinical Burden: Why This Problem Matters](#1-the-clinical-burden)
2. [VILI Mechanisms: The Current Landscape](#2-vili-mechanisms)
3. [The Static Monitoring Gap: What We Are Missing](#3-the-static-monitoring-gap)
4. [Pressure Support Ventilation: Physiology and Flow-Cycling](#4-pressure-support-ventilation)
5. [Esophageal Pressure: The Gold Standard Window to Lung Stress](#5-esophageal-pressure)
6. [Patient-Ventilator Asynchrony: The Clinical Scope](#6-patient-ventilator-asynchrony)
7. [Machine Learning for PVA Detection: State of the Art and Its Limits](#7-machine-learning-for-pva-detection)
8. [The Unexplored Territory: Flow-Termination Transients](#8-the-unexplored-territory)
9. [The Novel Problem Statement](#9-the-novel-problem-statement)
10. [The Research Program: Three Phases](#10-the-research-program)
11. [Dataset Characterisation](#11-dataset-characterisation)
12. [Limitations and Risks](#12-limitations-and-risks)
13. [References](#13-references)

---

## 1. The Clinical Burden

### 1.1 The Scale of Mechanical Ventilation in the ICU

Approximately 40 percent of patients admitted to intensive care units require mechanical ventilation at some point during their stay (Esteban et al., 2002). Mechanical ventilation is not merely a supportive therapy; it is an active physiological intervention that alters pulmonary mechanics, thoracic hemodynamics, diaphragmatic function, and systemic inflammatory tone. In the setting of acute respiratory failure, it is life-sustaining. In the setting of recovering respiratory function, it carries genuine risks of harm.

The transition from full ventilatory support to spontaneous breathing — commonly called weaning — is one of the most clinically demanding phases of critical care. Prolonged weaning is associated with extended ICU stays, ventilator-associated pneumonia, ventilator-induced diaphragm dysfunction, and increased mortality. Premature extubation leads to reintubation, which independently worsens outcomes. The balance between too much and too little ventilatory support during weaning is managed largely through clinical intuition and a small number of coarse physiological metrics.

### 1.2 ARDS and Its Mortality Burden

Acute respiratory distress syndrome (ARDS) affects approximately 10 percent of all ICU admissions globally and carries a mortality rate of 35 to 46 percent despite decades of research and the widespread adoption of lung-protective ventilation (Bellani et al., 2016; Ranieri et al., 2012). The landmark ARDSNet trial (Acute Respiratory Distress Syndrome Network, 2000) demonstrated that reducing tidal volume from 12 mL/kg to 6 mL/kg predicted body weight and constraining plateau pressure below 30 cmH₂O reduced absolute mortality by approximately 9 percent. This remains one of the largest treatment effects ever demonstrated in critical care.

But that was in 2000. In 2026, despite implementation of these protective strategies, patients with ARDS continue to die at unacceptable rates. A meaningful portion of that ongoing mortality is attributable not to the underlying disease but to **ventilator-induced lung injury** — harm caused directly by the mechanical ventilator. The static monitoring framework established by ARDSNet, which was a revolution in 2000, may now represent an active ceiling on further progress.

### 1.3 The Specific Problem This Research Addresses

This project is built around a single, tightly framed clinical question: during the weaning phase of mechanical ventilation, when patients breathe with partial ventilatory support through pressure support ventilation, does the moment at which the ventilator terminates each breath generate dynamic pressure events that are injurious to lung tissue and currently invisible to bedside monitoring?

That question has not been answered in any published literature. It requires a combination of high-frequency waveform measurement, esophageal pressure monitoring, machine learning for event characterisation, and ultimately an engineering solution if the answer turns out to be affirmative. The evidence base that makes this question urgent is assembled in the sections that follow.

---

## 2. VILI Mechanisms

### 2.1 The Classical Framework

Ventilator-induced lung injury encompasses several overlapping injury pathways, each operating through a different mechanical substrate.

**Barotrauma** refers to physical rupture of alveolar tissue from excessive intrathoracic pressure. Its most visible manifestation is pneumothorax, which occurs in approximately 7 to 10 percent of mechanically ventilated ARDS patients.

**Volutrauma** refers to overdistension injury from excessive tidal volume. The distinction from barotrauma is that it is the strain — the fractional change in volume relative to resting lung volume — that drives cellular and epithelial damage, not absolute pressure per se. High strain disrupts tight junctions between alveolar epithelial cells, increases permeability, and allows protein-rich fluid to flood the air spaces.

**Atelectotrauma** refers to shear stress injury from cyclic recruitment and derecruitment of collapsed alveolar units. Each re-opening event requires a transient pressure sufficient to overcome surface tension forces at the air-liquid interface. In mechanically heterogeneous lungs — which ARDS lungs invariably are — this occurs at the boundary between aerated and non-aerated regions, generating stress concentrations far exceeding any global pressure metric.

**Biotrauma** refers to the inflammatory mediator cascade triggered by these mechanical insults. Local lung inflammation, mediated by TNF-alpha, IL-6, and IL-8 among others, can spill into the systemic circulation and contribute to multi-organ dysfunction, a major driver of death in ARDS.

### 2.2 Beyond the Classical Framework: Dynamic Stress Contributors

The classical VILI framework is well validated. But it is incomplete.

A growing body of evidence establishes that **dynamic aspects of the breath cycle** — not captured by the static snapshot metrics of tidal volume and plateau pressure — contribute independently to injury. These include:

- **Rate of pressure change** during inspiration: how fast pressure rises, not only how high it rises
- **Inspiratory and expiratory flow amplitudes:** the velocity of gas moving through diseased peripheral airways generates viscous and turbulent energy dissipation
- **Cycling frequency:** more breaths per minute means more mechanical stress cycles per unit time, even if each cycle appears individually safe
- **Asymmetric loading:** in heterogeneous lungs, the inspiratory and expiratory loading phases may stress different subpopulations of alveoli in ways that global metrics cannot reveal

One integrative framework capturing several of these factors is **mechanical power** — the rate of energy transfer from the ventilator to the respiratory system, expressed in joules per minute (Gattinoni et al., 2016). Mechanical power integrates tidal volume, respiratory rate, driving pressure, and PEEP into a single dynamic quantity and correlates with VILI across experimental and clinical datasets more robustly than any single component variable.

However, mechanical power remains a time-averaged, single-value-per-breath quantity. It cannot resolve events occurring on a timescale shorter than one breath cycle, let alone sub-second events at the precise moment of inspiratory termination. A recent review of static and dynamic contributors to VILI concluded directly: **"Current clinical practice concentrates on static inflation characteristics... does not take into account key factors shown experimentally to influence VILI."** That statement defines the conceptual gap this research program addresses.

### 2.3 Expiratory Phase Injury: A Newly Recognised Concern

Until recently, VILI research focused almost exclusively on the inspiratory phase. That asymmetry is now being corrected. A review of flow-controlled ventilation (Bialka et al., 2022) and associated experimental work in rodent models demonstrates that **passive expiration with high and unstable flow is a source of energy dissipation that may be independently injurious**. In subjects with low respiratory compliance, passive exhalation driven purely by elastic recoil can generate abrupt expiratory flow spikes — particularly at the transition from machine-supported inspiration to passive exhalation.

In pressure support ventilation, every breath ends with the ventilator abruptly withdrawing pressurised inspiratory support when a flow threshold is reached. At that moment, the respiratory system transitions from an externally assisted, pressurised state to passive recoil. If the transition is not smooth — if ventilator support withdraws faster than the patient's elastic recoil can equilibrate — a dynamic pressure perturbation is generated at the lung. That perturbation is what this research proposes to measure, characterise, and ultimately mitigate.

---

## 3. The Static Monitoring Gap

### 3.1 What Current Bedside Monitoring Captures

Clinical ventilator monitors display, at minimum:

- **Peak airway pressure (Ppeak):** the maximum pressure measured during active inspiratory flow. Sensitive to airway resistance, secretions, and bronchospasm.
- **Plateau pressure (Pplat):** measured during an inspiratory hold with airflow at zero. Reflects static respiratory system recoil — the headline safety metric since ARDSNet.
- **PEEP:** end-expiratory pressure set to prevent alveolar derecruitment.
- **Tidal volume and minute ventilation:** gross delivered volume metrics.
- **Respiratory rate:** number of machine breaths per minute.
- **Derived compliance and resistance:** computed from Ppeak and Pplat during passive controlled breaths.

### 3.2 What Standard Monitoring Structurally Cannot Capture

| Dynamic Event | When It Occurs | Why Standard Monitoring Cannot Capture It |
|---|---|---|
| Rapid pressure rise rate at breath onset | First 50 ms of inspiration | Ppeak is a scalar maximum; rate of rise is not routinely computed |
| Flow oscillations during active inspiration | Mid-inspiration | Obscured in all coarse metrics |
| Pressure transient at inspiratory flow termination | At the cycling threshold crossing | Pplat measured after airflow ceases and transient has fully decayed |
| Expiratory flow spike at exhalation onset | First 100–200 ms of exhalation | No clinical metric captures expiratory flow dynamics |
| Asynchrony-driven pressure events | During dyssynchronous breaths | Visible on waveform display only; not automatically detected or alarmed |

The most important row in this table is the third. **Plateau pressure structurally cannot record any event occurring during active flow.** Pplat is measured by imposing an end-inspiratory occlusion after the breath has concluded and all flow has stopped. Any transient that occurred during flow termination has fully decayed by the time the measurement is taken. This is not a limitation of instrument accuracy — it is a physical impossibility embedded in the measurement definition.

### 3.3 Driving Pressure: Better but Still Incomplete

Amato et al. (2015) demonstrated that driving pressure (ΔP = Pplat − PEEP) is a stronger independent predictor of ARDS mortality than tidal volume or plateau pressure alone. Driving pressure normalises tidal volume to functional lung size, making it more patient-specific.

Yet driving pressure inherits the same fundamental constraint: it is computed from an inspiratory hold during zero flow, after the active breath has ended. It captures the integral mechanical cost of inflation but cannot register transient mechanical events at phase transitions. A full characterisation of ventilator-induced stress requires a continuous, high-frequency record of airway and lung pressure across the entire breath cycle — inspiration, end-inspiration, exhalation onset, and exhalation. That requires instrumentation beyond standard monitors and an analysis framework capable of isolating clinically meaningful signals from physiological and electrical noise.

---

## 4. Pressure Support Ventilation

### 4.1 PSV Is the Primary Weaning Mode

Pressure support ventilation is the most commonly used weaning mode in ICUs worldwide. Unlike volume-controlled ventilation, which delivers a fixed tidal volume on a fixed timing schedule independent of patient effort, PSV is patient-triggered, pressure-limited, and flow-cycled (Hess, 2005). The patient initiates each breath by generating a small negative pressure or flow deflection; the ventilator senses this and immediately delivers a constant pressure boost — the "pressure support" level — throughout inspiration. The breath ends when the patient's inspiratory flow decays to a set threshold fraction of its peak value.

This makes PSV the most physiologically interactive ventilation mode in routine clinical use, and simultaneously the most vulnerable to patient-ventilator mismatch.

### 4.2 Flow-Cycling: The Critical Mechanism

The cycling rule in PSV is the mechanism central to this research program.

PSV breaths do not end at a fixed time or a fixed delivered volume. They end when inspiratory flow drops to a threshold called the **expiratory trigger sensitivity (ETS)**, expressed as a percentage of peak inspiratory flow. The default ETS in most ventilators is 25 percent of peak flow. In the confirmed dataset available for this project (CCVW-ICU), ETS values are 0.20 to 0.25 — meaning breaths terminate when flow has dropped to 20 to 25 percent of the peak value reached during that specific breath.

The consequence of flow-cycling is that the ventilator switches from delivering pressurised support to opening the expiratory valve at a moment determined by the patient's own flow curve, not by a pre-set timer. When patient effort and machine timing are well matched, this is a physiologically natural transition. When they are not well matched — which is common — the result is asynchrony.

More specifically relevant to this research: when inspiratory flow drops to the ETS threshold, the ventilator abruptly removes the pressure support boost. The respiratory system still contains an actively pressurised gas column with momentum. The patient may still have an active neural inspiration signal. The ventilator valves actuate over a finite time that is not zero. The result is a rapid pressure-flow transient at the airway opening — the event this project characterises.

### 4.3 Mathematical Instability of Flow-Cycling

Flow-cycling can exhibit unstable and highly variable behaviour across breaths (Hotchkiss et al., 2001). Because the cycling threshold is a fraction of peak flow, the same ETS percentage corresponds to different absolute flow values in different patients and across different breaths in the same patient. When patients take larger breaths, peak flow rises, and the absolute flow at which cycling occurs also rises — meaning the breath may terminate at a higher absolute flow than intended, interrupting inspiration while the patient's effort is still active. This can produce premature cycling and secondary triggering (double triggering).

This instability means flow termination is not a deterministic, predictable event — even within a single patient. It is influenced simultaneously by:

- the set ETS level,
- the patient's instantaneous neural inspiratory drive,
- the patient's respiratory mechanics (compliance, resistance, inertance),
- the breath's peak flow (which itself depends on the above),
- the shape of the flow decay curve during late inspiration,
- any concurrent expiratory muscle activity.

This inter-breath variability is precisely why machine learning applied to a Pes-grounded dataset is the appropriate analytical tool — it can characterise the phenomenon statistically rather than deterministically, and it can identify which factors most reliably predict large vs. small termination events.

### 4.4 Clinical Consequences of PSV Asynchrony

Patient-ventilator asynchrony occurs when the timing, magnitude, or duration of the ventilator's mechanical action does not match the patient's neural respiratory drive. The clinical consequences of high PVA burden are well documented:

- Increased work of breathing that may exceed the therapeutic benefit of ventilatory support
- Sleep disruption and psychological distress
- Respiratory muscle fatigue that prolongs weaning
- Longer ICU stay and duration of mechanical ventilation
- Worse clinical outcomes independent of underlying disease severity

Autopilot observational epidemiology reveals that high PVA rates — above 10 events per 100 cycles — are far more common than clinicians perceive at the bedside, and that rates above 25 percent are independently associated with worse weaning outcomes (Thille et al., 2006). Clinicians can visually identify a fraction of asynchrony events; automated detection systems reveal the full burden.

But existing automated systems focus on the beat-to-beat, breath-level asynchrony classifications — double triggering, ineffective effort, flow starvation. The sub-breath events at flow termination, occurring on a 50 to 500 millisecond timescale, are not within the scope of any current auto-detection system. The measurement infrastructure to capture them did not previously exist in a validated public dataset.

---

## 5. Esophageal Pressure

### 5.1 Why Esophageal Pressure Changes the Problem

Standard airway pressure is measured at the ventilator circuit, proximal to the endotracheal tube. It quantifies the pressure at the machine interface, not the stress delivered to the lung parenchyma. To determine the actual mechanical stress experienced by lung tissue, the chest wall contribution must be subtracted from the total respiratory system pressure.

**Esophageal pressure (Pes)** is a catheter-measured pressure recorded from the mid-esophagus, which is anatomically adjacent to the pleural space. Because the esophagus is mechanically passive in sedated ICU patients, it faithfully transmits pleural pressure changes. Pes is therefore the closest clinically available approximation of pleural pressure.

**Transpulmonary pressure** is defined as:

$$P_L = P_{aw} - P_{es}$$

where P_aw is airway opening pressure and Pes is esophageal (pleural) pressure. Transpulmonary pressure reflects the stress applied directly to lung tissue, separated from chest wall mechanics. It is the physiologically correct quantity to monitor when assessing VILI risk — and it is what current bedside protocols entirely lack.

### 5.2 Frequency Response: Does Pes Capture Fast Events?

A critical question for this project is whether esophageal balloon systems accurately transmit rapid transients. Hartford et al. (2000) studied the Ppl-Pes tissue barrier in a primate model and characterised the frequency-dependent transmission properties of the pleural-esophageal system. Based on that experimental work and the passive mechanical properties of the mediastinum and esophageal wall — low stiffness, minimal inertia — the tissue barrier is expected to transmit pressure changes accurately up to at least **10–20 Hz** without significant amplitude attenuation. The precise upper frequency limit in human patients has not been exhaustively characterised, and a conservative reading of available evidence supports this 10–20 Hz range rather than more aggressive estimates. This is mechanistically sufficient: the flow-termination transients targeted by this study operate on timescales of 50 to 500 milliseconds, corresponding to dominant frequency content below 20 Hz. At 200 Hz sampling (the CCVW-ICU rate), the Nyquist limit is 100 Hz. Events with dominant frequency content below 20 Hz will therefore be faithfully recorded with substantial margin to spare.

This is not a trivial validation. It means Pes in the CCVW-ICU dataset is not only a static index of average respiratory mechanics. It is a dynamic, high-fidelity record of the mechanical stress imposed on the lung across the breath cycle — including at the precise moment of inspiratory flow termination — within the frequency range of clinical relevance. **Caveat:** Should analysis reveal flow-termination transients with characteristic rise times below 10–20 ms — which would imply dominant spectral content above 50 Hz — the Hartford evidence would need to be revisited and the interpretation of absolute Pes values at those moments qualified accordingly. This is a stated assumption rather than a verified fact for the specific event class under study.

### 5.3 Baydur Validation

An esophageal balloon's reliability depends critically on correct anatomical positioning and inflation volume. The standard clinical validation is the Baydur occlusion test: during a voluntary airway occlusion, changes in airway pressure and esophageal pressure should be equal in magnitude (ratio approaching 1.0) if the balloon is correctly positioned at the lower esophageal level near the cardia. A ratio significantly below 1.0 indicates incomplete signal transmission and systematic underestimation of pleural pressure changes.

The CCVW-ICU dataset applied the Baydur occlusion test to all seven patients. This is exceptional. Most clinical datasets that record Pes do not report validation, and many of those that do have incomplete validation documentation. The Baydur-validated Pes in this dataset is a physiologically trustworthy signal — not an assumed one.

### 5.4 What Pes Adds That Paw Alone Cannot

| Paw Only | Paw + Pes |
|---|---|
| Net pressure at airway opening | Transpulmonary pressure: actual mechanical lung stress |
| Cannot separate lung from chest wall | Isolates lung mechanics from thoracic cage contribution |
| Cannot detect patient effort | Directly quantifies inspiratory and expiratory muscle pressure |
| Cannot distinguish circuit artefact from physiological event | Pes corroboration confirms whether a Paw event has a physiological lung correlate |
| Cannot quantify how much of a circuit transient reaches the lung | P_L = Pao − Pes directly quantifies transmission fraction |

The fifth row is the decisive one. When the analysis detects a pressure transient in Pao at flow termination, the key clinical question is not whether it exists at the airway opening — it is what fraction propagates into the lung. Simultaneous Pes at 200 Hz provides the only available measurement in this dataset capable of answering that question without additional assumptions.

---

## 6. Patient-Ventilator Asynchrony

### 6.1 Classification of Asynchrony Types

The clinical classification of patient-ventilator asynchrony has converged on six principal categories organised by the breath phase in which the mismatch occurs.

**Triggering asynchronies**:
- *Ineffective effort:* the patient attempts to trigger a breath but fails; no ventilator response occurs. Common in air-trapped patients or those with high intrinsic PEEP.
- *Auto-triggering:* the ventilator delivers a breath without any patient neural effort. Caused by cardiac oscillations, circuit condensation, or sensor drift.
- *Double triggering:* a single neural inspiratory effort produces two consecutive machine-delivered breaths because the first cycling leaves the patient with residual inspiratory drive.

**Cycling asynchronies**:
- *Premature cycling:* the machine terminates pressure support while the patient's inspiratory effort is still active. Common when ETS is set too high for the patient's flow-decay profile.
- *Delayed cycling:* the machine continues delivering pressure support after the patient's inspiratory effort has ended and the patient has begun active exhalation. Results in the patient fighting against the ventilator, often generating secondary expiratory effort that further distorts the flow waveform.

**Flow asynchrony**: the delivered inspiratory flow does not match patient demand — either too low (producing patient flow starvation with scooped pressure-time curves) or too high in modes that permit adjustment.

Of these categories, **cycling asynchronies are most directly linked to flow-termination transients**. Premature cycling withdraws pressure support against active muscle effort, creating an abrupt mechanical discontinuity. Delayed cycling forces active exhalation against continued ventilatory inflation, generating abnormal pressure and flow profiles at the moment of eventual termination. Both scenarios create conditions for anomalous pressure events that differ qualitatively from physiologically synchronous breaths.

### 6.2 Active Expiration: An Underappreciated Source of Complexity

A 2024 study by Akoumianaki et al. used gastric pressure measurement — a surrogate for expiratory muscle activity — to demonstrate that **active expiratory muscle contraction during mechanical ventilation generates waveform patterns that, without the gastric pressure signal, would be misclassified as inspiratory asynchronies**.

The clinical consequence is material: without measuring expiratory effort, a clinician or detection algorithm interpreting an abnormal flow or pressure pattern as an inspiratory trigger failure will prescribe the wrong clinical response. The cause is active exhalation against ongoing inspiratory support, not failure to trigger. The mechanism, pathophysiology, and appropriate intervention are completely different.

This matters for the present project in an immediately practical way: at the moment of inspiratory flow termination in PSV, the patient's expiratory muscles may already be contracting, particularly in patients with high metabolic rate, elevated respiratory drive, or air hunger. Any pressure perturbation occurring at that moment is the composite result of machine valve actuation and active expiratory muscle forces. Without Pes, those two components cannot be separated. With validated Pes at 200 Hz, the separation is possible.

---

## 7. Machine Learning for PVA Detection

### 7.1 The Current Landscape

Machine learning applied to ventilator waveforms has demonstrated genuinely promising performance in detecting and classifying patient-ventilator asynchrony. Across published studies, models using convolutional neural networks, recurrent architectures, random forests, and gradient-boosted classifiers have achieved sensitivity and specificity above 90 percent for common asynchrony types in within-dataset validation.

The most recent systematic reviews summarise this landscape with important caveats:

**Jiang et al. (2025),** reviewing 74 screened studies and 14 meeting inclusion criteria, found that ML models demonstrated high performance for asynchrony detection but that **only two studies had conducted external validation** on held-out institutions or cohorts. The generalisability of published models across patients, ventilators, and clinical settings is almost entirely undemonstrated.

Systematic AI-in-ICU reviews also report broad methodological heterogeneity, frequent retrospective development, and limited external validation in deployed settings (van de Sande et al., 2021). Even where classification performance appears high, physiological reference standards are often inconsistent across studies.

### 7.2 The Ground-Truth Problem

This is the most consequential methodological limitation in the field, and it is the one this research program directly addresses.

Visual clinician labelling of asynchrony events has an inter-rater agreement of approximately 60 to 80 percent for common and well-defined event types. For subtle, fast, or rare events, agreement is lower. An ML model trained against clinician visual labels inherits all labelling errors, biases, and omissions in the training set. When validated against a second set of clinician labels, the "validation" measures agreement between two imperfect human references — it does not measure clinical physiological truth.

The physiological gold standard is not clinician review. It is esophageal pressure. Pes directly records the pressure generated by the inspiratory and expiratory muscles throughout the breath cycle, independent of any machine signal. An event showing anomalous Paw or flow behaviour with no corresponding Pes change is likely a circuit artefact or a haemodynamic oscillation. An event producing a clear Pes deflection that correlates temporally with the Paw anomaly is definitively patient-driven effort.

**No published ML study targeting PSV flow-termination transients has used Pes as the primary ground truth for model training.** More broadly, no published ML study using a publicly available dataset has used Pes as the training reference for PVA detection of any type. This gap is not a failure of recognition — researchers know Pes is the standard. The gap exists because validated, high-frequency, simultaneous Pao + Flow + Pes data in a public dataset has been essentially unavailable.

**Concurrent research context — an important qualification:** An ongoing prospective trial at Leiden University Medical Center (NCT06186557), registered in 2023 and actively recruiting as of 2024, is developing a convolutional neural network-based asynchrony detection algorithm using simultaneous Pes as the training reference (target enrolment: 50 patients; planned 200–400 hours of ventilation recording). Their stated scope is standard asynchrony classification — trigger failure, delayed cycling, double triggering. Their data will not be publicly released. This confirms that the research direction of Pes-grounded ML is timely; it also means the claim that no Pes-grounded ML model exists must be qualified. The novelty of this project is more precisely characterised as: **the first open, reproducible, Pes-grounded ML study specifically targeting PSV flow-termination transients.** This project differentiates from the Leiden trial on three substantive axes: (a) the phenomenon of interest is specifically the sub-second pressure-flow transient at the ETS cycling moment — not within the Leiden protocol's scope; (b) the data used (CCVW-ICU) are already publicly available, enabling open replication; (c) the resulting event annotations, trained models, and benchmark framework will be openly released, enabling community comparison — a contribution non-public studies structurally cannot provide.

A second line of concurrent work uses surface electromyography (sEMG) in combination with Pes as a reference for automated asynchrony detection (2024). While this demonstrates that Pes-grounded automated analysis is an active area with published results, the sEMG approach targets inspiratory effort detection rather than flow-termination transient characterisation and does not address the specific physical event under study here.

The CCVW-ICU dataset, with 200 Hz Pao + Flow + Pes, confirmed PSV mode, and Baydur-validated Pes for all seven patients, is the only existing public dataset with the necessary attributes for this analysis. A model produced by this project will be among the first ML detectors grounded in physiological truth rather than clinician consensus, and the first to specifically address flow-termination events as a distinct event class with a public, reproducible methodology.

### 7.3 What Pes-Grounded Training Changes

A detection model trained against Pes-validated events differs structurally from existing models:

- It will correctly distinguish events driven by expiratory muscle activity from those driven by inspiratory asynchrony, because Pes reveals the active muscle contribution
- It will not classify circuit artefacts as clinically meaningful, because Pes will not corroborate them
- It can produce quantitative output — estimated transpulmonary pressure magnitude — rather than binary classification
- It will be generalisable to datasets without Pes, because the learned features are physiologically grounded rather than fitted to clinician labelling style

This changes the clinical utility of the resulting model. A deployed system running on Paw and Flow alone (standard availability) but trained on Pes-validated events can provide a physiologically grounded risk estimate — something no current clinical decision support system for ventilation does.

### 7.4 The Generalisability Problem and Multi-Dataset Strategy

The CCVW-ICU dataset's limitation is N = 7. No model trained on seven patients can claim generalisability on statistical grounds alone.

This project addresses that limitation with a staged multi-dataset strategy:

- **Development:** CCVW-ICU (N = 7, 200 Hz, Pes-validated, confirmed PSV) — physiological ground truth
- **Algorithmic pre-training:** Simulated Patient-Ventilator Interaction Data (1,405 labelled simulation runs) — allows systematic parameter sweeping and ground-truth-labelled pre-training before application to messy clinical signals
- **External validation:** Puritan Bennett Waveform Data (N > 100, 50 Hz, no Pes) — tests whether Pes-trained features generalise to a lower-sampling-rate clinical dataset without esophageal referencing

This multi-dataset architecture transforms a small clinical dataset into a scientifically credible research program. The CCVW-ICU data establishes the physiological signal; the simulation data establishes the parameter space; the Puritan Bennett data tests generalisability.

### 7.5 Current ML Evidence from This Program (Benchmark, Interpretability, Uncertainty)

The ML component is intentionally positioned as a rigorous translational layer between clinical physiology and engineering design, not as a replacement for direct physiological measurement.

Three concrete ML contributions are now available from the current pipeline outputs:

1. **Benchmarking against strong small-data baselines** rather than a single model.
2. **Interpretability** through permutation feature importance on Paw+Flow predictors.
3. **Uncertainty-aware prediction** using Gaussian Process regression with prediction intervals.

#### 7.5.1 Benchmark Snapshot

| Model | LOPO-CV MAE (N=222) | LOPO-CV R² | Held-out Test MAE (N=58) | Held-out Test R² |
|---|---:|---:|---:|---:|
| Mean baseline | 4.692 | -0.493 | 6.004 | -6.885 |
| Ridge baseline | 2.114 | 0.755 | 3.550 | -1.738 |
| Gaussian Process | 3.205 | 0.469 | 3.717 | -2.131 |
| XGBoost (primary Paw+Flow features) | 5.151 | -0.438 | 3.055 | -1.128 |
| XGBoost (exploratory richer features) | 5.135 | -0.408 | 3.013 | -1.132 |

Interpretation:

- Cross-patient generalisation remains difficult in this small cohort.
- Simple/regularised models can outperform complex tree ensembles in LOPO-CV.
- Held-out performance remains modest across model classes, reinforcing that a universal surrogate is not yet clinically deployable from this sample size.

This is a **negative but high-value result**: it quantifies the current limit of non-invasive ΔPL prediction with limited patient diversity.

#### 7.5.2 Feature Importance (Physiological Insight)

Permutation-importance analysis of the primary XGBoost model indicates that lung-stress prediction is most sensitive to:

- baseline airway pressure (`paw_base`),
- pressure transient magnitude (`delta_paw_max`),
- inspiratory duration (`insp_dur_s`),
- late inspiratory deceleration (`flow_decel_slope`).

This is clinically coherent and mechanically relevant: the same variables that dominate ML prediction are also those that shape the boundary-condition envelopes used for Phase 3 valve design.

#### 7.5.3 Gaussian Process Uncertainty

Gaussian Process outputs provide uncertainty intervals rather than only point predictions.

- Mean predictive standard deviation on held-out local test: **4.196 cmH2O**
- Median predictive standard deviation: **4.730 cmH2O**
- Approximate 95% interval coverage on held-out test: **84.48%**

This uncertainty scale is clinically meaningful: it indicates that model confidence is currently broad and should be treated as decision support, not autonomous control.

#### 7.5.4 Role of ML in the Interdisciplinary Stack

The ML layer therefore contributes in three ways without displacing clinical or engineering foundations:

- **Physiological interpretation:** identifies waveform correlates of elevated lung stress.
- **Risk-aware estimation:** provides uncertainty-aware predictions when Pes is unavailable.
- **Benchmark contribution:** establishes an open, reproducible baseline for Pes-grounded ΔPL prediction.

At the same time, the mechanical design phase is intentionally anchored to **directly measured** boundary conditions (ΔPaw, dPaw/dt, flow deceleration, etc.), conservatively scaled for uncertainty. This separation is deliberate and safety-oriented.

Transition to engineering relevance:

> ML findings inform monitoring and feature prioritisation for future adaptive systems, while Phase 3 mechanical design relies on empirically measured, conservatively bounded physiological envelopes from the same cohort.

---

## 8. The Unexplored Territory

### 8.1 The Specific Gap

Synthesising the preceding seven sections reveals a precisely bounded scientific gap:

**To our knowledge, based on systematic review of the published literature, no published study has simultaneously measured airway opening pressure, inspiratory flow, and esophageal pressure at a sampling frequency adequate to characterise the pressure-flow transient occurring at the moment of PSV flow-cycling in human patients — and no study has used those measurements to compute transpulmonary pressure at that moment, classify the event physiologically, correlate it with patient mechanical properties, or propose an engineering mitigation.**

This is not a trivial omission. It is a gap at the intersection of the most common weaning mode, the most mechanically consequential instant within each breath, the only instrument (Pes) that can separate machine from lung contribution, and the measurement bandwidth that preserves the relevant signal.

Prior work has characterised the consequences of cycling-off mode selection. Mojoli and Braschi (2004) reported on the effectiveness of cycling-off settings in PSV, confirming that cycling logic materially affects patient-ventilator interaction. That study did not include simultaneous esophageal pressure measurement, did not characterise the sub-breath pressure-flow event at the exact moment of flow termination, and was not framed around high-frequency transient mechanics. Hess (2005) provided a comprehensive review of pressure support ventilation physiology from a waveform perspective — confirming that PSV is patient-triggered, pressure-limited, and flow-cycled — but again without Pes-grounded transient analysis. Hotchkiss et al. (2001) described dynamic behaviour during noninvasive ventilation and highlighted breath-to-breath interaction complexity, but did not provide high-frequency empirical Pes-based characterisation of the specific flow-termination transient in human PSV. In aggregate, prior work establishes that the cycling-off mechanism is clinically important and that its parameter selection affects patient effort and comfort — but the specific physical event at the flow-termination moment, at high temporal resolution with esophageal reference, has not been characterised in the published literature. This caveat is stated with the standard "to our knowledge" qualifier: if a paper in this space exists that was not identified through the literature review conducted for this document, it should be incorporated and the novelty claims revised accordingly before analysis begins.

The unanswered questions are specific and addressable:

| Question | Clinical Significance |
|---|---|
| Does a measurable dynamic pressure event occur at PSV flow termination in humans? | Establishes existence of the phenomenon in the target population |
| What is its typical transpulmonary pressure magnitude? | Determines whether it constitutes a threat to lung tissue |
| What fraction of the Pao transient propagates to P_L = Pao − Pes? | Determines whether proximal measurement overstates or understates lung stress |
| Is magnitude correlated with ETS setting, PS level, or compliance? | Identifies clinically modifiable risk factors |
| Does it differ between asynchronous and synchronous breaths? | Links the phenomenon to established PVA literature |
| Can ML detect it automatically from Pao + Flow without Pes? | Enables real-time monitoring without esophageal catheters |
| Is cumulative transient burden associated with weaning outcome? *(Exploratory only — N = 7 precludes statistical inference; any observed pattern is hypothesis-generating, not confirmatory.)* | Identifies direction and effect-size estimates for a future adequately powered study |

### 8.2 The Engineering Opportunity Conditional on Affirmative Answers

If the answers to the first three questions are affirmative — if a real, measurable, transmissible transpulmonary pressure transient does reliably occur at PSV cycling — an engineering intervention becomes clinically justified and precisely specifiable:

**What design modification to the flow-cycling mechanism would reduce the magnitude of the inspiration-to-exhalation pressure transient without degrading patient-ventilator synchrony or increasing work of breathing?**

Engineering approaches that could address this include:

- Proportional valve actuation that tapers pressure support over 20 to 50 milliseconds rather than removing it as a step change
- Modified ETS logic that adapts the cycling threshold to the shape of the current breath's flow-decay curve rather than applying a fixed percentage
- Active impedance shaping at the expiratory valve to smooth mechanical energy transmission during cycling
- Real-time ML-driven adaptive pressure termination running on the ventilator processor

Each approach requires both a quantified characterisation of the target phenomenon (the analysis phase deliverable) and a mechanically realisable design (the engineering phase deliverable). Phase 2 provides the boundary conditions; Phase 3 provides the design.

---

## 9. The Novel Problem Statement

### 9.1 The Synthesised Problem

Current lung-protective ventilation monitoring measures static pressure states that are physiologically valid only when airflow is zero. This leaves the dynamics of the inspiratory-to-expiratory phase transition entirely uncharacterised and unmonitored. In pressure support ventilation — the dominant mode in the weaning phase of critical illness — flow-cycling termination represents the highest-rate mechanical transition in the breath cycle, occurring on a timescale of tens to hundreds of milliseconds.

Whether this transition generates transmissible lung stress events of clinical significance is unknown. No published study has adequately instrumented this question in humans. The absence of evidence is not evidence of absence; it is a measurement gap caused by the historical rarity of simultaneous high-frequency Pao, Flow, and Pes recordings with confirmed ventilation-mode metadata and validated esophageal balloon placement.

That gap is now closable. The data exist. The analytical and computational tools are mature. The research program is structured to address this question rigorously, without methodological shortcuts, and in a way that produces actionable clinical conclusions at each phase.

### 9.2 The Formal Statement of the Unsolved Problem

> *The clinical significance of dynamic pressure transients at the termination of pressure-supported breaths remains unknown, and no engineering solution has been developed or validated to mitigate them. Current bedside monitoring cannot detect these events because it relies exclusively on static or time-averaged pressure metrics measured after active flow has ceased. This project will, to our knowledge for the first time, combine validated high-fidelity human waveform data — including simultaneous esophageal pressure at 200 Hz with confirmed ventilation mode metadata and Baydur-validated Pes — with multi-domain analysis encompassing biomechanical modelling, machine learning, and deep learning, to: (a) characterise the magnitude and transpulmonary transmission of flow-termination transients in pressure support ventilation; (b) identify the patient, ventilator, and mechanical factors that modulate their magnitude; (c) build and externally validate ML detection models using esophageal pressure as the physiological ground truth rather than clinician visual labels, producing an openly available annotated benchmark; (d) explore — in this small cohort, without statistical inference — whether cumulative transient burden correlates with observed clinical trajectories; and (e) propose and computationally validate a novel mechanical design to reduce transient magnitude at its source.*

### 9.3 Novelty Summary

| What Already Exists | What This Project Adds |
|---|---|
| Dynamic VILI contributors characterised in animal and simulation models | First human characterisation in confirmed PSV patients with simultaneous validated Pes at 200 Hz |
| ML models for PVA detection validated against clinician visual labels; concurrent prospective work (Leiden NCT06186557) developing Pes-grounded algorithms for standard asynchrony classification | First open, reproducible ML benchmark specifically for PSV flow-termination event detection, with Pes as physiological ground truth — publicly released annotations and models enabling community comparison |
| Theoretical description of flow-cycling instability | Empirical quantification of flow-termination transients across a real clinical cohort |
| Akoumianaki et al. (2024) identifying active expiration as a confound | First use of Pes to decompose machine vs. patient contributions to flow-termination events breath-by-breath |
| Driving pressure and mechanical power as improved VILI metrics | Transpulmonary pressure magnitude at flow termination — a genuinely new per-breath stress marker |
| No engineering solution for PSV cycling transients | Novel mechanical design proposal with performance targets derived empirically from Phase 2 boundary conditions |

---

## 10. The Research Program

### Phase 1: Medical Literature Review and Problem Statement (This Document)

**Goal:** Establish the clinical, physiological, and methodological foundation for the entire program. Document every prior claim with a citation. Define explicitly what is known, what is unknown, and what would constitute an adequate standard of evidence. Pre-specify what positive, negative, and inconclusive findings look like so that the study can be assessed honestly regardless of outcome.

**Deliverable:** This document, in its current form, with all claims traceable to cited literature or explicitly labelled as hypotheses requiring verification.

**Status:** Complete.

---

### Phase 2: Biomechanical Waveform Analysis and Machine Learning

**Goal:** Analyse the CCVW-ICU and supplementary datasets to answer the clinical characterisation questions. Implement breath segmentation, flow-termination event detection, transpulmonary pressure computation, and ML classification using Pes as the primary validation reference.

**Sub-objectives:**

1. Characterise flow-termination events in all seven CCVW-ICU patients across the full recording duration
2. Compute transpulmonary pressure at the moment of flow termination: P_L = Pao − Pes
3. Describe the distribution of event magnitudes, timescales, and decay profiles
4. Identify breath-level predictors: ETS, PS level, PEEP, estimated compliance, estimated resistance, patient effort index
5. Develop ML/DL detection models validated against Pes-confirmed events
6. Test model generalisability on the Puritan Bennett dataset (50 Hz, no Pes) and the simulation dataset (labelled ground truth)
7. Exploratory only: examine whether patients with higher measured transient burden had different clinical trajectories (e.g., weaning duration, in-hospital outcome). N = 7 precludes statistical inference; any observed association constitutes a hypothesis and an effect-size estimate for future powered studies, not a clinical finding.

**Note on independent impact:** The ML sub-component — PSV event detection with Pes as ground truth — is independently publishable and clinically impactful as a benchmarking contribution even before the design phase, particularly if the simulation dataset enables generation of a labelled benchmark for the community.

**Deliverables:** Validated Python analysis pipeline; event catalogue; statistical results with confidence intervals; ML model performance across all datasets; boundary condition parameters for Phase 3.

---

### Phase 3: Mechanical Engineering Design

**Goal:** Use the boundary conditions from Phase 2 — measured transient magnitudes, temporal profiles, patient mechanical property distributions, and ML-identified risk factors — to specify, design, and computationally validate an engineering solution that reduces transient magnitude at the source within clinical constraints.

**Design requirements (to be refined from Phase 2 output):**
- Reduce flow-termination transpulmonary transient magnitude by a design-specified target percentage
- Preserve or improve patient-ventilator synchrony as assessed by standard metrics
- Not materially increase expiratory work of breathing
- Be realisable within the constraints of existing Dräger-class ventilator hardware architectures

**Deliverable:** Mechanical design specification, computational simulation results, and performance predictions tied explicitly to the Phase 2 boundary conditions.

---

## 11. Dataset Characterisation

### 11.1 Primary Dataset: CCVW-ICU

Confirmed present in `REBOOT/data/Clinical and ventilator waveform datasets of critically ill patients in China/`.

| Attribute | Confirmed Value |
|---|---|
| Patients | 7 (P01 to P07) |
| Ventilation mode | Pressure Support Ventilation — all patients, confirmed from clinical data |
| Ventilator | Dräger V500 |
| Signals available | Pao [cmH₂O], Flow [L/s], Pes [cmH₂O] |
| Sampling frequency | **200 Hz** (Δt = 0.005 s) — confirmed from waveform file inspection |
| Pes validation | Baydur occlusion test applied — confirmed |
| Pressure support levels | 6–12 cmH₂O |
| PEEP | 4–6 cmH₂O |
| ETS | 0.20–0.25 (20–25% of peak inspiratory flow) |
| Clinical metadata | Demographic, diagnosis, laboratory, blood gas, vital signs, ventilator settings, in-hospital outcome |
| Mortality | 2 of 7 patients deceased (P02, P07) |

**Strengths:** Confirmed PSV mode with detailed parameter metadata; validated Pes at 200 Hz; rich clinical outcomes data; single ventilator model (Dräger V500) enabling device-specific analysis.

**Limitations:** N = 7; single centre (China); single institution; no gastric pressure (expiratory muscle effort cannot be fully separated from Pes without Pga); retrospective recording.

---

### 11.2 Secondary Dataset: Puritan Bennett Waveform Data

Confirmed present in `REBOOT/data/Ventilator Waveform Data/`.

| Attribute | Expected Value |
|---|---|
| N | > 100 patients |
| Centre | UC Davis Medical Center |
| Modes | Multiple, including PSV and controlled ventilation |
| Sampling | 50 Hz |
| Pes | Not available |

**Planned role:** External validation of detection models developed on CCVW-ICU. Primary question: can Pes-trained features generalise to a dataset with lower sampling and no esophageal referencing? If yes, the resulting model can run on standard bedside hardware without hardware modification.

**Curation risk:** Although present in the repository, this dataset still requires formal curation before use in model validation: confirmed PSV-epoch identification, channel/unit harmonisation, and pre-specified inclusion/exclusion criteria.

---

### 11.3 Tertiary Dataset: Simulated Patient-Ventilator Interaction Data

Confirmed present in `REBOOT/data/Simulated data from A Model-based Approach to Generating Annotated Pressure Support Waveforms/`.

| Attribute | Expected Value |
|---|---|
| Simulation runs | 1,405 |
| Conditions | Controlled, systematically varied parameters |
| Labelling | Fully labelled patient and ventilator event timings — ground truth available |

**Planned role:** Algorithm pre-training with known ground truth; systematic parameter sweeping (ETS, compliance, resistance, PS level) that cannot be controlled experimentally in living patients; potential community benchmark dataset contribution.

**Curation risk:** Although present in the repository, simulation metadata and event labels must be mapped explicitly to the Phase 2 event taxonomy before pre-training. If mapping is incomplete, pre-training scope should be reduced and transparently documented.

---

### 11.4 Quaternary Dataset: MIMIC-IV Temporal Benchmark

Confirmed present in `REBOOT/data/a-temporal-dataset-for-respiratory-support-in-critically-ill-patients-1.1.0/`.

| Attribute | Confirmed Value |
|---|---|
| N | 50,920 ICU patients |
| Centre | Beth Israel Deaconess Medical Center, Boston |
| Data type | Hourly clinical variables — **not waveform data** |
| Temporal resolution | Hourly aggregates |

**Planned role:** Epidemiological context and population-level outcomes modelling only. Not usable for waveform or transient analysis. Can characterise the population distribution of PSV weaning practices, risk factors, and outcomes to contextualise the clinical relevance of findings from the CCVW-ICU cohort.

---

## 12. Limitations and Risks

### 12.1 Dataset Limitations

**Small sample size.** The CCVW-ICU primary dataset contains N = 7 patients. No population-level statistical inference about prevalence, incidence, or clinical association can be drawn from this cohort. All clinical findings from Phase 2 are, by definition, hypothesis-generating observations from a small case series and must be described as such in any resulting publication or communication.

**Single centre and single ventilator.** All seven patients were managed at a single institution in China on Dräger V500 ventilators. ETS settings, flow waveform characteristics, and clinical management protocols may differ systematically from other institutional contexts. Crucially, the Dräger V500's valve actuation kinematics and control algorithm contribute to the measured flow-termination transient profile; results may differ on ventilators with different hardware architectures. Generalisation to other ventilator brands is not guaranteed by the CCVW-ICU data alone.

**Absence of gastric pressure.** Without Pga measurement, inspiratory and expiratory muscle contributions to Pes cannot be fully separated. At the moment of flow termination, if expiratory muscles are already contracting, the measured Pes change reflects a composite of passive pleural pressure rebound and active expiratory effort. This confound is acknowledged throughout the analysis and constitutes a structural interpretive limitation that cannot be resolved retrospectively.

**Retrospective recording.** The CCVW-ICU waveforms were collected as part of the original clinical study, not specifically designed for this program. The clinical conditions, acuity, and timing within each patient's ventilatory course were not controlled for the purposes of this analysis.

### 12.2 Secondary Dataset Scope and Curation Risks

**Puritan Bennett waveform data are present in the repository.** The remaining risk is not acquisition but curation: identifying confirmed PSV epochs, harmonising channel names/units, documenting sampling characteristics, and defining inclusion criteria for model validation. The Analysis Protocol (Phase 2 document) must pre-specify these criteria before model training.

**Simulation data are present in the repository.** The remaining risk is metadata completeness and mapping fidelity between simulation labels and clinical event definitions used in CCVW-ICU. If simulation labels cannot be mapped cleanly to the Phase 2 event taxonomy, the pre-training role should be reduced and transparently reported.

### 12.3 Concurrent Research and the Leiden Trial

Leiden University Medical Center (NCT06186557) is conducting an active prospective trial developing Pes-grounded ML algorithms for general asynchrony detection. Their planned data collection completion is April 2025 with publication results expected 2025–2026. If their publication precedes this project's ML output, the novelty of the ML contribution narrows from "first Pes-grounded ML study" to "first open benchmark with Pes grounding focused on flow-termination transients." This remains a genuine contribution — the public availability of CCVW-ICU and any resulting annotated benchmark provides reproducibility that non-public studies cannot offer. The physical characterisation (Phase 2 biomechanics) and the engineering design (Phase 3) are entirely unaffected by Leiden publication.

**Timeline sensitivity:** If the objective is to establish priority on the ML contribution specifically, the Phase 2 analysis must be completed and submitted before estimated Leiden publication. This is a strategic consideration, not a scientific one, and is recorded here for transparency.

### 12.4 Citations Pending Verification

Verification status as of March 14, 2026:

- Verified by DOI/registry metadata: Hartford et al. (2000), Hotchkiss et al. (2001), Akoumianaki et al. (2024), Jiang et al. (2025), Hess (2005), Leiden trial NCT06186557, Mojoli and Braschi (2004), Sauer et al. (2024) (sEMG + Pes reference), Bialka et al. (2022), and Jonkman et al. (2023).
- Not verified as originally cited and therefore removed/replaced: Hoff et al. (2014), Rietveld et al. (2025).
- Remaining action: retrieve full text for all load-bearing citations (especially Hartford and Hotchkiss) to verify claim-level wording, not only bibliographic existence.

If any full-text review shows mismatch between wording and evidence, the associated passage must be revised conservatively. The core physiological arguments (P_L = Pao − Pes, flow-cycling definition, Baydur validation, ETS mechanism) remain grounded in established respiratory physiology and do not depend on any single citation.

---

## 13. References

Acute Respiratory Distress Syndrome Network. (2000). Ventilation with lower tidal volumes as compared with traditional tidal volumes for acute lung injury and the acute respiratory distress syndrome. *New England Journal of Medicine*, 342(18), 1301–1308.

Akoumianaki, E., Vaporidi, K., Stamatopoulou, C., et al. (2024). Gastric pressure monitoring unveils abnormal patient-ventilator interaction related to active expiration: a retrospective observational study. *Anesthesiology*. https://doi.org/10.1097/ALN.0000000000005071.

Amato, M. B. P., et al. (2015). Driving pressure and survival in the acute respiratory distress syndrome. *New England Journal of Medicine*, 372(8), 747–755.

Bellani, G., et al. (2016). Epidemiology, patterns of care, and mortality for patients with acute respiratory distress syndrome in intensive care units in 50 countries. *JAMA*, 315(8), 788–800.

Bialka, S., et al. (2022). Flow-controlled ventilation — a new and promising method of ventilation presented with a review of the literature. *Anaesthesiology Intensive Therapy*. https://doi.org/10.5114/ait.2022.112889.

Dreyfuss, D., and Saumon, G. (1998). Ventilator-induced lung injury: lessons from experimental studies. *American Journal of Respiratory and Critical Care Medicine*, 157(1), 294–323.

Esteban, A., et al. (2002). Characteristics and outcomes in adult patients receiving mechanical ventilation: a 28-day international study. *JAMA*, 287(3), 345–355.

Gattinoni, L., et al. (2016). The future of mechanical ventilation: lessons from the present and the past. *Critical Care*, 21(1), 183.

Hartford, C. G., van Schalkwyk, J. M., Rogers, R. M., and Turner, D. A. (2000). Primate pleuroesophageal tissue barrier frequency response and esophageal pressure waveform bandwidth in health and acute lung injury. *Anesthesiology*. https://doi.org/10.1097/00000542-200002000-00039.

Hess, D. R. (2005). Ventilator waveforms and the physiology of pressure support ventilation. *Respiratory Care*, 50(2), 166–186. https://doi.org/10.4187/respcare.05500166.

Mojoli, F., and Braschi, A. (2004). Effectiveness of cycling-off during pressure support ventilation. *Intensive Care Medicine*. https://doi.org/10.1007/s00134-004-2274-9.

Hotchkiss, J. R., Adams, A. B., Dries, D. J., and Marini, J. J. (2001). Dynamic behavior during noninvasive ventilation. *American Journal of Respiratory and Critical Care Medicine*. https://doi.org/10.1164/ajrccm.163.2.2004004.

Jiang, Z., Ma, X., Xu, Z., et al. (2025). Application progress of machine learning in patient-ventilator asynchrony during mechanical ventilation: a systematic review. *Critical Care*, 29, 75. https://doi.org/10.1186/s13054-025-05523-3.

Jonkman, A. H., et al. (2023). The oesophageal balloon for respiratory monitoring in ventilated patients: updated clinical review and practical aspects. *European Respiratory Review*, 32. https://doi.org/10.1183/16000617.0186-2022.

Leiden University Medical Center. (2023–ongoing). Machine learning algorithm for the detection of patient-ventilator asynchrony using esophageal pressure. *ClinicalTrials.gov* identifier: NCT06186557. [Actively recruiting as of 2024; results anticipated 2025–2026.]

Ranieri, V. M., et al. (2012). Acute respiratory distress syndrome: the Berlin definition. *JAMA*, 307(23), 2526–2533.

van de Sande, D., van Genderen, M. E., Huiskens, J., and Gommers, D. (2021). Moving from bytes to bedside: a systematic review on the use of artificial intelligence in the intensive care unit. *Intensive Care Medicine*. https://doi.org/10.1007/s00134-021-06446-7.

Thille, A. W., et al. (2006). Patient-ventilator asynchrony during assisted mechanical ventilation. *Intensive Care Medicine*, 32(10), 1515–1522.

Sauer, J., et al. (2024). Automated characterization of patient-ventilator interaction using surface electromyography. *Annals of Intensive Care*, 14, 32. https://doi.org/10.1186/s13613-024-01259-5.

---

*End of Medical Problem Statement — Version 4.2*

*Change log v4.1 → v4.2 (March 14, 2026):*
*— Cross-verified citations against newly added local papers in REBOOT/papers*
*— Resolved final placeholder reference: sEMG + Pes paper replaced with full Sauer et al. (2024) citation and DOI*
*— Resolved remaining DOI placeholders for Bialka (2022) and Jonkman (2023) from local papers*
*— Removed duplicate Phase 2 sub-objective line (Section 10)*
*— Removed duplicate subsection heading in Section 12.2*

*Change log v4.0 → v4.1 (March 14, 2026):*
*— Verified citations by DOI/registry: Hartford 2000, Hotchkiss 2001, Akoumianaki 2024, Jiang 2025, Hess 2005, Leiden NCT06186557, Mojoli 2004*
*— Replaced uncertain prior-work citation Hoff 2014 with verified cycling-off study Mojoli and Braschi 2004*
*— Replaced unverified Rietveld 2025 review citation with verified AI-in-ICU systematic review van de Sande 2021*
*— Updated Section 11.2 and 11.3 status from anticipated to confirmed-present datasets in repository*
*— Converted dataset "contingency" wording to curation-and-eligibility risks*
*— Updated citation verification subsection with verified/removed-replaced status list*

*Next document: Phase 2 Analysis Protocol (`02_ANALYSIS_PROTOCOL.md`, v1.1) — locked and ready for execution.*
