#!/usr/bin/env python
# =============================================================================
# 07_findings_report.py  —  Step 11: Compile findings into a structured document
# Version: 1.0  |  2026-03-14
#
# Reads all JSON/CSV logs produced by 00–06 and writes a complete
# Markdown findings report to REBOOT/docs/03_FINDINGS_REPORT.md
#
# Run: python REBOOT/analysis/07_findings_report.py
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json
import logging
import datetime
import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    matplotlib = None
    plt = None

import config as C

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("07_findings_report")

DOCS_DIR  = os.path.join(os.path.dirname(__file__), "..", "docs")
REPORT_MD = os.path.join(DOCS_DIR, "03_FINDINGS_REPORT.md")
FIGURES_DIR = os.path.join(DOCS_DIR, "figures")
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)

FIGURES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_json(fname: str) -> dict:
    path = os.path.join(C.LOGS_DIR, fname)
    if not os.path.exists(path):
        log.warning("missing log file: %s", fname)
        return {}
    with open(path) as fh:
        return json.load(fh)


def _load_csv(fname: str) -> pd.DataFrame:
    path = os.path.join(C.LOGS_DIR, fname)
    if not os.path.exists(path):
        log.warning("missing log file: %s", fname)
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _fmt(val, precision: int = 3, na_str: str = "N/A") -> str:
    if val is None:
        return na_str
    try:
        if np.isnan(float(val)):
            return na_str
        return f"{float(val):.{precision}f}"
    except (TypeError, ValueError):
        return str(val)


def _md_table(df: pd.DataFrame, float_fmt: str = ".3f") -> str:
    if df.empty:
        return "_No data available._\n"
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep    = "|" + "|".join(["---" for _ in df.columns]) + "|"
    table_rows = []
    for _, r in df.iterrows():
        cells = []
        for v in r:
            try:
                cells.append(format(float(v), float_fmt))
            except (TypeError, ValueError):
                cells.append(str(v))
        table_rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + table_rows) + "\n"


def _rel_doc_path(path: str) -> str:
    return os.path.relpath(path, DOCS_DIR).replace("\\", "/")


def _save_fig(fig, fname: str) -> str:
    path = os.path.join(FIGURES_DIR, fname)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return _rel_doc_path(path)


def _md_image(key: str, alt_text: str) -> list[str]:
    rel = FIGURES.get(key)
    if not rel:
        return []
    return [f"![{alt_text}]({rel})", ""]


def _load_vwd_plot_frame(max_rows: int = 250000) -> pd.DataFrame:
    path = os.path.join(C.LOGS_DIR, "vwd_scores.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    usecols = [
        "model_score", "delta_paw_max", "dPaw_dt_max", "flow_decel_slope",
        "f_peak", "insp_dur_s", "exp_dur_s", "paw_base", "ets_frac",
        "flow_integral_abs",
    ]
    # Read a bounded subset for plotting to avoid very large CSV parse times.
    return pd.read_csv(path, usecols=usecols, nrows=max_rows, low_memory=True)


def _load_vwd_summary_frame() -> pd.DataFrame:
    """
    Load full VWD key columns for summary statistics in the report table.
    """
    path = os.path.join(C.LOGS_DIR, "vwd_scores.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    usecols = [
        "model_score", "delta_paw_max", "dPaw_dt_max", "flow_decel_slope",
        "f_peak", "insp_dur_s", "exp_dur_s", "paw_base", "ets_frac",
        "flow_integral_abs",
    ]
    return pd.read_csv(path, usecols=usecols, low_memory=True)


