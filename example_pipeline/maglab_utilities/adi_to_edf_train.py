# -*- coding: utf-8 -*-
"""
Convert LabChart (.adicht) recordings to EDF for TRAINING.

Workflow:
1) You already created annotation hypnograms (.txt) from LabChart comments (separate script).
2) This script:
   - Reads selected recordings metadata (Excel)
   - For each recording_id:
       * Loads the LabChart file
       * Finds the final stop time from the corresponding hypnogram .txt
       * Reads all channels, trims, and downsamples to target sample rate
       * Writes a multi-channel EDF

Edit ONLY the USER SETTINGS block at the bottom.
"""

#### -------------------------- Imports -------------------------- ####
import os
import sys
import adi
import pyedflib
import numpy as np
import pandas as pd
from tqdm import tqdm
from scipy.signal import decimate
#### ------------------------------------------------------------- ####


def save_to_edf(save_path, data, channel_properties):
    """
    Write multi-channel data to an EDF file with the provided channel metadata.

    Parameters
    ----------
    save_path : str
        Full path (including filename.edf) to write the EDF file.
    data : list[np.ndarray]
        One array per channel, all with the same length (samples per channel).
    channel_properties : dict
        Required keys (each a list of length n_channels):
            - "sample_rate", "channel_name", "dimension",
              "physical_max", "physical_min", "digital_max", "digital_min"

    Raises
    ------
    Exception
        If number of channels in `data` does not match metadata lengths.
    """
    n_channels = len(channel_properties["channel_name"])
    if len(data) != n_channels:
        raise Exception("--> Channel count mismatch between data and metadata.")

    # Validate metadata lengths
    for k in ("sample_frequency", "channel_name", "dimension",
              "physical_max", "physical_min", "digital_max", "digital_min"):
        if len(channel_properties[k]) != n_channels:
            raise Exception(f"--> channel_properties['{k}'] length != n_channels.")

    # Build EDF signal headers
    channel_info = []
    for i in range(n_channels):
        channel_dict = {
            "sample_frequency": channel_properties["sample_frequency"][i],
            "label":        channel_properties["channel_name"][i],
            "dimension":    channel_properties["dimension"][i],
            "physical_max": channel_properties["physical_max"][i],
            "physical_min": channel_properties["physical_min"][i],
            "digital_max":  channel_properties["digital_max"][i],
            "digital_min":  channel_properties["digital_min"][i],
        }
        channel_info.append(channel_dict)

    # Write EDF
    with pyedflib.EdfWriter(save_path, n_channels, file_type=pyedflib.FILETYPE_EDF) as edf:
        edf.setSignalHeaders(channel_info)
        edf.writeSamples(data)


def parse_stop_time_from_hypnogram(txt_path):
    """
    Read the Visbrain-format hypnogram and return the total duration (sec),
    which we use as the stop time for extracting raw signals.

    Assumes the file contains a header line like:
        *Duration_sec\t<duration>
    """
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("*Duration_sec"):
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    return float(parts[1])
    raise ValueError(f"Could not find *Duration_sec in {txt_path}")


