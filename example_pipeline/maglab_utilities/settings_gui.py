# -*- coding: utf-8 -*-
"""
GUI to collect pipeline settings and write a single JSON config the whole stack can use.

Design goals
------------
- One set of names, everywhere: EDF labels are also the Somnotate signal names and CSV columns.
- Keep the UI simple: **one setup tab** with all fields (paths + channels at the top), and a separate **Preview** tab.
- App saves `<parent_path>/config.json`.

Run
---
python settings_gui.py

Dependencies
------------
customtkinter (pip install customtkinter)

Changes in this version
-----------------------
- Channel order & mapping moved directly under Parent path.
- Footer buttons are pinned and right-aligned; only a single spacer column expands.
- Horizontal layout made responsive: inputs stretch/shrink with the window; fixed widths removed.
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

DEFAULTS = {
    "edf": {
        "target_fs": 250,
        "channel_order": ["BLA", "FC", "EMG"],
        "edf_label_map": {"BLA": "BLA-LFP", "FC": "FC-EEG", "EMG": "EMG"},
    },
    "state_annotation_signals": ["BLA-LFP", "FC-EEG", "EMG"],
    "state_annotation_signal_labels": ["BLA-LFP", "FC-EEG", "EMG"],
    "state_annotation_signal_frequency_bands": [[0.5, 30], [0.5, 30], [10, 45]],
    "paths": {
        "parent_path": "",
        "labchart_dir": "labchart_data",
        "edf_dir": "edf_data",
        "somno_csv": "somno_input.csv",
    },
}

class SettingsApp(ctk.CTk):
    def __init__(self, initial=None):
        super().__init__()
        self.title("Pipeline Settings")
        self.geometry("1000x800")
        self.minsize(800, 600)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # working copy
        self.cfg = json.loads(json.dumps(initial or DEFAULTS))
        self.final_config = None

        # ---- Root uses grid so footer is always visible
        self.grid_rowconfigure(0, weight=1)  # tabs stretch
        self.grid_columnconfigure(0, weight=1)

        # Layout: 2 tabs only → Setup, Preview
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.tabs.add("Setup")
        self.tabs.add("Preview")

        self._build_setup_tab()
        self._build_preview_tab()

        # ---- Sticky footer buttons (always visible + right-aligned)
        btns = ctk.CTkFrame(self)
        btns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        # Only col 0 expands; 1-2 are fixed button columns
        btns.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btns,
            text="Cancel",
            height=36,
            fg_color="grey",
            text_color="white",
            hover_color="#5a5a5a",
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8), pady=0, sticky="e")

        ctk.CTkButton(
            btns,
            text="Save config.json",
            height=36,
            command=self.on_save,
        ).grid(row=0, column=2, padx=0, pady=0, sticky="e")

        self._refresh_preview()

    # ---------------- Utilities ---------------- #
    def _stretch_col1(self, frame):
        """Labels in col 0, stretchy inputs in col 1, small actions in col 2."""
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

    # ---------------- Tabs ---------------- #
    def _build_setup_tab(self):
        tab = self.tabs.tab("Setup")

        # --- Section: Parent path (TOP) --- #
        paths_top = ctk.CTkFrame(tab)
        paths_top.pack(fill="x", padx=10, pady=(10, 6))
        self._stretch_col1(paths_top)

        ctk.CTkLabel(
            paths_top,
            text="Parent path (contains labchart_data and file_index.csv)",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.parent_entry = ctk.CTkEntry(paths_top)
        self.parent_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.parent_entry.insert(0, self.cfg["paths"]["parent_path"])
        ctk.CTkButton(paths_top, text="Browse", command=self._pick_parent).grid(
            row=0, column=2, padx=10, pady=10, sticky="e"
        )

        # --- Section: Channels (now directly under Parent path) --- #
        ch_frame = ctk.CTkFrame(tab)
        ch_frame.pack(fill="x", padx=10, pady=(6, 6))
        self._stretch_col1(ch_frame)

        ctk.CTkLabel(
            ch_frame,
            text="Channel order (comma-separated, and same as file_index.csv)",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.roles_entry = ctk.CTkEntry(ch_frame)
        self.roles_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.roles_entry.insert(0, ", ".join(self.cfg["edf"]["channel_order"]))
        ctk.CTkButton(ch_frame, text="Apply", command=self._apply_roles).grid(
            row=0, column=2, padx=10, pady=10, sticky="e"
        )

        # Mapping table
        ctk.CTkLabel(ch_frame, text="Channel Name → EDF label (header)").grid(
            row=1, column=0, sticky="w", padx=10, pady=(6, 4)
        )
        self.map_frame = ctk.CTkFrame(ch_frame)
        self.map_frame.grid(
            row=2, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 10)
        )
        # Make columns responsive
        self.map_frame.grid_columnconfigure(0, weight=0)
        self.map_frame.grid_columnconfigure(1, weight=1)
        self.map_rows = []  # list of (role, label_entry)
        self._rebuild_map_rows()

        # --- Section: Remaining path fields (moved below Channels) --- #
        paths_bottom = ctk.CTkFrame(tab)
        paths_bottom.pack(fill="x", padx=10, pady=(6, 6))
        self._stretch_col1(paths_bottom)

        gridrow = 0
        ctk.CTkLabel(paths_bottom, text="LabChart folder name").grid(
            row=gridrow, column=0, sticky="w", padx=10, pady=6
        )
        self.lab_dir_entry = ctk.CTkEntry(paths_bottom)
        self.lab_dir_entry.grid(row=gridrow, column=1, sticky="ew", padx=10, pady=6)
        self.lab_dir_entry.insert(0, self.cfg["paths"]["labchart_dir"])

        gridrow += 1
        ctk.CTkLabel(paths_bottom, text="EDF output folder name").grid(
            row=gridrow, column=0, sticky="w", padx=10, pady=6
        )
        self.edf_dir_entry = ctk.CTkEntry(paths_bottom)
        self.edf_dir_entry.grid(row=gridrow, column=1, sticky="ew", padx=10, pady=6)
        self.edf_dir_entry.insert(0, self.cfg["paths"]["edf_dir"])

        gridrow += 1
        ctk.CTkLabel(paths_bottom, text="Somnotate CSV filename").grid(
            row=gridrow, column=0, sticky="w", padx=10, pady=6
        )
        self.csv_entry = ctk.CTkEntry(paths_bottom)
        self.csv_entry.grid(row=gridrow, column=1, sticky="ew", padx=10, pady=6)
        self.csv_entry.insert(0, self.cfg["paths"]["somno_csv"])

        # --- Section: EDF + Somnotate minor settings --- #
        misc = ctk.CTkFrame(tab)
        misc.pack(fill="x", padx=10, pady=(6, 10))
        self._stretch_col1(misc)
        
        ctk.CTkLabel(misc, text="EDF target sampling frequency (Hz)").grid(
            row=0, column=0, sticky="w", padx=10, pady=10
        )
        self.fs_entry = ctk.CTkEntry(misc)
        self.fs_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        self.fs_entry.insert(0, str(self.cfg["edf"]["target_fs"]))

        ctk.CTkLabel(
            misc,
            text="Frequency bands (per channel, e.g. 0.5-30;0.5-30;10-100)",
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        self.bands_entry = ctk.CTkEntry(misc)
        self.bands_entry.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")
        bands = self.cfg.get(
            "state_annotation_signal_frequency_bands",
            [[0.5, 30], [0.5, 30], [10, 100]],
        )
        self.bands_entry.insert(0, "; ".join(f"{a}-{b}" for a, b in bands))

    def _build_preview_tab(self):
        tab = self.tabs.tab("Preview")
        self.preview_box = tk.Text(tab, height=28, width=100, wrap="word")
        self.preview_box.pack(padx=10, pady=10, fill="both", expand=True)
        self.preview_box.configure(state="disabled")

    # --------------- Helpers & events --------------- #
    def _pick_parent(self):
        path = filedialog.askdirectory(title="Select parent path")
        if path:
            self.parent_entry.delete(0, tk.END)
            self.parent_entry.insert(0, path)
            self.cfg["paths"]["parent_path"] = path
            self._refresh_preview()

    def _apply_roles(self):
        roles = [s.strip() for s in self.roles_entry.get().split(",") if s.strip()]
        if not roles:
            messagebox.showerror(
                "Error", "Please enter at least one Channel name (e.g., vHPC, FC, EMG)."
            )
            return
        self.cfg["edf"]["channel_order"] = roles
        m = self.cfg["edf"].get("edf_label_map", {})
        for r in roles:
            m.setdefault(r, r)
        for k in list(m.keys()):
            if k not in roles:
                del m[k]
        self.cfg["edf"]["edf_label_map"] = m
        self._rebuild_map_rows()
        self._refresh_preview()

    def _rebuild_map_rows(self):
        for w in self.map_frame.winfo_children():
            w.destroy()
        self.map_rows.clear()
        ctk.CTkLabel(self.map_frame, text="Channel Name", anchor="w").grid(
            row=0, column=0, padx=8, pady=6, sticky="w"
        )
        ctk.CTkLabel(self.map_frame, text="EDF Label", anchor="w").grid(
            row=0, column=1, padx=8, pady=6, sticky="w"
        )
        mapping = self.cfg["edf"]["edf_label_map"]
        for r in self.cfg["edf"]["channel_order"]:
            role_e = ctk.CTkEntry(self.map_frame)
            role_e.insert(0, r)
            role_e.configure(state="disabled")
            label_e = ctk.CTkEntry(self.map_frame)
            label_e.insert(0, mapping.get(r, r))
            row = len(self.map_rows) + 1
            role_e.grid(row=row, column=0, padx=8, pady=4, sticky="w")
            label_e.grid(row=row, column=1, padx=8, pady=4, sticky="ew")
            self.map_rows.append((r, label_e))

    def _collect(self):
        self.cfg["paths"]["parent_path"] = self.parent_entry.get().strip()
        self.cfg["paths"]["labchart_dir"] = self.lab_dir_entry.get().strip() or "labchart_data"
        self.cfg["paths"]["edf_dir"] = self.edf_dir_entry.get().strip() or "edf_data"
        self.cfg["paths"]["somno_csv"] = self.csv_entry.get().strip() or "somno_input.csv"
        try:
            self.cfg["edf"]["target_fs"] = int(float(self.fs_entry.get().strip()))
        except Exception:
            messagebox.showerror("Error", "Target fs must be a number.")
            return None
        roles = [s.strip() for s in self.roles_entry.get().split(",") if s.strip()]
        if not roles:
            messagebox.showerror(
                "Error", "Please enter channel roles order (e.g., vHPC, FC, EMG)."
            )
            return None
        mapping = {}
        for r, e in self.map_rows:
            mapping[r] = e.get().strip() or r
        self.cfg["edf"]["channel_order"] = roles
        self.cfg["edf"]["edf_label_map"] = mapping
        bands_text = self.bands_entry.get().strip()
        bands = []
        try:
            if bands_text:
                for part in bands_text.split(";"):
                    a, b = [float(x) for x in part.strip().split("-")]
                    bands.append([a, b])
        except Exception:
            messagebox.showerror(
                "Error", "Frequency bands must look like: 0.5-30; 0.5-30; 10-100"
            )
            return None
        if bands:
            self.cfg["state_annotation_signal_frequency_bands"] = bands
        labels = [self.cfg["edf"]["edf_label_map"][r] for r in self.cfg["edf"]["channel_order"]]
        self.cfg["state_annotation_signals"] = labels
        self.cfg["state_annotation_signal_labels"] = labels
        return self.cfg

    def _refresh_preview(self):
        cfg = self._collect()
        if cfg is None:
            return
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", tk.END)
        self.preview_box.insert(tk.END, json.dumps(cfg, indent=2))
        self.preview_box.configure(state="disabled")

    def on_save(self):
        cfg = self._collect()
        if cfg is None:
            return
        parent = cfg["paths"]["parent_path"]
        if not parent:
            messagebox.showerror("Error", "Please select a parent path.")
            return
        os.makedirs(parent, exist_ok=True)
        parent_out = os.path.join(parent, "config.json")

        try:
            # 1) Write the authoritative config to <parent>/config.json
            with open(parent_out, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            # 2) Also write a convenience copy to the current working directory
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            # 3) Expose the config to the caller and close the GUI
            self.final_config = cfg
            print(f"Saved:\n- {parent_out}\n- {os.path.abspath('config.json')}")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Could not write config.json: {e}")


if __name__ == "__main__":
    app = SettingsApp()
    app.mainloop()
