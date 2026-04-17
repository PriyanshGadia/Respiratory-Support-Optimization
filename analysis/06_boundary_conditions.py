#!/usr/bin/env python
# =============================================================================
# 06_boundary_conditions.py  —  Step 10: Derive mechanical design BCs
# Version: 1.0  |  2026-03-14
#
# Computes all physiological and mechanical boundary conditions from the
# combined validated CCVW dataset results.  These values are the direct
# inputs for Phase 3 mechanical valve/cycling mechanism design.
#
# Run: python REBOOT/analysis/06_boundary_conditions.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import numpy as np
import pandas as pd

import config as C

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("06_boundary_conditions")

os.makedirs(C.LOGS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Load combined feature data
# ---------------------------------------------------------------------------

def load_combined_features():
    path = os.path.join(C.LOGS_DIR, "combined_predictions.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found. Run 05_combined_test.py first.")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Boundary condition computation
# ---------------------------------------------------------------------------

PCTILES = C.BC_PERCENTILES

def _stat_row(name: str, arr: np.ndarray, unit: str = "") -> dict:
    """Compute descriptive statistics for one BC variable."""
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"name": name, "unit": unit, "n": 0}
    row = {"name": name, "unit": unit, "n": int(len(arr)),
           "mean": float(np.mean(arr)), "std": float(np.std(arr)),
           "min": float(np.min(arr)), "max": float(np.max(arr))}
    for p in PCTILES:
        row[f"p{p}"] = float(np.percentile(arr, p))
    return row