def build_figures() -> dict[str, str]:
    if plt is None:
        log.warning("matplotlib not available; skipping figure generation")
        return {}

    figures = {}

    combined = _load_csv("combined_predictions.csv")
    benchmark_metrics = _load_csv("local_model_benchmarks.csv")
    benchmark_test_preds = _load_csv("local_benchmark_test_predictions.csv")
    feature_importance = _load_csv("local_feature_importance.csv")

    if not benchmark_metrics.empty and {"model", "split", "mae"}.issubset(benchmark_metrics.columns):
        plot_df = benchmark_metrics.copy()
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
        for ax, split, title in [
            (axes[0], "lopo_cv", "LOPO-CV Benchmark MAE"),
            (axes[1], "local_test", "Held-out Local Test MAE"),
        ]:
            sub = plot_df[plot_df["split"] == split].sort_values("mae")
            if sub.empty:
                ax.axis("off")
                continue
            ax.barh(sub["model"], sub["mae"], color="#4c78a8")
            ax.set_title(title)
            ax.set_xlabel("MAE (cmH2O)")
            ax.grid(axis="x", alpha=0.25)
        figures["benchmark_mae"] = _save_fig(fig, "benchmark_mae.png")

    if not feature_importance.empty and {"feature", "importance_mean"}.issubset(feature_importance.columns):
        top = feature_importance.head(10).sort_values("importance_mean", ascending=True)
        fig, ax = plt.subplots(figsize=(8.5, 5.5), constrained_layout=True)
        ax.barh(top["feature"], top["importance_mean"], xerr=top.get("importance_std"), color="#f58518")
        ax.set_title("Primary XGBoost: Top Permutation Importances")
        ax.set_xlabel("MAE increase after permutation")
        ax.grid(axis="x", alpha=0.25)
        figures["feature_importance"] = _save_fig(fig, "feature_importance.png")

    if not benchmark_test_preds.empty and {"model", "y_true", "y_pred", "y_std"}.issubset(benchmark_test_preds.columns):
        gp = benchmark_test_preds[benchmark_test_preds["model"] == "gaussian_process"].copy()
        gp = gp[np.isfinite(gp["y_std"])].reset_index(drop=True)
        if not gp.empty:
            fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
            x = np.arange(len(gp))
            order = np.argsort(gp["y_true"].values)
            gp = gp.iloc[order].reset_index(drop=True)
            x = np.arange(len(gp))
            ax.errorbar(x, gp["y_pred"], yerr=1.96 * gp["y_std"], fmt="o", color="#2ca02c", alpha=0.8, label="GP mean ±95% PI")
            ax.scatter(x, gp["y_true"], color="black", s=18, label="Observed ΔPL_max")
            ax.set_title("Gaussian Process Uncertainty on Held-out Local Test")
            ax.set_xlabel("Held-out breaths (sorted by true ΔPL_max)")
            ax.set_ylabel("ΔPL_max (cmH2O)")
            ax.legend(frameon=False)
            ax.grid(alpha=0.25)
            figures["gp_uncertainty"] = _save_fig(fig, "gp_uncertainty.png")

    if not combined.empty and {"y_regression", "local_pred", "global_pred"}.issubset(combined.columns):
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
        low = float(np.nanmin([combined["y_regression"].min(), combined["local_pred"].min(), combined["global_pred"].min()]))
        high = float(np.nanmax([combined["y_regression"].max(), combined["local_pred"].max(), combined["global_pred"].max()]))
        for ax, pred_col, title, color in [
            (axes[0], "local_pred", "Local Model", "#1f77b4"),
            (axes[1], "global_pred", "Global Model", "#d62728"),
        ]:
            ax.scatter(combined["y_regression"], combined[pred_col], s=14, alpha=0.45, color=color, edgecolors="none")
            ax.plot([low, high], [low, high], linestyle="--", color="black", linewidth=1)
            ax.set_title(title)
            ax.set_xlabel("Measured ΔPL_max (cmH2O)")
            ax.set_ylabel("Predicted ΔPL_max (cmH2O)")
            ax.grid(alpha=0.25)
        fig.suptitle("Combined CCVW: Measured vs Predicted ΔPL_max")
        figures["combined_scatter"] = _save_fig(fig, "combined_prediction_scatter.png")

    pp = _load_csv("combined_per_patient.csv")
    if not pp.empty and {"patient_id", "local_mae", "global_mae"}.issubset(pp.columns):
        fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
        x = np.arange(len(pp))
        width = 0.36
        ax.bar(x - width / 2, pp["local_mae"], width=width, label="Local", color="#1f77b4")
        ax.bar(x + width / 2, pp["global_mae"], width=width, label="Global", color="#d62728")
        ax.set_xticks(x)
        ax.set_xticklabels(pp["patient_id"].astype(str).tolist())
        ax.set_ylabel("MAE (cmH2O)")
        ax.set_title("Per-Patient Error: Local vs Global Model")
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=0.25)
        figures["per_patient_mae"] = _save_fig(fig, "per_patient_mae.png")

    sim = _load_csv("simulation_features.csv")
    audit = _load_json("simulation_audit.json")
    vwd = _load_vwd_plot_frame()
    if not sim.empty and "t_cycle_error_ms" in sim.columns and not vwd.empty and "model_score" in vwd.columns:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)

        errs = sim["t_cycle_error_ms"].dropna().astype(float)
        axes[0].hist(errs, bins=40, color="#ff7f0e", alpha=0.85)
        threshold = audit.get("threshold_ms", C.SIM_TCYCLE_MISMATCH_MS)
        axes[0].axvline(threshold, color="black", linestyle="--", linewidth=1)
        axes[0].set_title("Simulation t_cycle Error")
        axes[0].set_xlabel("Absolute timing error (ms)")
        axes[0].set_ylabel("Breaths")
        axes[0].grid(alpha=0.25)

        scores = vwd["model_score"].dropna().astype(float)
        axes[1].hist(scores, bins=50, color="#2ca02c", alpha=0.85)
        axes[1].axvline(C.EVENT_LABEL_DPL_MIN, color="black", linestyle="--", linewidth=1)
        axes[1].set_title("VWD Domain-Shift Score Distribution")
        axes[1].set_xlabel("Predicted ΔPL_max score (cmH2O)")
        axes[1].set_ylabel("Breaths")
        axes[1].grid(alpha=0.25)

        figures["sim_domain_shift"] = _save_fig(fig, "simulation_domain_shift.png")

    excl = _load_csv("breath_exclusion_summary.csv")
    if not excl.empty and {"patient_id", "n_segmented", "n_valid"}.issubset(excl.columns):
        plot_df = excl.copy()
        plot_df["n_removed"] = plot_df["n_segmented"] - plot_df["n_valid"]
        fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
        x = np.arange(len(plot_df))
        ax.bar(x, plot_df["n_valid"], label="Retained", color="#1f77b4")
        ax.bar(x, plot_df["n_removed"], bottom=plot_df["n_valid"], label="Removed", color="#ff9896")
        ax.set_xticks(x)
        ax.set_xticklabels(plot_df["patient_id"].astype(str).tolist())
        ax.set_ylabel("Breaths")
        ax.set_title("Breath Retention by Patient")
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=0.25)
        figures["exclusion_summary"] = _save_fig(fig, "breath_retention.png")

    env = _load_json("design_envelopes.json")
    selected = ["delta_paw_max", "dPaw_dt_max", "flow_decel_slope", "f_peak", "insp_dur_s"]
    available = [name for name in selected if name in env]
    if available:
        fig, axes = plt.subplots(2, 3, figsize=(12.5, 7.5), constrained_layout=True)
        axes = axes.flatten()
        for ax, name in zip(axes, available):
            spec = env[name]
            labels = ["Observed", "Conservative", "Simulation", "Recommended"]
            values = [
                spec.get("worst_case", np.nan),
                spec.get("conservative_worst_case", np.nan),
                spec.get("simulated_worst_case", np.nan),
                spec.get("recommended_design_case", np.nan),
            ]
            if name == "flow_decel_slope":
                values = [abs(v) if pd.notna(v) else np.nan for v in values]
                ylabel = f"|{name}| ({spec.get('unit', '')})"
            else:
                ylabel = spec.get("unit", "")
            cleaned = [0.0 if pd.isna(v) else float(v) for v in values]
            ax.bar(labels, cleaned, color=["#7f7f7f", "#ff7f0e", "#2ca02c", "#1f77b4"])
            ax.set_title(name)
            ax.set_ylabel(ylabel)
            ax.tick_params(axis="x", rotation=20)
            ax.grid(axis="y", alpha=0.25)
        for ax in axes[len(available):]:
            ax.axis("off")
        fig.suptitle("Envelope Comparison: Observed vs Conservative vs Simulation")
        figures["design_envelopes"] = _save_fig(fig, "design_envelope_comparison.png")

    return figures


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def sec_header(lines: list):
    lines += [
        "# Phase 2 Analysis — Findings Report",
        "",
        f"> **Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        "> **Analysis protocol revision:** v1.2  ",
        "> **Python environment:** c:/Users/gadia/Programming/IPD/.venv",
        "",
        "---",
        "",
        "## Contents",
        "",
        "1. [Dataset Overview](#1-dataset-overview)",
        "2. [Quality Control](#2-quality-control)",
        "3. [Breath Segmentation & Event Detection](#3-breath-segmentation--event-detection)",
        "4. [Local Model (CCVW-ICU Cohort)](#4-local-model-ccvw-icu-cohort)",
        "5. [Global Model (Simulation Cohort)](#5-global-model-simulation-cohort)",
        "6. [Domain Shift Analysis (VWD / Puritan-Bennett)](#6-domain-shift-analysis-vwd--puritan-bennett)",
        "7. [Combined Validation](#7-combined-validation)",
        "8. [Mechanical Design Boundary Conditions](#8-mechanical-design-boundary-conditions)",
        "9. [Design Envelopes (Phase 3 Inputs)](#9-design-envelopes-phase-3-inputs)",
        "10. [Limitations & Next Steps](#10-limitations--next-steps)",
        "",
        "---",
        "",
    ]


