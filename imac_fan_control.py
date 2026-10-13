#!/usr/bin/env python3
"""
iMac Fan Control – Tkinter edition

A lightweight desktop application for monitoring temperatures and controlling
fan speeds on Intel iMacs running Linux, via the applesmc kernel module.

Target hardware : iMac 27" Late 2009 (iMac11,1) – Lynnfield / Nehalem
Target OS       : openSUSE Tumbleweed (or any Linux with applesmc support)
Toolkit         : Tkinter (ships with Python – no native-code dependency)

Requires: applesmc and coretemp kernel modules loaded
          Root privileges for writing fan speeds

Usage:
    sudo python3 imac_fan_control.py
"""

from __future__ import annotations

import os
import sys
import glob
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APPLESMC_BASE = Path("/sys/devices/platform/applesmc.768")

# iMac 27" Late 2009 has 3 fans
FAN_LABELS = {1: "ODD (Optical)", 2: "HDD (Hard Drive)", 3: "CPU"}

# Well-known SMC temperature key descriptions for iMac11,1
TEMP_KEY_DESCRIPTIONS = {
    "TA0P": "Ambient Air",
    "TC0D": "CPU Die",
    "TC0H": "CPU Heatsink",
    "TC0P": "CPU Proximity",
    "TG0D": "GPU Die",
    "TG0H": "GPU Heatsink",
    "TG0P": "GPU Proximity",
    "TH0P": "HDD Proximity",
    "TL0P": "LCD Proximity",
    "TN0D": "Northbridge Die",
    "TN0P": "Northbridge Proximity",
    "TO0P": "ODD Proximity",
    "Tm0P": "Memory Proximity",
    "Tp0P": "Power Supply Proximity",
    "Ts0P": "Palm Rest",
    "TW0P": "Wireless Module",
}

POLL_INTERVAL_MS = 2000

# Colour palette (dark theme – easy on the eyes)
COL_BG        = "#1e1e2e"
COL_SURFACE   = "#2a2a3c"
COL_BORDER    = "#3a3a4c"
COL_TEXT      = "#cdd6f4"
COL_DIM       = "#7f849c"
COL_GREEN     = "#a6e3a1"
COL_YELLOW    = "#f9e2af"
COL_RED       = "#f38ba8"
COL_BLUE      = "#89b4fa"
COL_ACCENT    = "#cba6f7"
COL_TROUGH    = "#45475a"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FanInfo:
    fan_id: int
    label: str
    rpm_current: int = 0
    rpm_min: int = 0
    rpm_max: int = 0
    manual: bool = False
    target_rpm: int = 0


@dataclass
class TempSensor:
    index: int
    smc_key: str
    description: str
    value_celsius: float = 0.0


@dataclass
class CoretempSensor:
    label: str
    value_celsius: float = 0.0
    high_celsius: float = 0.0
    crit_celsius: float = 0.0


# ---------------------------------------------------------------------------
# Sysfs backend
# ---------------------------------------------------------------------------

