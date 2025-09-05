# -*- coding: utf-8 -*-
"""
Create Somnotate input CSV from EDF files.

Scans an EDF folder and writes a CSV that Somnotate consumes.
Channel columns are created dynamically from the user-provided EDF labels
(e.g., ["BLA-LFP","FC-EEG","EMG"]). Each label becomes a column whose cell
value is the same string, so downstream code can select signals by name.
"""

import os
import pandas as pd


def create_somno_csv(
    raw_path: str,
    processed_path: str,
    save_path: str,
    channel_labels: list[str],          # e.g., ["bla-lfp","fc-eeg","emg"]
    sample_frequency: int,              # Hz
    csv_signal_columns: list[str] = None,  # e.g., ["channel_1_label","channel_2_label","channel_3_label"]
):
    """
    Generate a Somnotate-compatible input CSV.

    This CSV tells Somnotate:
      - Where each EDF file lives,
      - Which columns in the CSV correspond to EDF channel labels,
      - The sampling rate,
      - Paths to derived annotations and processed data.

    Parameters
    ----------
    raw_path : str
        Directory containing EDF files.
    processed_path : str
        Directory where processed .npy signals and annotation files will be stored.
    save_path : str
        Full path (CSV file) to save the output.
    channel_labels : list[str]
        Labels to insert into the CSV for each channel (order matters).
        These will be **lowercased automatically** to ensure consistency
        with Somnotate’s downstream parsing.
    sample_frequency : int
        Target sampling frequency in Hz (applied to all EDFs).
    csv_signal_columns : list[str], optional
        Column headers for the channels in the CSV (default = ["channel_1_label", ...]).
        Length must match `channel_labels`.

    Notes
    -----
    - Somnotate expects *generic* channel column names (e.g., "channel_1_label"),
      and the *values* in those columns to be the EDF channel names (lowercased).
    - The order of channels in `channel_labels` must match the EDF writing order.
    """

    # Default to N channels named channel_1/2/3_label if not provided
    if not csv_signal_columns:
        csv_signal_columns = [f"channel_{i+1}_label" for i in range(len(channel_labels))]

    # Force channel labels lowercase for downstream compatibility
    channel_labels = [s.lower() for s in channel_labels]

    # Build CSV columns
    columns = [
        "file_path_raw_signals",
        *csv_signal_columns,  # generic channel column headers
        "sampling_frequency_in_hz",
        "file_path_preprocessed_signals",
        "file_path_manual_state_annotation",
        "file_path_automated_state_annotation",
        "file_path_refined_state_annotation",
        "file_path_review_intervals",
        "file_path_manual_artefact_annotation",
        "file_path_automated_artefact_annotation",
        "file_path_artefact_intervals",
        "file_path_missing_value_intervals",
    ]

    # Gather EDFs
    edf_files = [f for f in os.listdir(raw_path) if f.lower().endswith(".edf")]
    if not edf_files:
        raise FileNotFoundError(f"No EDF files found in {raw_path}")

    rows = []
    for edf_file in edf_files:
        base = os.path.splitext(edf_file)[0]
        row = [os.path.join(raw_path, edf_file)]
        row.extend(channel_labels)  # <- VALUES are lowercased here
        row.extend([
            sample_frequency,
            os.path.join(processed_path, f"{base}.npy"),
            "",  # manual state annotation
            os.path.join(processed_path, f"{base}_auto_state_annotation.hyp"),
            os.path.join(processed_path, f"{base}_refined_state_annotation.hyp"),
            os.path.join(processed_path, f"{base}_review_intervals.csv"),
            "",  # manual artefact annotation
            os.path.join(processed_path, f"{base}_automated_artefact_annotation.hyp"),
            os.path.join(processed_path, f"{base}_artefact_intervals.csv"),
            os.path.join(processed_path, f"{base}_missing_value_intervals.csv"),
        ])
        rows.append(row)

    df = pd.DataFrame(rows, columns=columns)

    os.makedirs(processed_path, exist_ok=True)
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    df.to_csv(save_path, index=False)

    print(f"---> Somnotate input CSV created: {save_path} ({len(edf_files)} EDFs)")

