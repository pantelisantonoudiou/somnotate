# -*- coding: utf-8 -*-
"""
Create Somnotate input CSV from EDF files.

Scans an EDF folder and writes a CSV that Somnotate consumes.
Channel columns are created dynamically from the user-provided EDF labels
(e.g., ["BLA-LFP","FC-EEG","EMG"]). Each label becomes a column whose cell
value is the same string, so downstream code can select signals by name.
"""

import os
import numpy as np
import pandas as pd


def create_somno_csv(
    raw_path: str,
    processed_path: str,
    save_path: str,
    channel_labels: list[str],   # EDF header labels to use as column names
    sample_frequency: int,       # Hz
) -> None:
    """
    Generate Somnotate input CSV.

    Parameters
    ----------
    raw_path : str
        Directory containing EDF files.
    processed_path : str
        Directory where processed files and annotations will be stored.
    save_path : str
        Full path (CSV file) to save the output.
    channel_labels : list[str]
        EDF labels to use as dynamic CSV columns (order matters).
    sample_frequency : int
        Sampling frequency in Hz.
    """
    if not channel_labels:
        raise ValueError("channel_labels must be a non-empty list of EDF labels.")
    if not os.path.isdir(raw_path):
        raise FileNotFoundError(f"EDF folder not found: {raw_path}")

    # Collect EDF files deterministically
    edf_files = sorted([f for f in os.listdir(raw_path) if f.lower().endswith(".edf")])
    if not edf_files:
        raise FileNotFoundError(f"No EDF files found in {raw_path}")

    os.makedirs(processed_path, exist_ok=True)
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

    rows = []
    for edf_file in edf_files:
        base = os.path.splitext(edf_file)[0]

        row = []
        # file_path_raw_signals
        row.append(os.path.join(raw_path, edf_file))

        # dynamic channel columns: values are the same as their column names
        for lbl in channel_labels:
            row.append(lbl)

        # sampling_frequency_in_hz
        row.append(int(sample_frequency))

        # remaining paths / placeholders
        row.extend([
            os.path.join(processed_path, f"{base}.npy"),                         # file_path_preprocessed_signals
            "",                                                                  # file_path_manual_state_annotation
            os.path.join(processed_path, f"{base}_auto_state_annotation.hyp"),   # file_path_automated_state_annotation
            os.path.join(processed_path, f"{base}_refined_state_annotation.hyp"),
            os.path.join(processed_path, f"{base}_review_intervals.csv"),
            "",                                                                  # file_path_manual_artefact_annotation
            os.path.join(processed_path, f"{base}_automated_artefact_annotation.hyp"),
            os.path.join(processed_path, f"{base}_artefact_intervals.csv"),
            os.path.join(processed_path, f"{base}_missing_value_intervals.csv"),
        ])

        rows.append(row)

    # Final header: EDF labels become their own columns
    header = (
        ["file_path_raw_signals"]
        + list(channel_labels)
        + [
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
    )

    df = pd.DataFrame(data=np.array(rows, dtype=object), columns=header)
    df.to_csv(save_path, index=False)

    print(f"---> Somnotate input CSV created: {save_path}")
    print(f"     {len(edf_files)} EDF files listed.")