class AppleSMCBackend:

    def __init__(self, base: Path = APPLESMC_BASE):
        self.base = base
        self._coretemp_hwmon: Optional[Path] = None
        self._find_coretemp_hwmon()

    def is_available(self) -> bool:
        return self.base.is_dir()

    # -- discovery -----------------------------------------------------------

    def discover_fans(self) -> list[FanInfo]:
        fans: list[FanInfo] = []
        fan_id = 1
        while (self.base / f"fan{fan_id}_input").exists():
            label = FAN_LABELS.get(fan_id, f"Fan {fan_id}")
            fans.append(FanInfo(fan_id=fan_id, label=label))
            fan_id += 1
        return fans

    def discover_temp_sensors(self) -> list[TempSensor]:
        sensors: list[TempSensor] = []
        idx = 1
        while (self.base / f"temp{idx}_input").exists():
            smc_key = self._read_text(self.base / f"temp{idx}_label").strip()
            desc = TEMP_KEY_DESCRIPTIONS.get(smc_key, smc_key)
            sensors.append(TempSensor(index=idx, smc_key=smc_key, description=desc))
            idx += 1
        return sensors

    def discover_coretemp_sensors(self) -> list[CoretempSensor]:
        sensors: list[CoretempSensor] = []
        if self._coretemp_hwmon is None:
            return sensors
        idx = 1
        while (self._coretemp_hwmon / f"temp{idx}_input").exists():
            label = self._read_text(
                self._coretemp_hwmon / f"temp{idx}_label"
            ).strip()
            high = self._read_int(self._coretemp_hwmon / f"temp{idx}_max", 0)
            crit = self._read_int(self._coretemp_hwmon / f"temp{idx}_crit", 0)
            sensors.append(CoretempSensor(
                label=label,
                high_celsius=high / 1000.0,
                crit_celsius=crit / 1000.0,
            ))
            idx += 1
        return sensors

    # -- reading -------------------------------------------------------------

    def read_fan(self, fan: FanInfo) -> None:
        fid = fan.fan_id
        fan.rpm_current = self._read_int(self.base / f"fan{fid}_input")
        fan.rpm_min = self._read_int(self.base / f"fan{fid}_min")
        fan.rpm_max = self._read_int(self.base / f"fan{fid}_max")
        fan.manual = self._read_int(self.base / f"fan{fid}_manual") == 1

    def read_temp(self, sensor: TempSensor) -> None:
        raw = self._read_int(self.base / f"temp{sensor.index}_input")
        sensor.value_celsius = raw / 1000.0

    def read_coretemp(self, sensor: CoretempSensor, idx: int) -> None:
        if self._coretemp_hwmon is None:
            return
        raw = self._read_int(self._coretemp_hwmon / f"temp{idx}_input")
        sensor.value_celsius = raw / 1000.0

    # -- writing (requires root) --------------------------------------------

    def set_fan_manual(self, fan_id: int, manual: bool) -> None:
        self._write_text(self.base / f"fan{fan_id}_manual",
                         "1" if manual else "0")

    def set_fan_speed(self, fan_id: int, rpm: int) -> None:
        self._write_text(self.base / f"fan{fan_id}_output", str(int(rpm)))

    # -- helpers -------------------------------------------------------------

    def _find_coretemp_hwmon(self) -> None:
        for hwmon_dir in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_file = Path(hwmon_dir) / "name"
            if name_file.exists():
                name = self._read_text(name_file).strip()
                if name == "coretemp":
                    self._coretemp_hwmon = Path(hwmon_dir)
                    return

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text()
        except (OSError, IOError):
            return ""

    @staticmethod
    def _read_int(path: Path, default: int = 0) -> int:
        try:
            return int(path.read_text().strip())
        except (OSError, IOError, ValueError):
            return default

    @staticmethod
    def _write_text(path: Path, value: str) -> None:
        path.write_text(value)


# ---------------------------------------------------------------------------
# GUI helpers
# ---------------------------------------------------------------------------

def temp_colour(celsius: float) -> str:
    if celsius < 0 or celsius > 120:
        return COL_DIM
    if celsius < 50:
        return COL_GREEN
    if celsius < 75:
        return COL_YELLOW
    return COL_RED


def rpm_colour(current: int, maximum: int) -> str:
    if maximum <= 0:
        return COL_TEXT
    frac = current / maximum
    if frac < 0.4:
        return COL_GREEN
    if frac < 0.7:
        return COL_YELLOW
    return COL_RED


def _show_permission_error():
    messagebox.showwarning(
        "Permission Denied",
        "Cannot write to fan control files.\n\n"
        "Please restart with root privileges:\n"
        "  sudo python3 imac_fan_control.py")


class BarCanvas:
    """A thin horizontal progress bar drawn on a Canvas."""

    def __init__(self, parent, width=440, height=6):
        self.width = width
        self.height = height
        self.canvas = tk.Canvas(parent, width=width, height=height,
                                bg=COL_TROUGH, highlightthickness=0)
        self._rect = self.canvas.create_rectangle(
            0, 0, 0, height, fill=COL_BLUE, width=0)

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)

    def update(self, fraction: float, colour: str = COL_BLUE):
        fraction = max(0.0, min(1.0, fraction))
        w = int(self.width * fraction)
        self.canvas.coords(self._rect, 0, 0, w, self.height)
        self.canvas.itemconfig(self._rect, fill=colour)


# ---------------------------------------------------------------------------
# Fan panel
# ---------------------------------------------------------------------------

