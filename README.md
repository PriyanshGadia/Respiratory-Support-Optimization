# IPD REBOOT
## Dynamic Flow-Termination Transients in Pressure Support Ventilation

This README is written as a practical handoff: what we built, what failed, what improved, and what still blocks hardware transition.

**Project Version:** 3.2  
**Status:** Active — Phase 1 complete; Phase 2 analysis package complete; Phase 3 redesign in progress (not prototype-ready)  
**Date:** April 18, 2026

---

## What We Built and Why

This is a three-phase interdisciplinary research program designed to characterise, detect, and mitigate a class of dynamic pressure events that are currently invisible to bedside monitoring in ICU ventilators.

We built this as a practical bridge between clinical physiology, data science, and device engineering. Instead of treating waveform analysis as a purely academic task, we framed every step around one question: can we turn hard-to-see transient mechanics into something measurable, testable, and eventually safer at the bedside?

**The clinical problem:** Pressure support ventilation terminates each breath at a flow threshold rather than at a fixed time or volume. That termination event may generate a rapid mechanical transient — a sub-second pressure perturbation — that is not captured by plateau pressure, driving pressure, or any other metric in routine use. Whether it reaches the lung in a form that can cause injury is unknown. No study has measured it directly in humans using the instrumentation needed to assess its clinical significance.

**Why it is solvable now:** The CCVW-ICU dataset provides, for the first time in a publicly available form, simultaneous airway opening pressure, inspiratory flow, and validated esophageal pressure (Pes) at 200 Hz for confirmed PSV patients. Pes allows direct computation of transpulmonary pressure — the actual mechanical stress at the lung — at the exact moment of flow termination.

**Why it is novel:** No ML study has used Pes as ground truth for training. No engineering solution for PSV cycling transients has been proposed. No human characterisation of this phenomenon at sufficient bandwidth exists in the literature.

---

## Three-Phase Program

| Phase | Domain | Objective | Status |
|---|---|---|---|
| **Phase 1** | Biomedical / Clinical | Establish the medical problem statement grounded in literature | **Complete** |
| **Phase 2** | Data Science / ML / Biomechanics | Characterise transients, build Pes-grounded ML detector, validate externally | **Complete (analysis package generated)** |
| **Phase 3** | Mechanical Engineering | Redesign and safety-gated computational validation strategy | Active redesign (see docs/04_PHASE3_MECHANICAL_DESIGN.md) |

*Phase 2 may independently yield a publishable benchmark: the first PVA detection model trained and validated against Pes as physiological ground truth.*

---

## Folder Structure

```
REBOOT/
├── README.md                    ← You are here
│
├── docs/
│   └── 01_MEDICAL_PROBLEM_STATEMENT.md   ← Phase 1 complete; read first
│
├── data/
│   ├── Clinical and ventilator waveform datasets of critically ill patients in China/
│   │   ├── Waveform data/           ← P01–P07 at 200 Hz: Pao, Flow, Pes
│   │   └── Clinical data/           ← Demographics, labs, ventilator settings, outcomes
│   │
│   ├── a-temporal-dataset-for-respiratory-support-in-critically-ill-patients-1.1.0/
│   │   └── (MIMIC-IV hourly clinical data — 50,920 patients; NOT waveform data)
│   │
│   └── Processed_Dataset/           ← Original University of Canterbury data (100 Hz, no Pes,
│                                       no confirmed mode — retained for reference only;
│                                       not used in primary analysis)
│
├── analysis/                        ← Phase 2 and Phase 3 Python pipelines (implemented)
└── figures/                         ← Generated report figures and exported artifacts
```

---

## Datasets in This Project

