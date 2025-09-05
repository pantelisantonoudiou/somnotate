# -*- coding: utf-8 -*-
"""
Create Somnotate TRAINING input CSV from EDF files.

What it does
------------
- Scans a folder of EDF files (one per recording).
- Builds rows for Somnotate training, including paths to:
  * raw signals (EDF),
  * manual state annotations (Visbrain .txt hypnogram),
  * preprocessed/automated/refined outputs (placeholders Somnotate will write).

How to use
----------
1) Convert LabChart -> EDF and create hypnogram .txt files first.
2) Edit the USER SETTINGS block below (paths, channel labels, sample rate).
3) Run:  python create_somno_train.py
"""

import os
import numpy as np
import pandas as pd


def create_somno_train_csv(
    raw_path: str,
    processed_path: str,
    save_path: str,
    channel_labels: list,
    sample_rate: int,
    require_hypnogram: bool = True,
    edf_suffix: str = ".edf",
    hyp_suffix: str = ".txt",
):
    """
    Generate Somnotate training CSV.

    Parameters
    ----------
    raw_path : str
        Directory containing EDF files (and hypnogram .txt files).
    processed_path : str
        Directory where Somnotate will write processed/annotation outputs.
    save_path : str
        Full path to the output CSV file.
    channel_labels : list[str]
        Exactly 3 labels: [EEG1, EEG2, EMG] (order must match EDF channels).
    sample_rate : int
        Sampling frequency (Hz) of the downsampled EDF.
    require_hypnogram : bool
        If True, skip any EDF without a matching .txt hypnogram.
    edf_suffix : str
        File extension for EDF (default ".edf").
    hyp_suffix : str
        File extension for hypnogram (default ".txt").
    """

    # Required columns for Somnotate
    columns = [
        "file_path_raw_signals",
        "eeg1_signal_label",
        "eeg2_signal_label",
        "emg_signal_label",
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

    if len(channel_labels) != 3:
        raise ValueError("channel_labels must have exactly 3 entries: [EEG1, EEG2, EMG].")
    if not os.path.isdir(raw_path):
        raise FileNotFoundError(f"raw_path not found: {raw_path}")

    # List EDFs
    edf_files = sorted([f for f in os.listdir(raw_path) if f.lower().endswith(edf_suffix)])
    if not edf_files:
        raise FileNotFoundError(f"No EDF files found in: {raw_path}")

    # Ensure output dirs exist (processed_path is a DIR; save_path is a FILE)
    os.makedirs(processed_path, exist_ok=True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    rows, skipped = [], []

    for edf_file in edf_files:
        base = os.path.splitext(edf_file)[0]
        edf_fp = os.path.join(raw_path, edf_file)
        hyp_fp = os.path.join(raw_path, f"{base}{hyp_suffix}")

        # For training, we typically require manual hypnogram (.txt)
        if require_hypnogram and not os.path.exists(hyp_fp):
            skipped.append((edf_file, "missing hypnogram"))
            continue

        rows.append([
            edf_fp,                                 # file_path_raw_signals
            channel_labels[0],                      # eeg1_signal_label
            channel_labels[1],                      # eeg2_signal_label
            channel_labels[2],                      # emg_signal_label
            sample_rate,                            # sampling_frequency_in_hz
            os.path.join(processed_path, f"{base}.npy"),                             # preprocessed
            hyp_fp if os.path.exists(hyp_fp) else "",                                 # manual state annotation
            os.path.join(processed_path, f"{base}_auto_state_annotation.hyp"),        # automated
            os.path.join(processed_path, f"{base}_refined_state_annotation.hyp"),     # refined
            os.path.join(processed_path, f"{base}_review_intervals.csv"),             # review intervals
            "",                                                                        # manual artefact annotation (optional)
            os.path.join(processed_path, f"{base}_automated_artefact_annotation.hyp"),
            os.path.join(processed_path, f"{base}_artefact_intervals.csv"),
            os.path.join(processed_path, f"{base}_missing_value_intervals.csv"),
        ])

    # Build DataFrame and write CSV
    df = pd.DataFrame(data=np.array(rows), columns=columns)
    df.to_csv(save_path, index=False)

    # Summary
    print(f"\n---> Somnotate training CSV created: {save_path}")
    print(f"     EDF files found: {len(edf_files)}")
    print(f"     Rows written:    {len(rows)}")
    if skipped:
        print(f"     Skipped:         {len(skipped)}")
        for fname, reason in skipped[:10]:
            print(f"       - {fname} [{reason}]")
        if len(skipped) > 10:
            print("       ...")


if __name__ == "__main__":
    # --------------------------- USER SETTINGS --------------------------- #
    PARENT_PATH    = r"R:\Pantelis\for_sleep_scoring\trained_models"
    EDF_PATH       = os.path.join(PARENT_PATH, 'edf_data')                      # EDFs + .txt hypnograms
    PROCESSED_PATH = os.path.join(PARENT_PATH, 'processed')                     # Somnotate outputs
    SAVE_PATH      = os.path.join(PARENT_PATH, 'somno_input_for_train.csv')     # output CSV for somnotate
    SAMPLE_RATE    = 250                                                        # Hz
    CHANNEL_LABELS = ["BLA-LFP", "FC-EEG", "EMG"]                               # Must match EDF channel order

    REQUIRE_HYPNOGRAM = True   # require a .txt hypnogram next to each EDF
    # -------------------------------------------------------------------- #

    create_somno_train_csv(
        raw_path=EDF_PATH,
        processed_path=PROCESSED_PATH,
        save_path=SAVE_PATH,
        channel_labels=CHANNEL_LABELS,
        sample_rate=SAMPLE_RATE,
        require_hypnogram=REQUIRE_HYPNOGRAM,
    )
