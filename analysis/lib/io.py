# =============================================================================
# lib/io.py  —  Smart dataset loading for all four data sources
# Version: 1.0  |  2026-03-14
# Loads each dataset under a unified schema:
#   time [s], flow [L/s], paw [cmH2O], pes [cmH2O or NaN], patient_id, source
# =============================================================================

import os
import glob
import re
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified record schema
# ---------------------------------------------------------------------------
UNIFIED_COLS = ["time", "flow", "paw", "pes", "patient_id", "source"]


def _make_record(time, flow, paw, pes, patient_id, source):
    df = pd.DataFrame({
        "time":       np.asarray(time, dtype=np.float64),
        "flow":       np.asarray(flow, dtype=np.float64),
        "paw":        np.asarray(paw,  dtype=np.float64),
        "pes":        np.asarray(pes,  dtype=np.float64),
        "patient_id": patient_id,
        "source":     source,
    })
    return df


# ---------------------------------------------------------------------------
# CCVW-ICU: Chinese clinical PSV + Pes dataset
# ---------------------------------------------------------------------------

def load_ccvw(waveform_dir: str, mv_file: str, patients=None) -> dict:
    """
    Load CCVW-ICU waveform files and merge ETS/PS/PEEP/FiO2 metadata.

    Returns
    -------
    dict: {patient_id: DataFrame(UNIFIED_COLS + ['ps','peep','fio2','ets'])}
    """
    # Load clinical metadata
    mv = pd.read_excel(mv_file)
    mv.columns = [c.strip().lower() for c in mv.columns]
    # Normalise patient ID key
    mv["patient_id"] = mv["patient id"].str.strip().str.upper()
    meta = mv.set_index("patient_id")[["ps", "peep", "fio2", "ets"]].to_dict("index")

    records = {}
    xlsx_files = sorted(glob.glob(os.path.join(waveform_dir, "*.xlsx")))
    if not xlsx_files:
        raise FileNotFoundError(f"No xlsx files in {waveform_dir}")

    for fpath in xlsx_files:
        df_raw = pd.read_excel(fpath)
        # Normalise column names
        df_raw.columns = [c.strip() for c in df_raw.columns]

        pid = str(df_raw["Patient ID"].iloc[0]).strip().upper()
        if patients is not None and pid not in [p.upper() for p in patients]:
            continue

        time = df_raw["Time [s]"].values
        flow = df_raw["Flow [l/s]"].values
        paw  = df_raw["Pao [cm H2O]"].values
        pes  = df_raw["Pes [cm H2O]"].values

        df = _make_record(time, flow, paw, pes, pid, "ccvw")

        # Attach clinical metadata
        clinical = meta.get(pid, {})
        for key in ["ps", "peep", "fio2", "ets"]:
            df[key] = clinical.get(key, np.nan)

        records[pid] = df
        log.debug("Loaded CCVW patient %s: %d samples", pid, len(df))

    return records


# ---------------------------------------------------------------------------
# Simulation dataset
# ---------------------------------------------------------------------------

def load_simulation(waveforms_dir: str, mech_ref_dir: str,
                    pat_ref_dir: str, settings_file: str,
                    run_ids=None) -> dict:
    """
    Load simulation waveforms + ground-truth cycle labels.

    Returns
    -------
    dict: {run_id: {
        'waveform': DataFrame(time,flow,paw,pes,patient_id,source),
        'mech_ref': DataFrame(tim,tem),
        'pat_ref':  DataFrame(tip,tep),
        'settings': dict
    }}
    """
    settings_df = pd.read_csv(settings_file)
    settings_df.columns = [c.strip() for c in settings_df.columns]
    settings_index = settings_df.set_index("run").to_dict("index")

    wf_files = sorted(glob.glob(os.path.join(waveforms_dir, "*.csv")))
    records = {}

    for wf_path in wf_files:
        run_id = os.path.splitext(os.path.basename(wf_path))[0]
        if run_ids is not None and run_id not in run_ids:
            continue

        try:
            wf = pd.read_csv(wf_path)
            wf.columns = [c.strip().lower() for c in wf.columns]

            # pmus is the muscle pressure (Pes analog in simulation)
            pes_col = wf["pmus"].values if "pmus" in wf.columns else np.full(len(wf), np.nan)

            df = _make_record(
                time=wf["time"].values,
                flow=wf["flow"].values,
                paw=wf["paw"].values,
                pes=pes_col,
                patient_id=run_id,
                source="simulation",
            )

            # Load mechanical reference (t_cycle ground truth)
            mech_path = os.path.join(mech_ref_dir, os.path.basename(wf_path))
            mech_ref = pd.read_csv(mech_path) if os.path.exists(mech_path) else pd.DataFrame()

            pat_path = os.path.join(pat_ref_dir, os.path.basename(wf_path))
            pat_ref = pd.read_csv(pat_path) if os.path.exists(pat_path) else pd.DataFrame()

            settings = settings_index.get(run_id, {})

            records[run_id] = {
                "waveform": df,
                "mech_ref": mech_ref,
                "pat_ref":  pat_ref,
                "settings": settings,
            }
        except Exception as exc:
            log.warning("Failed to load simulation run %s: %s", run_id, exc)

    log.info("Loaded %d simulation runs", len(records))
    return records