class FanPanel:
    """UI block for a single fan with RPM display, bar, and manual control."""

    def __init__(self, parent: tk.Frame, fan: FanInfo,
                 backend: AppleSMCBackend):
        self.fan = fan
        self.backend = backend
        self._slider_active = False  # guard against poll overwriting slider

        # Outer frame
        self.frame = tk.Frame(parent, bg=COL_SURFACE, padx=12, pady=10,
                              highlightbackground=COL_BORDER,
                              highlightthickness=1)

        # Row 1 – title
        tk.Label(self.frame,
                 text=f"Fan {fan.fan_id}: {fan.label}",
                 font=("sans-serif", 11, "bold"),
                 bg=COL_SURFACE, fg=COL_TEXT).pack(anchor="w")

        # Row 2 – current RPM
        rpm_row = tk.Frame(self.frame, bg=COL_SURFACE)
        rpm_row.pack(fill="x", pady=(4, 0))
        tk.Label(rpm_row, text="Current:", font=("sans-serif", 9),
                 bg=COL_SURFACE, fg=COL_DIM).pack(side="left")
        self.rpm_label = tk.Label(rpm_row, text="— RPM",
                                  font=("monospace", 13, "bold"),
                                  bg=COL_SURFACE, fg=COL_TEXT)
        self.rpm_label.pack(side="left", padx=(6, 0))

        # Row 3 – bar
        self.bar = BarCanvas(self.frame, width=440, height=6)
        self.bar.pack(fill="x", pady=(4, 0))

        # Row 4 – range
        self.range_label = tk.Label(self.frame,
                                    text="Range: — – — RPM",
                                    font=("sans-serif", 8),
                                    bg=COL_SURFACE, fg=COL_DIM)
        self.range_label.pack(anchor="w", pady=(2, 0))

        # Row 5 – manual override checkbox
        self.manual_var = tk.BooleanVar(value=False)
        self.manual_cb = tk.Checkbutton(
            self.frame, text="Manual override",
            variable=self.manual_var,
            command=self._on_manual_toggle,
            bg=COL_SURFACE, fg=COL_TEXT,
            selectcolor=COL_TROUGH,
            activebackground=COL_SURFACE,
            activeforeground=COL_TEXT,
            font=("sans-serif", 9))
        self.manual_cb.pack(anchor="w", pady=(6, 0))

        # Row 6 – slider + target readout
        slider_row = tk.Frame(self.frame, bg=COL_SURFACE)
        slider_row.pack(fill="x", pady=(4, 0))

        self.slider_var = tk.IntVar(value=0)
        self.slider = tk.Scale(
            slider_row,
            from_=0, to=6000,
            orient="horizontal",
            variable=self.slider_var,
            command=self._on_slider_move,
            showvalue=False, sliderlength=18,
            bg=COL_SURFACE, fg=COL_TEXT,
            troughcolor=COL_TROUGH,
            highlightthickness=0, bd=0,
            activebackground=COL_ACCENT)
        self.slider.pack(side="left", fill="x", expand=True)
        self.slider.config(state="disabled")

        self.target_label = tk.Label(
            slider_row, text="Auto",
            font=("monospace", 10, "bold"),
            bg=COL_SURFACE, fg=COL_ACCENT,
            width=12, anchor="e")
        self.target_label.pack(side="right", padx=(8, 0))

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    # -- refresh from data model ---------------------------------------------

    def update_display(self):
        fan = self.fan
        colour = rpm_colour(fan.rpm_current, fan.rpm_max)

        # RPM readout
        self.rpm_label.config(text=f"{fan.rpm_current} RPM", fg=colour)

        # Bar
        if fan.rpm_max > fan.rpm_min:
            frac = ((fan.rpm_current - fan.rpm_min)
                    / (fan.rpm_max - fan.rpm_min))
        else:
            frac = 0.0
        self.bar.update(frac, colour)

        # Range text
        self.range_label.config(
            text=f"Range: {fan.rpm_min} – {fan.rpm_max} RPM")

        # Slider limits
        if fan.rpm_min > 0 and fan.rpm_max > 0:
            self.slider.config(from_=fan.rpm_min, to=fan.rpm_max)

        # Sync checkbox without triggering the command
        self.manual_var.set(fan.manual)
        self.slider.config(state="normal" if fan.manual else "disabled")

        if not fan.manual:
            self.target_label.config(text="Auto", fg=COL_ACCENT)
        else:
            self.target_label.config(text=f"{fan.rpm_current} RPM", fg=COL_TEXT)
            self.slider_var.set(fan.rpm_current)

    # -- callbacks -----------------------------------------------------------

    def _on_manual_toggle(self):
        manual = self.manual_var.get()
        try:
            self.backend.set_fan_manual(self.fan.fan_id, manual)
            self.fan.manual = manual
            self.slider.config(state="normal" if manual else "disabled")
            if manual:
                self.slider_var.set(self.fan.rpm_current)
                self.target_label.config(
                    text=f"{self.fan.rpm_current} RPM", fg=COL_TEXT)
            else:
                self.target_label.config(text="Auto", fg=COL_ACCENT)
        except PermissionError:
            self.manual_var.set(False)
            _show_permission_error()
        except OSError as e:
            self.manual_var.set(False)
            messagebox.showwarning("Error",
                                   f"Failed to set fan mode:\n{e}")

    def _on_slider_move(self, _value):
        if not self.fan.manual:
            return
        rpm = self.slider_var.get()
        self.fan.target_rpm = rpm
        self.target_label.config(text=f"{rpm} RPM", fg=COL_TEXT)
        try:
            self.backend.set_fan_speed(self.fan.fan_id, rpm)
        except PermissionError:
            _show_permission_error()
        except OSError as e:
            messagebox.showwarning("Error",
                                   f"Failed to set fan speed:\n{e}")


