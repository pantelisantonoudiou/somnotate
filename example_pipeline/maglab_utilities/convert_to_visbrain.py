# -*- coding: utf-8 -*-
"""
Convert LabChart comments (from ANY channel in the Excel group) to Visbrain hypnogram text files.

Workflow
--------
1) Convert LabChart .adicht files to EDF (separate script).
2) Use THIS script to convert LabChart comments -> Visbrain-format .txt hypnograms.
   - For each recording_id in the Excel:
       * Read the LabChart file once
       * Collect comments from ALL channels listed for that recording
       * Merge, sort by time, resolve duplicate timestamps, map to Somnotate labels
       * Write one .txt hypnogram file

Edit ONLY the USER SETTINGS block at the bottom.
"""

#### -------------------------- Imports -------------------------- ####
import os
import numpy as np
import pandas as pd
from tqdm import tqdm
import adi
#### ------------------------------------------------------------- ####

def comments_to_visbrain(com_df: pd.DataFrame, state_map: dict):
    """
    LabChart comments -> Visbrain lines.

    Rules:
    - Comments mark ONSET.
    - Emit label[i-1] at time[i] (first label at the second comment’s time).
    - Final comment is STOP only (no label for it).
    - Never write t=0.
    - Unknown labels are printed and IGNORED (others still emitted).
    """
    if com_df.empty:
        return []

    # Sort & last-wins de-dupe across channels
    com_df = (
        com_df.sort_values(["com_time", "channel_id"])
              .drop_duplicates(subset=["com_time"], keep="last")
              .reset_index(drop=True)
    )

    # Map labels and get times
    somno_labels = [state_map.get(txt, txt) for txt in com_df["com_text"].astype(str)]
    com_times = com_df["com_time"].astype(float).values

    # Need at least two timestamps to emit anything
    if len(com_times) < 2:
        return []

    # Allowed set; print unknowns but do not abort
    allowed = set(state_map.values()) | {"undefined"}
    unknown = sorted({lbl for lbl in somno_labels if lbl not in allowed})
    if unknown:
        print(f"--> Unmapped/unknown labels (ignored): {set(unknown)}")

    # Duration rounded up; add undefined tail only if rounding extends it
    file_duration = float(np.ceil(com_times[-1]))

    lines = []
    lines.append(f"*Duration_sec\t{file_duration}")
    lines.append("*Datafile\tUnspecified")

    # Emit transitions: label[i-1] at time[i]
    for i in range(1, len(com_times)):
        prev_label = somno_labels[i - 1]
        t_next = com_times[i]
        if prev_label in allowed:
            lines.append(f"{prev_label}\t{t_next}")
        # else: skip this transition

    if file_duration > com_times[-1]:
        lines.append(f"undefined\t{file_duration}")

    return lines


def convert_annotations_any_channel(
    selected_recordings: pd.DataFrame,
    labchart_path: str,
    save_path: str,
    state_map: dict,
    animal_position_col: str = "animal_position",
    file_name_col: str = "file_name",
    block_id_col: str = "block_id",
    channel_id_col: str = "channel_id",
):
    """
    Convert LabChart comments from ALL channels (single (file, block) per recording_id)
    into one Visbrain hypnogram .txt per recording.

    - Aggregates comments from that (file, block).
    - Onset semantics handled in comments_to_visbrain: label[i-1] at time[i],
      never t=0, final comment is stop-only, unknown labels skipped (printed).
    """
    os.makedirs(save_path, exist_ok=True)

    for rec_id, df in tqdm(selected_recordings.groupby("recording_id"), desc="Converting"):
        animal_pos = str(df[animal_position_col].dropna().unique()[0])
        file_name  = str(df[file_name_col].dropna().unique()[0])
        block_idx  = int(df[block_id_col].dropna().unique()[0]) - 1  # ADI 0-based for your setup

        stem = os.path.splitext(file_name)[0]
        txt_out = os.path.join(save_path, f"{stem}_an{animal_pos}.txt")

        all_comments = []
        fread = None
        try:
            fread = adi.read_file(os.path.join(labchart_path, file_name))
            # For your ADI build: top-level records
            records = fread.records[block_idx].comments
            for c in records:
                all_comments.append(
                    (float(c.time), float(c.tick_position), int(c.channel_), float(c.tick_dt), str(c.text))
                )
        except Exception as e:
            print(f"\n---> Could not open/read LabChart for recording_id {rec_id}: {e}")
            continue
        finally:
            if fread is not None:
                del fread

        if not all_comments:
            print(f"\n---> No comments present across ANY channel/file for recording_id {rec_id}")
            continue

        # Build comments DF
        com_df_all = pd.DataFrame(
            [[t, s, ch_id, dt] for (t, s, ch_id, dt, txt) in all_comments],
            columns=["com_time", "com_sample", "channel_id", "com_dt"],
            dtype=float,
        )
        com_df_all["com_text"] = [txt for (_, _, _, _, txt) in all_comments]

        # Filter to channels in this recording (Excel 1-based → ADI 0-based)
        channel_ids = (df[channel_id_col].dropna().unique() - 1).astype(int).tolist()
        com_df_all = com_df_all[com_df_all["channel_id"].astype(int).isin(channel_ids)]
        if com_df_all.empty:
            print(f"\n---> No comments present on the specified channels for recording_id {rec_id}")
            continue

        # Convert to Visbrain lines (onset semantics; no t=0; last comment = stop; unknowns ignored)
        lines = comments_to_visbrain(com_df_all.copy(), state_map)
        if not lines:
            print(f"\n---> Skipping recording_id {rec_id} due to unmapped/insufficient labels")
            continue

        with open(txt_out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


if __name__ == "__main__":
    # ------------------------------ USER SETTINGS ------------------------------ #
    # Parent path and key folders/files
    PARENT_PATH   = r"C:\temp_files_to_clean\sleep_scoring\scored_files_kj\train_new_scripts"
    LABCHART_PATH = os.path.join(PARENT_PATH, "labchart_data")   # Folder with .adicht files
    SAVE_PATH     = os.path.join(PARENT_PATH, "edf_data")        # Where to save .txt hypnograms
    EXCEL_FILE    = os.path.join(PARENT_PATH, "file_index.xlsx") # Excel with recording info

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
    # ---------------------------------------------------------------------------- #

    # Load metadata
    meta = pd.read_excel(EXCEL_FILE)

    # Run conversion (collect comments from ALL channels listed for each recording)
    convert_annotations_any_channel(
        selected_recordings=meta,
        labchart_path=LABCHART_PATH,
        save_path=SAVE_PATH,
        state_map=SOMNO_STATES,
        animal_position_col="animal_position",
        file_name_col="file_name",
        channel_id_col="channel_id",
    )

    print("---> All hypnogram annotation files were created.")