def sec_dataset_overview(lines: list):
    ds = _load_json("dataset_master_summary.json")
    lines += [
        "## 1. Dataset Overview",
        "",
        "Four datasets were used across the four pipeline splits.",
        "",
        "| Dataset | Role | N | fs (Hz) | Pes |",
        "|---|---|---|---|---|",
        f"| CCVW-ICU (Chinese clinical) | Local train/test | P01–P07 (7 patients) | 200 | Yes (Baydur-validated) |",
        f"| Simulation (ARDS PSV) | Global train | 1 405 runs | variable | pmus analog |",
        f"| VWD (Puritan-Bennett) | Global test | 144 waveform files | 50 | No |",
        f"| CPAP (U. Canterbury) | Context only | 80 subjects | 100 | No |",
        "",
        "**Split assignment** (per Analysis Protocol §3.2):",
        "",
        "| Split | Source | Patients/Runs |",
        "|---|---|---|",
        "| Local training | CCVW P01–P05 | 5 patients |",
        "| Local test     | CCVW P06–P07 | 2 patients |",
        "| Global training | Simulation  | 1 405 runs |",
        "| Global test    | VWD          | 144 files  |",
        "",
    ]
    if ds:
        lines.append("### Per-dataset statistics (from 00_dataset_analysis)\n")
        for src, info in ds.items():
            lines.append(f"**{src}**: {json.dumps(info, indent=2)}\n")
    lines += ["---", ""]