# ---------------------------------------------------------------------------
# Temperature row
# ---------------------------------------------------------------------------

class TempRow:
    """One row in the temperature grid: label + value."""

    def __init__(self, parent: tk.Frame, row: int, col: int,
                 label_text: str):
        base_col = col * 2
        self.name_lbl = tk.Label(
            parent, text=label_text,
            font=("sans-serif", 9), bg=COL_SURFACE, fg=COL_DIM,
            anchor="w", width=28)
        self.name_lbl.grid(row=row, column=base_col,
                           sticky="w", padx=(8, 4), pady=1)

        self.val_lbl = tk.Label(
            parent, text="  —  ",
            font=("monospace", 10, "bold"), bg=COL_SURFACE, fg=COL_TEXT,
            anchor="e", width=9)
        self.val_lbl.grid(row=row, column=base_col + 1,
                          sticky="e", padx=(0, 14), pady=1)

    def set_value(self, celsius: float):
        self.val_lbl.config(text=f"{celsius:5.1f} °C",
                            fg=temp_colour(celsius))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class App:

    def __init__(self, root: tk.Tk, backend: AppleSMCBackend):
        self.root = root
        self.backend = backend

        root.title("iMac Fan Control")
        root.configure(bg=COL_BG)
        root.minsize(520, 400)

        # Discover hardware
        self.fans = backend.discover_fans()
        self.temp_sensors = backend.discover_temp_sensors()
        self.coretemp_sensors = backend.discover_coretemp_sensors()

        # Set fan2 (HDD) to manual mode and 1850 RPM immediately
        for fan in self.fans:
            if fan.fan_id == 2:
                try:
                    self.backend.set_fan_manual(2, True)
                    self.backend.set_fan_speed(2, 1850)
                    fan.manual = True
                    fan.target_rpm = 1850
                except (PermissionError, OSError):
                    pass

        self._fan_panels: list[FanPanel] = []
        self._temp_rows: list[tuple] = []

        self._build_ui()
        self._poll()

    # -- layout --------------------------------------------------------------

    def _build_ui(self):
        # Scrollable wrapper
        outer = tk.Frame(self.root, bg=COL_BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=COL_BG, highlightthickness=0)
        vscroll = tk.Scrollbar(outer, orient="vertical",
                               command=canvas.yview)
        self._inner = tk.Frame(canvas, bg=COL_BG)
        self._inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=self._inner, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        # Linux mousewheel scrolling
        canvas.bind_all("<Button-4>",
                        lambda e: canvas.yview_scroll(-3, "units"))
        canvas.bind_all("<Button-5>",
                        lambda e: canvas.yview_scroll(3, "units"))

        c = self._inner  # shorthand

        # ── Header ──
        tk.Label(c, text="iMac Fan Control",
                 font=("sans-serif", 16, "bold"),
                 bg=COL_BG, fg=COL_TEXT
                 ).pack(anchor="w", padx=10, pady=(14, 0))
        tk.Label(c,
                 text='iMac 27" Late 2009  ·  applesmc + coretemp',
                 font=("sans-serif", 9),
                 bg=COL_BG, fg=COL_DIM
                 ).pack(anchor="w", padx=10, pady=(0, 10))

        # ── Fans ──
        self._section(c, f"Fans  ({len(self.fans)} detected)")
        for fan in self.fans:
            panel = FanPanel(c, fan, self.backend)
            panel.pack(fill="x", padx=10, pady=(0, 6))
            self._fan_panels.append(panel)

        # ── SMC Temperatures ──
        if self.temp_sensors:
            self._section(
                c,
                f"Apple SMC Temperatures  ({len(self.temp_sensors)} sensors)")
            tf = tk.Frame(c, bg=COL_SURFACE, padx=4, pady=6,
                          highlightbackground=COL_BORDER,
                          highlightthickness=1)
            tf.pack(fill="x", padx=10, pady=(0, 6))
            for i, ts in enumerate(self.temp_sensors):
                r, col = divmod(i, 2)
                tr = TempRow(tf, r, col,
                             f"{ts.description}  [{ts.smc_key}]")
                self._temp_rows.append((ts, tr, ts.index))

        # ── Core Temperatures ──
        if self.coretemp_sensors:
            self._section(
                c,
                f"CPU Core Temperatures"
                f"  ({len(self.coretemp_sensors)} cores)")
            cf = tk.Frame(c, bg=COL_SURFACE, padx=4, pady=6,
                          highlightbackground=COL_BORDER,
                          highlightthickness=1)
            cf.pack(fill="x", padx=10, pady=(0, 6))
            for i, cs in enumerate(self.coretemp_sensors):
                r, col = divmod(i, 2)
                extra = (f"  (high={cs.high_celsius:.0f}°C)"
                         if cs.high_celsius else "")
                tr = TempRow(cf, r, col, f"{cs.label}{extra}")
                self._temp_rows.append((cs, tr, i + 1))

        # ── Status ──
        writable = os.access(APPLESMC_BASE / "fan1_manual", os.W_OK)
        if writable:
            stxt, scol = "Running with write access (root)", COL_GREEN
        else:
            stxt = "⚠  Read-only mode — run with sudo for fan control"
            scol = COL_YELLOW
        tk.Frame(c, bg=COL_BG, height=6).pack()
        tk.Label(c, text=stxt, font=("sans-serif", 8),
                 bg=COL_BG, fg=scol).pack(anchor="w", padx=10, pady=(0, 12))

    def _section(self, parent, text):
        tk.Label(parent, text=text,
                 font=("sans-serif", 10, "bold"),
                 bg=COL_BG, fg=COL_ACCENT
                 ).pack(anchor="w", padx=10, pady=(12, 4))

    # -- polling -------------------------------------------------------------

    def _poll(self):
        for panel in self._fan_panels:
            try:
                self.backend.read_fan(panel.fan)
            except Exception:
                pass
            panel.update_display()

        for sensor, row, idx in self._temp_rows:
            try:
                if isinstance(sensor, TempSensor):
                    self.backend.read_temp(sensor)
                else:
                    self.backend.read_coretemp(sensor, idx)
                row.set_value(sensor.value_celsius)
            except Exception:
                pass

        self.root.after(POLL_INTERVAL_MS, self._poll)

    # -- shutdown ------------------------------------------------------------

    def on_close(self):
        """Restore all fans to automatic mode before exiting."""
        for panel in self._fan_panels:
            if panel.fan.manual:
                try:
                    self.backend.set_fan_manual(panel.fan.fan_id, False)
                except OSError:
                    pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def check_prerequisites() -> Optional[str]:
    if not APPLESMC_BASE.is_dir():
        return (
            f"applesmc sysfs not found at {APPLESMC_BASE}\n\n"
            "Make sure the applesmc kernel module is loaded:\n"
            "  sudo modprobe applesmc\n\n"
            "And optionally:\n"
            "  sudo modprobe coretemp")
    return None


def main():
    error = check_prerequisites()
    if error:
        tmp = tk.Tk()
        tmp.withdraw()
        messagebox.showerror("Prerequisites Not Met", error)
        tmp.destroy()
        sys.exit(1)

    backend = AppleSMCBackend()
    root = tk.Tk()
    app = App(root, backend)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
