# =============================================================================
# config.py  —  Phase 2 Analysis Configuration
# Version: 1.0  |  2026-03-14
# All paths and protocol-locked thresholds in one place.
# Never hard-code values below; import from here everywhere.
# =============================================================================

import os

# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # REBOOT/
DATA_DIR        = os.path.join(_BASE, "data")
ANALYSIS_DIR    = os.path.join(_BASE, "analysis")
LOGS_DIR        = os.path.join(ANALYSIS_DIR, "logs")
FIGURES_DIR     = os.path.join(_BASE, "figures")
DOCS_DIR        = os.path.join(_BASE, "docs")
SPLITS_DIR      = os.path.join(ANALYSIS_DIR, "splits")

# ---------------------------------------------------------------------------
# Dataset paths
# ---------------------------------------------------------------------------
# Primary (CCVW-ICU — Chinese clinical PSV+Pes, 200 Hz, N=7)
CCVW_WAVEFORM_DIR  = os.path.join(DATA_DIR, "Clinical and ventilator waveform datasets of critically ill patients in China", "Waveform data")
CCVW_CLINICAL_DIR  = os.path.join(DATA_DIR, "Clinical and ventilator waveform datasets of critically ill patients in China", "Clinical data")
CCVW_MV_FILE       = os.path.join(CCVW_CLINICAL_DIR, "Mechanical Ventilation.xlsx")

# Simulation (PSV, 1405 runs, ~100 Hz)
SIM_BASE           = os.path.join(DATA_DIR, "Simulated data from A Model-based Approach to Generating Annotated Pressure Support Waveforms")
SIM_WAVEFORMS_DIR  = os.path.join(SIM_BASE, "Waveforms")
SIM_MECH_REF_DIR   = os.path.join(SIM_BASE, "Mechanical Reference")
SIM_PAT_REF_DIR    = os.path.join(SIM_BASE, "Patient Reference")
SIM_SETTINGS_FILE  = os.path.join(SIM_BASE, "Simulation settings", "settings.csv")

# External validation — Puritan Bennett / Ventilator Waveform Data (~50 Hz, no Pes)
VWD_DIR            = os.path.join(DATA_DIR, "Ventilator Waveform Data")

# CPAP dataset — University of Canterbury (100 Hz, no Pes, no PSV)
CPAP_DIR           = os.path.join(DATA_DIR, "Processed_Dataset")

# ---------------------------------------------------------------------------
# Signal conventions  (do NOT change post-lock)
# ---------------------------------------------------------------------------
CCVW_PATIENT_COL   = "Patient ID"
CCVW_TIME_COL      = "Time [s]"
CCVW_FLOW_COL      = "Flow [l/s]"
CCVW_PAW_COL       = "Pao [cm H2O]"
CCVW_PES_COL       = "Pes [cm H2O]"
CCVW_FS            = 200        # Hz — declared sampling rate

SIM_TIME_COL       = "time"
SIM_PAW_COL        = "paw"
SIM_FLOW_COL       = "flow"
SIM_VOL_COL        = "vol"
SIM_PMUS_COL       = "pmus"    # muscle pressure — Pes analog in simulation
SIM_MECH_TIM_COL   = "tim"     # ventilator trigger time
SIM_MECH_TEM_COL   = "tem"     # ventilator cycle time = t_cycle ground truth
SIM_PAT_TIP_COL    = "tip"
SIM_PAT_TEP_COL    = "tep"
SIM_FS_TOL         = 0.05       # +/-5% tolerance on declared fs

VWD_FS_DECLARED    = 50         # Hz (approximate; verified per file)
VWD_COL_FLOW_IDX   = 0         # first data column = Flow [L/min]
VWD_COL_PAW_IDX    = 1         # second data column = Paw [cmH2O]
VWD_FLOW_SCALE     = 1.0 / 60  # L/min → L/s

CPAP_TIME_COL      = "Time [s]"
CPAP_FLOW_COL      = "Flow [L/s]"
CPAP_PAW_COL       = "Pressure [cmH2O]"
CPAP_FS            = 100

# ---------------------------------------------------------------------------
# Dataset split: local vs global
# ---------------------------------------------------------------------------
LOCAL_TRAIN_PATIENTS = ["P01", "P02", "P03", "P04", "P05"]
LOCAL_TEST_PATIENTS  = ["P06", "P07"]
# Global train = simulation dataset
# Global test  = VWD dataset

# ---------------------------------------------------------------------------
# Protocol-locked QC thresholds  (Section 4  of 02_ANALYSIS_PROTOCOL.md)
# ---------------------------------------------------------------------------
FS_TOLERANCE        = 0.05     # +/-5% on declared fs
MAX_MISSINGNESS     = 0.05     # <5% per channel
FLATLINE_MAX_S      = 2.0      # >2.0s flatline triggers file exclusion
HAMPEL_WINDOW       = 11       # samples (odd)
HAMPEL_THRESHOLD    = 6.0      # MAD multiplier
HAMPEL_BREATH_FRAC  = 0.05     # >5% flagged → low_quality
FLATLINE_BREATH_MS  = 200      # >200ms flatline in breath → low_quality

FLOW_LOWPASS_HZ     = 12.0     # Section 4.2 filter cutoffs
PRES_LOWPASS_HZ     = 20.0

