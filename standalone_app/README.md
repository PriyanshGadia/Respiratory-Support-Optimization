# REBOOT Standalone Dataset Tester

This standalone tool exists for quick external waveform testing without changing the main training pipeline.

This folder contains a separate single-application GUI built on the existing REBOOT analysis code.

It lets you:
- Import an external CSV or Excel waveform file.
- Import multiple external files together for batch testing.
- Map your dataset headers to required channels through a GUI.
- Run segmentation and event analytics using the same core logic as REBOOT.
- Export a statistical report and machine-readable outputs.

## What it reuses

The app reuses the existing modules from REBOOT analysis:
- Breath segmentation
- t_cycle detection
- Event feature extraction
- Quality checks and preprocessing

No changes are required in the main REBOOT pipeline to use this tool.

## Supported input formats

- .csv
- .xlsx
- .xls

## Minimum required channels

- Flow column
- Paw/pressure column
- Time column OR manual sampling rate (fs)

Optional:
- Pes column (if provided, transpulmonary metrics are included)
- Metadata values: ETS, PS, PEEP, FiO2

## Run

From workspace root:

```powershell
.venv\Scripts\python.exe REBOOT\standalone_app\app.py
```

Or from this folder:

```powershell
python app.py
```

## GUI workflow

1. Click Browse Single or Browse Multiple.
2. Click Load Columns.
3. Map Time, Flow, Paw, and optional Pes.
4. If Time is not mapped, enter fs (Hz).
5. Click Run Analysis.
6. Click Export Statistical Report and choose output folder.

## Exported files

Single-file run:
- analysis_summary.json
- breath_features.csv
- cleaned_unified_waveform.csv
- summary_metrics.csv
- report.md

Batch run (multi-file):
- batch_summary.json
- batch_per_file_summary.csv
- batch_combined_breath_features.csv
- batch_combined_cleaned_waveform.csv
- batch_report.md

## Notes

- The app is single-file oriented (one imported file per run).
- The app supports both single-file and multi-file batch mode.
- If your flow unit is L/min, convert to L/s before import for best consistency.
- QC and segmentation thresholds follow REBOOT config defaults.
