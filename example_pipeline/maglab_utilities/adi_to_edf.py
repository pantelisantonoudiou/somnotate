# -*- coding: utf-8 -*-
"""
LabChart (.adicht) → EDF converter driven by file_index.csv (one EDF per recording_id)

This module exposes a single entry point used by the high‑level pipeline:

    convert_index_to_edf(
        parent_path: str,
        labchart_dir: str,
        edf_dir: str,
        index_csv: str,
        channel_order: list[str],
        edf_label_map: dict[str, str],
        target_fs: int,
    ) -> None

Behavior
--------
- Reads <index_csv> produced by your summarizer.
- For each unique `recording_id`, selects exactly one row per role in `channel_order`
  using the `channel_user` column; order is enforced by `channel_order`.
- Opens the corresponding .adicht file and **reads only those channels** for the
  specified `block_index` (CSV stores 0‑based; ADI API uses 1‑based when reading).
- Zero‑phase decimates each channel to `target_fs` (integer factor; forward+reverse
  IIR via `scipy.signal.decimate(zero_phase=True)`), aligns all channels to the
  shortest, and writes a single EDF named `<recording_id>.edf` under <edf_dir>.
- EDF headers use the provided `edf_label_map` for labels and a fixed set of
  range parameters (physical/digital min/max) that you can customize below.

Notes
-----
- `channel_user` values in the index must exactly match the entries in `channel_order`
  (case‑insensitive) once per recording. Extra/missing/duplicate roles will skip that recording.
- The numeric sampling rate in the EDF headers is set from `target_fs`.
- No HDF5/windowing/reshaping is done here.

Dependencies: numpy, pandas, scipy, pyedflib, adi, tqdm
"""

from __future__ import annotations
import os
import json
from typing import List, Dict
import numpy as np
import pandas as pd
from tqdm import tqdm
from scipy import signal
import pyedflib
import adi

# ------------------------ Defaults / Ranges ------------------------ #
# You can adjust these ranges if your amplifier scaling changes. They remain
# constant irrespective of the input sampling rate.
DEFAULT_RANGE = {
    "dimension":    "V",
    "physical_min": -0.1,
    "physical_max":  0.1,
    "digital_min":  -32000,
    "digital_max":   32000,
}

FS_TOL = 0.02  # allowed relative error between effective fs and target fs

# ----------------------------- Helpers ----------------------------- #