# ---------------------------------------------------------------------------
# Ventilator Waveform Data (Puritan Bennett, external validation)
# ---------------------------------------------------------------------------

def _parse_vwd_file(fpath: str, declared_fs: float = 50.0, flow_scale: float = 1.0 / 60):
    """
    Parse one VWD file.
    Format:
      Line 0: datetime string
      Line 1: 'BS, S:<n_samples>,'
      Lines 2..: <flow_Lmin>,<paw_cmH2O>

    Parameters
    ----------
    flow_scale : float
        Conversion factor for flow column (default 1/60: L/min → L/s).

    Returns
    -------
    dict with keys: 'time','flow','paw','patient_id','source','n_samples',
                    'fs_estimated','datetime_str'
    """
    with open(fpath, "r", errors="replace") as fh:
        lines = fh.readlines()

    if len(lines) < 3:
        raise ValueError(f"File too short: {fpath}")

    datetime_str = lines[0].strip()
    header2 = lines[1].strip()

    # Parse declared sample count
    m = re.search(r"S:(\d+)", header2)
    declared_n = int(m.group(1)) if m else None

    data_lines = [l.strip() for l in lines[2:] if l.strip()]
    parsed = []
    for line in data_lines:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                col1 = float(parts[0])
                col2 = float(parts[1])
                parsed.append((col1, col2))
            except ValueError:
                continue

    if not parsed:
        raise ValueError(f"No parseable data in {fpath}")

    arr = np.array(parsed, dtype=np.float64)
    n = len(arr)
    time = np.arange(n) / declared_fs
    flow = arr[:, 0] * flow_scale   # L/min → L/s
    paw  = arr[:, 1]                # cmH2O

    # Infer patient-level ID from filename hash prefix
    basename = os.path.basename(fpath)
    patient_id = basename.split("-")[0][:16]

    return {
        "time":           time,
        "flow":           flow,
        "paw":            paw,
        "patient_id":     patient_id,
        "source":         "vwd",
        "n_samples":      n,
        "declared_n":     declared_n,
        "fs_estimated":   declared_fs,
        "datetime_str":   datetime_str,
        "filename":       basename,
    }


def load_vwd(vwd_dir: str, declared_fs: float = 50.0,
             flow_scale: float = 1.0 / 60,
             max_files: int = None) -> list:
    """
    Load all VWD files.

    Returns
    -------
    list of dicts, each from _parse_vwd_file, augmented with unified DataFrame.
    """
    csv_files = sorted(glob.glob(os.path.join(vwd_dir, "*.csv")))
    if max_files is not None:
        csv_files = csv_files[:max_files]

    records = []
    for fpath in csv_files:
        try:
            rec = _parse_vwd_file(fpath, declared_fs=declared_fs,
                                  flow_scale=flow_scale)
            df = _make_record(
                time=rec["time"],
                flow=rec["flow"],
                paw=rec["paw"],
                pes=np.full(len(rec["time"]), np.nan),
                patient_id=rec["patient_id"],
                source="vwd",
            )
            rec["df"] = df
            records.append(rec)
        except Exception as exc:
            log.warning("Skipped VWD file %s: %s", os.path.basename(fpath), exc)

    log.info("Loaded %d VWD files", len(records))
    return records


# ---------------------------------------------------------------------------
# CPAP dataset (University of Canterbury, 100 Hz, no Pes, no PSV)
# ---------------------------------------------------------------------------

def load_cpap(cpap_dir: str, subjects=None) -> dict:
    """
    Load CPAP waveform files.  Pes column is filled with NaN.

    Returns
    -------
    dict: {subject_id: DataFrame(UNIFIED_COLS + ['vtidal'])}
    """
    csv_files = sorted(glob.glob(os.path.join(cpap_dir, "ProcessedData_Subject*.csv")))
    records = {}
    for fpath in csv_files:
        m = re.search(r"ProcessedData_Subject(\d+)\.csv$", os.path.basename(fpath))
        if not m:
            continue
        sid = f"S{int(m.group(1)):03d}"
        if subjects is not None and sid not in subjects:
            continue
        try:
            raw = pd.read_csv(fpath)
            raw.columns = [c.strip() for c in raw.columns]
            df = _make_record(
                time=raw["Time [s]"].values,
                flow=raw["Flow [L/s]"].values,
                paw=raw["Pressure [cmH2O]"].values,
                pes=np.full(len(raw), np.nan),
                patient_id=sid,
                source="cpap",
            )
            df["vtidal"] = raw["V_tidal [L]"].values if "V_tidal [L]" in raw.columns else np.nan
            records[sid] = df
        except Exception as exc:
            log.warning("Failed to load CPAP subject %s: %s", sid, exc)

    log.info("Loaded %d CPAP subjects", len(records))
    return records