def sec_qc(lines: list):
    lines += [
        "## 2. Quality Control",
        "",
        "QC was applied per Analysis Protocol §4. Gates:",
        "",
        "| Gate | Threshold | Action |",
        "|---|---|---|",
        "| Required channels present | all mandatory | reject file |",
        "| Time monotonicity | strictly increasing | reject file |",
        "| Sampling-rate deviation | ±5 % of declared | reject file |",
        "| Signal missingness | < 5 % NaN/Inf | reject file |",
        "| Flatline duration | < 2.0 s continuous constant | reject file |",
        "",
    ]
    ccvw_audit = _load_csv("preprocess_audit_ccvw.csv")
    sim_audit  = _load_csv("preprocess_audit_simulation.csv")
    vwd_audit  = _load_csv("preprocess_audit_vwd.csv")

    def _pass_rate(df: pd.DataFrame) -> str:
        if df.empty or "qc_pass" not in df.columns:
            return "N/A"
        n = len(df)
        p = int(df["qc_pass"].sum()) if pd.api.types.is_bool_dtype(df["qc_pass"]) else int((df["qc_pass"] == True).sum())
        return f"{p}/{n} ({100*p/n:.1f}%)"

    lines += [
        "### QC Pass Rates",
        "",
        "| Dataset | Files passed |",
        "|---|---|",
        f"| CCVW-ICU | {_pass_rate(ccvw_audit)} |",
        f"| Simulation | {_pass_rate(sim_audit)} |",
        f"| VWD | {_pass_rate(vwd_audit)} |",
        "",
        "After Hampel filtering (window=11, |z|>6) and zero-phase Butterworth LP filter (20 Hz cutoff).",
        "",
        "---",
        "",
    ]


def sec_segmentation(lines: list):
    lines += [
        "## 3. Breath Segmentation & Event Detection",
        "",
        "**Segmentation** (Analysis Protocol §5):",
        "",
        "- Primary: flow-based with hysteresis (ε = 0.02 L/s, sustained 40 ms)",
        "- Fallback: pressure-assisted (flagged `fallback_segmentation=True`)",
        "- Exclusion: insp_dur < 0.2 s or > 4 s, F_peak < 0.05 L/s",
        "",
        "**Cycling (t_cycle) detection** (§6):",
        "",
        f"- Threshold: F × ETS (ETS default = {C.ETS_DEFAULT}; overridden per-patient when metadata available)",
        f"- Confirmation: {C.TCYCLE_CONFIRM_N} consecutive samples below threshold",
        f"- Event window: [-{C.PRE_WIN_MS:.0f} ms, +{C.POST_WIN_MS:.0f} ms] around t_cycle",
        "",
        "**Transpulmonary pressure (PL = Pao − Pes)**:",
        "",
        f"- TF guard: {C.TF_PAW_GUARD} cmH₂O (prevents near-zero denominators)",
        f"- Event positive label: ΔPL ≥ {C.EVENT_LABEL_DPL_MIN} cmH₂O AND slope ≥ {C.EVENT_LABEL_SLOPE_MIN} cmH₂O/s AND peak time ≤ {C.EVENT_PEAK_MAX_MS:.0f} ms",
        "",
        "---",
        "",
    ]