# ---------------------------------------------------------------------------
# Protocol-locked segmentation thresholds  (Section 5)
# ---------------------------------------------------------------------------
FLOW_EPS            = 0.02     # L/s — zero-crossing hysteresis
INSP_SUSTAIN_MS     = 40       # ms — must stay above eps to confirm onset
INSP_DUR_MIN_S      = 0.20     # s
INSP_DUR_MAX_S      = 4.0      # s
FLOW_PEAK_MIN       = 0.05     # L/s — minimum F_peak
PAW_SLOPE_FALLBACK  = 1.5      # cmH2O/s — fallback pressure slope threshold

# ---------------------------------------------------------------------------
# Protocol-locked event detection thresholds  (Section 6)
# ---------------------------------------------------------------------------
ETS_DEFAULT         = 0.25     # provisional when metadata absent
ETS_SENSITIVITY     = [0.15, 0.20, 0.25, 0.30, 0.35]  # sensitivity range
TCYCLE_CONFIRM_N    = 3        # consecutive samples below F_ETS required
PRE_WIN_MS          = 150      # ms — pre-window for baseline
POST_WIN_MS         = 350      # ms — post-window for event

# ---------------------------------------------------------------------------
# Protocol-locked PL computation thresholds  (Section 7)
# ---------------------------------------------------------------------------
TF_PAW_GUARD        = 0.2      # cmH2O — minimum Delta Paw to compute TF
TF_WINSORIZE_PCT    = 99       # percentile for summary winsorization

# ---------------------------------------------------------------------------
# Protocol-locked ML event label thresholds  (Section 6.4)
# ---------------------------------------------------------------------------
EVENT_LABEL_DPL_MIN   = 1.0    # cmH2O
EVENT_LABEL_SLOPE_MIN = 8.0    # cmH2O/s
EVENT_PEAK_MAX_MS     = 200    # ms post t_cycle
# Sensitivity thresholds
EVENT_DPL_SENS        = [0.75, 1.0, 1.25]
EVENT_SLOPE_SENS      = [6.0, 8.0, 10.0]

# ---------------------------------------------------------------------------
# ML input window  (Section 9.2)
# ---------------------------------------------------------------------------
ML_WIN_PRE_MS       = 500      # ms before t_cycle
ML_WIN_POST_MS      = 500      # ms after t_cycle
ML_TARGET_FS        = 100      # Hz — resampling target for deep models
ML_INPUT_CHANNELS   = ["paw", "flow"]  # Pes NOT used as ML input

# ---------------------------------------------------------------------------
# XGBoost hyperparameter grid  (Appendix A.3)
# ---------------------------------------------------------------------------
XGB_PARAM_GRID = {
    "max_depth":        [3, 5, 7],
    "learning_rate":    [0.03, 0.1],
    "n_estimators":     [200, 500],
    "subsample":        [0.7, 1.0],
    "colsample_bytree": [0.8],
    "min_child_weight": [1, 3],
    "objective":        ["reg:squarederror"],  # regression primary
}

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Simulation pre-training audit thresholds  (Appendix C)
# ---------------------------------------------------------------------------
SIM_AUDIT_N                = 200   # breaths to sample
SIM_TCYCLE_MISMATCH_MS     = 20    # ms
SIM_MISMATCH_RATE_THRESHOLD = 0.10  # 10%

# ---------------------------------------------------------------------------
# Boundary condition derivation  (for Phase 3 mechanical design)
# ---------------------------------------------------------------------------
BC_PERCENTILES = [5, 10, 25, 50, 75, 90, 95, 99]

# Conservative mechanical-design multipliers (engineering heuristics).
# These are explicit safety margins, not statistical guarantees of population extrema.
DESIGN_SAFETY_FACTOR = 2.0
FILTER_ATTENUATION_MARGIN = 0.20
MIN_EXCLUSION_MARGIN = 0.05
COHORT_Z = 1.96

# ---------------------------------------------------------------------------
# ML feature allowlist  (Protocol §9.2 — Paw + Flow only, no Pes-derived quantities)
# ---------------------------------------------------------------------------
# ANY feature added here must be computable from Paw and Flow alone.
# Pes-derived features (pes_base, pl_base, pl_at_cycle, delta_pl_max, dPL_dt_max, tf)
# are computed for descriptive statistics only and must NOT appear in this list.
PAW_FLOW_FEATURES = [
    # Kinematic (Flow)
    "f_peak", "insp_dur_s", "exp_dur_s",
    # Pressure baseline (Paw)
    "paw_base",
    # Event magnitudes (Paw)
    "delta_paw_max", "dPaw_dt_max",
    # Cycling metadata (no Pes required)
    "ets_frac", "ets_defaulted_flag",
    # Derived waveform-shape features (Paw + Flow)
    "flow_decel_slope", "paw_ratio_peak_end",
    "flow_integral_abs", "flow_rise_time_ms",
    "paw_spectral_ratio",
    # Clinical ventilator settings (not Pes-derived)
    "ps", "peep", "fio2",
]

# ---------------------------------------------------------------------------
# VWD processing limit  (None = all files per protocol; set integer to subsample)
# ---------------------------------------------------------------------------
VWD_MAX_FILES = None   # Protocol §8.2: entire VWD dataset must be used
