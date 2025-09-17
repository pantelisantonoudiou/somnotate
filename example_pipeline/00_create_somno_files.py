# -*- coding: utf-8 -*-
"""
Pipeline: LabChart (.adicht) → EDF → Somnotate CSV, with a one-time GUI setup.

What this script does
---------------------
1) Launches a minimal GUI (settings_gui.py) so the user can pick:
   - parent path
   - EDF target sampling frequency
   - channel roles order and Role→EDF label mapping (single naming scheme)
   - folder/file names (labchart_data, edf_data, somno_input.csv)
   The GUI writes `<parent>/config.json` and to local dir and closes.

2) Converts LabChart to EDF using **file_index.csv** and the config
   - One EDF per `recording_id` (labels = EDF labels from config, order = channel_order)
   - Decimation to the target fs from config (e.g., 256 Hz)
   - Channel ranges/units handled in the underlying converter (adi_to_edf.py)

3) Creates the Somnotate input CSV
   - Uses the same EDF labels for CSV columns (no extra mapping)

Notes
-----
- This script intentionally avoids argparse; user interaction is via the GUI and a single prompt fallback.
- Requires the companion modules: settings_gui.py, adi_to_edf.py, create_somno_csv.py

Run
---
python 00_create_somno_files.py
"""

import json
import os
import sys
from typing import Dict, Any
from maglab_utilities.settings_gui import SettingsApp
from maglab_utilities.adi_to_edf import convert_index_to_edf
from maglab_utilities.create_somno_csv import create_somno_csv

# ----------------------------- Helpers ----------------------------- #