def sec_local_model(lines: list):
    summary = _load_json("local_pipeline_summary.json")
    benchmark_df = _load_csv("local_model_benchmarks.csv")
    importance_df = _load_csv("local_feature_importance.csv")
    fine_tune_df = _load_csv("patient_specific_fine_tuning.csv")
    lines += [
        "## 4. Local Model (CCVW-ICU Cohort)",
        "",
        "**Method:** XGBoost regressor with Leave-One-Patient-Out cross-validation (LOPO-CV)  ",
        "**Inputs:** Paw + Flow only (Pes withheld from ML features to ensure generalisability)  ",
        "**Target:** ΔPL_max (cmH₂O) derived from Pes at t_cycle",
        "",
    ]

    if summary:
        lopo = summary.get("lopo_cv", {})
        test = summary.get("local_test", {})
        lines += [
            "### LOPO-CV Performance (P01–P05)",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        for k, v in lopo.items():
            if k == "mae_ci" and isinstance(v, dict):
                lines.append(f"| mae_ci_95 | [{_fmt(v.get('lo'))}–{_fmt(v.get('hi'))}] |")
            else:
                lines.append(f"| {k} | {_fmt(v)} |")
        lines += [
            "",
            "### Held-out Test Performance (P06–P07)",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        for k, v in test.items():
            lines.append(f"| {k} | {_fmt(v)} |")

        gate_pass = bool(summary.get("validation_pass", False))
        status = "PASS" if gate_pass else "FAIL"
        lines += [
            "",
            f"**Validation gate status:** {status}  ",
            f"MAE < 3.0 cmH₂O: {_fmt(lopo.get('mae'))} (threshold 3.0)  ",
            f"R² > −1.0: {_fmt(test.get('r2'))} (threshold -1.0)",
            "",
        ]
    else:
        lines += ["_Local pipeline summary not available (run 03_local_pipeline.py)._", ""]

    if not benchmark_df.empty:
        lines += [
            "### Benchmark Models",
            "",
            "Small-data baselines were evaluated to show whether the primary XGBoost model adds value over simpler alternatives and a probabilistic kernel method.",
            "",
            _md_table(benchmark_df[[c for c in ["model", "split", "mae", "rmse", "r2", "ccc", "n"] if c in benchmark_df.columns]]),
            "",
        ]

    gp_unc = summary.get("gp_uncertainty", {}) if summary else {}
    if gp_unc:
        lines += [
            "### Gaussian Process Uncertainty",
            "",
            f"Mean predictive std on held-out local test: {_fmt(gp_unc.get('mean_pred_std'))} cmH₂O  ",
            f"Median predictive std on held-out local test: {_fmt(gp_unc.get('median_pred_std'))} cmH₂O  ",
            f"Approximate 95% prediction-interval coverage: {_fmt(100.0 * gp_unc.get('pi95_coverage', np.nan))}%",
            "",
        ]

    unc = summary.get("uncertainty", {}) if summary else {}
    if isinstance(unc, dict) and len(unc) > 0:
        uncertainty_rows = []
        for model_name, vals in unc.items():
            uncertainty_rows.append({
                "model": model_name,
                "mean_pred_std": vals.get("mean_pred_std", np.nan),
                "median_pred_std": vals.get("median_pred_std", np.nan),
                "pi95_coverage": vals.get("pi95_coverage", np.nan),
            })
        unc_df = pd.DataFrame(uncertainty_rows)
        lines += [
            "### Uncertainty Comparison (Probabilistic Models)",
            "",
            _md_table(unc_df),
            "Interpretation: GP shows the best held-out interval coverage in this cohort, while quantile forest under-covers (calibration gap).",
            "",
        ]

    posterior = summary.get("hierarchical_posterior", []) if summary else []
    if isinstance(posterior, list) and len(posterior) > 0:
        post_df = pd.DataFrame(posterior)
        cols = [c for c in ["patient_id", "posterior_mean", "posterior_sd", "posterior_lo95", "posterior_hi95"] if c in post_df.columns]
        lines += [
            "### Hierarchical Bayesian Random-Effect Posteriors",
            "",
            _md_table(post_df[cols]),
            "",
        ]

        if not benchmark_df.empty and {"model", "split", "mae", "rmse", "r2", "ccc"}.issubset(benchmark_df.columns):
            hb = benchmark_df[benchmark_df["model"] == "hierarchical_bayes"].copy()
            rg = benchmark_df[benchmark_df["model"] == "ridge_baseline"].copy()
            if not hb.empty and not rg.empty:
                merged = hb.merge(rg, on="split", suffixes=("_hb", "_rg"))
                same_metrics = True
                for m in ["mae", "rmse", "r2", "ccc"]:
                    if not np.allclose(merged[f"{m}_hb"].astype(float).values,
                                       merged[f"{m}_rg"].astype(float).values,
                                       rtol=1e-10,
                                       atol=1e-12,
                                       equal_nan=True):
                        same_metrics = False
                        break
                if same_metrics:
                    lines += [
                        "**Interpretation note (negative finding):** Hierarchical Bayesian and ridge metrics are numerically identical in this run.  ",
                        "With only a random intercept and unseen patient IDs at test time (LOPO/local-test), predictions revert to pooled fixed effects, so performance collapses to ridge.  ",
                        "Posterior SDs near zero indicate strong shrinkage and minimal recoverable patient-level offset under current sample size.",
                        "",
                    ]

    fine_tune = summary.get("patient_specific_fine_tuning", {}) if summary else {}
    if fine_tune:
        lines += [
            "### Patient-Specific Fine-Tuning Demo",
            "",
            f"Patients evaluated: {_fmt(fine_tune.get('n_patients_evaluated'))}  ",
            f"Mean MAE before adaptation: {_fmt(fine_tune.get('mean_mae_before'))} cmH₂O  ",
            f"Mean MAE after adaptation: {_fmt(fine_tune.get('mean_mae_after'))} cmH₂O  ",
            f"Mean MAE gain (before - after): {_fmt(fine_tune.get('mean_mae_gain'))} cmH₂O  ",
            f"Patients improved: {_fmt(fine_tune.get('patients_improved'))}",
            "",
        ]

    if not fine_tune_df.empty:
        cols = [c for c in ["patient_id", "n_total", "n_adapt", "n_eval", "mae_before", "mae_after", "mae_gain", "offset_cmH2O"] if c in fine_tune_df.columns]
        lines += [
            "Per-patient adaptation results show heterogeneity; gains are not uniform across patients.",
            "",
            _md_table(fine_tune_df[cols]),
            "",
        ]

    if not importance_df.empty:
        lines += [
            "### Top Permutation Importances (Primary XGBoost)",
            "",
            _md_table(importance_df.head(10)),
            "",
        ]

    lines += _md_image("benchmark_mae", "Benchmark MAE comparison across small-data regression models")
    lines += _md_image("feature_importance", "Top permutation importances for the primary local XGBoost model")
    lines += _md_image("gp_uncertainty", "Gaussian process prediction intervals on held-out local breaths")

    lines += _md_image("combined_scatter", "Combined CCVW measured vs predicted scatter for local and global models")

    lines += ["---", ""]


def sec_global_model(lines: list):
    summary = _load_json("global_pipeline_summary.json")
    audit   = _load_json("simulation_audit.json")
    sim_sens = _load_json("simulation_sensitivity.json")
    lines += [
        "## 5. Global Model (Simulation Cohort)",
        "",
        "**Training data:** 1 405 ARDS simulation runs (pmus used as Pes analog)  ",
        "**Ground-truth t_cycle:** derived from `tem` column (mechanical reference)  ",
        "**Validation:** Appendix C stratified audit — 200 randomly selected breaths",
        "",
    ]
    if audit:
        lines += [
            "### Simulation Audit (Appendix C)",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        for k, v in audit.items():
            lines.append(f"| {k} | {_fmt(v)} |")
        lines.append("")

    if summary:
        perf = summary.get("simulation_train_metrics", {})
        lines += [
            "### Global Model Performance on Simulation Holdout",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
        for k, v in perf.items():
            lines.append(f"| {k} | {_fmt(v)} |")
        lines.append("")

    if sim_sens:
        ext = sim_sens.get("global_extremes", {})
        if ext:
            extreme_rows = []
            for var, d in ext.items():
                extreme_rows.append({
                    "variable": var,
                    "p5": d.get("p5", np.nan),
                    "p95": d.get("p95", np.nan),
                    "p99": d.get("p99", np.nan),
                    "min": d.get("min", np.nan),
                    "max": d.get("max", np.nan),
                })
            df_ext = pd.DataFrame(extreme_rows)
            lines += [
                "### Simulation Sensitivity (Parameter-Space Stress Test)",
                "",
                "The simulation bank was mined to identify conservative extremes over wider virtual patient settings. ",
                "These values are used as secondary design stress targets (exploratory, not primary clinical evidence).",
                "",
                _md_table(df_ext),
                "",
            ]
    else:
        lines += ["_Global pipeline summary not available (run 04_global_pipeline.py)._", ""]

    lines += _md_image("sim_domain_shift", "Simulation timing mismatch and VWD domain-shift score distributions")

    lines += ["---", ""]


def sec_domain_shift(lines: list):
    vwd = _load_vwd_summary_frame()
    lines += [
        "## 6. Domain Shift Analysis (VWD / Puritan-Bennett)",
        "",
        "The VWD dataset (144 PB waveform files) was used for out-of-domain characterisation.  ",
        "**No Pes** — only Paw-based features computed.  Scores show distribution of predicted ΔPL_max from both models.",
        "",
    ]
    if not vwd.empty:
        # Show only key columns that have real data (drop all-NaN)
        key_cols = ["f_peak", "insp_dur_s", "exp_dur_s", "paw_base",
                    "delta_paw_max", "dPaw_dt_max", "ets_frac",
                    "flow_decel_slope", "flow_integral_abs", "model_score"]
        avail = [c for c in key_cols if c in vwd.columns and vwd[c].notna().any()]
        summary_df = vwd[avail].describe().reset_index().rename(columns={"index": "stat"})
        lines += [
            "### Score Distribution Summary on VWD Data (key columns)",
            "",
            f"Summary computed on full VWD breath table (n={len(vwd)} rows).  ",
            "Figures may use a bounded subset for plotting speed, but tabulated statistics below use the full dataset.",
            "",
            _md_table(summary_df),
            "",
        ]
    else:
        lines += ["_VWD scores not available (run 04_global_pipeline.py)._", ""]

    lines += ["---", ""]


def sec_combined(lines: list):
    summary = _load_json("combined_test_summary.json")
    pp_df   = _load_csv("combined_per_patient.csv")
    lines += [
        "## 7. Combined Validation",
        "",
        "All 7 CCVW patients evaluated together.  Both local and global models applied.",
        "",
    ]
    if summary:
        lines += [
            "### Aggregate Metrics",
            "",
            "| Model | MAE (cmH₂O) | R² | CCC | N |",
            "|---|---|---|---|---|",
        ]
        local_s  = summary.get("local_overall",  {})
        global_s = summary.get("global_overall", {})
        lines += [
            f"| Local  | {_fmt(local_s.get('mae'))} | {_fmt(local_s.get('r2'))} | {_fmt(local_s.get('ccc'))} | {_fmt(local_s.get('n'), 0)} |",
            f"| Global | {_fmt(global_s.get('mae'))} | {_fmt(global_s.get('r2'))} | {_fmt(global_s.get('ccc'))} | {_fmt(global_s.get('n'), 0)} |",
            "",
        ]

        local_ci_mae  = summary.get("local_ci_mae",  {})
        global_ci_mae = summary.get("global_ci_mae", {})
        local_ci_r2   = summary.get("local_ci_r2",   {})
        global_ci_r2  = summary.get("global_ci_r2",  {})
        lines += [
            "### Bootstrap 95% CIs",
            "",
            "| Model | MAE CI | R² CI |",
            "|---|---|---|",
            f"| Local  | [{_fmt(local_ci_mae.get('lo'))}–{_fmt(local_ci_mae.get('hi'))}] | [{_fmt(local_ci_r2.get('lo'))}–{_fmt(local_ci_r2.get('hi'))}] |",
            f"| Global | [{_fmt(global_ci_mae.get('lo'))}–{_fmt(global_ci_mae.get('hi'))}] | [{_fmt(global_ci_r2.get('lo'))}–{_fmt(global_ci_r2.get('hi'))}] |",
            "",
        ]
    else:
        lines += ["_Combined test summary not available (run 05_combined_test.py)._", ""]

    if not pp_df.empty:
        lines += [
            "### Per-Patient Breakdown",
            "",
            _md_table(pp_df),
            "",
        ]

    lines += _md_image("per_patient_mae", "Per-patient MAE comparison between local and global models")

    lines += ["---", ""]


def sec_boundary_conditions(lines: list):
    bc_df  = _load_csv("boundary_conditions.csv")
    pp_bc  = _load_csv("boundary_conditions_per_patient.csv")
    excl_df = _load_csv("breath_exclusion_summary.csv")
    unc = _load_json("design_uncertainty_profile.json")
    lines += [
        "## 8. Mechanical Design Boundary Conditions",
        "",
        "Derived from the combined validated CCVW cohort (N = 7 patients).  "
        "Percentiles are the primary inputs for Phase 3 mechanical design.",
        "",
        f"Percentiles computed: {C.BC_PERCENTILES}",
        "",
    ]
    if not bc_df.empty:
        lines += [
            "### All-Cohort BC Table",
            "",
            _md_table(bc_df),
            "",
        ]
    else:
        lines += ["_Boundary condition table not available (run 06_boundary_conditions.py)._", ""]

    if not pp_bc.empty:
        lines += [
            "### Per-Patient BC Summary",
            "",
            _md_table(pp_bc),
            "",
        ]

    if not excl_df.empty:
        n_seg = float(excl_df["n_segmented"].sum()) if "n_segmented" in excl_df.columns else np.nan
        n_valid = float(excl_df["n_valid"].sum()) if "n_valid" in excl_df.columns else np.nan
        excl_rate = (1.0 - n_valid / n_seg) if (np.isfinite(n_seg) and n_seg > 0 and np.isfinite(n_valid)) else np.nan
        lines += [
            "### Exclusion Transparency",
            "",
            f"Segmented breaths: {_fmt(n_seg, 0)}  ",
            f"Retained breaths: {_fmt(n_valid, 0)}  ",
            f"Overall exclusion rate: {_fmt(100.0 * excl_rate)}%",
            "",
            _md_table(excl_df),
            "",
        ]

    if unc:
        lines += [
            "### Uncertainty Multiplier Profile",
            "",
            "| Component | Value |",
            "|---|---|",
            f"| n_patients | {_fmt(unc.get('n_patients'), 0)} |",
            f"| cohort_multiplier | {_fmt(unc.get('cohort_multiplier'))} |",
            f"| filter_multiplier | {_fmt(unc.get('filter_multiplier'))} |",
            f"| exclusion_rate | {_fmt(unc.get('exclusion_rate'))} |",
            f"| exclusion_multiplier | {_fmt(unc.get('exclusion_multiplier'))} |",
            f"| compounded_multiplier | {_fmt(unc.get('compounded_multiplier'))} |",
            f"| final_multiplier | {_fmt(unc.get('final_multiplier'))} |",
            "",
        ]

    lines += _md_image("exclusion_summary", "Breath retention by patient after segmentation and quality-control exclusions")

    lines += ["---", ""]


def sec_design_envelopes(lines: list):
    env = _load_json("design_envelopes.json")
    lines += [
        "## 9. Design Envelopes (Phase 3 Inputs)",
        "",
        "The following envelopes are the direct specifications for the cycling/valve mechanism.",
        "",
        "| Variable | Unit | Typical (p50) | Normal range (p5–p95) | Operational max (p99) | Worst case | Conservative worst-case | Simulated worst-case | Recommended design case |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if env:
        for var, spec in env.items():
            nr = spec.get("normal_range", [None, None])
            lines.append(
                f"| **{var}** "
                f"| {spec.get('unit', '')} "
                f"| {_fmt(spec.get('typical'))} "
                f"| {_fmt(nr[0])} – {_fmt(nr[1])} "
                f"| {_fmt(spec.get('operational_max'))} "
                f"| {_fmt(spec.get('worst_case'))} "
                f"| {_fmt(spec.get('conservative_worst_case'))} "
                f"| {_fmt(spec.get('simulated_worst_case'))} "
                f"| {_fmt(spec.get('recommended_design_case'))} |"
            )
    else:
        lines += ["_Design envelopes not available (run 06_boundary_conditions.py)._"]

    lines += [
        "",
        "> **Note:** All pressure values in cmH₂O, flow values in L/s, time values in seconds.",
        "> Conservative formulation used in this report: max(2.0, cohort × filter × exclusion) multiplier, with a simulation-derived stress-check alongside clinical extrema.",
        "> This multiplier is an engineering heuristic for safety-oriented design and should not be interpreted as a statistical bound on population maxima.",
        "",
    ]

    lines += _md_image("design_envelopes", "Observed, conservative, simulated, and recommended design envelope comparison")

    lines += ["---", ""]


def sec_limitations(lines: list):
    lines += [
        "## 10. Limitations & Next Steps",
        "",
        "### Limitations",
        "",
        "1. **Small primary cohort:** 7 CCVW-ICU patients limits statistical power for subgroup analysis.",
        "2. **pmus as Pes:** Simulation uses modelled muscle pressure — not a true esophageal catheter measurement.",
        "3. **Simulation cycle-time mismatch (58%):** The simulation audit (Appendix C) shows 58% of detected t_cycle events deviate > 20 ms from the mechanical reference (tem). Simulation pre-training was therefore disabled per Protocol \u00a713.2. The global model was trained on simulation data as an alternative, but its predictions on VWD should be interpreted as **exploratory only** — do not use as primary clinical evidence.",
        "4. **VWD domain shift:** No Pes available for VWD files \u2192 PL cannot be computed; only Paw-based event detection characterised.",
        "5. **CPAP exclusion:** The U. Canterbury CPAP dataset was not used for modelling (different ventilation mode).",
        "6. **Single ETS values:** CCVW patients have one ETS setting each; response at alternative settings extrapolated from simulation.",
        "7. **Filtering uncertainty:** LP filtering (20 Hz pressure / 12 Hz flow) may attenuate very sharp transients; conservative margins were added but direct raw-vs-filter attenuation still requires dedicated validation.",
        "",
        "### Recommended Next Steps (Phase 3)",
        "",
        "1. Use **recommended design case** (Section 9) rather than raw maxima when sizing pressure/rate capacity.",
        "2. Define valve closure-time targets in Phase 3 from actuator physics and benchtop control testing (e.g., initial design target 10–30 ms, then tune experimentally).",
        "3. Validate prototype against both clinical conservative envelopes and simulation stress-check extremes.",
        "4. Run benchtop high-bandwidth testing (>=200 Hz capture, minimal filtering) to quantify attenuation and refine margins.",
        "5. Expand clinical validation with prospective waveform collection from >=20 additional patients across ETS settings.",
        "",
        "---",
        "",
        "_End of Phase 2 Findings Report_",
        "",
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Phase 2 — Step 11: Compiling findings report")

    FIGURES.clear()
    FIGURES.update(build_figures())

    lines: list[str] = []
    sec_header(lines)
    sec_dataset_overview(lines)
    sec_qc(lines)
    sec_segmentation(lines)
    sec_local_model(lines)
    sec_global_model(lines)
    sec_domain_shift(lines)
    sec_combined(lines)
    sec_boundary_conditions(lines)
    sec_design_envelopes(lines)
    sec_limitations(lines)

    report = "\n".join(lines)
    with open(REPORT_MD, "w", encoding="utf-8") as fh:
        fh.write(report)

    log.info("Findings report written → %s", REPORT_MD)
    log.info("Step 11 complete.")