| Dataset | N | Sampling | Key Signals | Role |
|---|---|---|---|---|
| CCVW-ICU (China) | 7 | **200 Hz** | Pao, Flow, **Pes** (Baydur-validated), confirmed PSV | **Primary development** |
| Puritan Bennett (UC Davis) | >100 | 50 Hz | Pao, Flow | External shift and controller-replay validation |
| Simulated PVI Data | 1,405 runs | Synthetic trajectories (protocol-driven) | Pao, Flow, labelled ground truth | Model stress testing and transfer benchmarking |
| MIMIC-IV Temporal | 50,920 | Hourly aggregate | Clinical variables, ventilation settings | Population context only |
| University of Canterbury | 80 | 100 Hz | Pao, Flow | Not used in primary analysis |

---

## Upload and Handoff Checklist

This repository is ready for upload with the current evidence state.

1. Confirm the latest analysis artifacts exist under analysis/logs (readiness packet, gate summary, blocker tracker, closure plan).
2. Keep docs aligned with the current gate state: redesign active, hardware transition blocked pending evidence closure.
3. Upload the repository root with history preserved so the iterative decision trail remains auditable.
4. For external review, point readers first to this README, then docs/04_PHASE3_MECHANICAL_DESIGN.md and analysis/logs/phase3_readiness_packet.md.

---

## How We Got This Working (After a Few Iterations)

- We started by locking protocol decisions before running models, because changing thresholds after seeing results makes the whole analysis less trustworthy.
- We split patient IDs up front and kept leave-one-patient-out validation strict, since leakage looked deceptively good in early dry runs.
- We treated uncertainty as a first-class output, not a side metric, because point estimates alone hid how unstable cross-patient generalization could be.

---

## Phase 3 Safety Update (March 19, 2026)

- Prior "final" Phase 3 claims were withdrawn.
- Phase 3 now runs under a formal redesign plan with explicit safety and validation gates.
- Current CAD outputs are concept geometry for analysis workflows and are not manufacturing release data.
- See `docs/04_PHASE3_MECHANICAL_DESIGN.md` for the active task checklist and corrected engineering baseline.
- Rule-based adaptive simulation runner added: `analysis/08_phase3_adaptive_rule_sim.py` (outputs in `analysis/logs/phase3_adaptive_rule_*`).
- Draft Phase 3 risk register added: `docs/05_PHASE3_RISK_REGISTER.md`.

---

## Reading Order

If you are starting fresh:

1. **This README** — project overview
2. **[docs/01_MEDICAL_PROBLEM_STATEMENT.md](docs/01_MEDICAL_PROBLEM_STATEMENT.md)** — the full clinical and scientific rationale (~8,000 words; 45–60 min)
3. **The key literature papers** listed in Section 12 of the problem statement
4. **docs/02_ANALYSIS_PROTOCOL.md** — locked analysis protocol used for reproducible execution

---

## What Changed From the Previous Version

Version 2.0 of this reboot was in a "literature-review hold state" after two fatal flaws were identified in the original project: unconfirmed ventilation mode and inadequate sampling rate.

Version 3.0 resolves both:

| Prior Fatal Flaw | Resolution |
|---|---|
| Ventilation mode unconfirmed | CCVW-ICU: confirmed PSV for all 7 patients via clinical metadata |
| 100 Hz too low for the phenomenon | CCVW-ICU: 200 Hz — confirmed from waveform files (Δt = 0.005 s) |
| No esophageal pressure | CCVW-ICU: validated Pes present for all 7 patients (Baydur test) |

Additionally, the scientific framing has been substantially sharpened. The prior version framed the project around abstract "transients in VCV." The current version frames it around a specific, measurable, mechanistically grounded phenomenon — flow-termination transients in PSV — with a defined measurement approach (Pes-based transpulmonary pressure at 200 Hz) and a multi-phase research architecture that generates publishable contributions at each stage.

---

## Lessons Learned

- I underestimated how easy it is to accidentally leak patient-specific patterns into validation; forcing strict LOPO splits was non-negotiable.
- We hit a real roadblock when simulation timing mismatched detected cycle points, so we paused pre-training instead of forcing a shaky workaround.
- I found that uncertainty-aware outputs were more honest and more useful than chasing one flashy headline metric.
