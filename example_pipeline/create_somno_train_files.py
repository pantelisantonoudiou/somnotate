# -*- coding: utf-8 -*-
"""
Pipeline runner:
1) Create hypnogram .txt files from comments (all channels listed in Excel).
2) Convert LabChart .adicht -> EDF (trim to hypnogram duration) for training.
3) Build Somnotate TRAINING CSV that references EDF + hypnograms.

Usage:
  python run_pipeline.py
"""

# ------------------------- Imports ------------------------------ #
import sys
import os
import pandas as pd

from maglab_utilities.convert_to_visbrain import convert_annotations_any_channel
from maglab_utilities.adi_to_edf_train import process_training_recordings
from maglab_utilities.create_somno_train_csv import create_somno_train_csv
# ---------------------------------------------------------------- #


def _validate_channel_names(meta: pd.DataFrame,
                            expected_labels: list,
                            channel_name_col: str,
                            recording_id_col: str = "recording_id") -> None:
    """Ensure each recording_id has exactly the expected channel names (in any order)."""
    if channel_name_col not in meta.columns:
        return
    expected = set(expected_labels)
    bad = []
    for rid, df in meta.groupby(recording_id_col):
        names = set(map(str, df[channel_name_col].dropna().astype(str)))
        if names != expected:
            bad.append((rid, sorted(names), sorted(expected)))
    if bad:
        msg = ["Channel name mismatch detected in file_index:"]
        for rid, got, exp in bad:
            msg.append(f"  - recording_id={rid}: found={got}, expected={exp}")
        raise ValueError("\n".join(msg))


def run_pipeline(
    excel_file: str,
    labchart_path: str,
    hypnogram_out_path: str,
    edf_out_path: str,
    processed_path: str,
    csv_out_path: str,
    somno_states: dict,
    channel_properties: dict,
    channel_labels: list,            # e.g. ["BLA-LFP", "FC-EEG", "EMG"]
    sample_rate: int,
    animal_position_col: str = "animal_position",
    file_name_col: str = "file_name",
    channel_name_col: str = "channel_name",  # optional; validate if present
    block_id_col: str = "block_id",          # passed through to converter
    require_hypnogram: bool = True,
):
    # Create output dirs
    os.makedirs(hypnogram_out_path, exist_ok=True)
    os.makedirs(edf_out_path, exist_ok=True)
    os.makedirs(processed_path, exist_ok=True)
    csv_dir = os.path.dirname(csv_out_path)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)

    # Load metadata
    if not os.path.exists(excel_file):
        raise FileNotFoundError(f"Excel file not found:\n  {excel_file}")
    meta = pd.read_excel(excel_file)

    # Ensure recording_id exists and is non-empty
    if "recording_id" not in meta.columns:
        raise KeyError("file_index must contain a 'recording_id' column.")
    if meta["recording_id"].isna().all():
        raise ValueError("No recording_id values found in file_index.xlsx.")
    meta["recording_id"] = meta["recording_id"].astype(str)

    # Validate channel names (if present in Excel)
    _validate_channel_names(meta, channel_labels, channel_name_col)

    # -------------------- Step 1: hypnograms --------------------
    print("\n[1/3] Creating hypnogram .txt files from comments...")
    print(f"    • Records to process: {meta['recording_id'].nunique()} recordings")
    convert_annotations_any_channel(
        selected_recordings=meta,
        labchart_path=labchart_path,
        save_path=hypnogram_out_path,
        state_map=somno_states,
        animal_position_col=animal_position_col,
        file_name_col=file_name_col,
        block_id_col=block_id_col,   # use block index exactly as in Excel
    )
    print("    ✓ Hypnogram generation finished.")

    # -------------------- Step 2: EDF conversion --------------------
    print("\n[2/3] Converting LabChart -> EDF (trim to hypnogram duration)...")
    process_training_recordings(
        selected_recordings=meta,
        labchart_path=labchart_path,
        score_path=hypnogram_out_path,    # where .txt hypnograms were written
        edf_out_path=edf_out_path,        # where .edf will be written
        channel_properties=channel_properties,
        block_id_col=block_id_col,
        # implement per-record block usage inside adi_to_edf_train if needed
    )
    print("    ✓ EDF conversion finished.")

    # -------------------- Step 3: Training CSV --------------------
    print("\n[3/3] Building Somnotate TRAINING CSV...")
    create_somno_train_csv(
        raw_path=edf_out_path,            # EDF + .txt live together here
        processed_path=processed_path,    # Somnotate outputs will go here
        save_path=csv_out_path,           # final CSV path
        channel_labels=channel_labels,
        sample_rate=sample_rate,
        require_hypnogram=require_hypnogram,
    )
    print("    ✓ Training CSV created.")

    print("\nPipeline complete.")


