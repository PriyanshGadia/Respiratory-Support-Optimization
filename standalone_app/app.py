#!/usr/bin/env python
"""
Standalone GUI app for testing imported respiratory waveform datasets.
"""

from __future__ import annotations

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import (
    AnalysisResult,
    BatchAnalysisResult,
    RunConfig,
    export_batch_report,
    export_report,
    list_columns,
    run_analysis,
    run_batch_analysis,
)


class StandaloneTesterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("REBOOT Standalone Dataset Tester")
        self.root.geometry("1200x760")

        self.file_path_var = tk.StringVar()
        self.file_count_var = tk.StringVar(value="0 files selected")
        self.patient_id_var = tk.StringVar(value="EXT001")
        self.source_var = tk.StringVar(value="external")
        self.fs_var = tk.StringVar(value="")
        self.ets_var = tk.StringVar(value="")
        self.ps_var = tk.StringVar(value="")
        self.peep_var = tk.StringVar(value="")
        self.fio2_var = tk.StringVar(value="")

        self.time_col_var = tk.StringVar()
        self.flow_col_var = tk.StringVar()
        self.paw_col_var = tk.StringVar()
        self.pes_col_var = tk.StringVar(value="<none>")

        self.column_values: list[str] = []
        self.selected_files: list[str] = []
        self.last_result: AnalysisResult | None = None
        self.last_batch_result: BatchAnalysisResult | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(frame, text="1) Dataset Import", padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Input file:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(top, textvariable=self.file_path_var, width=90).grid(row=0, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(top, text="Browse Single", command=self.on_browse).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(top, text="Browse Multiple", command=self.on_browse_multiple).grid(row=0, column=3, padx=4, pady=4)
        ttk.Button(top, text="Load Columns", command=self.on_load_columns).grid(row=0, column=4, padx=4, pady=4)
        ttk.Label(top, textvariable=self.file_count_var).grid(row=1, column=1, sticky="w", padx=4, pady=2)

        map_frame = ttk.LabelFrame(frame, text="2) Column Mapping", padding=10)
        map_frame.pack(fill=tk.X, pady=(10, 0))

        self.time_combo = self._combo_row(map_frame, 0, "Time column (optional):", self.time_col_var)
        self.flow_combo = self._combo_row(map_frame, 1, "Flow column:", self.flow_col_var)
        self.paw_combo = self._combo_row(map_frame, 2, "Paw column:", self.paw_col_var)
        self.pes_combo = self._combo_row(map_frame, 3, "Pes column (optional):", self.pes_col_var)

        meta = ttk.LabelFrame(frame, text="3) Metadata and Settings", padding=10)
        meta.pack(fill=tk.X, pady=(10, 0))

        self._entry_row(meta, 0, "Patient ID:", self.patient_id_var)
        self._entry_row(meta, 1, "Source tag:", self.source_var)
        self._entry_row(meta, 2, "Sampling rate fs (Hz, required if no time column):", self.fs_var)
        self._entry_row(meta, 3, "ETS fraction (optional, e.g. 0.25):", self.ets_var)
        self._entry_row(meta, 4, "PS (optional):", self.ps_var)
        self._entry_row(meta, 5, "PEEP (optional):", self.peep_var)
        self._entry_row(meta, 6, "FiO2 (optional):", self.fio2_var)

        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(actions, text="Run Analysis", command=self.on_run_analysis).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Export Statistical Report", command=self.on_export_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Clear Log", command=self.on_clear_log).pack(side=tk.LEFT, padx=4)

        out = ttk.LabelFrame(frame, text="4) Output", padding=10)
        out.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.output_text = tk.Text(out, wrap="word", height=20)
        self.output_text.pack(fill=tk.BOTH, expand=True)

        self._log("Ready. Import a dataset, map columns, and run analysis.")

    def _combo_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        combo = ttk.Combobox(parent, textvariable=var, state="readonly", width=70)
        combo.grid(row=row, column=1, sticky="we", padx=4, pady=4)
        return combo

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(parent, textvariable=var, width=50).grid(row=row, column=1, sticky="w", padx=4, pady=4)

    def _log(self, text: str) -> None:
        self.output_text.insert(tk.END, text + "\n")
        self.output_text.see(tk.END)

    def on_clear_log(self) -> None:
        self.output_text.delete("1.0", tk.END)

    def on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select dataset",
            filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if path:
            self.file_path_var.set(path)
            self.selected_files = [path]
            self.file_count_var.set("1 file selected")

    def on_browse_multiple(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select one or more datasets",
            filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if not paths:
            return
        self.selected_files = list(paths)
        self.file_path_var.set(self.selected_files[0])
        self.file_count_var.set(f"{len(self.selected_files)} files selected")
        self._log(f"Selected {len(self.selected_files)} files for batch processing.")

    def on_load_columns(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Missing file", "Choose a dataset file first.")
            return

        if not os.path.exists(path):
            messagebox.showerror("Invalid file", "Selected file does not exist.")
            return

        try:
            cols, preview = list_columns(path)
            self.column_values = ["<none>"] + cols
            for combo in [self.time_combo, self.flow_combo, self.paw_combo, self.pes_combo]:
                combo["values"] = self.column_values

            self._auto_guess(cols)
            self._log(f"Loaded {len(cols)} columns from: {path}")
            self._log("Preview:")
            self._log(preview.to_string(index=False))
        except Exception as exc:  # pragma: no cover - GUI path
            messagebox.showerror("Load failed", f"Could not read file:\n{exc}")

    def _auto_guess(self, cols: list[str]) -> None:
        lower_map = {c.lower(): c for c in cols}

        def pick(candidates: list[str], default: str = "<none>") -> str:
            for cand in candidates:
                if cand in lower_map:
                    return lower_map[cand]
            return default

        self.time_col_var.set(
            pick(["time", "time [s]", "t", "timestamp"], default="<none>")
        )
        self.flow_col_var.set(
            pick(["flow", "flow [l/s]", "flow [l/min]", "flow_lps", "flow_lpm"], default="<none>")
        )
        self.paw_col_var.set(
            pick(["paw", "pao", "pressure", "pao [cm h2o]", "pressure [cmh2o]"], default="<none>")
        )
        self.pes_col_var.set(
            pick(["pes", "pes [cm h2o]"], default="<none>")
        )

    def _to_optional_float(self, value: str):
        cleaned_value = value.strip()
        if not cleaned_value:
            return None
        return float(cleaned_value)

    def _build_config(self) -> RunConfig:
        flow_col = self.flow_col_var.get().strip()
        paw_col = self.paw_col_var.get().strip()
        if flow_col in {"", "<none>"}:
            raise ValueError("Flow column is required.")
        if paw_col in {"", "<none>"}:
            raise ValueError("Paw column is required.")

        time_col = self.time_col_var.get().strip()
        pes_col = self.pes_col_var.get().strip()

        return RunConfig(
            file_path=self.file_path_var.get().strip(),
            time_col=None if time_col in {"", "<none>"} else time_col,
            flow_col=flow_col,
            paw_col=paw_col,
            pes_col=None if pes_col in {"", "<none>"} else pes_col,
            patient_id=self.patient_id_var.get().strip() or "EXT001",
            source_tag=self.source_var.get().strip() or "external",
            fs_hz=self._to_optional_float(self.fs_var.get()),
            ets_frac=self._to_optional_float(self.ets_var.get()),
            ps=self._to_optional_float(self.ps_var.get()),
            peep=self._to_optional_float(self.peep_var.get()),
            fio2=self._to_optional_float(self.fio2_var.get()),
        )

    def on_run_analysis(self) -> None:
        try:
            cfg = self._build_config()

            files = self.selected_files or [cfg.file_path]
            if not files or files == [""]:
                raise ValueError("No input files selected.")

            if len(files) == 1:
                self._log("Running single-file analysis...")
                self.last_batch_result = None
                self.last_result = run_analysis(cfg)
                self._print_summary(self.last_result)
            else:
                self._log(f"Running batch analysis on {len(files)} files...")
                self.last_result = None
                self.last_batch_result = run_batch_analysis(cfg, files)
                self._print_batch_summary(self.last_batch_result)
        except Exception as exc:  # pragma: no cover - GUI path
            self._log("Run failed.")
            self._log(str(exc))
            self._log(traceback.format_exc())
            messagebox.showerror("Analysis failed", str(exc))

    def _print_summary(self, result: AnalysisResult) -> None:
        summary = result.summary
        self._log("Analysis complete.")
        self._log("Summary:")
        for key in [
            "status",
            "qc_pass",
            "has_pes",
            "fs_used_hz",
            "n_samples",
            "duration_s",
            "n_segmented",
            "n_excluded_segmentation",
            "n_cycle_undefined",
            "n_incomplete_window",
            "n_quality_excluded",
            "n_valid_breaths",
            "retained_rate",
            "event_positive_rate",
        ]:
            self._log(f"- {key}: {summary.get(key)}")

        reasons = summary.get("qc_reasons", [])
        if reasons:
            self._log(f"- qc_reasons: {reasons}")

    def _print_batch_summary(self, batch: BatchAnalysisResult) -> None:
        batch_summary = batch.batch_summary
        self._log("Batch analysis complete.")
        for key in [
            "n_files_total",
            "n_files_ok",
            "n_files_qc_pass",
            "n_valid_breaths_total",
        ]:
            self._log(f"- {key}: {batch_summary.get(key)}")

        per_file = batch_summary.get("per_file", [])
        if isinstance(per_file, list):
            self._log("Per-file:")
            for file_summary in per_file:
                self._log(
                    f"- {file_summary.get('input_file')}: status={file_summary.get('status')}, "
                    f"qc_pass={file_summary.get('qc_pass')}, n_valid_breaths={file_summary.get('n_valid_breaths')}"
                )

    def on_export_report(self) -> None:
        if self.last_result is None and self.last_batch_result is None:
            messagebox.showwarning("No result", "Run analysis first.")
            return

        out_dir = filedialog.askdirectory(title="Select report output folder")
        if not out_dir:
            return

        try:
            self._log("debug: entered report export flow")
            if self.last_batch_result is not None:
                paths = export_batch_report(self.last_batch_result, out_dir)
            elif self.last_result is not None:
                paths = export_report(self.last_result, out_dir)
            else:
                raise ValueError("No analysis result available.")
            self._log("Export complete:")
            for artifact_name, artifact_path in paths.items():
                self._log(f"- {artifact_name}: {artifact_path}")
            messagebox.showinfo("Export complete", "Statistical report and CSV files were saved.")
        except Exception as exc:  # pragma: no cover - GUI path
            self._log("Export failed.")
            self._log(str(exc))
            messagebox.showerror("Export failed", str(exc))


def main() -> None:
    root = tk.Tk()
    app = StandaloneTesterApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