def _zero_phase_decimate(x: np.ndarray, fs_src: float, fs_target: float) -> tuple[np.ndarray, float, int]:
    """Integer‑factor zero‑phase decimation toward `fs_target`.

    Returns
    -------
    x_dec : np.ndarray
        Decimated 1‑D float64 signal.
    eff_fs : float
        Effective sampling rate after decimation.
    d : int
        Integer decimation factor used.
    """
    d = int(round(fs_src / fs_target))
    if d < 1:
        raise ValueError(f"Target fs {fs_target} exceeds source fs {fs_src}")
    eff_fs = fs_src / d
    if abs(eff_fs - fs_target) > FS_TOL * fs_target:
        raise ValueError(
            f"Effective fs {eff_fs:.3f} Hz not within {FS_TOL*100:.1f}% of target {fs_target} Hz (src {fs_src}, d={d})."
        )
    trim = (len(x) // d) * d
    if trim <= 0:
        raise ValueError("Insufficient samples for decimation")
    x = np.asarray(x[:trim], dtype=np.float64)
    x_dec = signal.decimate(x, d, zero_phase=True)
    return x_dec, eff_fs, d


def _build_signal_headers(labels: List[str], fs: float) -> List[dict]:
    """Create pyEDFlib signal headers, one per label, using default ranges.

    The EDF writer expects per‑channel dictionaries with keys:
    label, dimension, sample_frequency, physical_[min|max], digital_[min|max].
    """
    headers: List[dict] = []
    for lab in labels:
        headers.append(
            {
                "label": lab,
                "dimension": DEFAULT_RANGE["dimension"],
                "sample_frequency": float(fs),
                "physical_min": float(DEFAULT_RANGE["physical_min"]),
                "physical_max": float(DEFAULT_RANGE["physical_max"]),
                "digital_min": int(DEFAULT_RANGE["digital_min"]),
                "digital_max": int(DEFAULT_RANGE["digital_max"]),
            }
        )
    return headers


def _find_channel_idx_by_exact_name(fobj, name: str) -> int:
    """Return 0‑based ADI channel index by *exact* channel name; raise if missing."""
    for i in range(fobj.n_channels):
        if str(fobj.channels[i].name) == str(name):
            return i
    raise ValueError(f"Channel not found in ADI file: {name}")


# ------------------------------- Core ------------------------------- #

def convert_index_to_edf(
    *,
    parent_path: str,
    labchart_dir: str,
    edf_dir: str,
    index_csv: str,
    channel_order: List[str],
    edf_label_map: Dict[str, str],
    target_fs: int,
    ) -> None:
    """Convert each unique `recording_id` from file_index.csv into an EDF file.

    Parameters
    ----------
    parent_path : str
        Root folder (used only for provenance saved alongside EDFs).
    labchart_dir : str
        Directory containing source .adicht files.
    edf_dir : str
        Output directory for EDF files. Created if missing.
    index_csv : str
        Path to file_index.csv (must include columns: recording_id, file_name,
        channel_name, channel_user, block_index, animal_id).
    channel_order : list[str]
        Ordered roles the user expects (must match `channel_user` values per recording).
    edf_label_map : dict[str, str]
        Mapping Role → EDF label to use in the EDF header.
    target_fs : int
        Desired sampling frequency in Hz (integer; achieved by integer decimation).
    """
    os.makedirs(edf_dir, exist_ok=True)

    df = pd.read_csv(index_csv)
    required = [
        "recording_id",
        "file_name",
        "channel_name",
        "channel_user",
        "block_index",
        "animal_id",
    ]
    miss = [c for c in required if c not in df.columns]
    if miss:
        raise ValueError(f"Index missing columns: {miss}")

    # Normalize case for matching against channel_order
    roles_lc = [r.lower() for r in channel_order]

    # Group by recording and process each block/animal selection
    for rec_id, g in tqdm(df.groupby("recording_id", dropna=False), desc="Converting to EDF"):
        try:
            # Validate channel set: exactly one row per role
            cu = g["channel_user"].astype(str)
            cu_lc = cu.str.lower()
            missing = [r for r in roles_lc if (cu_lc == r).sum() == 0]
            dups = [r for r in roles_lc if (cu_lc == r).sum() > 1]
            extra = sorted(set(cu_lc.unique()) - set(roles_lc))
            if missing or dups or extra:
                print(
                    f"  Skip {rec_id}: channel set mismatch. Missing={missing or []}, Duplicates={dups or []}, Unexpected={extra or []}"
                )
                continue

            # Order rows by channel_order and extract labels
            order_map = {r.lower(): i for i, r in enumerate(channel_order)}
            g = g.sort_values(
                by="channel_user",
                key=lambda s: s.astype(str).str.lower().map(order_map),
            ).reset_index(drop=True)
            
            edf_label_map = {str(k).lower(): str(v).lower() for k, v in edf_label_map.items()}
            edf_labels = [edf_label_map[str(role)]for role in g["channel_user"].tolist()]

            # Open the ADI file and capture block index
            file_name = g["file_name"].iloc[0]
            block_idx = int(g["block_index"].iloc[0])  # 0‑based in CSV
            adi_path = os.path.join(labchart_dir, file_name)
            if not os.path.exists(adi_path):
                print(f"  Skip {rec_id}: missing file {adi_path}")
                continue
            fread = adi.read_file(adi_path)

            # Map to ADI channel indices by exact channel_name stored in the index
            ch_names = g["channel_name"].tolist()
            ch_idx = [_find_channel_idx_by_exact_name(fread, nm) for nm in ch_names]

            # Determine uniform block length across selected channels
            n_per_ch = [int(fread.channels[i].n_samples[block_idx]) for i in ch_idx]
            n_block = min(n_per_ch)
            if n_block <= 0:
                print(f"  Skip {rec_id}: empty block {block_idx}")
                continue

            # Per‑channel decimation to target_fs
            decimated = []
            eff_fs_vals = []
            for i in ch_idx:
                fs_src = float(fread.channels[i].fs[block_idx])
                raw = fread.channels[i].get_data(block_idx + 1)
                if raw is None or len(raw) == 0:
                    raise ValueError("Empty data slice from ADI")
                x_dec, eff_fs, _ = _zero_phase_decimate(np.asarray(raw), fs_src, float(target_fs))
                decimated.append(x_dec)
                eff_fs_vals.append(eff_fs)

            # Align to shortest and write
            L = min(map(len, decimated))
            if L <= 0:
                print(f"  Skip {rec_id}: insufficient samples after decimation")
                continue
            decimated = [x[:L] for x in decimated]

            headers = _build_signal_headers(edf_labels, fs=float(target_fs))
            out_path = os.path.join(edf_dir, f"{rec_id}.edf")
            with pyedflib.EdfWriter(out_path, len(decimated), file_type=pyedflib.FILETYPE_EDF) as edf:
                edf.setSignalHeaders(headers)
                edf.writeSamples(decimated)
                # quick provenance
                edf.setHeader({"patientname": rec_id})

            # Also drop a tiny JSON next to the EDF for reproducibility
            meta = {
                "recording_id": rec_id,
                "source_file": file_name,
                "block_index_0based": block_idx,
                "target_fs": float(target_fs),
                "effective_fs": eff_fs_vals,
                "labels": edf_labels,
                "channel_names": ch_names,
                "samples_per_channel": int(L),
                "index_csv": os.path.abspath(index_csv),
            }
            with open(os.path.splitext(out_path)[0] + "_meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            print(f"  Wrote {os.path.basename(out_path)} @ {target_fs} Hz, n={L}")

        except Exception as e:
            print(f"!!! Error processing (rec_id={rec_id}): {e}")