def launch_and_save_config() -> Dict[str, Any]:
    """
    Launch the GUI once, return the config dict.
    - GUI writes <parent>/config.json and ./config.json, and sets app.final_config.
    - We prefer the in-memory config (no widget calls post-destroy), then verify disk files.
    """
    if SettingsApp is None:
        sys.exit("[ERROR] SettingsApp (GUI) is unavailable. Make sure settings_gui.py is present.")

    app = SettingsApp()
    app.mainloop()  # blocks until user saves (or cancels)

    # Prefer the config object produced by the GUI
    cfg = getattr(app, "final_config", None)
    if cfg is None:
        sys.exit("[ERROR] Configuration was not saved. Please click 'Run' in the GUI.")

    # Verify parent path + parent config.json exists
    parent = cfg.get("paths", {}).get("parent_path", "")
    if not parent:
        sys.exit("[ERROR] parent_path missing from config. Please set it in the GUI.")
    parent_cfg_path = os.path.join(parent, "config.json")
    if not os.path.isfile(parent_cfg_path):
        sys.exit(f"[ERROR] Expected to find: {parent_cfg_path}")

    # Re-load authoritative parent config (so downstream always uses the file-on-disk)
    with open(parent_cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Ensure parent_path is set (guard against manual edits)
    cfg.setdefault("paths", {})
    cfg["paths"]["parent_path"] = parent

    # Best-effort: keep a local copy up-to-date (GUI already wrote it)
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not refresh local config.json copy: {e}")

    return cfg


def step_labchart_to_edf(cfg: Dict[str, Any]) -> None:
    """Convert LabChart to EDF according to config + file_index.csv.

    This delegates the heavy lifting to `adi_to_edf.convert_index_to_edf` which is
    expected to:
      - read `<parent>/file_index.csv`
      - group by `recording_id`
      - for each group, select channels whose `channel_user` match `edf.channel_order`
      - write EDF with labels `edf.edf_label_map[role]` in that order
      - decimate to `edf.target_fs`

    Parameters
    ----------
    cfg : dict
        Settings JSON loaded from config.json.
    """
    parent = cfg["paths"]["parent_path"]
    lab_dir = os.path.join(parent, cfg["paths"].get("labchart_dir", "labchart_data"))
    edf_dir = os.path.join(parent, cfg["paths"].get("edf_dir", "edf_data"))
    index_csv = os.path.join(parent, "file_index.csv")

    if not os.path.isdir(lab_dir):
        sys.exit(f"[ERROR] LabChart folder not found: {lab_dir}")
    if not os.path.isfile(index_csv):
        sys.exit(f"[ERROR] file_index.csv not found: {index_csv}")
    os.makedirs(edf_dir, exist_ok=True)

    if convert_index_to_edf is None:
        sys.exit("[ERROR] adi_to_edf.convert_index_to_edf is unavailable. Make sure adi_to_edf.py is present and exports this function.")

    # pluck the essentials from config
    target_fs = int(cfg["edf"].get("target_fs", 250))
    roles = list(cfg["edf"].get("channel_order", []))
    label_map = dict(cfg["edf"].get("edf_label_map", {}))

    print("\n[1/2] LabChart → EDF")
    print(f"  parent:      {parent}")
    print(f"  labchart:    {lab_dir}")
    print(f"  edf out:     {edf_dir}")
    print(f"  index:       {index_csv}")
    print(f"  target fs:   {target_fs}")
    print(f"  channels:       {roles}")
    print(f"  channel name →label:  {label_map}")

    # run conversion
    convert_index_to_edf(
        parent_path=parent,
        labchart_dir=lab_dir,
        edf_dir=edf_dir,
        index_csv=index_csv,
        channel_order=roles,
        edf_label_map=label_map,
        target_fs=target_fs,
    )

    # Quick sanity
    n_edf = sum(1 for f in os.listdir(edf_dir) if f.lower().endswith(".edf"))
    if n_edf == 0:
        sys.exit(f"[ERROR] No EDF files were written to {edf_dir}. Check index/config.")
    print(f"  ✓ EDFs written: {n_edf}")


def step_build_somno_csv(cfg: Dict[str, Any]) -> None:
    """Create the Somnotate input CSV using the same EDF labels from config.

    Parameters
    ----------
    cfg : dict
        Settings JSON loaded from config.json.
    """

    parent = cfg["paths"]["parent_path"]
    edf_dir = os.path.join(parent, cfg["paths"].get("edf_dir", "edf_data"))
    processed_dir = os.path.join(parent, "processed")
    csv_out = os.path.join(parent, cfg["paths"].get("somno_csv", "somno_input.csv"))

    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(os.path.dirname(csv_out) or ".", exist_ok=True)

    # Use the config values created by the GUI:
    csv_signal_columns = list(cfg.get("state_annotation_signals", []))          # e.g., ["channel_1_label", ...]
    channel_labels = list(cfg.get("state_annotation_signal_labels", []))        # e.g., ["bla-lfp", "fc-eeg", "emg"]
    target_fs = int(cfg["edf"].get("target_fs", 250))

    print("\n[2/2] Building Somnotate CSV")
    print(f"  edf in:      {edf_dir}")
    print(f"  processed:   {processed_dir}")
    print(f"  csv out:     {csv_out}")
    print(f"  columns:     {csv_signal_columns}")
    print(f"  labels:      {channel_labels}")
    print(f"  fs (Hz):     {target_fs}")

    create_somno_csv(
        raw_path=edf_dir,
        processed_path=processed_dir,
        save_path=csv_out,
        channel_labels=channel_labels,       # values in the rows
        csv_signal_columns=csv_signal_columns,  # column headers
        sample_frequency=target_fs,
    )
    print("  ✓ Somnotate CSV created")



# ----------------------------- Main ----------------------------- #

if __name__ == "__main__":
    print("\n=== LabChart to EDF to Somnotate CSV Pipeline ===")
    print("This will launch a GUI to set parameters and save config.json.")
    cfg = launch_and_save_config()

    run_mode = (
        cfg.get("pipeline", {}).get("run_mode", "both")
        .strip()
        .lower()
    )

    if run_mode in ("both", "edf_only"):
        step_labchart_to_edf(cfg)

    if run_mode in ("both", "csv_only"):
        step_build_somno_csv(cfg)

    print("\nPipeline complete.")
