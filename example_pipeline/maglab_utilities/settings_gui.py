# -*- coding: utf-8 -*-
"""
GUI to collect pipeline settings and write a single JSON config the whole stack can use.

Changes in this version:
- Added Pipeline → Run mode dropdown (both | edf_only | csv_only). Default = both.
- Footer primary button label changed to "Run" (still saves config and exits).

Expected downstream behavior:
- Driver script (e.g., 00_create_somno_files.py) should read cfg["pipeline"]["run_mode"]
  and conditionally run EDF conversion and/or CSV creation.

Run
---
python settings_gui.py

Dependencies
------------
- customtkinter  (pip install customtkinter)
- tkinter (usually ships with Python; on some Linux distros install via OS package)

"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
import tkinter as tk
from tkinter import messagebox, filedialog

try:
    import customtkinter as ctk
except Exception as e:  # pragma: no cover
    print("customtkinter is required. pip install customtkinter", file=sys.stderr)
    raise


# ----------------------------- Defaults ----------------------------- #
DEFAULTS = {
    "edf": {
        "target_fs": 250,
        "channel_order": ["BLA", "FC", "EMG"],
        "edf_label_map": {"BLA": "BLA-LFP", "FC": "FC-EEG", "EMG": "EMG"},
    },
    # Somnotate / CSV signals
    "state_annotation_signals": ["BLA-LFP", "FC-EEG", "EMG"],
    "state_annotation_signal_labels": ["BLA-LFP", "FC-EEG", "EMG"],
    "state_annotation_signal_frequency_bands": [[0.5, 30], [0.5, 30], [10, 45]],
    "paths": {
        "parent_path": "",
        "labchart_dir": "labchart_data",
        "edf_dir": "edf_data",
        "somno_csv": "somno_input.csv",
    },
    # NEW: pipeline run mode (both | edf_only | csv_only)
    "pipeline": {"run_mode": "both"},
}


# ----------------------------- Small helpers ----------------------------- #
@dataclass
class LabeledEntry:
    frame: ctk.CTkFrame
    label: ctk.CTkLabel
    entry: ctk.CTkEntry


class SettingsApp(ctk.CTk):
    def __init__(self, initial: dict | None = None):
        super().__init__()
        self.title("Pipeline Settings")
        self.geometry("1000x800")
        self.minsize(900, 650)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # working copy
        self.cfg = json.loads(json.dumps(initial or DEFAULTS))
        self.final_config: dict | None = None

        # ---- Root uses grid so footer is always visible
        self.grid_rowconfigure(0, weight=1)  # tabs stretch
        self.grid_columnconfigure(0, weight=1)

        # Tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        self._setup_tab = self.tabs.add("Setup")
        self._preview_tab = self.tabs.add("Preview")

        # Build tabs
        self._build_setup_tab(self._setup_tab)
        self._build_preview_tab(self._preview_tab)

        # Footer buttons
        footer = ctk.CTkFrame(self)
        footer.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        footer.grid_columnconfigure((0, 1, 2), weight=1)

        self.save_btn = ctk.CTkButton(
            footer,
            text="Run",  # renamed from "Save config.json"
            height=40,
            command=self.on_save,
        )
        self.save_btn.grid(row=0, column=2, sticky="e")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------- Tab: Setup ------------------------- #
    def _build_setup_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)

        # Section: Paths
        paths = ctk.CTkFrame(tab)
        paths.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(paths, text="Paths", font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        # Parent path (project root)
        ctk.CTkLabel(paths, text="Parent path (project root)").grid(row=1, column=0, sticky="w", padx=10)
        self.parent_var = tk.StringVar(value=self.cfg.get("paths", {}).get("parent_path", ""))
        parent_entry = ctk.CTkEntry(paths, textvariable=self.parent_var)
        parent_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        paths.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(paths, text="Browse", command=self._browse_parent).grid(row=1, column=2, padx=10)

        # LabChart dir
        self.labchart_var = tk.StringVar(value=self.cfg["paths"]["labchart_dir"])
        self._labeled_entry(paths, 2, "LabChart directory", self.labchart_var)

        # EDF output dir
        self.edf_dir_var = tk.StringVar(value=self.cfg["paths"]["edf_dir"])
        self._labeled_entry(paths, 3, "EDF output directory", self.edf_dir_var)

        # Somno CSV path
        self.somno_csv_var = tk.StringVar(value=self.cfg["paths"]["somno_csv"])
        self._labeled_entry(paths, 4, "Somno CSV filename", self.somno_csv_var)

        # Section: EDF
        edf = ctk.CTkFrame(tab)
        edf.pack(fill="x", padx=10, pady=(6, 6))
        ctk.CTkLabel(edf, text="EDF Settings", font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        # target Fs
        ctk.CTkLabel(edf, text="Target sampling rate (Hz)").grid(row=1, column=0, sticky="w", padx=10)
        self.fs_var = tk.IntVar(value=self.cfg["edf"].get("target_fs", 250))
        ctk.CTkEntry(edf, textvariable=self.fs_var).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        edf.grid_columnconfigure(1, weight=1)

        # channel order (simple comma string)
        ctk.CTkLabel(edf, text="Channel order (comma-separated)").grid(row=2, column=0, sticky="w", padx=10)
        self.chan_order_var = tk.StringVar(value=",".join(self.cfg["edf"].get("channel_order", [])))
        ctk.CTkEntry(edf, textvariable=self.chan_order_var).grid(row=2, column=1, sticky="ew", padx=10, pady=6)

        # label map (K:V json string)
        ctk.CTkLabel(edf, text="EDF label map (JSON)").grid(row=3, column=0, sticky="w", padx=10)
        self.label_map_var = tk.StringVar(value=json.dumps(self.cfg["edf"].get("edf_label_map", {})))
        ctk.CTkEntry(edf, textvariable=self.label_map_var).grid(row=3, column=1, sticky="ew", padx=10, pady=6)

        # Section: Somnotate / CSV signals
        somno = ctk.CTkFrame(tab)
        somno.pack(fill="x", padx=10, pady=(6, 6))
        ctk.CTkLabel(somno, text="Somnotate Signals", font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        ctk.CTkLabel(somno, text="Signal labels (JSON list)").grid(row=1, column=0, sticky="w", padx=10)
        self.somno_labels_var = tk.StringVar(value=json.dumps(self.cfg.get("state_annotation_signal_labels", [])))
        ctk.CTkEntry(somno, textvariable=self.somno_labels_var).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        somno.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(somno, text="Signal bands (JSON list of [low, high])").grid(row=2, column=0, sticky="w", padx=10)
        self.somno_bands_var = tk.StringVar(value=json.dumps(self.cfg.get("state_annotation_signal_frequency_bands", [])))
        ctk.CTkEntry(somno, textvariable=self.somno_bands_var).grid(row=2, column=1, sticky="ew", padx=10, pady=6)

        # Section: Pipeline run mode
        run = ctk.CTkFrame(tab)
        run.pack(fill="x", padx=10, pady=(6, 10))
        ctk.CTkLabel(run, text="Pipeline", font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        ctk.CTkLabel(run, text="Run mode (what to execute)").grid(row=1, column=0, sticky="w", padx=10)
        self.run_mode_var = tk.StringVar(value=self.cfg.get("pipeline", {}).get("run_mode", "both"))
        self.run_mode_menu = ctk.CTkOptionMenu(run, variable=self.run_mode_var, values=["both", "edf_only", "csv_only"]) 
        self.run_mode_menu.grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        run.grid_columnconfigure(1, weight=1)

    # ------------------------- Tab: Preview ------------------------- #
    def _build_preview_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="Preview", font=("", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        self.preview_box = ctk.CTkTextbox(tab, wrap="none")
        self.preview_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        btns = ctk.CTkFrame(tab)
        btns.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        btns.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(btns, text="Refresh Preview", command=self.refresh_preview).grid(row=0, column=2, sticky="e")

    # ------------------------- UI helpers ------------------------- #
    def _labeled_entry(self, parent: ctk.CTkFrame, row: int, label: str, var: tk.StringVar) -> LabeledEntry:
        lbl = ctk.CTkLabel(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=10)
        ent = ctk.CTkEntry(parent, textvariable=var)
        ent.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        parent.grid_columnconfigure(1, weight=1)
        return LabeledEntry(parent, lbl, ent)

    def _browse_parent(self) -> None:
        path = filedialog.askdirectory(title="Select parent path")
        if path:
            self.parent_var.set(path)

    # ------------------------- Preview + Save ------------------------- #
    def refresh_preview(self) -> None:
        cfg = self._collect()
        self.preview_box.delete("1.0", tk.END)
        self.preview_box.insert("1.0", json.dumps(cfg, indent=2))

    def on_save(self) -> None:
        try:
            cfg = self._collect()

            # Ensure parent path exists
            parent_path = cfg.get("paths", {}).get("parent_path") or os.getcwd()
            parent_path = os.path.abspath(parent_path)
            os.makedirs(parent_path, exist_ok=True)

            # Write config.json in parent_path and cwd for convenience
            parent_out = os.path.join(parent_path, "config.json")
            with open(parent_out, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            self.final_config = cfg
            print(f"Saved config to:\n- {parent_out}\n- {os.path.abspath('config.json')}")
            self.destroy()
        except Exception as e:  # pragma: no cover
            messagebox.showerror("Error", f"Could not write config.json: {e}")

    def _collect(self) -> dict:
        # Paths
        self.cfg.setdefault("paths", {})
        self.cfg["paths"]["parent_path"] = self.parent_var.get().strip()
        self.cfg["paths"]["labchart_dir"] = self.labchart_var.get().strip()
        self.cfg["paths"]["edf_dir"] = self.edf_dir_var.get().strip()
        self.cfg["paths"]["somno_csv"] = self.somno_csv_var.get().strip()

        # EDF
        self.cfg.setdefault("edf", {})
        self.cfg["edf"]["target_fs"] = int(self.fs_var.get())
        chan_order = [c.strip() for c in self.chan_order_var.get().split(",") if c.strip()]
        self.cfg["edf"]["channel_order"] = chan_order
        try:
            self.cfg["edf"]["edf_label_map"] = json.loads(self.label_map_var.get())
        except json.JSONDecodeError:
            messagebox.showwarning("Warning", "EDF label map is not valid JSON. Keeping previous value.")

        # Somnotate signals
        try:
            somno_labels = json.loads(self.somno_labels_var.get())
            self.cfg["state_annotation_signal_labels"] = somno_labels
        except json.JSONDecodeError:
            messagebox.showwarning("Warning", "Signal labels are not valid JSON. Keeping previous value.")
            somno_labels = self.cfg.get("state_annotation_signal_labels", [])

        try:
            self.cfg["state_annotation_signal_frequency_bands"] = json.loads(self.somno_bands_var.get())
        except json.JSONDecodeError:
            messagebox.showwarning("Warning", "Signal bands are not valid JSON. Keeping previous value.")

        # Keep a single set of names for Somnotate to read directly
        self.cfg["state_annotation_signals"] = [
            f"channel_{i+1}_label" for i in range(len(self.cfg.get("state_annotation_signal_labels", [])))
        ]

        # NEW: pipeline run mode
        self.cfg.setdefault("pipeline", {})
        self.cfg["pipeline"]["run_mode"] = (self.run_mode_var.get() or "both").strip().lower()

        return self.cfg

    def _on_close(self) -> None:
        if messagebox.askokcancel("Quit", "Close without saving config?"):
            self.final_config = None
            self.destroy()


# ----------------------------- Entrypoint ----------------------------- #
if __name__ == "__main__":
    app = SettingsApp()
    app.mainloop()