def derive_boundary_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all boundary condition variables relevant for Phase 3.

    Returns DataFrame of BC rows — one per variable.
    """
    bc_rows = []

    # --- Pressure transients ---
    bc_rows.append(_stat_row(
        "delta_paw_max", df["delta_paw_max"].values, "cmH2O",
    ))
    bc_rows.append(_stat_row(
        "delta_pl_max", df["delta_pl_max"].values, "cmH2O",
    ))

    # --- Rising/falling rate ---
    bc_rows.append(_stat_row(
        "dPaw_dt_max", df["dPaw_dt_max"].values, "cmH2O/s",
    ))
    bc_rows.append(_stat_row(
        "dPL_dt_max", df["dPL_dt_max"].values, "cmH2O/s",
    ))

    # --- Flow deceleration at cycling ---
    if "flow_decel_slope" in df.columns:
        bc_rows.append(_stat_row(
            "flow_decel_slope", df["flow_decel_slope"].values, "L/s^2",
        ))

    # --- Transmission fraction ---
    if "tf" in df.columns:
        tf_vals = df["tf"].values
        tf_vals = tf_vals[(tf_vals > 0) & (tf_vals < 5)]   # physiological range only
        bc_rows.append(_stat_row("transmission_fraction", tf_vals, "dimensionless"))

    # --- ETS fraction at cycling ---
    bc_rows.append(_stat_row("ets_frac", df["ets_frac"].values, "fraction"))

    # --- Peak inspiratory flow ---
    bc_rows.append(_stat_row("f_peak", df["f_peak"].values, "L/s"))

    # --- Inspiration / expiration durations ---
    bc_rows.append(_stat_row("insp_dur_s", df["insp_dur_s"].values, "s"))
    bc_rows.append(_stat_row("exp_dur_s",  df["exp_dur_s"].values,  "s"))

    # --- Baseline pressures ---
    bc_rows.append(_stat_row("paw_base", df["paw_base"].values, "cmH2O"))
    bc_rows.append(_stat_row("pl_base",  df["pl_base"].values,  "cmH2O"))

    # --- Clinical settings ---
    if "ps" in df.columns:
        bc_rows.append(_stat_row("ps_level", df["ps"].values, "cmH2O"))
    if "peep" in df.columns:
        bc_rows.append(_stat_row("peep_level", df["peep"].values, "cmH2O"))

    # --- Predicted delta_pl by local model ---
    if "local_pred" in df.columns:
        bc_rows.append(_stat_row("predicted_delta_pl_max_local",
                                  df["local_pred"].values, "cmH2O"))

    # --- Event positive rate ---
    if "event_positive" in df.columns:
        ep = df["event_positive"].dropna()
        if len(ep) > 0:
            bc_rows.append({
                "name": "event_positive_rate",
                "unit": "fraction",
                "n": int(len(ep)),
                "mean": float(ep.mean()),
                "std": float(ep.std()),
                "min": float(ep.min()),
                "max": float(ep.max()),
            })

    return pd.DataFrame(bc_rows)


# ---------------------------------------------------------------------------
# Per-patient BC summary
# ---------------------------------------------------------------------------

def per_patient_bc(df: pd.DataFrame) -> pd.DataFrame:
    """Compute key BC statistics per patient."""
    rows = []
    target_vars = ["delta_paw_max", "delta_pl_max", "dPaw_dt_max",
                   "dPL_dt_max", "flow_decel_slope", "tf",
                   "f_peak", "insp_dur_s", "exp_dur_s"]

    for pid, grp in df.groupby("patient_id"):
        row = {"patient_id": pid, "n_breaths": len(grp)}
        for var in target_vars:
            if var not in grp.columns:
                continue
            vals = grp[var].dropna().values
            if len(vals):
                row[f"{var}_mean"]   = float(np.mean(vals))
                row[f"{var}_p95"]    = float(np.percentile(vals, 95))
                row[f"{var}_median"] = float(np.median(vals))
        if "event_positive" in grp.columns:
            ep = grp["event_positive"].dropna()
            row["event_rate"] = float(ep.mean()) if len(ep) > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Condition buckets for mechanical design specs
# ---------------------------------------------------------------------------

def compute_uncertainty_profile(pp_bc_df: pd.DataFrame,
                                exclusion_df: pd.DataFrame | None = None) -> dict:
    """
    Build a conservative uncertainty multiplier for Phase-3 mechanical design.
    Multiplier components:
      1) cohort-size inflation (small N)
      2) filter-attenuation margin
      3) exclusion-rate margin
    Final multiplier is clamped at least to DESIGN_SAFETY_FACTOR.
    """
    n_patients = int(pp_bc_df["patient_id"].nunique()) if (pp_bc_df is not None and not pp_bc_df.empty and "patient_id" in pp_bc_df.columns) else 0
    n_patients_eff = max(n_patients, 1)

    cohort_multiplier = 1.0 + (C.COHORT_Z / np.sqrt(n_patients_eff))
    filter_multiplier = 1.0 + float(C.FILTER_ATTENUATION_MARGIN)

    exclusion_rate = np.nan
    exclusion_multiplier = 1.0 + float(C.MIN_EXCLUSION_MARGIN)
    if exclusion_df is not None and not exclusion_df.empty and {"n_segmented", "n_valid"}.issubset(exclusion_df.columns):
        n_segmented = float(exclusion_df["n_segmented"].sum())
        n_valid = float(exclusion_df["n_valid"].sum())
        if n_segmented > 0:
            exclusion_rate = max(0.0, 1.0 - (n_valid / n_segmented))
            exclusion_multiplier = 1.0 + max(float(C.MIN_EXCLUSION_MARGIN), float(exclusion_rate))

    compounded = cohort_multiplier * filter_multiplier * exclusion_multiplier
    final_multiplier = max(float(C.DESIGN_SAFETY_FACTOR), float(compounded))

    return {
        "n_patients": n_patients,
        "cohort_multiplier": float(cohort_multiplier),
        "filter_multiplier": float(filter_multiplier),
        "exclusion_rate": float(exclusion_rate) if np.isfinite(exclusion_rate) else np.nan,
        "exclusion_multiplier": float(exclusion_multiplier),
        "compounded_multiplier": float(compounded),
        "design_safety_factor_floor": float(C.DESIGN_SAFETY_FACTOR),
        "final_multiplier": float(final_multiplier),
    }


def simulation_sensitivity_analysis() -> dict:
    """
    Stress-test envelope variables on the simulation feature bank.
    This does not claim direct clinical equivalence; it provides conservative
    trend-aware bounds over a wider parameter space.
    """
    path = os.path.join(C.LOGS_DIR, "simulation_features.csv")
    if not os.path.exists(path):
        return {}

    sim_df = pd.read_csv(path)
    if sim_df.empty:
        return {}

    envelope_vars = ["delta_paw_max", "dPaw_dt_max", "f_peak", "insp_dur_s", "flow_decel_slope"]
    envelope_vars = [c for c in envelope_vars if c in sim_df.columns]
    if not envelope_vars:
        return {}

    global_extremes = {}
    for col in envelope_vars:
        vals = sim_df[col].dropna().values.astype(float)
        if len(vals) == 0:
            continue
        global_extremes[col] = {
            "p5": float(np.percentile(vals, 5)),
            "p95": float(np.percentile(vals, 95)),
            "p99": float(np.percentile(vals, 99)),
            "max": float(np.max(vals)),
            "min": float(np.min(vals)),
        }

    setting_slices = []
    for setting_col in ["ps", "peep", "ets_frac"]:
        if setting_col not in sim_df.columns:
            continue
        s = sim_df[setting_col].dropna().astype(float)
        if len(s) < 30:
            continue
        q10, q90 = np.percentile(s.values, [10, 90])
        low_mask = sim_df[setting_col] <= q10
        high_mask = sim_df[setting_col] >= q90
        for var in envelope_vars:
            low_vals = sim_df.loc[low_mask, var].dropna().astype(float).values
            high_vals = sim_df.loc[high_mask, var].dropna().astype(float).values
            if len(low_vals) == 0 or len(high_vals) == 0:
                continue
            setting_slices.append({
                "setting": setting_col,
                "q10": float(q10),
                "q90": float(q90),
                "variable": var,
                "mean_low_q10": float(np.mean(low_vals)),
                "mean_high_q90": float(np.mean(high_vals)),
                "p99_high_q90": float(np.percentile(high_vals, 99)),
                "max_high_q90": float(np.max(high_vals)),
            })

    pd.DataFrame(setting_slices).to_csv(
        os.path.join(C.LOGS_DIR, "simulation_sensitivity_slices.csv"), index=False
    )

    return {
        "n_breaths": int(len(sim_df)),
        "global_extremes": global_extremes,
        "setting_slices": setting_slices,
    }


def design_envelopes(bc_df: pd.DataFrame,
                     uncertainty: dict,
                     sim_sensitivity: dict) -> dict:
    """
    Extract min/max design-spec envelopes directly usable by mechanical engineers:
      - 'normal_range': p5–p95
      - 'operational_max': p99
      - 'worst_case': absolute max
    """
    envelopes = {}
    key_vars = ["delta_paw_max", "delta_pl_max", "dPaw_dt_max", "f_peak", "insp_dur_s", "flow_decel_slope"]
    u_mult = float(uncertainty.get("final_multiplier", C.DESIGN_SAFETY_FACTOR))
    sim_ext = sim_sensitivity.get("global_extremes", {}) if sim_sensitivity else {}

    for _, row in bc_df.iterrows():
        name = row["name"]
        if name not in key_vars:
            continue
        if name == "flow_decel_slope":
            worst_case = row.get("min", np.nan)  # most negative (fastest decel)
            operational = row.get("p5", np.nan)
            conservative_wc = (float(worst_case) * u_mult) if np.isfinite(worst_case) else np.nan
            sim_wc = sim_ext[name].get("min", np.nan) if name in sim_ext else np.nan
            if np.isfinite(conservative_wc) and np.isfinite(sim_wc):
                recommended_case = min(conservative_wc, sim_wc)
            elif np.isfinite(conservative_wc):
                recommended_case = conservative_wc
            else:
                recommended_case = sim_wc
        else:
            worst_case = row.get("max", np.nan)
            operational = row.get("p99", row.get("max", np.nan))
            conservative_wc = (float(worst_case) * u_mult) if np.isfinite(worst_case) else np.nan
            sim_wc = sim_ext[name].get("max", np.nan) if name in sim_ext else np.nan
            recommended_case = np.nanmax([conservative_wc, sim_wc]) if np.isfinite(conservative_wc) or np.isfinite(sim_wc) else np.nan

        envelopes[name] = {
            "unit":           row.get("unit", ""),
            "normal_range":   [row.get("p5", np.nan), row.get("p95", np.nan)],
            "operational_max": operational,
            "worst_case":     worst_case,
            "typical":        row.get("p50", np.nan),
            "conservative_worst_case": conservative_wc,
            "simulated_worst_case": sim_wc,
            "recommended_design_case": recommended_case,
        }

    return envelopes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Step 10: Boundary Condition Derivation")

    df = load_combined_features()
    log.info("Loaded combined features: %d breaths, %d patients",
             len(df), df["patient_id"].nunique())

    exclusion_path = os.path.join(C.LOGS_DIR, "breath_exclusion_summary.csv")
    exclusion_df = pd.read_csv(exclusion_path) if os.path.exists(exclusion_path) else pd.DataFrame()

    # Cohort-level BCs
    bc_df = derive_boundary_conditions(df)
    bc_path = os.path.join(C.LOGS_DIR, "boundary_conditions.csv")
    bc_df.to_csv(bc_path, index=False)
    log.info("Boundary conditions table → %s", bc_path)

    # Per-patient BCs
    pp_bc = per_patient_bc(df)
    pp_bc.to_csv(os.path.join(C.LOGS_DIR, "boundary_conditions_per_patient.csv"),
                 index=False)

    uncertainty = compute_uncertainty_profile(pp_bc, exclusion_df)
    with open(os.path.join(C.LOGS_DIR, "design_uncertainty_profile.json"), "w") as fh:
        json.dump(uncertainty, fh, indent=2, default=str)

    sim_sensitivity = simulation_sensitivity_analysis()
    with open(os.path.join(C.LOGS_DIR, "simulation_sensitivity.json"), "w") as fh:
        json.dump(sim_sensitivity, fh, indent=2, default=str)

    # Design envelopes
    envelopes = design_envelopes(bc_df, uncertainty, sim_sensitivity)
    env_path = os.path.join(C.LOGS_DIR, "design_envelopes.json")
    with open(env_path, "w") as fh:
        json.dump(envelopes, fh, indent=2, default=str)
    log.info("Design envelopes → %s", env_path)

    # Print key design specs
    log.info("=" * 60)
    log.info("KEY MECHANICAL DESIGN BOUNDARY CONDITIONS")
    log.info("=" * 60)
    for var, spec in envelopes.items():
        log.info("  %-25s [%s]  typical=%.3f  p5–p95=[%.3f, %.3f]  max=%.3f  conservative=%.3f",
                 var, spec["unit"],
                 spec["typical"] if np.isfinite(spec["typical"]) else -999,
                 spec["normal_range"][0] if np.isfinite(spec["normal_range"][0]) else -999,
                 spec["normal_range"][1] if np.isfinite(spec["normal_range"][1]) else -999,
             spec["worst_case"] if np.isfinite(spec["worst_case"]) else -999,
             spec["conservative_worst_case"] if np.isfinite(spec.get("conservative_worst_case", np.nan)) else -999)

    # Legacy-compatible CSV (same structure as existing VGV_Boundary_Conditions.csv)
    # to integrate with CODE/BC.py format
    legacy_rows = []
    for _, row in df.iterrows():
        legacy_rows.append({
            "Patient_ID":              row.get("patient_id", ""),
            "Deceleration_event":      row.get("dPaw_dt_max", np.nan),
            "Pressure_Rise_Rate_cmH2O_s": row.get("dPaw_dt_max", np.nan),
            "Overshoot_cmH2O":         row.get("delta_paw_max", np.nan),
            "DeltaPL_max_cmH2O":       row.get("delta_pl_max", np.nan),
            "DeltaPaw_max_cmH2O":      row.get("delta_paw_max", np.nan),
            "dPL_dt_max_cmH2Os":       row.get("dPL_dt_max", np.nan),
            "TransmissionFraction":    row.get("tf", np.nan),
            "ETS_frac":                row.get("ets_frac", np.nan),
            "F_peak_Ls":               row.get("f_peak", np.nan),
            "InspDur_s":               row.get("insp_dur_s", np.nan),
            "ExpDur_s":                row.get("exp_dur_s", np.nan),
            "Paw_base_cmH2O":          row.get("paw_base", np.nan),
            "PL_base_cmH2O":           row.get("pl_base", np.nan),
            "PS_cmH2O":                row.get("ps", np.nan),
            "PEEP_cmH2O":              row.get("peep", np.nan),
            "Predicted_DeltaPL_local": row.get("local_pred", np.nan),
        })

    pd.DataFrame(legacy_rows).to_csv(
        os.path.join(C.LOGS_DIR, "PSV_Boundary_Conditions_Phase2.csv"), index=False
    )
    log.info("Step 10 complete. BCs → %s", C.LOGS_DIR)