def process_training_recordings(
    selected_recordings: pd.DataFrame,
    labchart_path: str,
    score_path: str,
    edf_out_path: str,
    channel_properties: dict,
    block_id_col: str = "block_id",   # NEW: per-recording block id (used as-is)
):
    """
    Convert a set of LabChart recordings to EDF using stop times from hypnogram .txt files.

    Assumptions
    -----------
    - Hypnogram files are named: {recording_id}_an{animal_position}.txt
      (i.e., consistent with convert_annotations_any_channel).
    - channel_id in selected_recordings is 1-based (LabChart channel numbering).
    - ADI block index is used exactly as present in the index (no -1).

    Parameters
    ----------
    selected_recordings : pd.DataFrame
        Columns required per row: recording_id, file_name, channel_name, channel_id, animal_position, block_id.
        Multiple rows per recording_id (one per channel).
    labchart_path : str
        Directory containing the .adicht files.
    score_path : str
        Directory containing the hypnogram .txt files (from annotation conversion).
    edf_out_path : str
        Directory where EDF files will be written (auto-created).
    channel_properties : dict
        EDF metadata (see save_to_edf).
    block_id_col : str
        Column name for the LabChart block id in the index (used as-is).
    """
    os.makedirs(edf_out_path, exist_ok=True)

    for rec_id, df in tqdm(selected_recordings.groupby('recording_id'), desc="Converting to EDF"):
        # ---- Naming: match hypnogram stem ----
        animal_pos = str(df['animal_position'].unique()[0])
        recording_name = str(df['file_name'].unique()[0]).replace(".adicht", "")
        edf_stem = f"{recording_name}_an{animal_pos}"
        edf_file_name = f"{edf_stem}.edf"

        # ---- Hypnogram path (must exist) ----
        score_txt = os.path.join(score_path, f"{edf_stem}.txt")
        if not os.path.exists(score_txt):
            print(f"\n---> Hypnogram not found; skipping recording_id {rec_id}:\n     {score_txt}")
            continue

        # ---- Duration from hypnogram ----
        try:
            duration_sec = parse_stop_time_from_hypnogram(score_txt)
        except Exception as e:
            print(f"\n---> Could not parse duration for recording_id {rec_id}: {e}")
            continue

        # ---- Pick source LabChart file & block ----
        # (Assumes all channels for a recording live in the same file/block; uses first row.)
        base_row = df.iloc[0]
        lab_path = os.path.join(labchart_path, str(base_row['file_name']))
        block_idx = int(base_row[block_id_col])  # use exactly as in the index

        try:
            fread = adi.read_file(lab_path)
        except Exception as e:
            print(f"\n---> Could not open LabChart file for recording_id {rec_id}: {e}")
            continue

        # ---- Sampling rate from source ----
        fs = float(fread.channels[0].fs[0])  # Hz (assumes uniform fs across channels)

        # ---- Stop sample (floor) ----
        stop_sample = int(duration_sec * fs)

        # ---- Downsample factor based on target EDF properties ----
        target_sr = float(channel_properties['sample_frequency'][0])
        ds_factor = int(round(fs / target_sr))
        if ds_factor <= 0:
            del fread
            raise ValueError(f"Invalid downsample factor computed from fs={fs}, target={target_sr}")

        # ---- Collect, trim, decimate all channels in the requested order ----
        ch_data = []
        for ch_label in channel_properties['channel_name']:
            # Map desired label -> channel_id (1-based) from the index
            try:
                ch_id = int(df.loc[df['channel_name'] == ch_label, 'channel_id'].values[0])
            except Exception:
                del fread
                raise KeyError(f"recording_id={rec_id}: missing channel_id for label '{ch_label}'")

            # Read raw samples from the specified block (ADI expects this block index as-is)
            raw = fread.channels[ch_id - 1].get_data(block_idx, start_sample=1, stop_sample=stop_sample)

            # Trim to multiple of ds_factor (avoid edge artifacts), then decimate
            trim_len = (len(raw) // ds_factor) * ds_factor
            trimmed = raw[:trim_len]
            downsampled = decimate(trimmed, ds_factor, zero_phase=True)
            ch_data.append(downsampled)

        del fread  # free handle

        # ---- Equalize lengths (truncate to the shortest) ----
        min_len = min(map(len, ch_data))
        ch_data = [x[:min_len] for x in ch_data]

        # ---- Write EDF ----
        out_path = os.path.join(edf_out_path, edf_file_name)
        save_to_edf(out_path, ch_data, channel_properties)

if __name__ == '__main__':

    # ------------------------------ USER SETTINGS ------------------------------ #
    # Where your LabChart .adicht files live:
    PARENT_PATH   = input("Enter the parent folder path (where 'labchart_data' is located): ").strip()
    if not os.path.isdir(PARENT_PATH):
        sys.exit(f"[ERROR] Invalid path: {PARENT_PATH}. Please provide an existing folder.")

    LABCHART_PATH = os.path.join(PARENT_PATH, "labchart_data")          # Folder with .adicht files
    EDF_OUT_PATH  = os.path.join(PARENT_PATH, "edf_data")               # Where to save .edf files
    INDEX_FILE_PATH  = os.path.join(PARENT_PATH, "file_index.xlsx")     # Excel with recording info

    # LabChart block index to read:
    BLOCK_INDEX   = 1

    # Channel properties for the TARGET (downsampled) EDF:
    CHANNEL_PROPERTIES = {
        "sample_frequency":  [250, 250, 250],
        "channel_name": ["BLA-LFP", "FC-EEG", "EMG"],
        "dimension":    ["V", "V", "V"],
        "physical_max": [0.1, 0.1, 0.01],
        "physical_min": [-0.1, -0.1, -0.01],
        "digital_max":  [32000, 32000, 32000],
        "digital_min":  [-32000, -32000, -32000],
    }

    # Which channel name substring to prefer when forming the EDF file name:
    COMMENT_CHANNEL_HINT = "BLA"
    # ---------------------------------------------------------------------------- #

    # Load metadata and run
    selected = pd.read_excel(INDEX_FILE_PATH)
    process_training_recordings(
        selected_recordings=selected,
        labchart_path=LABCHART_PATH,
        score_path=EDF_OUT_PATH,
        edf_out_path=EDF_OUT_PATH,
        block=BLOCK_INDEX,
        channel_properties=CHANNEL_PROPERTIES,
        comment_channel_hint=COMMENT_CHANNEL_HINT,
    )
    print('---> All files were converted to EDF.')