if __name__ == "__main__":
    # ------------------------------ USER SETTINGS ------------------------------ #
    PARENT_PATH   = input("Enter the parent folder path (where 'labchart_data' is located): ").strip()
    if not os.path.isdir(PARENT_PATH):
        sys.exit(f"[ERROR] Invalid path: {PARENT_PATH}. Please provide an existing folder.")
    EXCEL_FILE        = os.path.join(PARENT_PATH, "file_index.xlsx")
    LABCHART_PATH     = os.path.join(PARENT_PATH, "labchart_data")        # .adicht files
    HYPNOGRAM_OUT     = os.path.join(PARENT_PATH, "edf_data")             # .txt hypnograms
    EDF_OUT           = os.path.join(PARENT_PATH, "edf_data")             # .edf output
    PROCESSED_PATH    = os.path.join(PARENT_PATH, "processed")            # Somnotate outputs
    CSV_OUT           = os.path.join(PARENT_PATH, "somno_input_for_train.csv")

    # Map LabChart comment text -> Somnotate labels
    SOMNO_STATES = {
        "WAKE": "awake",
        "NREM": "non-REM",
        "REM":  "REM",
        "WAKJE": "awake",
        "WAKR":  "awake",
        "WAKE\\": "awake",
        "WALE":  "awake",
        "NEWM":  "non-REM",
        "WAKKE": "awake",
        "undefined": "undefined",
    }

    # --- User-configurable EDF properties ---
    default_labels = "BLA-LFP,FC-EEG,EMG"
    labels_str = input(f"Channel labels (comma-separated) [default: {default_labels}]: ").strip() or default_labels
    channel_labels = [s.strip() for s in labels_str.split(",")]
    if len(channel_labels) != 3:
        sys.exit("[ERROR] Please provide exactly 3 channel labels separated by commas (e.g., EEG1,EEG2,EMG).")

    default_sr = 250
    sr_str = input(f"Sample rate [default: {default_sr}]: ").strip()
    try:
        sample_rate = int(sr_str) if sr_str else default_sr
    except ValueError:
        sys.exit("[ERROR] Sample rate must be an integer.")

    CHANNEL_PROPERTIES = {
        "sample_frequency":  [sample_rate] * len(channel_labels),
        "channel_name": channel_labels,
        "dimension":    ["V"] * len(channel_labels),
        "physical_max": [0.1, 0.1, 0.01],
        "physical_min": [-0.1, -0.1, -0.01],
        "digital_max":  [32000] * len(channel_labels),
        "digital_min":  [-32000] * len(channel_labels),
    }

    run_pipeline(
        excel_file=EXCEL_FILE,
        labchart_path=LABCHART_PATH,
        hypnogram_out_path=HYPNOGRAM_OUT,
        edf_out_path=EDF_OUT,
        processed_path=PROCESSED_PATH,
        csv_out_path=CSV_OUT,
        somno_states=SOMNO_STATES,
        channel_properties=CHANNEL_PROPERTIES,
        channel_labels=channel_labels,
        sample_rate=sample_rate,
        require_hypnogram=True,
        block_id_col="block_index",
    )
