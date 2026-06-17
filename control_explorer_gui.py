
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import ctypes
from ctypes import wintypes
import ast
import json
import os
from pathlib import Path
import re
import sys
import traceback
import warnings
import importlib.metadata as importlib_metadata
import webbrowser

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import control as ct

from PIL import Image, ImageDraw, ImageFont, ImageTk
import io
from matplotlib.backends.backend_agg import FigureCanvasAgg

try:
    from matplotlib.backends._backend_tk import add_tooltip
except Exception:
    add_tooltip = None


class ControlExplorerApp(tk.Tk):
    """
    Tkinter GUI for interactive analysis of SISO transfer functions with python-control.

    Main idea:
    - Enter parameters as Python statements, e.g. K_R = 2.0, T_t = np.pi/4
    - Enter a rational transfer function expression using s, e.g.
          K_R / (s**3 + 3*s**2 + 3*s + 1)
    - Enter an optional exact delay for frequency-domain plots, e.g. T_t
    - Nyquist/Bode use exact delay e^{-j omega T_t}
    - Step response uses a Padé approximation of the delay
    """

    SYSTEM_OPEN = r"Offener Kreis L(s)=K(s)G(s)"
    SYSTEM_CLOSED = r"Führungsübertragung Y(s)/W(s)"
    SYSTEM_SENS = "Sensitivität S(s)"
    BODE_UNIT_OMEGA = "rad/s"
    BODE_UNIT_HZ = "Hz"
    DISTURBANCE_INPUT = r"Streckeneingang d_u"
    DISTURBANCE_OUTPUT = r"Streckenausgang d_y"
    APP_NAME = "Control Explorer"
    APP_VERSION_FALLBACK = "0.3.0"
    COPYRIGHT_HOLDER = "Florian Hillitzer"
    APP_LICENSE = "Apache License 2.0"

    DEFAULT_SETTINGS = {
        "omega_min": "0",
        "omega_max": "100",
        "n_points": "10000",
        "bode_x_min": "1e-1",
        "bode_x_max": "1e3",
        "bode_frequency_unit": BODE_UNIT_OMEGA,
        "show_bode_margins": False,
        "controller_enabled": True,
        "prefilter_enabled": False,
        "root_locus_gain_min": "0",
        "root_locus_gain_max": "1e4",
        "root_locus_points": "1000",
        "root_locus_marker_gain": "1",
        "root_locus_gain_parameter": "",
        "root_locus_log_gain": True,
        "root_locus_include_delay": False,
        "root_locus_equal_axis": False,
        "root_locus_show_damping": False,
        "root_locus_damping_ratios": "0.2, 0.4, 0.6, 0.8",
        "t_max": "20",
        "t_points": "2000",
        "step_amplitude": "1",
        "disturbance_amplitude": "2",
        "disturbance_time": "5",
        "disturbance_end_time": "",
        "disturbance_location": DISTURBANCE_OUTPUT,
        "disturbance_settling_tolerance": "2",
        "disturbance_show_reference_component": True,
        "disturbance_show_disturbance_component": True,
        "pade_order": "6",
        "marker_omega": "1",
        "nyquist_plot_system": SYSTEM_OPEN,
        "bode_plot_system": SYSTEM_OPEN,
        "step_plot_system": SYSTEM_CLOSED,
        "auto_update": True,
        "grid": True,
        "equal_axis": True,
        "show_negative_freq": False,
        "show_critical_point": True,
        "normalized_nyquist": False,
        "direction_arrow_omegas": "0.5, 2, 5",
    }
    GLOBAL_SETTING_KEYS = frozenset(
        {
            "auto_update",
            "grid",
            "bode_frequency_unit",
            "show_bode_margins",
            "root_locus_log_gain",
            "root_locus_equal_axis",
            "root_locus_show_damping",
            "root_locus_damping_ratios",
            "disturbance_show_reference_component",
            "disturbance_show_disturbance_component",
            "equal_axis",
            "show_negative_freq",
            "show_critical_point",
            "normalized_nyquist",
            "direction_arrow_omegas",
        }
    )
    EXAMPLE_SETTING_KEYS = frozenset(set(DEFAULT_SETTINGS) - GLOBAL_SETTING_KEYS)

    def __init__(self):
        self._set_windows_app_id()
        super().__init__()
        self._native_icon_handles = []

        self._after_id = None
        self._is_updating = False
        self._settings_window = None
        self._settings_save_after_id = None
        self._loading_settings = False
        self._last_warning_text = ""
        self._control_warnings = []
        self._hover_data = {}
        self._hover_annotations = {}
        self._hover_backgrounds = {}
        self._hover_ready = set()
        self._hover_after_id = None
        self._pending_hover = None
        self._last_hover_target = (None, None)
        self._root_locus_click_data = None

        appdata = Path(os.environ.get("APPDATA", Path.home()))
        self.settings_path = appdata / "ControlExplorer" / "settings.json"
        self.examples_dir = self._documents_directory() / "Control Explorer Examples"
        self.app_version = self._read_version()
        self.current_example_path = None
        self.current_example_var = tk.StringVar(value="Aktuelles Beispiel: Standard")

        self.title(f"{self.APP_NAME} {self.app_version} - Nyquist, Bode, Wurzelortskurve, Sprungantwort, Störaufschaltung")
        self._set_window_icon()
        self.geometry("1300x820")
        self.minsize(1050, 650)

        self._create_variables()
        self._load_settings()
        self._create_menu()
        self._create_layout()
        self._bind_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.schedule_update()

        # wichtig: nach GUI-Aufbau Icon nochmal setzen und dann anzeigen
        self.after(80, self._set_window_icon)
        self.after(120, self.deiconify)

    def _resource_path(self, filename):
        candidates = []

        if getattr(sys, "frozen", False):
            # PyInstaller onefile / onedir internal bundle
            if hasattr(sys, "_MEIPASS"):
                candidates.append(Path(sys._MEIPASS) / filename)

            # Neben der exe
            candidates.append(Path(sys.executable).resolve().parent / filename)

            # PyInstaller 6 onedir: häufig _internal
            candidates.append(Path(sys.executable).resolve().parent / "_internal" / filename)

        # Entwicklungsmodus
        candidates.append(Path(__file__).resolve().parent / filename)

        for path in candidates:
            if path.exists():
                return path

        return candidates[0]

    def _read_version(self):
        version_path = self._resource_path("VERSION")
        try:
            version = version_path.read_text(encoding="utf-8").strip()
        except OSError:
            version = ""
        return version or self.APP_VERSION_FALLBACK

    @staticmethod
    def _set_windows_app_id():
        if os.name != "nt":
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ControlExplorer.GUI.1"
            )
        except (AttributeError, OSError):
            pass

    def _set_window_icon(self):
        png_path = self._resource_path("control_explorer_icon.png")
        ico_path = self._resource_path("control_explorer.ico")

        try:
            if png_path.exists():
                self._logo_image = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._logo_image)
            else:
                self._logo_image = None

            if os.name == "nt" and ico_path.exists():
                self.iconbitmap(str(ico_path), default=str(ico_path))
                self._set_windows_native_icons(ico_path)
        except tk.TclError:
            self._logo_image = None

    def _set_windows_native_icons(self, ico_path):
        try:
            self.update_idletasks()
            user32 = ctypes.windll.user32

            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.LoadImageW.argtypes = [
                wintypes.HINSTANCE,
                wintypes.LPCWSTR,
                wintypes.UINT,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.SendMessageW.restype = wintypes.LPARAM

            hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
            big_size = user32.GetSystemMetrics(11)
            small_size = user32.GetSystemMetrics(49)
            load_from_file = 0x0010
            image_icon = 1

            big_icon = user32.LoadImageW(
                None, str(ico_path), image_icon, big_size, big_size, load_from_file
            )
            small_icon = user32.LoadImageW(
                None, str(ico_path), image_icon, small_size, small_size, load_from_file
            )

            if big_icon:
                user32.SendMessageW(hwnd, 0x0080, 1, big_icon)
                self._native_icon_handles.append(big_icon)
            if small_icon:
                user32.SendMessageW(hwnd, 0x0080, 0, small_icon)
                self._native_icon_handles.append(small_icon)
        except (AttributeError, OSError, tk.TclError):
            pass

    # ------------------------------------------------------------------
    # GUI construction
    # ------------------------------------------------------------------
    def _create_variables(self):
        defaults = self.DEFAULT_SETTINGS
        self.omega_min_var = tk.StringVar(value=defaults["omega_min"])
        self.omega_max_var = tk.StringVar(value=defaults["omega_max"])
        self.n_points_var = tk.StringVar(value=defaults["n_points"])
        self.bode_x_min_var = tk.StringVar(value=defaults["bode_x_min"])
        self.bode_x_max_var = tk.StringVar(value=defaults["bode_x_max"])
        self.bode_frequency_unit_var = tk.StringVar(value=defaults["bode_frequency_unit"])
        self.show_bode_margins_var = tk.BooleanVar(value=defaults["show_bode_margins"])
        self.controller_enabled_var = tk.BooleanVar(value=defaults["controller_enabled"])
        self.prefilter_enabled_var = tk.BooleanVar(value=defaults["prefilter_enabled"])

        self.root_locus_gain_min_var = tk.StringVar(value=defaults["root_locus_gain_min"])
        self.root_locus_gain_max_var = tk.StringVar(value=defaults["root_locus_gain_max"])
        self.root_locus_points_var = tk.StringVar(value=defaults["root_locus_points"])
        self.root_locus_marker_gain_var = tk.StringVar(value=defaults["root_locus_marker_gain"])
        self.root_locus_gain_parameter_var = tk.StringVar(value=defaults["root_locus_gain_parameter"])
        self.root_locus_log_gain_var = tk.BooleanVar(value=defaults["root_locus_log_gain"])
        self.root_locus_include_delay_var = tk.BooleanVar(value=defaults["root_locus_include_delay"])
        self.root_locus_equal_axis_var = tk.BooleanVar(value=defaults["root_locus_equal_axis"])
        self.root_locus_show_damping_var = tk.BooleanVar(value=defaults["root_locus_show_damping"])
        self.root_locus_damping_ratios_var = tk.StringVar(value=defaults["root_locus_damping_ratios"])

        self.t_max_var = tk.StringVar(value=defaults["t_max"])
        self.t_points_var = tk.StringVar(value=defaults["t_points"])
        self.step_amplitude_var = tk.StringVar(value=defaults["step_amplitude"])
        self.disturbance_amplitude_var = tk.StringVar(value=defaults["disturbance_amplitude"])
        self.disturbance_time_var = tk.StringVar(value=defaults["disturbance_time"])
        self.disturbance_end_time_var = tk.StringVar(value=defaults["disturbance_end_time"])
        self.disturbance_location_var = tk.StringVar(value=defaults["disturbance_location"])
        self.disturbance_settling_tolerance_var = tk.StringVar(value=defaults["disturbance_settling_tolerance"])
        self.disturbance_show_reference_component_var = tk.BooleanVar(
            value=defaults["disturbance_show_reference_component"]
        )
        self.disturbance_show_disturbance_component_var = tk.BooleanVar(
            value=defaults["disturbance_show_disturbance_component"]
        )

        self.pade_order_var = tk.StringVar(value=defaults["pade_order"])
        self.marker_omega_var = tk.StringVar(value=defaults["marker_omega"])

        self.nyquist_plot_system_var = tk.StringVar(value=defaults["nyquist_plot_system"])
        self.bode_plot_system_var = tk.StringVar(value=defaults["bode_plot_system"])
        self.step_plot_system_var = tk.StringVar(value=defaults["step_plot_system"])
        self.auto_update_var = tk.BooleanVar(value=defaults["auto_update"])
        self.grid_var = tk.BooleanVar(value=defaults["grid"])
        self.equal_axis_var = tk.BooleanVar(value=defaults["equal_axis"])
        self.show_negative_freq_var = tk.BooleanVar(value=defaults["show_negative_freq"])
        self.show_critical_point_var = tk.BooleanVar(value=defaults["show_critical_point"])
        self.normalized_nyquist_var = tk.BooleanVar(value=defaults["normalized_nyquist"])
        self.direction_arrow_positions_var = tk.StringVar(value=defaults["direction_arrow_omegas"])

    def _settings_variables(self):
        return {
            "omega_min": self.omega_min_var,
            "omega_max": self.omega_max_var,
            "n_points": self.n_points_var,
            "bode_x_min": self.bode_x_min_var,
            "bode_x_max": self.bode_x_max_var,
            "bode_frequency_unit": self.bode_frequency_unit_var,
            "show_bode_margins": self.show_bode_margins_var,
            "controller_enabled": self.controller_enabled_var,
            "prefilter_enabled": self.prefilter_enabled_var,
            "root_locus_gain_min": self.root_locus_gain_min_var,
            "root_locus_gain_max": self.root_locus_gain_max_var,
            "root_locus_points": self.root_locus_points_var,
            "root_locus_marker_gain": self.root_locus_marker_gain_var,
            "root_locus_gain_parameter": self.root_locus_gain_parameter_var,
            "root_locus_log_gain": self.root_locus_log_gain_var,
            "root_locus_include_delay": self.root_locus_include_delay_var,
            "root_locus_equal_axis": self.root_locus_equal_axis_var,
            "root_locus_show_damping": self.root_locus_show_damping_var,
            "root_locus_damping_ratios": self.root_locus_damping_ratios_var,
            "t_max": self.t_max_var,
            "t_points": self.t_points_var,
            "step_amplitude": self.step_amplitude_var,
            "disturbance_amplitude": self.disturbance_amplitude_var,
            "disturbance_time": self.disturbance_time_var,
            "disturbance_end_time": self.disturbance_end_time_var,
            "disturbance_location": self.disturbance_location_var,
            "disturbance_settling_tolerance": self.disturbance_settling_tolerance_var,
            "disturbance_show_reference_component": self.disturbance_show_reference_component_var,
            "disturbance_show_disturbance_component": self.disturbance_show_disturbance_component_var,
            "pade_order": self.pade_order_var,
            "marker_omega": self.marker_omega_var,
            "nyquist_plot_system": self.nyquist_plot_system_var,
            "bode_plot_system": self.bode_plot_system_var,
            "step_plot_system": self.step_plot_system_var,
            "auto_update": self.auto_update_var,
            "grid": self.grid_var,
            "equal_axis": self.equal_axis_var,
            "show_negative_freq": self.show_negative_freq_var,
            "show_critical_point": self.show_critical_point_var,
            "normalized_nyquist": self.normalized_nyquist_var,
            "direction_arrow_omegas": self.direction_arrow_positions_var,
        }

    def _settings_snapshot(self, keys=None):
        variables = self._settings_variables()
        selected_keys = variables.keys() if keys is None else keys
        return {key: variables[key].get() for key in selected_keys if key in variables}

    def _global_settings_snapshot(self):
        return self._settings_snapshot(self.GLOBAL_SETTING_KEYS)

    def _example_settings_snapshot(self):
        return self._settings_snapshot(self.EXAMPLE_SETTING_KEYS)

    @staticmethod
    def _settings_subset(settings, keys):
        if not isinstance(settings, dict):
            return {}
        return {key: settings[key] for key in keys if key in settings}

    def _normalize_system_selection(self, selected):
        legacy_system_labels = {
            r"Offener Kreis G_0(s)": self.SYSTEM_OPEN,
            r"Offener Kreis G₀(s)": self.SYSTEM_OPEN,
            r"Geschlossener Kreis G(s)": self.SYSTEM_CLOSED,
        }
        return legacy_system_labels.get(selected, selected)

    def _normalize_settings(self, settings):
        normalized = dict(settings)
        valid_system_labels = {self.SYSTEM_OPEN, self.SYSTEM_CLOSED, self.SYSTEM_SENS}
        for key in ("nyquist_plot_system", "bode_plot_system", "step_plot_system"):
            value = self._normalize_system_selection(normalized.get(key))
            if value is not None and value not in valid_system_labels:
                normalized[key] = self.DEFAULT_SETTINGS[key]
            elif value is not None:
                normalized[key] = value
        if normalized.get("disturbance_location") not in (None, self.DISTURBANCE_INPUT, self.DISTURBANCE_OUTPUT):
            normalized["disturbance_location"] = self.DEFAULT_SETTINGS["disturbance_location"]
        return normalized

    def _apply_settings(self, settings):
        settings = self._normalize_settings(settings)
        self._loading_settings = True
        try:
            for key, variable in self._settings_variables().items():
                if key in settings:
                    variable.set(settings[key])
        finally:
            self._loading_settings = False

    def _load_settings(self):
        if not self.settings_path.exists():
            return

        try:
            with self.settings_path.open("r", encoding="utf-8") as handle:
                settings = json.load(handle)
            if not isinstance(settings, dict):
                raise ValueError("Die Einstellungsdatei enthält kein JSON-Objekt.")
            self._apply_settings(self._settings_subset(settings, self.GLOBAL_SETTING_KEYS))
        except Exception as exc:
            messagebox.showwarning(
                "Einstellungen",
                f"Die gespeicherten Einstellungen konnten nicht geladen werden. Werkseinstellungen werden verwendet.\n\n{exc}",
            )

    def _save_settings(self):
        self._settings_save_after_id = None
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with self.settings_path.open("w", encoding="utf-8") as handle:
                json.dump(self._global_settings_snapshot(), handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.status_var.set(f"Einstellungen konnten nicht gespeichert werden: {exc}")

    def _schedule_settings_save(self):
        if self._loading_settings:
            return
        if self._settings_save_after_id is not None:
            self.after_cancel(self._settings_save_after_id)
        self._settings_save_after_id = self.after(500, self._save_settings)

    def reset_settings(self):
        if not messagebox.askyesno("Werkseinstellungen", "Alle Einstellungen auf Werkseinstellungen zurücksetzen?"):
            return
        self._apply_settings(self.DEFAULT_SETTINGS)
        self._save_settings()
        self.update_plots()

    def _on_close(self):
        if self._settings_save_after_id is not None:
            self.after_cancel(self._settings_save_after_id)
        if self._hover_after_id is not None:
            self.after_cancel(self._hover_after_id)
        self._save_settings()
        native_icon_handles = list(self._native_icon_handles)
        self.destroy()
        if os.name == "nt":
            for icon_handle in native_icon_handles:
                ctypes.windll.user32.DestroyIcon(icon_handle)

    def _create_menu(self):
        menu_bar = tk.Menu(self)

        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(label="Einstellungen öffnen...", command=self._open_settings_window)

        menu_bar.add_cascade(label="Einstellungen", menu=settings_menu)
        menu_bar.add_command(label="Hilfe", command=lambda: self._open_markdown_window("Hilfe", "docs/help.md", self._help_text()))
        menu_bar.add_command(
            label="Über / Lizenz",
            command=lambda: self._open_markdown_window("Über / Lizenz", "docs/legal.md", self._legal_text()),
        )
        self.config(menu=menu_bar)

    def _open_direction_arrow_settings(self):
        self._open_settings_window()

    def _open_settings_window(self, initial_tab=None):
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            if initial_tab is not None:
                try:
                    notebook = self._settings_window.notebook
                    tab_widgets = getattr(self._settings_window, "_tab_widgets", {})
                    if initial_tab in tab_widgets:
                        notebook.select(tab_widgets[initial_tab])
                except Exception:
                    pass
            return

        dialog = tk.Toplevel(self)
        self._settings_window = dialog
        dialog.title("Einstellungen")
        dialog.transient(self)
        dialog.geometry("760x640")
        dialog.minsize(700, 560)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings_window(dialog))

        notebook = ttk.Notebook(dialog)
        dialog.notebook = notebook
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        tab_nyquist = ttk.Frame(notebook, padding=10)
        tab_freq = ttk.Frame(notebook, padding=10)
        tab_root_locus = ttk.Frame(notebook, padding=10)
        tab_step = ttk.Frame(notebook, padding=10)
        tab_disturbance = ttk.Frame(notebook, padding=10)
        tab_general = ttk.Frame(notebook, padding=10)

        notebook.add(tab_nyquist, text="Nyquist / Ortskurve")
        notebook.add(tab_freq, text="Frequenz / Bode")
        notebook.add(tab_root_locus, text="Wurzelortskurve")
        notebook.add(tab_step, text="Sprungantwort")
        notebook.add(tab_disturbance, text="Störaufschaltung")
        notebook.add(tab_general, text="Allgemein")

        dialog._tab_widgets = {
            "Nyquist / Ortskurve": tab_nyquist,
            "Frequenz / Bode": tab_freq,
            "Wurzelortskurve": tab_root_locus,
            "Sprungantwort": tab_step,
            "Störaufschaltung": tab_disturbance,
            "Allgemein": tab_general,
        }

        for tab in (tab_nyquist, tab_freq, tab_root_locus, tab_step, tab_disturbance, tab_general):
            tab.columnconfigure(0, weight=1)

        self._create_nyquist_settings(tab_nyquist)
        self._create_frequency_settings(tab_freq)
        self._create_root_locus_settings(tab_root_locus)
        self._create_step_settings(tab_step)
        self._create_disturbance_settings(tab_disturbance)
        self._create_general_settings(tab_general)

        if initial_tab is not None and initial_tab in dialog._tab_widgets:
            notebook.select(dialog._tab_widgets[initial_tab])

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        button_frame.columnconfigure(0, weight=1)
        ttk.Button(button_frame, text="Aktualisieren", command=self.update_plots).grid(row=0, column=0, sticky="w")
        ttk.Button(button_frame, text="Werkseinstellungen", command=self.reset_settings).grid(row=0, column=1, padx=6)
        ttk.Button(button_frame, text="Schließen", command=lambda: self._close_settings_window(dialog)).grid(row=0, column=2, sticky="e")

    def _close_settings_window(self, dialog):
        if dialog.winfo_exists():
            dialog.destroy()
        if self._settings_window is dialog:
            self._settings_window = None

    def _create_general_settings(self, parent):
        ttk.Checkbutton(
            parent,
            text="Auto-Update",
            variable=self.auto_update_var,
            command=self.schedule_update,
        ).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Checkbutton(
            parent,
            text="Grid anzeigen",
            variable=self.grid_var,
            command=self.schedule_update,
        ).grid(row=1, column=0, sticky="w", pady=3)

    def _create_frequency_settings(self, parent):
        range_box = ttk.LabelFrame(parent, text="Berechnungsbereich der Ortskurve")
        range_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        range_box.columnconfigure(0, weight=1)
        self._add_entry(range_box, "omega_min", self.omega_min_var, 0, 0)
        self._add_entry(range_box, "omega_max", self.omega_max_var, 1, 0)
        self._add_entry(range_box, "Punkte", self.n_points_var, 2, 0)

        bode_box = ttk.LabelFrame(parent, text="Bode-Frequenzskala")
        bode_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        bode_box.columnconfigure(0, weight=1)
        self._add_entry(bode_box, "Linke Grenze", self.bode_x_min_var, 0, 0)
        self._add_entry(bode_box, "Rechte Grenze", self.bode_x_max_var, 1, 0)
        unit_frame = ttk.Frame(bode_box)
        unit_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=3)
        unit_frame.columnconfigure(1, weight=1)
        ttk.Label(unit_frame, text="Frequenzeinheit").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Combobox(
            unit_frame,
            textvariable=self.bode_frequency_unit_var,
            values=[self.BODE_UNIT_OMEGA, self.BODE_UNIT_HZ],
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky="ew")
        ttk.Label(
            bode_box,
            text="Die Grenzen werden in der gewählten Einheit interpretiert.",
            foreground="#555555",
        ).grid(row=3, column=0, sticky="w", padx=6, pady=(2, 6))

        marker_frame = ttk.Frame(parent)
        marker_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=3)
        marker_frame.columnconfigure(1, weight=1)
        ttk.Label(marker_frame, text="Marker-omega").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(marker_frame, textvariable=self.marker_omega_var).grid(row=0, column=1, sticky="ew")

    def _create_step_settings(self, parent):
        self._add_entry(parent, "t_max", self.t_max_var, 0, 0)
        self._add_entry(parent, "Punkte", self.t_points_var, 1, 0)
        self._add_entry(parent, "Sprungfaktor A", self.step_amplitude_var, 2, 0)
        self._add_entry(parent, "Padé-Ordnung", self.pade_order_var, 3, 0)
        ttk.Label(
            parent,
            text=(
                "Die Padé-Ordnung ersetzt die Totzeit im Zeitbereich durch eine rationale Näherung. "
                "Kleine Werte rechnen schneller, bilden die Totzeit aber grober ab. Größere Werte sind im relevanten "
                "Frequenzbereich genauer, erhöhen jedoch Systemordnung, Rechenzeit und das Risiko numerischer Probleme. "
                "Werte zwischen 3 und 8 sind meist ein sinnvoller Ausgangspunkt."
            ),
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).grid(row=4, column=0, sticky="w", padx=6, pady=(10, 0))

    def _create_disturbance_settings(self, parent):
        signal_box = ttk.LabelFrame(parent, text="Störsignal")
        signal_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        signal_box.columnconfigure(0, weight=1)
        location_frame = ttk.Frame(signal_box)
        location_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=3)
        location_frame.columnconfigure(1, weight=1)
        ttk.Label(location_frame, text="Störort").grid(row=0, column=0, sticky="w", padx=(0, 6))
        location_combo = ttk.Combobox(
            location_frame,
            textvariable=self.disturbance_location_var,
            values=[self.DISTURBANCE_INPUT, self.DISTURBANCE_OUTPUT],
            state="readonly",
        )
        location_combo.grid(row=0, column=1, sticky="ew")
        location_combo.bind("<<ComboboxSelected>>", lambda _event: self.schedule_update())
        self._add_entry(signal_box, "Amplitude d_0 [V]", self.disturbance_amplitude_var, 1, 0)
        self._add_entry(signal_box, "Startzeit t_d [s]", self.disturbance_time_var, 2, 0)
        self._add_entry(signal_box, "Endzeit t_e [s]", self.disturbance_end_time_var, 3, 0)
        self._add_entry(signal_box, "Ausregel-Toleranz [%]", self.disturbance_settling_tolerance_var, 4, 0)

        display_box = ttk.LabelFrame(parent, text="Darstellung")
        display_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        display_box.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            display_box,
            text="Führungsanteil y_w(t) anzeigen",
            variable=self.disturbance_show_reference_component_var,
            command=self.schedule_update,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Checkbutton(
            display_box,
            text="Störanteil anzeigen",
            variable=self.disturbance_show_disturbance_component_var,
            command=self.schedule_update,
        ).grid(row=1, column=0, sticky="w", padx=6, pady=3)

        ttk.Label(
            parent,
            text=(
                "Die Störung kann als d_u additiv am Streckeneingang oder als d_y additiv am Streckenausgang wirken. "
                "Der Führungssprung w(t) nutzt den Sprungfaktor A aus dem Reiter Sprung. "
                "Leere Endzeit bedeutet: Die Störung bleibt bis zum Simulationsende aktiv."
            ),
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).grid(row=2, column=0, sticky="w", padx=6)

    def _create_root_locus_settings(self, parent):
        gain_box = ttk.LabelFrame(parent, text="Zusatzverstärkung K")
        gain_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        gain_box.columnconfigure(0, weight=1)
        self._add_entry(gain_box, "K min", self.root_locus_gain_min_var, 0, 0)
        self._add_entry(gain_box, "K max", self.root_locus_gain_max_var, 1, 0)
        self._add_entry(gain_box, "Punkte", self.root_locus_points_var, 2, 0)
        ttk.Checkbutton(
            gain_box,
            text="K logarithmisch abtasten",
            variable=self.root_locus_log_gain_var,
            command=self.schedule_update,
        ).grid(row=3, column=0, sticky="w", padx=6, pady=3)

        display_box = ttk.LabelFrame(parent, text="Darstellung")
        display_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        display_box.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            display_box,
            text="Totzeit mit Padé-Approximation berücksichtigen",
            variable=self.root_locus_include_delay_var,
            command=self.schedule_update,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Checkbutton(
            display_box,
            text="gleiche Skalierung für Real- und Imaginärachse",
            variable=self.root_locus_equal_axis_var,
            command=self.schedule_update,
        ).grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Checkbutton(
            display_box,
            text="Linien konstanten Dämpfungsgrades anzeigen",
            variable=self.root_locus_show_damping_var,
            command=self.schedule_update,
        ).grid(row=2, column=0, sticky="w", padx=6, pady=3)
        self._add_entry(
            display_box,
            "Dämpfungsgrade zeta",
            self.root_locus_damping_ratios_var,
            3,
            0,
        )
        ttk.Label(
            parent,
            text=(
                "Gezeichnet werden die Pole von 1 + K L_0(s) = 0. "
                "Bei Totzeit entstehen durch Padé zusätzliche approximierte Pole und Nullstellen."
            ),
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).grid(row=2, column=0, sticky="w", padx=6)

    def _create_nyquist_settings(self, parent):
        ttk.Checkbutton(parent, text="axis equal", variable=self.equal_axis_var, command=self.schedule_update).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(
            parent,
            text="Gleiche Skalierung: Eine Einheit auf Real- und Imaginärachse wird gleich lang dargestellt; die Ortskurve wird nicht geometrisch verzerrt.",
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", padx=(22, 0), pady=(0, 6))
        ttk.Checkbutton(parent, text="negative Frequenzen spiegeln", variable=self.show_negative_freq_var, command=self.schedule_update).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="kritischen Punkt -1 zeigen", variable=self.show_critical_point_var, command=self.schedule_update).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="normierte Ortskurve ohne Zahlen/Raster", variable=self.normalized_nyquist_var, command=self.schedule_update).grid(row=4, column=0, sticky="w", pady=3)

        arrow_frame = ttk.LabelFrame(parent, text="Richtungspfeile")
        arrow_frame.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        arrow_frame.columnconfigure(1, weight=1)
        ttk.Label(arrow_frame, text="omega-Werte").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(arrow_frame, textvariable=self.direction_arrow_positions_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(
            arrow_frame,
            text="Ein Pfeil pro angegebenem omega-Wert, getrennt durch Kommas.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

    @staticmethod
    def _set_readonly_text(widget, text):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _open_markdown_window(self, title, markdown_path, fallback_markdown):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.geometry("920x760")
        dialog.minsize(760, 560)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_widget = ScrolledText(dialog, wrap=tk.WORD, padx=18, pady=14)
        text_widget.grid(row=0, column=0, sticky="nsew")
        markdown = self._read_markdown_resource(markdown_path, fallback_markdown)
        self._render_markdown(text_widget, markdown)

        ttk.Button(dialog, text="Schließen", command=dialog.destroy).grid(
            row=1,
            column=0,
            sticky="e",
            padx=10,
            pady=(0, 10),
        )

    def _read_markdown_resource(self, filename, fallback_text):
        path = self._resource_path(filename)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = fallback_text
        replacements = {
            "APP_NAME": self.APP_NAME,
            "APP_VERSION": self.app_version,
            "COPYRIGHT_HOLDER": self.COPYRIGHT_HOLDER,
            "APP_LICENSE": self.APP_LICENSE,
            "THIRD_PARTY_NOTICES": self._third_party_notice_text(),
        }
        for key, value in replacements.items():
            text = text.replace("{{" + key + "}}", value)
        return text

    def _render_markdown(self, widget, markdown):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget._markdown_images = []

        widget.tag_configure("h1", font=("Segoe UI", 18, "bold"), spacing1=10, spacing3=8)
        widget.tag_configure("h2", font=("Segoe UI", 14, "bold"), spacing1=10, spacing3=5)
        widget.tag_configure("h3", font=("Segoe UI", 11, "bold"), spacing1=8, spacing3=4)
        widget.tag_configure("body", font=("Segoe UI", 10), spacing3=4)
        widget.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        widget.tag_configure("code", font=("Consolas", 9), background="#f0f0f0")
        widget.tag_configure("list", lmargin1=20, lmargin2=38, spacing3=3)
        widget.tag_configure("rule", foreground="#888888")
        widget.tag_configure("link", foreground="#0645ad", underline=True)

        self._insert_brand_logos(widget)

        in_code_block = False
        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                widget.insert(tk.END, line + "\n", ("code",))
                continue
            if not line.strip():
                widget.insert(tk.END, "\n")
                continue
            if line.startswith("# "):
                widget.insert(tk.END, line[2:].strip() + "\n", ("h1",))
            elif line.startswith("## "):
                widget.insert(tk.END, line[3:].strip() + "\n", ("h2",))
            elif line.startswith("### "):
                widget.insert(tk.END, line[4:].strip() + "\n", ("h3",))
            elif line.startswith("- "):
                widget.insert(tk.END, "- ", ("list",))
                self._insert_markdown_inline(widget, line[2:].strip(), ("list",))
                widget.insert(tk.END, "\n", ("list",))
            elif set(line.strip()) <= {"-"} and len(line.strip()) >= 3:
                widget.insert(tk.END, "-" * 72 + "\n", ("rule",))
            else:
                self._insert_markdown_inline(widget, line, ("body",))
                widget.insert(tk.END, "\n", ("body",))

        widget.configure(state=tk.DISABLED)

    def _insert_markdown_inline(self, widget, text, base_tags):
        pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")
        position = 0
        for match in pattern.finditer(text):
            if match.start() > position:
                widget.insert(tk.END, text[position:match.start()], base_tags)
            token = match.group(0)
            if token.startswith("**"):
                widget.insert(tk.END, token[2:-2], base_tags + ("bold",))
            elif token.startswith("`"):
                widget.insert(tk.END, token[1:-1], base_tags + ("code",))
            else:
                label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
                tag_name = f"link_{len(widget.tag_names())}_{match.start()}"
                widget.insert(tk.END, label, base_tags + ("link", tag_name))
                widget.tag_bind(tag_name, "<Button-1>", lambda _event, link=url: webbrowser.open(link))
            position = match.end()
        if position < len(text):
            widget.insert(tk.END, text[position:], base_tags)

    def _insert_brand_logos(self, widget):  
        ce_logo = self._load_ce_logo_image()
        mrm_logo = self._load_mrm_logo_image()
        logos = [image for image in (ce_logo, mrm_logo) if image is not None]
        if not logos:
            return

        target_height = 88
        gap = 18
        resized_logos = []
        for image in logos:
            scale = min(1.0, target_height / image.height)
            resized_logos.append(
                image.resize(
                    (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                    Image.LANCZOS,
                )
            )

        total_width = sum(image.width for image in resized_logos) + gap * (len(resized_logos) - 1)
        max_width = 660
        if total_width > max_width:
            scale = max_width / total_width
            resized_logos = [
                image.resize(
                    (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                    Image.LANCZOS,
                )
                for image in resized_logos
            ]
            total_width = sum(image.width for image in resized_logos) + gap * (len(resized_logos) - 1)

        height = max(image.height for image in resized_logos)
        combined = Image.new("RGBA", (total_width, height), "white")
        x = 0
        for image in resized_logos:
            y = (height - image.height) // 2
            combined.alpha_composite(image, (x, y))
            x += image.width + gap

        photo = ImageTk.PhotoImage(combined)
        widget._markdown_images.append(photo)
        widget.image_create(tk.END, image=photo)
        widget.insert(tk.END, "\n\n")

    def _load_ce_logo_image(self):
        for filename in (
            "control_explorer_logo.png",
            "ce_logo.png",
            "control_explorer_icon.png",
            "assets/control_explorer_logo.png",
            "assets/ce_logo.png",
            "docs/control_explorer_logo.png",
        ):
            path = self._resource_path(filename)
            if path.exists():
                try:
                    with Image.open(path) as image:
                        return image.convert("RGBA")
                except OSError:
                    pass
        return None

    def _load_mrm_logo_image(self):
        for filename in ("mrm_logo.png", "assets/mrm_logo.png", "docs/mrm_logo.png"):
            path = self._resource_path(filename)
            if path.exists():
                try:
                    with Image.open(path) as image:
                        return image.convert("RGBA")
                except OSError:
                    pass
        return self._generated_mrm_logo_image()

    @staticmethod
    def _generated_mrm_logo_image():
        width, height = 720, 180
        image = Image.new("RGBA", (width, height), "white")
        draw = ImageDraw.Draw(image)
        try:
            font_big = ImageFont.truetype("arialbd.ttf", 78)
            font_small = ImageFont.truetype("arial.ttf", 34)
        except OSError:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()
        red = "#aa2035"
        black = "#1f1f1f"
        draw.arc((140, 16, 360, 166), start=110, end=260, fill=red, width=10)
        draw.arc((350, 32, 430, 150), start=-70, end=70, fill=black, width=9)
        draw.text((18, 58), "MRM", fill="black", font=font_big)
        draw.text((455, 52), "Mess-, Regel- und", fill=black, font=font_small)
        draw.text((455, 96), "Mikrotechnik", fill=black, font=font_small)
        return image

    @staticmethod
    def _package_version(package_name):
        try:
            return importlib_metadata.version(package_name)
        except importlib_metadata.PackageNotFoundError:
            return "nicht installiert / nicht im Python-Metadatensystem gefunden"

    def _third_party_notice_text(self):
        packages = [
            ("python-control", "control", "BSD-3-Clause"),
            ("Matplotlib", "matplotlib", "Matplotlib License"),
            ("NumPy", "numpy", "BSD-3-Clause; binäre Wheels können OpenBLAS/LAPACK enthalten"),
            ("SciPy", "scipy", "BSD-3-Clause; binäre Wheels können OpenBLAS/LAPACK enthalten"),
            ("Pillow", "Pillow", "HPND/Pillow License"),
            ("PyInstaller", "PyInstaller", "GPL-2.0-or-later mit Bootloader-Ausnahme (nur Build/Packaging)"),
        ]
        lines = ["Verwendete Open-Source-Komponenten:"]
        for display_name, package_name, license_name in packages:
            lines.append(
                f"- {display_name}: Version {self._package_version(package_name)}, Lizenz: {license_name}"
            )
        lines.append("")
        lines.append(
            "Die vollständigen Lizenztexte der Drittkomponenten liegen in den jeweiligen "
            "Python-Paketen bzw. Projektveröffentlichungen. Beim Weitergeben eines gebauten "
            "Programmpakets sollten diese Lizenz- und Copyright-Hinweise mit ausgeliefert werden."
        )
        return "\n".join(lines)

    def _legal_text(self):
        return (
            f"{self.APP_NAME}\n"
            f"Version: {self.app_version}\n\n"
            "Impressum / Herausgeber\n"
            "----------------------\n"
            f"Copyright (c) 2026 {self.COPYRIGHT_HOLDER}\n"
            "Projekt: Control Explorer\n"
            "Zweck: Lehr- und Analysewerkzeug für SISO-Regelkreise im regelungstechnischen Praktikum.\n"
            "Kontakt / dienstliche Anschrift: bitte vor externer Weitergabe mit der offiziellen Institutsangabe ergänzen.\n\n"
            "Lizenz\n"
            "------\n"
            f"Control Explorer steht unter der {self.APP_LICENSE}.\n"
            "Kurzfassung: Nutzung, Kopieren, Verändern und Weitergabe sind erlaubt, solange Lizenz- "
            "und Copyright-Hinweise erhalten bleiben. Die Software wird ohne Gewährleistung bereitgestellt.\n"
            "Maßgeblich ist der vollständige Lizenztext in der Datei LICENSE.\n\n"
            + self._third_party_notice_text()
        )

    def _help_text(self):
        return (
            "Gebrauchsanweisung\n"
            "==================\n\n"
            "1. Grundmodell\n"
            "Der Control Explorer geht von einem Standardregelkreis mit Einheitsrückführung aus. "
            "Links werden Parameter, optionaler Vorfilter V(s), Regler K(s), Strecke G(s) und Totzeit definiert. "
            "Der offene Kreis für Nyquist, Bode und Wurzelortskurve ist L(s)=K(s)G(s). Der Vorfilter wirkt nur "
            "auf die Führungsgröße w(t).\n\n"
            "2. Eingaben\n"
            "Parameter werden im Parameterfeld als Python-Code definiert, zum Beispiel K_R = 2.0 oder T_t = 0.16. "
            "Die Variable s ist bereits als TransferFunction.s vorbereitet. Übertragungsfunktionen können daher "
            "direkt als Ausdrücke wie K_R * (1 + 1/(T_I*s)) oder 1/(s**2 + 2*s + 1) eingegeben werden.\n\n"
            "3. Aktualisieren und Beispiele\n"
            "Mit Aktualisieren werden alle Darstellungen neu berechnet. Beispiele können gespeichert und geladen "
            "werden; der Standardordner ist 'Control Explorer Examples' im Dokumente-Ordner. "
            "Beispiele speichern Modell- und Analyseparameter; reine Anzeige- und Bedienvorlieben bleiben globale "
            "Programmeinstellungen.\n\n"
            "4. Nyquist / Ortskurve\n"
            "Der Tab zeigt wahlweise den offenen Kreis, die Führungsübertragung oder die Sensitivität. Für "
            "Stabilitätsbetrachtungen ist meist der offene Kreis mit kritischem Punkt -1 relevant. Richtungspfeile "
            "können in den Einstellungen über omega-Werte gesetzt werden.\n\n"
            "5. Frequenzgang / Bode\n"
            "Bode-Grenzen und Frequenzeinheit werden unter Einstellungen > Frequenz gesetzt. Die Totzeit wird im "
            "Frequenzbereich exakt als exp(-j omega T) berücksichtigt. Amplituden- und Phasenreserve können "
            "eingeblendet werden.\n\n"
            "6. Wurzelortskurve\n"
            "Die WOK basiert auf dem offenen Kreis ohne Vorfilter. Ein Klick auf die Kurve übernimmt den passenden "
            "Gain in den Parametercode bzw. in den markierten Gain-Parameter. Mehrfachpole werden mit ihrer "
            "Vielfachheit gekennzeichnet. Totzeit kann optional über Padé approximiert werden.\n\n"
            "7. Sprungantwort\n"
            "Die Sprungantwort nutzt die Zeitachse, den Sprungfaktor und die Padé-Ordnung aus Einstellungen > Sprung. "
            "Bei aktivem Vorfilter wird für die Führungsantwort V(s)L(s)/(1+L(s)) verwendet.\n\n"
            "8. Störaufschaltung\n"
            "Die Störung kann als d_u additiv am Streckeneingang oder als d_y additiv am Streckenausgang wirken. "
            "Amplitude, Startzeit, optionale Endzeit, Toleranz "
            "und Komponentenanzeige liegen unter Einstellungen > Störung. Eine leere Endzeit bedeutet, dass die "
            "Störung bis zum Simulationsende aktiv bleibt.\n\n"
            "9. Grenzen und Didaktik\n"
            "Der Explorer soll Rechnen und Visualisieren beschleunigen, ersetzt aber nicht das Verständnis. "
            "Studierende sollten zu jeder Darstellung formulieren können, welcher Übertragungspfad geplottet wird "
            "und welche Annahmen gelten, besonders bei Totzeit, Padé-Approximation und Stabilitätsreserven."
        )

    def _create_layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(paned)
        right = ttk.Frame(paned, padding=6)

        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self._create_left_panel(left)
        self._create_right_panel(right)

        self.output_var = tk.StringVar(value="")
        self.output_label = tk.Label(
            self,
            textvariable=self.output_var,
            anchor="w",
            justify="left",
            padx=8,
            pady=5,
            bg="#fff4cc",
            fg="#5a3d00",
        )
        self.output_label.grid(row=1, column=0, sticky="ew")
        self.output_label.grid_remove()
        self.output_label.bind(
            "<Configure>",
            lambda event: self.output_label.configure(wraplength=max(100, event.width - 16)),
        )

        self.status_var = tk.StringVar(value="Bereit.")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN, padding=(6, 3))
        status.grid(row=2, column=0, sticky="ew")

    def _refresh_hover_state_after_layout_change(self):
        self._pending_hover = None
        self._last_hover_target = (None, None)
        for annotation in self._hover_annotations.values():
            if annotation.get_visible():
                annotation.set_visible(False)
        for ax in list(self._hover_backgrounds):
            self._hover_backgrounds.pop(ax, None)
        self._hover_ready.clear()
        self.update_idletasks()
        for canvas in (
            self.canvas_nyquist,
            self.canvas_bode,
            self.canvas_root_locus,
            self.canvas_step,
            self.canvas_disturbance,
        ):
            canvas.draw_idle()

    def _set_output_message(self, message="", level="warning"):
        if not hasattr(self, "output_label"):
            return

        if not message:
            self.output_var.set("")
            self.output_label.grid_remove()
            self._refresh_hover_state_after_layout_change()
            return

        colors = {
            "warning": ("#fff4cc", "#5a3d00"),
            "error": ("#ffe5e5", "#7a1111"),
            "info": ("#eef5ff", "#234d73"),
        }
        background, foreground = colors.get(level, colors["warning"])
        self.output_label.configure(bg=background, fg=foreground)
        self.output_var.set(message)
        self.output_label.grid()
        self._refresh_hover_state_after_layout_change()

    def _create_left_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, width=500)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        content = ttk.Frame(canvas, padding=8)
        content.columnconfigure(0, weight=1)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_content_width(event):
            canvas.itemconfigure(content_window, width=event.width)

        def on_mousewheel(event):
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
            else:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        def bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_content_width)
        parent.bind("<Enter>", bind_mousewheel)
        parent.bind("<Leave>", unbind_mousewheel)
        canvas.bind("<Enter>", bind_mousewheel)
        content.bind("<Enter>", bind_mousewheel)

        self._create_left_panel_content(content)

    def _create_left_panel_content(self, parent):
        block_frame = ttk.LabelFrame(parent, text="Standardregelkreis")
        block_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        block_frame.columnconfigure(0, weight=1)
        self.fig_block = Figure(figsize=(4.8, 1.65), dpi=100)
        self.ax_block = self.fig_block.add_subplot(111)
        self.ax_block.axis("off")
        self.canvas_block = FigureCanvasTkAgg(self.fig_block, master=block_frame)
        self.canvas_block.get_tk_widget().grid(row=0, column=0, sticky="ew")

        title = ttk.Label(parent, text="Eingaben", font=("Segoe UI", 12, "bold"))
        title.grid(row=1, column=0, sticky="w", pady=(0, 8))

        ttk.Label(parent, text="Strecke G(s)").grid(row=2, column=0, sticky="w")
        self.plant_text = ScrolledText(parent, height=3, width=48, wrap=tk.WORD)
        self.plant_text.grid(row=3, column=0, sticky="ew", pady=(2, 8))
        self.plant_text.insert("1.0", "1 / (s**3 + 3*s**2 + 3*s + 1)")
        self.system_text = self.plant_text

        controller_header = ttk.Frame(parent)
        controller_header.grid(row=4, column=0, sticky="ew")
        ttk.Checkbutton(
            controller_header,
            text="Regler K(s) aktiv",
            variable=self.controller_enabled_var,
            command=self.schedule_update,
        ).pack(side=tk.LEFT)
        self.controller_text = ScrolledText(parent, height=2, width=48, wrap=tk.WORD)
        self.controller_text.grid(row=5, column=0, sticky="ew", pady=(2, 6))
        self.controller_text.insert("1.0", "K_R")

        prefilter_header = ttk.Frame(parent)
        prefilter_header.grid(row=6, column=0, sticky="ew")
        ttk.Checkbutton(
            prefilter_header,
            text="Vorfilter V(s) aktiv",
            variable=self.prefilter_enabled_var,
            command=self.schedule_update,
        ).pack(side=tk.LEFT)
        self.prefilter_text = ScrolledText(parent, height=2, width=48, wrap=tk.WORD)
        self.prefilter_text.grid(row=7, column=0, sticky="ew", pady=(2, 6))
        self.prefilter_text.insert("1.0", "1")

        delay_frame = ttk.Frame(parent)
        delay_frame.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        delay_frame.columnconfigure(1, weight=1)
        ttk.Label(delay_frame, text="Totzeit T_t [s]").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.delay_var = tk.StringVar(value="T_t")
        ttk.Entry(delay_frame, textvariable=self.delay_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(parent, text="Parametercode").grid(row=9, column=0, sticky="w")
        self.params_text = ScrolledText(parent, height=5, width=48, wrap=tk.NONE)
        self.params_text.grid(row=10, column=0, sticky="ew", pady=(2, 8))
        self.params_text.insert(
            "1.0",
            "K_R = 2.0\n"
            "T_t = np.pi / 4\n"
            "\n"
            "# Beispiele:\n"
            "# T1 = 1.0\n"
            "# Kp = 1.5\n"
        )

        ttk.Label(parent, text="Übertragungsfunktionen").grid(row=11, column=0, sticky="w")
        self.fig_latex = Figure(figsize=(4.8, 1.65), dpi=100)
        self.ax_latex = self.fig_latex.add_subplot(111)
        self.ax_latex.axis("off")
        self.canvas_latex = FigureCanvasTkAgg(self.fig_latex, master=parent)
        self.canvas_latex.get_tk_widget().grid(row=12, column=0, sticky="ew", pady=(0, 8))

        self.current_example_label = ttk.Label(
            parent,
            textvariable=self.current_example_var,
            foreground="#555555",
            wraplength=460,
            justify="left",
        )
        self.current_example_label.grid(row=13, column=0, sticky="ew", pady=(0, 6))

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=14, column=0, sticky="ew", pady=(4, 8))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Button(button_frame, text="Aktualisieren", command=self.update_plots).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))
        ttk.Button(button_frame, text="Einstellungen", command=self._open_settings_window).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4))
        ttk.Button(button_frame, text="Beispiel speichern", command=self.save_example).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(4, 0))
        ttk.Button(button_frame, text="Beispiel laden", command=self.load_example).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(4, 0))

        help_text = (
            "Eingabehinweise:\n"
            "- s ist als ct.TransferFunction.s definiert.\n"
            "- Parameter können im Parameterfeld definiert werden.\n"
            "- Der offene Kreis ist K(s)G(s); V(s) wirkt nur auf die Führung.\n"
            "- Frequenzplots nutzen die Totzeit exakt.\n"
            "- Sprungantwort und Wurzelortskurve können Padé für die Totzeit nutzen.\n"
            "- Ein Klick auf die Wurzelortskurve übernimmt den Gain in den Parametercode.\n"
            "- Frequenzbereich, Sprungantwort und Optionen liegen im Einstellungsfenster."
        )
        ttk.Label(parent, text=help_text, justify="left", foreground="#555555").grid(row=15, column=0, sticky="w", pady=(4, 0))

    def _create_tab_plot_system_selector(self, parent, variable, hint_text=None):
        """
        Erstellt eine kompakte Systemauswahl direkt im jeweiligen Hauptfenster-Tab.
        Jede Registerkarte besitzt damit ihre eigene Auswahl.
        """
        selector_frame = ttk.Frame(parent, padding=(0, 0, 0, 4))
        selector_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(selector_frame, text="Angezeigtes System:").pack(side=tk.LEFT, padx=(0, 6))
        combo = ttk.Combobox(
            selector_frame,
            textvariable=variable,
            values=[self.SYSTEM_OPEN, self.SYSTEM_CLOSED, self.SYSTEM_SENS],
            state="readonly",
            width=28,
            takefocus=False,
        )
        combo.pack(side=tk.LEFT)

        if hint_text:
            ttk.Label(
                selector_frame,
                text=hint_text,
                foreground="#555555",
            ).pack(side=tk.LEFT, padx=(10, 0))

        return combo

    def _create_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.tab_nyquist = ttk.Frame(self.notebook)
        self.tab_bode = ttk.Frame(self.notebook)
        self.tab_root_locus = ttk.Frame(self.notebook)
        self.tab_step = ttk.Frame(self.notebook)
        self.tab_disturbance = ttk.Frame(self.notebook)
        self.tab_info = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_nyquist, text="Nyquist / Ortskurve")
        self.notebook.add(self.tab_bode, text="Frequenzgang / Bode")
        self.notebook.add(self.tab_root_locus, text="Wurzelortskurve")
        self.notebook.add(self.tab_step, text="Sprungantwort")
        self.notebook.add(self.tab_disturbance, text="Störaufschaltung")
        self.notebook.add(self.tab_info, text="Info")

        self._create_tab_plot_system_selector(
            self.tab_nyquist,
            self.nyquist_plot_system_var,
            "Standard: offener Kreis",
        )
        self._create_tab_plot_system_selector(
            self.tab_bode,
            self.bode_plot_system_var,
            "Standard: offener Kreis",
        )

        bode_options_frame = ttk.Frame(self.tab_bode, padding=(0, 0, 0, 4))
        bode_options_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Checkbutton(
            bode_options_frame,
            text="Phasen- und Amplitudenreserve anzeigen",
            variable=self.show_bode_margins_var,
            command=self.schedule_update,
        ).pack(side=tk.LEFT)

        root_locus_options = ttk.Frame(self.tab_root_locus, padding=(0, 0, 0, 4))
        root_locus_options.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(root_locus_options, text="Gain-Parameter:").pack(side=tk.LEFT, padx=(0, 6))
        self.root_locus_gain_parameter_combo = ttk.Combobox(
            root_locus_options,
            textvariable=self.root_locus_gain_parameter_var,
            state="readonly",
            width=10,
            values=[],
        )
        self.root_locus_gain_parameter_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.root_locus_gain_parameter_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.schedule_update(),
        )
        self.root_locus_marker_controls = ttk.Frame(root_locus_options)
        self.root_locus_marker_controls.pack(side=tk.LEFT)
        ttk.Label(
            self.root_locus_marker_controls,
            text="Markierter Entwurfswert K:",
        ).pack(side=tk.LEFT, padx=(0, 6))
        self.root_locus_marker_entry = ttk.Entry(
            self.root_locus_marker_controls,
            textvariable=self.root_locus_marker_gain_var,
            width=12,
        )
        self.root_locus_marker_entry.pack(side=tk.LEFT)
        self.root_locus_marker_entry.bind(
            "<Return>",
            self._commit_root_locus_marker_entry,
        )
        ttk.Label(
            root_locus_options,
            text="WOK-Linie anklicken oder Wert eingeben und Enter drücken",
            foreground="#555555",
        ).pack(side=tk.LEFT, padx=(10, 0))

        self._create_tab_plot_system_selector(
            self.tab_step,
            self.step_plot_system_var,
            "Standard: geschlossener Kreis",
        )

        disturbance_options = ttk.Frame(self.tab_disturbance, padding=(0, 0, 0, 4))
        disturbance_options.pack(side=tk.TOP, fill=tk.X)
        self.disturbance_summary_label = ttk.Label(
            disturbance_options,
            text="Störung d_u oder d_y; Parameter unter Einstellungen > Störung.",
            foreground="#555555",
        )
        self.disturbance_summary_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            disturbance_options,
            text="Störung einstellen...",
            command=lambda: self._open_settings_window(initial_tab="Störaufschaltung"),
        ).pack(side=tk.RIGHT)

        self.fig_nyquist = Figure(figsize=(7, 6), dpi=100)
        self.ax_nyquist = self.fig_nyquist.add_subplot(111)
        self.canvas_nyquist = self._embed_figure(self.tab_nyquist, self.fig_nyquist)

        self.fig_bode = Figure(figsize=(7, 6), dpi=100)
        self.ax_mag = self.fig_bode.add_subplot(211)
        self.ax_phase = self.fig_bode.add_subplot(212)
        self.canvas_bode = self._embed_figure(self.tab_bode, self.fig_bode)

        self.fig_root_locus = Figure(figsize=(7, 6), dpi=100)
        self.ax_root_locus = self.fig_root_locus.add_subplot(111)
        self.canvas_root_locus = self._embed_figure(self.tab_root_locus, self.fig_root_locus)

        self.fig_step = Figure(figsize=(7, 6), dpi=100)
        self.ax_step = self.fig_step.add_subplot(111)
        self.canvas_step = self._embed_figure(self.tab_step, self.fig_step)

        self.fig_disturbance = Figure(figsize=(7, 6), dpi=100)
        self.ax_dist_y = self.fig_disturbance.add_subplot(211)
        self.ax_dist_u = self.fig_disturbance.add_subplot(212)
        self.canvas_disturbance = self._embed_figure(self.tab_disturbance, self.fig_disturbance)

        for canvas in (
            self.canvas_nyquist,
            self.canvas_bode,
            self.canvas_root_locus,
            self.canvas_step,
            self.canvas_disturbance,
        ):
            canvas.mpl_connect("motion_notify_event", self._on_plot_hover)
            canvas.mpl_connect("draw_event", self._cache_hover_backgrounds)
        self.canvas_root_locus.mpl_connect("button_press_event", self._on_root_locus_click)

        self.info_text = ScrolledText(self.tab_info, wrap=tk.WORD)
        self.info_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.info_text.configure(state=tk.DISABLED)

    @staticmethod
    def _replace_parameter_assignment(params_code, parameter_name, value_text):
        pattern = re.compile(
            rf"^(\s*{re.escape(parameter_name)}\s*=\s*)([^#]*?)(\s*(?:#.*)?)$"
        )
        lines = params_code.splitlines()
        for index in range(len(lines) - 1, -1, -1):
            match = pattern.match(lines[index])
            if match:
                lines[index] = f"{match.group(1)}{value_text}{match.group(3)}"
                return "\n".join(lines)

        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{parameter_name} = {value_text}")
        return "\n".join(lines)

    def _apply_root_locus_gain(self, gain):
        if not np.isfinite(gain) or gain < 0:
            return

        parameter_name = self.root_locus_gain_parameter_var.get().strip()
        params_code = self.params_text.get("1.0", tk.END).rstrip("\n")

        if not parameter_name:
            parameter_name = "K_WOK"
            controller_expr = self.controller_text.get("1.0", tk.END).strip()
            self.controller_enabled_var.set(True)
            self.controller_text.delete("1.0", tk.END)
            if controller_expr and controller_expr != "1":
                self.controller_text.insert("1.0", f"{parameter_name} * ({controller_expr})")
            else:
                self.controller_text.insert("1.0", parameter_name)

        value_text = f"{gain:.12g}"
        updated_params = self._replace_parameter_assignment(
            params_code,
            parameter_name,
            value_text,
        )
        self.params_text.delete("1.0", tk.END)
        self.params_text.insert("1.0", updated_params)
        self.root_locus_gain_parameter_var.set(parameter_name)
        self.root_locus_marker_gain_var.set(value_text)
        self.status_var.set(f"WOK: {parameter_name} = {value_text} ausgewählt.")
        self.after_idle(self.update_plots)

    def _commit_root_locus_marker_entry(self, _event=None):
        try:
            env = self._base_eval_environment()
            params_code = self.params_text.get("1.0", tk.END).strip()
            if params_code:
                exec(params_code, env, env)
            gain = float(eval(self.root_locus_marker_gain_var.get(), env, env))
        except Exception:
            return
        self._apply_root_locus_gain(gain)

    def _on_root_locus_click(self, event):
        click_data = self._root_locus_click_data
        if (
            click_data is None
            or event.button != 1
            or event.inaxes is not self.ax_root_locus
            or event.x is None
            or event.y is None
        ):
            return

        toolbar = getattr(event.canvas, "toolbar", None)
        if toolbar is not None and getattr(toolbar, "mode", ""):
            return

        loci = click_data["loci"]
        gains = click_data["gains"]
        click = np.array([event.x, event.y], dtype=float)
        best_distance = float("inf")
        best_gain = None

        for branch in range(loci.shape[1]):
            points = np.asarray(loci[:, branch], dtype=complex)
            finite = np.isfinite(points.real) & np.isfinite(points.imag)
            points = points[finite]
            branch_gains = gains[finite]
            if points.size < 2:
                continue

            display_points = self.ax_root_locus.transData.transform(
                np.column_stack((points.real, points.imag))
            )
            starts = display_points[:-1]
            vectors = display_points[1:] - starts
            lengths_squared = np.sum(vectors * vectors, axis=1)
            valid = lengths_squared > np.finfo(float).eps
            if not np.any(valid):
                continue

            projections = np.zeros(len(vectors), dtype=float)
            projections[valid] = np.clip(
                np.sum((click - starts[valid]) * vectors[valid], axis=1)
                / lengths_squared[valid],
                0.0,
                1.0,
            )
            nearest = starts + projections[:, None] * vectors
            distances = np.linalg.norm(nearest - click, axis=1)
            segment = int(np.argmin(distances))
            if distances[segment] >= best_distance:
                continue

            fraction = projections[segment]
            gain_start = float(branch_gains[segment])
            gain_end = float(branch_gains[segment + 1])
            if gain_start > 0 and gain_end > 0:
                selected_gain = float(np.exp(
                    np.log(gain_start)
                    + fraction * (np.log(gain_end) - np.log(gain_start))
                ))
            else:
                selected_gain = gain_start + fraction * (gain_end - gain_start)
            best_distance = float(distances[segment])
            best_gain = selected_gain

        if best_gain is not None and best_distance <= 14.0:
            self._apply_root_locus_gain(best_gain)

    @staticmethod
    def _documents_directory():
        if os.name == "nt":
            try:
                path_buffer = ctypes.create_unicode_buffer(32768)
                result = ctypes.windll.shell32.SHGetFolderPathW(
                    None,
                    5,  # CSIDL_PERSONAL / Documents
                    None,
                    0,
                    path_buffer,
                )
                if result == 0 and path_buffer.value:
                    return Path(path_buffer.value)
            except (AttributeError, OSError):
                pass
        return Path.home() / "Documents"

    def _embed_figure(self, parent, fig):
        canvas = FigureCanvasTkAgg(fig, master=parent)

        toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        toolbar.update()

        self._add_custom_toolbar_buttons(toolbar, fig)

        toolbar.pack(side=tk.TOP, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        return canvas
    
    def _add_custom_toolbar_buttons(self, toolbar, fig):
        """
        Ergänzt die Matplotlib-Toolbar um eigene Zoom-In/Zoom-Out-Buttons
        im gleichen Icon-Stil wie die Standard-Buttons.
        """
        zoom_in_icon, zoom_out_icon = self._ensure_toolbar_zoom_icons()

        # Gleicher Separator-Stil wie Matplotlib intern
        toolbar._Spacer()

        btn_zoom_in = toolbar._Button(
            "Zoom in",
            str(zoom_in_icon),
            False,
            lambda: self._zoom_figure(fig, factor=0.8, toolbar=toolbar),
        )

        btn_zoom_out = toolbar._Button(
            "Zoom out",
            str(zoom_out_icon),
            False,
            lambda: self._zoom_figure(fig, factor=1.25, toolbar=toolbar),
        )

        if add_tooltip is not None:
            add_tooltip(btn_zoom_in, "Zoom in")
            add_tooltip(btn_zoom_out, "Zoom out")


    def _ensure_toolbar_zoom_icons(self):
        """
        Erstellt transparente PNG-Icons für Zoom-In und Zoom-Out.

        Wichtig:
        - schwarzes Symbol auf transparentem Hintergrund
        - Matplotlib recoloriert schwarze Pixel automatisch passend zum Theme
        - zusätzlich werden *_large.png Varianten erzeugt
        """
        icon_dir = Path(__file__).resolve().parent / "toolbar_icons"
        icon_dir.mkdir(parents=True, exist_ok=True)

        zoom_in = icon_dir / "zoom_in_custom.png"
        zoom_out = icon_dir / "zoom_out_custom.png"

        specs = [
            (zoom_in, "+"),
            (zoom_out, "-"),
            (icon_dir / "zoom_in_custom_large.png", "+"),
            (icon_dir / "zoom_out_custom_large.png", "-"),
        ]

        for path, sign in specs:
            size = 48 if path.stem.endswith("_large") else 24
            if not path.exists():
                self._draw_zoom_toolbar_icon(path, sign=sign, size=size)

        return zoom_in, zoom_out


    def _draw_zoom_toolbar_icon(self, path, sign, size=24):
        """
        Zeichnet ein Lupen-Icon mit + oder - als transparente PNG-Datei.
        Der Stil orientiert sich an den Matplotlib-Toolbar-Icons.
        """
        scale = 4
        w = h = size * scale

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        black = (0, 0, 0, 255)

        lw = max(2 * scale, int(0.10 * w))
        symbol_lw = max(2 * scale, int(0.085 * w))

        # Lupenkreis
        x0 = int(0.14 * w)
        y0 = int(0.12 * h)
        x1 = int(0.64 * w)
        y1 = int(0.62 * h)

        draw.ellipse((x0, y0, x1, y1), outline=black, width=lw)

        # Griff
        draw.line(
            (int(0.58 * w), int(0.58 * h), int(0.84 * w), int(0.84 * h)),
            fill=black,
            width=lw,
        )

        # Plus/Minus im Lupenkreis
        cx = int(0.39 * w)
        cy = int(0.37 * h)
        r = int(0.13 * w)

        draw.line((cx - r, cy, cx + r, cy), fill=black, width=symbol_lw)

        if sign == "+":
            draw.line((cx, cy - r, cx, cy + r), fill=black, width=symbol_lw)

        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        img = img.resize((size, size), resample)

        img.save(path)


    def _zoom_figure(self, fig, factor, toolbar=None):
        """
        Zoomt alle sichtbaren Achsen einer Figure.

        factor < 1  -> Zoom in
        factor > 1  -> Zoom out

        Funktioniert auch für logarithmische x-Achsen, z. B. beim Bode-Plot.
        """
        if toolbar is not None:
            try:
                toolbar.push_current()
            except Exception:
                pass

        for ax in fig.axes:
            if not ax.get_visible():
                continue

            self._zoom_axis_limits(ax, axis="x", factor=factor)
            self._zoom_axis_limits(ax, axis="y", factor=factor)

        if toolbar is not None:
            try:
                toolbar.push_current()
                toolbar.set_history_buttons()
            except Exception:
                pass

        fig.canvas.draw_idle()


    def _zoom_axis_limits(self, ax, axis, factor):
        """
        Zoomt x- oder y-Grenzen einer Achse um deren Mittelpunkt.
        Berücksichtigt lineare und logarithmische Achsenskalierung.
        """
        if axis == "x":
            lower, upper = ax.get_xlim()
            scale = ax.get_xscale()
            setter = ax.set_xlim
        else:
            lower, upper = ax.get_ylim()
            scale = ax.get_yscale()
            setter = ax.set_ylim

        if not np.isfinite(lower) or not np.isfinite(upper):
            return

        if lower == upper:
            return

        # Logarithmische Achse, z. B. Bode-Frequenzachse
        if scale == "log":
            if lower <= 0 or upper <= 0:
                return

            log_lower = np.log10(lower)
            log_upper = np.log10(upper)

            center = 0.5 * (log_lower + log_upper)
            half_width = 0.5 * (log_upper - log_lower) * factor

            new_lower = 10 ** (center - half_width)
            new_upper = 10 ** (center + half_width)

        # Lineare Achse
        else:
            center = 0.5 * (lower + upper)
            half_width = 0.5 * (upper - lower) * factor

            new_lower = center - half_width
            new_upper = center + half_width

        setter(new_lower, new_upper)

    def _register_hover(self, ax, kind, x, y, **extra):
        """
        Registriert Hover-Daten für eine Achse.

        Hover-Annotationen verwenden wieder einen Pfeil, werden aber
        zusätzlich robust gegen Matplotlib-Fehler behandelt, damit die
        Annotation stabil bleibt und der GUI-Callback nicht abstürzt.
        """
        annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            annotation_clip=False,
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#555555", "alpha": 0.95},
            arrowprops={
                "arrowstyle": "->",
                "color": "#555555",
                "shrinkA": 0,
                "shrinkB": 3,
                "connectionstyle": "arc3,rad=0",
            },
            fontsize=9,
            zorder=20,
        )
        annotation.set_visible(False)
        annotation.set_clip_on(False)
        if annotation.get_bbox_patch() is not None:
            annotation.get_bbox_patch().set_clip_on(False)

        self._hover_annotations[ax] = annotation
        self._hover_data[ax] = {
            "kind": kind,
            "x": np.asarray(x, dtype=float),
            "y": np.asarray(y, dtype=float),
            **extra,
        }

        if not hasattr(ax, "_control_explorer_hover_callbacks"):
            ax._control_explorer_hover_callbacks = [
                ax.callbacks.connect("xlim_changed", self._on_hover_axes_limits_changed),
                ax.callbacks.connect("ylim_changed", self._on_hover_axes_limits_changed),
            ]

    def _on_hover_axes_limits_changed(self, ax):
        if self._is_updating:
            return
        annotation = self._hover_annotations.get(ax)
        if annotation is None or not annotation.get_visible():
            return
        annotation.set_visible(False)
        self._last_hover_target = (None, None)
        self._hover_backgrounds.pop(ax, None)
        ax.figure.canvas.draw_idle()

    def _cache_hover_backgrounds(self, event):
        canvas = event.canvas
        self._hover_ready.add(canvas)
        for ax in canvas.figure.axes:
            if ax in self._hover_annotations:
                self._hover_backgrounds[ax] = canvas.copy_from_bbox(ax.bbox)

    def _draw_hover_axes(self, axes):
        """
        Zeichnet Hover-Annotationen performant per Blitting.

        Falls Matplotlib beim Zeichnen einer Annotation intern scheitert
        (z. B. StopIteration in der Pfeil-/Connection-Logik), wird der Fehler
        abgefangen und auf ein normales draw_idle() zurückgefallen. Dadurch
        stürzt der Tkinter-Callback nicht ab und das Hover-Tool bleibt nutzbar.
        """
        for ax in set(axes):
            canvas = ax.figure.canvas
            background = self._hover_backgrounds.get(ax)
            annotation = self._hover_annotations.get(ax)

            if background is None:
                if annotation is not None and annotation.get_visible():
                    annotation.set_visible(False)
                canvas.draw_idle()
                continue

            try:
                canvas.restore_region(background)

                if annotation is not None and annotation.get_visible():
                    ax.draw_artist(annotation)

                canvas.blit(ax.bbox)

            except Exception:
                # Robuster Fallback: keine Exception aus Tkinter-Callbacks herauslassen.
                # Falls doch irgendwo ein Pfeil existiert, wird er deaktiviert und die
                # komplette Figure neu gezeichnet.
                try:
                    if annotation is not None and annotation.arrow_patch is not None:
                        annotation.arrow_patch.set_visible(False)
                except Exception:
                    pass
                canvas.draw_idle()

    def _clear_hover_annotations(self, axes=None, redraw=True):
        if self._hover_after_id is not None:
            self.after_cancel(self._hover_after_id)
            self._hover_after_id = None
        self._pending_hover = None
        self._last_hover_target = (None, None)

        if axes is None:
            axes_to_clear = list(self._hover_annotations.keys())
        else:
            axes_to_clear = list(axes)

        canvases = set()
        for ax in axes_to_clear:
            annotation = self._hover_annotations.pop(ax, None)
            if annotation is not None:
                try:
                    annotation.set_visible(False)
                    annotation.remove()
                except (ValueError, RuntimeError):
                    pass
                canvases.add(ax.figure.canvas)
            self._hover_data.pop(ax, None)
            self._hover_backgrounds.pop(ax, None)
            self._hover_ready.discard(ax.figure.canvas)

        if redraw:
            for canvas in canvases:
                canvas.draw_idle()

    def _clear_hover_for_axes(self, *axes):
        self._clear_hover_annotations(axes=axes, redraw=False)

    def _update_block_diagram(self, data):
        ax = self.ax_block
        ax.clear()
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        signal_color = "#333333"
        muted_color = "#8a8a8a"
        block_edge = "#444444"
        block_inactive = "#f0f0f0"
        block_width = 0.105
        block_height = 0.12
        sum_marker_size = 150
        sum_marker_radius_pts = float(np.sqrt(sum_marker_size / np.pi))

        def add_arrow(
            start,
            end,
            text=None,
            text_offset=(0.0, 0.045),
            color=signal_color,
            lw=1.2,
            shrink_a=0.0,
            shrink_b=0.0,
            fontsize=10,
        ):
            arrow = FancyArrowPatch(
                start,
                end,
                arrowstyle="->",
                mutation_scale=9,
                linewidth=lw,
                color=color,
                shrinkA=shrink_a,
                shrinkB=shrink_b,
            )
            ax.add_patch(arrow)
            if text:
                ax.text(
                    0.5 * (start[0] + end[0]) + text_offset[0],
                    0.5 * (start[1] + end[1]) + text_offset[1],
                    text,
                    ha="center",
                    va="center",
                    fontsize=fontsize,
                    color=color,
                )

        def add_block(center, text, active=True, width=block_width, height=block_height):
            x = center[0] - width / 2
            y = center[1] - height / 2
            face = "#ffffff" if active else block_inactive
            edge = block_edge if active else muted_color
            rect = Rectangle(
                (x, y),
                width,
                height,
                facecolor=face,
                edgecolor=edge,
                linewidth=1.1,
                joinstyle="round",
            )
            ax.add_patch(rect)
            ax.text(center[0], center[1], text, ha="center", va="center", fontsize=8.8, color=edge)

        def add_sum(center, sign=None, sign_pos="bottom"):
            ax.scatter(
                [center[0]],
                [center[1]],
                s=sum_marker_size,
                facecolors="#ffffff",
                edgecolors=block_edge,
                linewidths=1.1,
                zorder=3,
            )
            if sign == "-" and sign_pos == "bottom":
                ax.text(
                    center[0] + 0.02,
                    center[1] - 0.085,
                    "-",
                    ha="center",
                    va="center",
                    fontsize=12,
                    color=signal_color,
                )
            elif sign == "+" and sign_pos == "top":
                ax.text(
                    center[0] + 0.02,
                    center[1] + 0.085,
                    "+",
                    ha="center",
                    va="center",
                    fontsize=10,
                    color=signal_color,
                )

        y_main = 0.64
        y_feedback = 0.27
        x_v = 0.12
        x_sum_e = 0.26
        x_k = 0.40
        x_sum_du = 0.54
        x_g = 0.68
        x_sum_dy = 0.82
        x_out = 0.97
        delta_arrow = 0.005

        add_block((x_v, y_main), "V(s)" if data["prefilter_enabled"] else "V=1", data["prefilter_enabled"])
        add_sum((x_sum_e, y_main), sign="-", sign_pos="bottom")
        add_block((x_k, y_main), "K(s)" if data["controller_enabled"] else "K=1", data["controller_enabled"])
        add_sum((x_sum_du, y_main), sign="+", sign_pos="top")
        add_block((x_g, y_main), "G(s)", True)
        add_sum((x_sum_dy, y_main), sign="+", sign_pos="top")

        add_arrow((0.02, y_main), (x_v - block_width / 2, y_main), "$w$", text_offset=(-0.01, 0.06))
        add_arrow(
            (x_v + block_width / 2, y_main),
            (x_sum_e + delta_arrow, y_main),
            shrink_b=sum_marker_radius_pts,
        )
        add_arrow(
            (x_sum_e, y_main),
            (x_k - block_width / 2, y_main),
            "$e$",
            text_offset=(0.0, 0.06),
            shrink_a=sum_marker_radius_pts,
        )
        add_arrow(
            (x_k + block_width / 2, y_main),
            (x_sum_du + delta_arrow, y_main),
            "$u_R$",
            text_offset=(-0.01, 0.05),
            shrink_b=sum_marker_radius_pts,
        )
        add_arrow(
            (x_sum_du, y_main),
            (x_g - block_width / 2, y_main),
            "$u$",
            text_offset=(0.0, 0.06),
            shrink_a=sum_marker_radius_pts,
        )
        add_arrow(
            (x_g + block_width / 2, y_main),
            (x_sum_dy + delta_arrow, y_main),
            shrink_b=sum_marker_radius_pts,
        )
        add_arrow(
            (x_sum_dy, y_main),
            (x_out, y_main),
            "$y$",
            text_offset=(0.0, 0.05),
            shrink_a=sum_marker_radius_pts,
        )
        add_arrow(
            (x_sum_du, 0.92),
            (x_sum_du, y_main - delta_arrow),
            r"$d_u$",
            text_offset=(0.026, 0.06),
            shrink_b=sum_marker_radius_pts,
        )
        add_arrow(
            (x_sum_dy, 0.92),
            (x_sum_dy, y_main - delta_arrow),
            r"$d_y$",
            text_offset=(0.026, 0.06),
            shrink_b=sum_marker_radius_pts,
        )

        x_feedback = 0.92
        ax.plot([x_feedback, x_feedback, x_sum_e], [y_main, y_feedback, y_feedback], color=signal_color, linewidth=1.1)
        add_arrow(
            (x_sum_e, y_feedback),
            (x_sum_e, y_main + delta_arrow),
            color=signal_color,
            lw=1.1,
            shrink_b=sum_marker_radius_pts,
        )

        # ax.text(
        #     0.02,
        #     0.05,
        #     "Einheitsrückführung, Störung d_u additiv am Streckeneingang, Störung d_y additiv am Ausgang",
        #     ha="left",
        #     va="bottom",
        #     fontsize=7.5,
        #     color="#666666",
        # )

        self.fig_block.subplots_adjust(left=0.02, right=0.98, bottom=0.04, top=0.98)
        self.canvas_block.draw_idle()

    def _position_hover_annotation(self, ax, annotation, x_value, y_value):
        """
        Positioniert die Hover-Box ähnlich wie ein Cursor-Tooltip.

        Die Methode testet mehrere Kandidatenpositionen um den Datenpunkt
        herum und nimmt die erste Position, bei der die gesamte Box innerhalb
        der Achsenfläche bleibt. Dadurch klappt die Box z. B. automatisch nach
        unten, wenn oberhalb des Punktes zu wenig Platz ist.
        """
        try:
            canvas = ax.figure.canvas
            renderer = canvas.get_renderer()
            bbox = ax.bbox
            padding = 4

            x_disp, y_disp = ax.transData.transform((x_value, y_value))
            x_frac = (x_disp - bbox.x0) / max(bbox.width, np.finfo(float).eps)
            y_frac = (y_disp - bbox.y0) / max(bbox.height, np.finfo(float).eps)

            # Bevorzugte Richtung: weg von den nächsten Rändern.
            horizontal_order = [1, -1] if x_frac <= 0.55 else [-1, 1]
            vertical_order = [1, -1] if y_frac <= 0.55 else [-1, 1]

            candidates = []
            for sy in vertical_order:
                for sx in horizontal_order:
                    candidates.append((14 * sx, 14 * sy))

            # Zusätzlich noch reine Vertikal-/Horizontalvarianten als Fallback.
            candidates.extend([
                (0, 18 if y_frac <= 0.5 else -18),
                (18 if x_frac <= 0.5 else -18, 0),
                (14, 14),
                (14, -14),
                (-14, 14),
                (-14, -14),
            ])

            best = candidates[0]
            best_overflow = float("inf")

            for dx, dy in candidates:
                annotation.set_position((dx, dy))
                annotation.set_ha("right" if dx < 0 else "left")
                annotation.set_va("top" if dy < 0 else "bottom")

                ann_bbox = annotation.get_window_extent(renderer=renderer)

                overflow_left = max(0.0, bbox.x0 + padding - ann_bbox.x0)
                overflow_right = max(0.0, ann_bbox.x1 - (bbox.x1 - padding))
                overflow_bottom = max(0.0, bbox.y0 + padding - ann_bbox.y0)
                overflow_top = max(0.0, ann_bbox.y1 - (bbox.y1 - padding))
                overflow = overflow_left + overflow_right + overflow_bottom + overflow_top

                if overflow == 0:
                    best = (dx, dy)
                    break

                if overflow < best_overflow:
                    best_overflow = overflow
                    best = (dx, dy)

            dx, dy = best
            annotation.set_position((dx, dy))
            annotation.set_ha("right" if dx < 0 else "left")
            annotation.set_va("top" if dy < 0 else "bottom")

        except Exception:
            annotation.set_position((12, 12))
            annotation.set_ha("left")
            annotation.set_va("bottom")


    def _on_plot_hover(self, event):
        if self._is_updating:
            return
        if (
            event.inaxes is None
            or event.canvas not in self._hover_ready
            or event.inaxes not in self._hover_annotations
            or event.inaxes not in self._hover_backgrounds
        ):
            return
        self._pending_hover = (event.inaxes, event.xdata, event.ydata, event.canvas)
        if self._hover_after_id is None:
            self._hover_after_id = self.after(25, self._process_plot_hover)

    def _process_plot_hover(self):
        self._hover_after_id = None
        if self._is_updating:
            self._pending_hover = None
            return
        if self._pending_hover is None:
            return

        ax, xdata, ydata, canvas = self._pending_hover
        self._pending_hover = None

        if (
            ax not in self._hover_data
            or xdata is None
            or ydata is None
            or not np.isfinite(xdata)
            or not np.isfinite(ydata)
        ):
            changed_axes = []
            for annotation in self._hover_annotations.values():
                if annotation.get_visible():
                    annotation.set_visible(False)
                    changed_axes.append(annotation.axes)
            self._last_hover_target = (None, None)
            self._draw_hover_axes(changed_axes)
            return

        if ax not in self._hover_backgrounds:
            # Der Plot ist noch nicht vollständig gerendert; Hover-Labels werden
            # erst dann gezeigt, wenn ein sauberer Hintergrund vorhanden ist.
            annotation = self._hover_annotations.get(ax)
            if annotation is not None and annotation.get_visible():
                annotation.set_visible(False)
            canvas.draw_idle()
            return

        data = self._hover_data[ax]
        x = data["x"]
        y = data["y"]
        if not x.size:
            return

        kind = data["kind"]
        if kind.startswith("bode") and xdata > 0:
            idx = self._nearest_sorted_index(x, xdata)
        elif kind == "step":
            idx = self._nearest_sorted_index(x, xdata)
        else:
            x_span = max(abs(ax.get_xlim()[1] - ax.get_xlim()[0]), np.finfo(float).eps)
            y_span = max(abs(ax.get_ylim()[1] - ax.get_ylim()[0]), np.finfo(float).eps)
            stride = max(1, int(np.ceil(x.size / 1200)))
            coarse_indices = np.arange(0, x.size, stride)
            coarse_distance = (
                ((x[coarse_indices] - xdata) / x_span) ** 2
                + ((y[coarse_indices] - ydata) / y_span) ** 2
            )
            coarse_idx = int(coarse_indices[int(np.argmin(coarse_distance))])
            start = max(0, coarse_idx - stride)
            stop = min(x.size, coarse_idx + stride + 1)
            local_distance = (
                ((x[start:stop] - xdata) / x_span) ** 2
                + ((y[start:stop] - ydata) / y_span) ** 2
            )
            idx = start + int(np.argmin(local_distance))

        if self._last_hover_target == (ax, idx) and self._hover_annotations[ax].get_visible():
            return
        self._last_hover_target = (ax, idx)

        if kind == "nyquist":
            omega = data["omega"][idx]
            text = (
                rf"$\omega = {omega:.5g}\,\mathrm{{rad/s}}$" "\n"
                rf"$\Re\{{H(j\omega)\}} = {x[idx]:.5g}$" "\n"
                rf"$\Im\{{H(j\omega)\}} = {y[idx]:.5g}$" "\n"
                rf"$\left|H(j\omega)\right| = {abs(complex(x[idx], y[idx])):.5g}$"
            )
        elif kind == "bode_mag":
            if data["frequency_unit"] == self.BODE_UNIT_HZ:
                frequency_text = rf"$f = {x[idx]:.5g}\,\mathrm{{Hz}}$"
                response_text = rf"$\left|H(j2\pi f)\right| = {y[idx]:.5g}\,\mathrm{{dB}}$"
                phase_text = rf"$\varphi(f) = {data['phase'][idx]:.5g}^\circ$"
            else:
                frequency_text = rf"$\omega = {x[idx]:.5g}\,\mathrm{{rad/s}}$"
                response_text = rf"$\left|H(j\omega)\right| = {y[idx]:.5g}\,\mathrm{{dB}}$"
                phase_text = rf"$\varphi(\omega) = {data['phase'][idx]:.5g}^\circ$"
            text = (
                frequency_text + "\n"
                + response_text + "\n"
                + phase_text
            )
        elif kind == "bode_phase":
            if data["frequency_unit"] == self.BODE_UNIT_HZ:
                frequency_text = rf"$f = {x[idx]:.5g}\,\mathrm{{Hz}}$"
                phase_text = rf"$\varphi(f) = {y[idx]:.5g}^\circ$"
                response_text = rf"$\left|H(j2\pi f)\right| = {data['magnitude'][idx]:.5g}\,\mathrm{{dB}}$"
            else:
                frequency_text = rf"$\omega = {x[idx]:.5g}\,\mathrm{{rad/s}}$"
                phase_text = rf"$\varphi(\omega) = {y[idx]:.5g}^\circ$"
                response_text = rf"$\left|H(j\omega)\right| = {data['magnitude'][idx]:.5g}\,\mathrm{{dB}}$"
            text = (
                frequency_text + "\n"
                + phase_text + "\n"
                + response_text
            )
        elif kind == "root_locus":
            pole = complex(x[idx], y[idx])
            natural_frequency = abs(pole)
            damping_ratio = (
                -pole.real / natural_frequency
                if natural_frequency > np.finfo(float).eps
                else np.nan
            )
            damping_text = (
                rf"$\zeta = {damping_ratio:.5g}$"
                if np.isfinite(damping_ratio)
                else r"$\zeta$ nicht definiert"
            )
            text = (
                rf"$K = {data['gain'][idx]:.5g}$" "\n"
                rf"$s = {pole.real:.5g} {pole.imag:+.5g}j$" "\n"
                rf"$\omega_n = {natural_frequency:.5g}\,\mathrm{{rad/s}}$" "\n"
                + damping_text
            )
        else:
            text = (
                rf"$t = {x[idx]:.5g}\,\mathrm{{s}}$" "\n"
                rf"$y(t) = {y[idx]:.5g}$" "\n"
                rf"$u(t) = {data['input_signal'][idx]:.5g}$"
            )

        changed_axes = [ax]
        for hover_ax, annotation in self._hover_annotations.items():
            should_be_visible = hover_ax is ax
            if annotation.get_visible() != should_be_visible:
                annotation.set_visible(should_be_visible)
                changed_axes.append(hover_ax)

        annotation = self._hover_annotations[ax]
        annotation.xy = (x[idx], y[idx])
        annotation.set_text(text)
        self._position_hover_annotation(ax, annotation, x[idx], y[idx])
        self._draw_hover_axes(changed_axes)

    @staticmethod
    def _nearest_sorted_index(values, target):
        index = int(np.searchsorted(values, target))
        if index <= 0:
            return 0
        if index >= len(values):
            return len(values) - 1
        before = index - 1
        return before if abs(target - values[before]) <= abs(values[index] - target) else index

    def _add_entry(self, parent, label, variable, row, col):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky="ew", padx=6, pady=3)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=label).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(frame, textvariable=variable, width=14).grid(row=0, column=1, sticky="ew")

    def _bind_events(self):
        for variable in self._settings_variables().values():
            if variable is self.root_locus_marker_gain_var:
                continue
            variable.trace_add("write", lambda *_: self._on_setting_changed())

        self.delay_var.trace_add("write", lambda *_: self.schedule_update())

        self.params_text.bind("<KeyRelease>", lambda _event: self.schedule_update())
        self.plant_text.bind("<KeyRelease>", lambda _event: self.schedule_update())
        self.controller_text.bind("<KeyRelease>", lambda _event: self.schedule_update())
        self.prefilter_text.bind("<KeyRelease>", lambda _event: self.schedule_update())

        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

    def _on_setting_changed(self):
        if self._loading_settings:
            return
        self._schedule_settings_save()
        self.schedule_update()

    def _on_notebook_tab_changed(self, _event):
        self._clear_hover_annotations(redraw=True)
        self.schedule_update()

    # ------------------------------------------------------------------
    # Parsing and computation
    # ------------------------------------------------------------------
    def _bode_frequency_to_omega(self, frequency):
        values = np.asarray(frequency, dtype=float)
        if self.bode_frequency_unit_var.get() == self.BODE_UNIT_HZ:
            values = 2.0 * np.pi * values
        return float(values) if np.isscalar(frequency) else values

    def _omega_to_bode_frequency(self, omega):
        values = np.asarray(omega, dtype=float)
        if self.bode_frequency_unit_var.get() == self.BODE_UNIT_HZ:
            values = values / (2.0 * np.pi)
        return float(values) if np.isscalar(omega) else values

    def _base_eval_environment(self):
        s = ct.TransferFunction.s

        env = {
            "__builtins__": {},
            "np": np,
            "ct": ct,
            "s": s,
            "tf": ct.tf,
            "zpk": ct.zpk,
            "ss": ct.ss,
            "pi": np.pi,
            "e": np.e,
            "sqrt": np.sqrt,
            "sin": np.sin,
            "cos": np.cos,
            "tan": np.tan,
            "exp": np.exp,
            "log": np.log,
            "log10": np.log10,
            "abs": abs,
        }
        return env

    @staticmethod
    def _assigned_parameter_names(params_code):
        if not params_code.strip():
            return []
        tree = ast.parse(params_code, mode="exec")
        names = []
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.append(target.id)
        return names

    def _is_multiplicative_gain_parameter(self, system_expr, env, parameter_name):
        try:
            systems = []
            for value in (1.0, 2.0):
                test_env = dict(env)
                test_env[parameter_name] = value
                systems.append(self._ensure_lti(eval(system_expr, test_env, test_env)))

            frequencies = (0.731, 1.937, 4.123)
            response_one = np.asarray([complex(np.squeeze(systems[0](1j * w))) for w in frequencies])
            response_two = np.asarray([complex(np.squeeze(systems[1](1j * w))) for w in frequencies])
            finite = np.isfinite(response_one) & np.isfinite(response_two)
            return bool(
                np.any(finite)
                and np.allclose(
                    response_two[finite],
                    2.0 * response_one[finite],
                    rtol=1e-7,
                    atol=1e-9,
                )
            )
        except Exception:
            return False

    def _root_locus_gain_candidates(self, params_code, system_expr, env):
        try:
            expression_names = {
                node.id
                for node in ast.walk(ast.parse(system_expr, mode="eval"))
                if isinstance(node, ast.Name)
            }
            assigned_names = self._assigned_parameter_names(params_code)
        except (SyntaxError, ValueError):
            return []

        candidates = []
        for name in assigned_names:
            if name not in expression_names or not isinstance(env.get(name), (int, float, np.number)):
                continue
            if self._is_multiplicative_gain_parameter(system_expr, env, name):
                candidates.append(name)

        def priority(name):
            lowered = name.lower()
            preferred = lowered == "k" or lowered.startswith("k_") or lowered.startswith("k") or "gain" in lowered
            return (not preferred, assigned_names.index(name))

        return sorted(candidates, key=priority)

    def _update_root_locus_gain_parameter_controls(self, candidates, selected):
        combo = getattr(self, "root_locus_gain_parameter_combo", None)
        if combo is not None:
            combo.configure(values=candidates)
        if self.root_locus_gain_parameter_var.get() != selected:
            self.root_locus_gain_parameter_var.set(selected)

    def _parse_user_input(self):
        env = self._base_eval_environment()

        params_code = self.params_text.get("1.0", tk.END).strip()
        plant_expr = self.plant_text.get("1.0", tk.END).strip()
        controller_expr = self.controller_text.get("1.0", tk.END).strip() or "1"
        prefilter_expr = self.prefilter_text.get("1.0", tk.END).strip() or "1"
        controller_enabled = self.controller_enabled_var.get()
        prefilter_enabled = self.prefilter_enabled_var.get()
        delay_expr = self.delay_var.get().strip() or "0"

        if params_code:
            exec(params_code, env, env)

        if not plant_expr:
            raise ValueError("Es wurde keine Strecke G(s) eingegeben.")

        plant = self._ensure_lti(eval(plant_expr, env, env))
        controller = self._ensure_lti(eval(controller_expr, env, env)) if controller_enabled else ct.tf([1], [1])
        prefilter = self._ensure_lti(eval(prefilter_expr, env, env)) if prefilter_enabled else ct.tf([1], [1])

        system_expr = f"({controller_expr}) * ({plant_expr})" if controller_enabled else f"({plant_expr})"
        sys_rational = controller * plant

        gain_candidates = self._root_locus_gain_candidates(params_code, system_expr, env)
        selected_gain_parameter = self.root_locus_gain_parameter_var.get()
        if selected_gain_parameter not in gain_candidates:
            selected_gain_parameter = gain_candidates[0] if gain_candidates else ""

        root_locus_sys_rational = sys_rational
        if selected_gain_parameter:
            root_locus_env = dict(env)
            root_locus_env[selected_gain_parameter] = 1.0
            root_locus_sys_rational = self._ensure_lti(
                eval(system_expr, root_locus_env, root_locus_env)
            )

        delay = float(eval(delay_expr, env, env))
        if delay < 0:
            raise ValueError("Die Totzeit muss >= 0 sein.")

        omega_min = float(eval(self.omega_min_var.get(), env, env))
        omega_max = float(eval(self.omega_max_var.get(), env, env))
        n_points = int(float(eval(self.n_points_var.get(), env, env)))
        bode_frequency_min = float(eval(self.bode_x_min_var.get(), env, env))
        bode_frequency_max = float(eval(self.bode_x_max_var.get(), env, env))

        root_locus_gain_min = float(eval(self.root_locus_gain_min_var.get(), env, env))
        root_locus_gain_max = float(eval(self.root_locus_gain_max_var.get(), env, env))
        root_locus_points = int(float(eval(self.root_locus_points_var.get(), env, env)))
        if selected_gain_parameter:
            root_locus_marker_gain = float(env[selected_gain_parameter])
        else:
            root_locus_marker_gain = float(eval(self.root_locus_marker_gain_var.get(), env, env))

        t_max = float(eval(self.t_max_var.get(), env, env))
        t_points = int(float(eval(self.t_points_var.get(), env, env)))
        step_amplitude = float(eval(self.step_amplitude_var.get(), env, env))
        disturbance_amplitude = float(eval(self.disturbance_amplitude_var.get(), env, env))
        disturbance_time = float(eval(self.disturbance_time_var.get(), env, env))
        disturbance_end_time_expr = self.disturbance_end_time_var.get().strip()
        disturbance_end_time = None
        if disturbance_end_time_expr:
            disturbance_end_time = float(eval(disturbance_end_time_expr, env, env))
        disturbance_location = self.disturbance_location_var.get()
        if disturbance_location not in (self.DISTURBANCE_INPUT, self.DISTURBANCE_OUTPUT):
            disturbance_location = self.DISTURBANCE_INPUT
            self.disturbance_location_var.set(disturbance_location)
        disturbance_settling_tolerance = float(eval(self.disturbance_settling_tolerance_var.get(), env, env))

        pade_order = int(float(eval(self.pade_order_var.get(), env, env)))

        if omega_max <= omega_min:
            raise ValueError("ω_max muss größer als ω_min sein.")
        if n_points < 10:
            raise ValueError("Die Anzahl der Frequenzpunkte muss mindestens 10 sein.")
        if self.bode_frequency_unit_var.get() not in (self.BODE_UNIT_OMEGA, self.BODE_UNIT_HZ):
            raise ValueError("Unbekannte Bode-Frequenzeinheit.")
        if bode_frequency_min <= 0 or bode_frequency_max <= bode_frequency_min:
            raise ValueError("Die Bode-Grenzen müssen 0 < links < rechts erfüllen.")
        gain_values = [root_locus_gain_min, root_locus_gain_max, root_locus_marker_gain]
        if not np.all(np.isfinite(gain_values)):
            raise ValueError("Die Verstärkungswerte der Wurzelortskurve müssen endlich sein.")
        if root_locus_gain_min < 0 or root_locus_gain_max <= root_locus_gain_min:
            raise ValueError("Für die Wurzelortskurve muss 0 <= K min < K max gelten.")
        if root_locus_points < 10:
            raise ValueError("Die Wurzelortskurve benötigt mindestens 10 Verstärkungspunkte.")
        if not root_locus_gain_min <= root_locus_marker_gain <= root_locus_gain_max:
            raise ValueError("Der markierte Wert K muss zwischen K min und K max liegen.")
        if t_max <= 0:
            raise ValueError("t_max muss > 0 sein.")
        if t_points < 10:
            raise ValueError("Die Anzahl der Zeitpunkte muss mindestens 10 sein.")
        if not np.isfinite(step_amplitude):
            raise ValueError("Der Sprungfaktor muss eine endliche Zahl sein.")
        if not np.isfinite(disturbance_amplitude):
            raise ValueError("Die Störamplitude muss eine endliche Zahl sein.")
        if disturbance_time < 0 or disturbance_time >= t_max:
            raise ValueError("Der Störzeitpunkt muss 0 <= t_d < t_max erfüllen.")
        if disturbance_end_time is not None:
            if not np.isfinite(disturbance_end_time):
                raise ValueError("Das Störende muss eine endliche Zahl sein.")
            if disturbance_end_time <= disturbance_time or disturbance_end_time > t_max:
                raise ValueError("Das Störende muss t_d < t_e <= t_max erfüllen.")
        if not np.isfinite(disturbance_settling_tolerance) or disturbance_settling_tolerance <= 0:
            raise ValueError("Die Ausregel-Toleranz der Störung muss eine positive endliche Prozentzahl sein.")
        if pade_order < 0:
            raise ValueError("Die Padé-Ordnung muss >= 0 sein.")

        omega = np.linspace(omega_min, omega_max, n_points)
        bode_omega_min = self._bode_frequency_to_omega(bode_frequency_min)
        bode_omega_max = self._bode_frequency_to_omega(bode_frequency_max)
        bode_omega = np.logspace(np.log10(bode_omega_min), np.log10(bode_omega_max), n_points)
        if self.root_locus_log_gain_var.get():
            if root_locus_gain_min == 0:
                positive_min = max(root_locus_gain_max * 1e-9, np.finfo(float).tiny)
                root_locus_gains = np.concatenate((
                    [0.0],
                    np.geomspace(positive_min, root_locus_gain_max, root_locus_points - 1),
                ))
            else:
                root_locus_gains = np.geomspace(
                    root_locus_gain_min,
                    root_locus_gain_max,
                    root_locus_points,
                )
        else:
            root_locus_gains = np.linspace(
                root_locus_gain_min,
                root_locus_gain_max,
                root_locus_points,
            )
        root_locus_gains = np.unique(np.append(root_locus_gains, root_locus_marker_gain))
        t = np.linspace(0.0, t_max, t_points)

        markers = self._parse_marker_frequencies(env)

        return {
            "env": env,
            "params_code": params_code,
            "system_expr": system_expr,
            "plant_expr": plant_expr,
            "controller_expr": controller_expr,
            "prefilter_expr": prefilter_expr,
            "controller_enabled": controller_enabled,
            "prefilter_enabled": prefilter_enabled,
            "plant": plant,
            "controller": controller,
            "prefilter": prefilter,
            "sys_rational": sys_rational,
            "root_locus_sys_rational": root_locus_sys_rational,
            "root_locus_gain_candidates": gain_candidates,
            "root_locus_gain_parameter": selected_gain_parameter,
            "delay": delay,
            "omega": omega,
            "bode_omega": bode_omega,
            "bode_x_min": bode_omega_min,
            "bode_x_max": bode_omega_max,
            "root_locus_gains": root_locus_gains,
            "root_locus_marker_gain": root_locus_marker_gain,
            "t": t,
            "step_amplitude": step_amplitude,
            "disturbance_amplitude": disturbance_amplitude,
            "disturbance_time": disturbance_time,
            "disturbance_end_time": disturbance_end_time,
            "disturbance_location": disturbance_location,
            "disturbance_settling_tolerance": disturbance_settling_tolerance,
            "disturbance_show_reference_component": self.disturbance_show_reference_component_var.get(),
            "disturbance_show_disturbance_component": self.disturbance_show_disturbance_component_var.get(),
            "pade_order": pade_order,
            "markers": markers,
        }

    def _ensure_lti(self, obj):
        if isinstance(obj, (int, float, complex, np.number)):
            return ct.tf([obj], [1])

        # python-control systems have ninputs/noutputs and are callable in the frequency domain.
        if hasattr(obj, "ninputs") and hasattr(obj, "noutputs"):
            if obj.ninputs != 1 or obj.noutputs != 1:
                raise ValueError("Diese GUI unterstützt aktuell nur SISO-Systeme.")
            return obj

        raise TypeError(
            "Die Systemeingabe muss ein python-control System oder ein Skalar sein. "
            "Beispiel: K_R / (s**2 + 2*s + 1)"
        )

    def _parse_marker_frequencies(self, env):
        text = self.marker_omega_var.get().strip()
        if not text:
            return []

        markers = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            val = float(eval(part, env, env))
            if val >= 0:
                markers.append(val)
        return markers

    def _parse_direction_arrow_settings(self):
        env = self._base_eval_environment()
        positions = []
        for part in self.direction_arrow_positions_var.get().split(","):
            part = part.strip()
            if not part:
                continue
            value = float(eval(part, env, env))
            if value >= 0.0:
                positions.append(value)
        return positions

    def _parse_root_locus_damping_ratios(self):
        env = self._base_eval_environment()
        ratios = []
        for part in self.root_locus_damping_ratios_var.get().split(","):
            part = part.strip()
            if not part:
                continue
            value = float(eval(part, env, env))
            if not 0.0 < value < 1.0:
                raise ValueError("Dämpfungsgrade für die Wurzelortskurve müssen zwischen 0 und 1 liegen.")
            ratios.append(value)
        return sorted(set(ratios))

    def _frequency_response_exact_delay(self, sys_rational, omega, delay):
        omega = np.asarray(omega, dtype=float)
        evaluation_omega = omega

        # Bei einem Pol im Ursprung ist G(j*0) unendlich. Diesen einzelnen
        # Grenzpunkt nicht numerisch auswerten; die Ortskurve beginnt dann beim
        # kleinsten von null verschiedenen Frequenzpunkt.
        if self._count_origin_integrators(sys_rational) > 0:
            evaluation_omega = omega[omega != 0.0]
            if evaluation_omega.size == 0:
                raise ValueError(
                    "Der Frequenzbereich enthält für ein System mit Pol im Ursprung "
                    "keinen von null verschiedenen Frequenzpunkt."
                )

        mag, phase, omega_out = self._call_control(
            "frequency_response",
            ct.frequency_response,
            sys_rational,
            evaluation_omega,
        )
        response = np.squeeze(mag) * np.exp(1j * np.squeeze(phase))

        if response.ndim != 1:
            raise ValueError("Der Frequenzgang ist nicht eindimensional. Bitte ein SISO-System verwenden.")

        delay_response = np.exp(-1j * omega_out * delay)
        L = response * delay_response
        return omega_out, L

    def _frequency_response_of_block(self, sys_rational, omega, label):
        mag, phase, omega_out = self._call_control(
            label,
            ct.frequency_response,
            sys_rational,
            omega,
        )
        response = np.squeeze(mag) * np.exp(1j * np.squeeze(phase))
        if response.ndim != 1:
            raise ValueError("Der Frequenzgang ist nicht eindimensional. Bitte ein SISO-System verwenden.")
        return omega_out, response

    def _selected_frequency_system(self, L, selected, data=None, omega=None):
        selected = self._normalize_system_selection(selected)
        if selected == self.SYSTEM_OPEN:
            return L
        if selected == self.SYSTEM_CLOSED:
            closed = L / (1.0 + L)
            if data is not None and omega is not None and data["prefilter_enabled"]:
                _, V = self._frequency_response_of_block(data["prefilter"], omega, "frequency_response Vorfilter")
                closed = V * closed
            return closed
        if selected == self.SYSTEM_SENS:
            return 1.0 / (1.0 + L)
        raise ValueError(f"Unbekannte Systemauswahl: {selected}")

    def _is_open_loop_selection(self, selected):
        return self._normalize_system_selection(selected) == self.SYSTEM_OPEN

    def _count_origin_integrators(self, sys_rational, tol=1e-10):
        """
        Bestimmt die Anzahl der Netto-Integratoren im offenen Kreis.

        Ein I-Anteil entspricht einem Pol im Ursprung. Falls im Zähler ebenfalls
        Nullstellen im Ursprung liegen, werden diese als algebraische Kuerzung
        berücksichtigt. Rückgabe ist daher die Netto-Anzahl der Faktoren 1/s.
        """
        try:
            num, den = self._tf_num_den_arrays(sys_rational)
        except Exception:
            return 0

        def trailing_zero_count(coeffs):
            coeffs = np.asarray(coeffs, dtype=float)
            if coeffs.size == 0:
                return 0
            scale = max(1.0, float(np.nanmax(np.abs(coeffs))))
            count = 0
            for coeff in coeffs[::-1]:
                if abs(coeff) <= tol * scale:
                    count += 1
                else:
                    break
            return count

        zeros_at_origin = trailing_zero_count(num)
        poles_at_origin = trailing_zero_count(den)
        return max(0, poles_at_origin - zeros_at_origin)

    def _integrator_margin_note(self, integrator_order):
        if integrator_order <= 0:
            return ""
        if integrator_order == 1:
            prefix = "I-Anteil erkannt: 1 Pol im Ursprung."
        else:
            prefix = f"I-Anteil erkannt: {integrator_order} Pole im Ursprung."
        return (
            prefix
            + " Phasenreserve bleibt der Abstand zur -180°-Linie bei |G₀|=1; "
            + "wegen Pol im Ursprung nicht als alleiniger Stabilitätsbeweis verwenden."
        )

    def _rational_high_frequency_limit(self, sys_rational):
        """
        Grenzwert des rationalen Anteils für s -> infinity.

        Rückgabe:
        - complex value: endlicher Grenzwert
        - np.inf: Betrag divergiert
        """
        try:
            sys_tf = ct.tf(sys_rational)
            num = np.trim_zeros(np.asarray(sys_tf.num[0][0], dtype=float), trim="f")
            den = np.trim_zeros(np.asarray(sys_tf.den[0][0], dtype=float), trim="f")
        except Exception:
            return None

        if num.size == 0:
            return 0.0 + 0.0j
        if den.size == 0:
            return np.inf

        degree_num = num.size - 1
        degree_den = den.size - 1

        if degree_num < degree_den:
            return 0.0 + 0.0j
        if degree_num == degree_den:
            return complex(num[0] / den[0])

        return np.inf

    def _frequency_limit_summary(self, sys_rational, delay):
        """
        Bestimmt die Grenzwerte für omega -> infinity soweit eindeutig.
        """
        rational_limit = self._rational_high_frequency_limit(sys_rational)

        if rational_limit is None:
            return {
                "open": "nicht bestimmbar",
                "closed": "nicht bestimmbar",
                "sensitivity": "nicht bestimmbar",
            }

        if rational_limit is np.inf or rational_limit == np.inf:
            return {
                "open": "|L(jw)| -> unendlich",
                "closed": "L/(1+L) -> 1",
                "sensitivity": "S(jw) -> 0",
            }

        rational_limit = complex(rational_limit)

        if delay > 0 and abs(rational_limit) > 1e-14:
            return {
                "open": (
                    "kein komplexer Grenzwert; "
                    f"|L(jw)| -> {abs(rational_limit):.6g} "
                    "wegen oszillierender Totzeitphase"
                ),
                "closed": "kein eindeutiger komplexer Grenzwert wegen Totzeitphase",
                "sensitivity": "kein eindeutiger komplexer Grenzwert wegen Totzeitphase",
            }

        L_inf = rational_limit
        closed_inf = self._safe_closed_loop_value(L_inf)
        sensitivity_inf = self._safe_sensitivity_value(L_inf)

        return {
            "open": self._format_complex_limit(L_inf),
            "closed": self._format_complex_limit(closed_inf),
            "sensitivity": self._format_complex_limit(sensitivity_inf),
        }

    def _safe_closed_loop_value(self, L):
        denominator = 1.0 + L
        if abs(denominator) < 1e-14:
            return np.inf
        return L / denominator

    def _safe_sensitivity_value(self, L):
        denominator = 1.0 + L
        if abs(denominator) < 1e-14:
            return np.inf
        return 1.0 / denominator

    def _format_complex_limit(self, value):
        if value is np.inf or value == np.inf:
            return "∞"
        value = complex(value)
        if abs(value.imag) < 1e-13:
            return f"{value.real:.6g}"
        return f"{value.real:.6g} {value.imag:+.6g}j"

    def _pade_delay_tf(self, delay, pade_order, label="Padé"):
        if delay > 0 and pade_order > 0:
            num_delay, den_delay = self._call_control(label, ct.pade, delay, pade_order)
            return self._call_control("tf für Padé-Totzeit", ct.tf, num_delay, den_delay)
        return self._call_control("tf für Eins", ct.tf, [1], [1])

    def _time_domain_system_with_pade(self, data, selected):
        selected = self._normalize_system_selection(selected)
        delay_tf = self._pade_delay_tf(data["delay"], data["pade_order"], label="pade")
        L_time = data["controller"] * data["plant"] * delay_tf

        if selected == self.SYSTEM_OPEN:
            return L_time
        if selected == self.SYSTEM_CLOSED:
            closed = self._call_control("feedback für G(s)", ct.feedback, L_time, 1)
            return data["prefilter"] * closed
        if selected == self.SYSTEM_SENS:
            one = self._call_control("tf für Sensitivität", ct.tf, [1], [1])
            return self._call_control("feedback für S(s)", ct.feedback, one, L_time)
        raise ValueError(f"Unbekannte Systemauswahl: {selected}")

    def _disturbance_time_models(self, data):
        delay_tf = self._pade_delay_tf(data["delay"], data["pade_order"], label="Padé für Störung")
        plant_time = data["plant"] * delay_tf
        controller_time = data["controller"]
        prefilter_time = data["prefilter"]
        L_time = controller_time * plant_time
        one = self._call_control("tf für Störpfad", ct.tf, [1], [1])
        sensitivity = self._call_control("feedback für Störsensitivität", ct.feedback, one, L_time)
        y_from_w = prefilter_time * self._call_control("feedback Y/W", ct.feedback, L_time, 1)
        y_from_du = self._call_control("feedback Y/D_u", ct.feedback, plant_time, controller_time)
        y_from_dy = sensitivity
        ur_from_w = controller_time * prefilter_time * sensitivity
        ur_from_du = -controller_time * plant_time * sensitivity
        ur_from_dy = -controller_time * sensitivity
        u_from_du = sensitivity
        u_from_dy = ur_from_dy

        return {
            "y_from_w": y_from_w,
            "y_from_du": y_from_du,
            "y_from_dy": y_from_dy,
            "ur_from_w": ur_from_w,
            "ur_from_du": ur_from_du,
            "ur_from_dy": ur_from_dy,
            "u_from_du": u_from_du,
            "u_from_dy": u_from_dy,
        }

    def _root_locus_system(self, sys_rational, delay, pade_order):
        if not self.root_locus_include_delay_var.get() or delay <= 0:
            return sys_rational
        if pade_order <= 0:
            self._control_warnings.append(
                "Wurzelortskurve: Totzeit wurde nicht berücksichtigt, weil die Padé-Ordnung 0 ist."
            )
            return sys_rational

        num_delay, den_delay = self._call_control(
            "Padé für Wurzelortskurve",
            ct.pade,
            delay,
            pade_order,
        )
        delay_tf = self._call_control(
            "tf für Wurzelortskurven-Totzeit",
            ct.tf,
            num_delay,
            den_delay,
        )
        return sys_rational * delay_tf

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------
    def schedule_update(self):
        if self._is_updating:
            return
        if not self.auto_update_var.get():
            return

        if self._after_id is not None:
            self.after_cancel(self._after_id)

        self._after_id = self.after(350, self.update_plots)

    def _call_control(self, label, func, *args, **kwargs):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = func(*args, **kwargs)

        for warning in caught:
            self._control_warnings.append(f"{label}: {warning.message}")

        return result

    def _show_control_warnings_if_needed(self):
        if not self._control_warnings:
            self._last_warning_text = ""
            self._set_output_message("")
            return

        warnings_text = list(dict.fromkeys(self._control_warnings))
        warning_text = "\n".join(f"- {line}" for line in warnings_text)
        self._last_warning_text = warning_text
        self._set_output_message(f"Hinweise / Warnungen:\n{warning_text}", level="warning")

    def update_plots(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = None
        self._clear_hover_annotations(redraw=True)
        self._is_updating = True
        self._control_warnings = []
        self._set_output_message("")

        try:
            data = self._parse_user_input()
            self._update_root_locus_gain_parameter_controls(
                data["root_locus_gain_candidates"],
                data["root_locus_gain_parameter"],
            )
            marker_text = f"{data['root_locus_marker_gain']:.12g}"
            if self.root_locus_marker_gain_var.get() != marker_text:
                self.root_locus_marker_gain_var.set(marker_text)
            self._update_block_diagram(data)
            self._update_latex_preview(data)
            active_tab = self.notebook.index(self.notebook.select())

            if active_tab == 0:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(
                    L,
                    self.nyquist_plot_system_var.get(),
                    data=data,
                    omega=omega_out,
                )
            elif active_tab == 1:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["bode_omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(
                    L,
                    self.bode_plot_system_var.get(),
                    data=data,
                    omega=omega_out,
                )
            elif active_tab == 5:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(
                    L,
                    self.nyquist_plot_system_var.get(),
                    data=data,
                    omega=omega_out,
                )
            else:
                omega_out = L = H_freq = None

            if active_tab in (3, 5):
                sys_time = self._time_domain_system_with_pade(data, self.step_plot_system_var.get())
            else:
                sys_time = None

            if active_tab == 2:
                sys_root_locus = self._root_locus_system(
                    data["root_locus_sys_rational"],
                    data["delay"],
                    data["pade_order"],
                )
            else:
                sys_root_locus = None

            if active_tab == 0:
                self._plot_nyquist(omega_out, H_freq, data["markers"])
            elif active_tab == 1:
                self._plot_bode(omega_out, H_freq, L, data["sys_rational"])
            elif active_tab == 2:
                self._plot_root_locus(
                    sys_root_locus,
                    data["root_locus_gains"],
                    data["root_locus_marker_gain"],
                    data["delay"],
                    data["pade_order"],
                )
            elif active_tab == 3:
                self._plot_step(sys_time, data["t"], data["step_amplitude"])
            elif active_tab == 4:
                self._plot_disturbance_response(data)
            else:
                self._update_info(data, omega_out, L, H_freq, sys_time)

            if self._control_warnings:
                self.status_var.set("Aktualisiert mit Warnung.")
            else:
                self.status_var.set("Aktualisiert.")
            self._show_control_warnings_if_needed()

        except Exception as exc:
            self.status_var.set(f"Fehler: {exc}")
            self._set_output_message(f"Fehler bei der Auswertung: {exc}", level="error")
            self._show_error_in_info(exc)

        finally:
            self._is_updating = False

    def _plot_nyquist(self, omega, H, markers):
        ax = self.ax_nyquist
        self._clear_hover_for_axes(ax)
        ax.clear()

        selected = self.nyquist_plot_system_var.get()
        normalized = self.normalized_nyquist_var.get()

        omega = np.asarray(omega, dtype=float)
        H = np.asarray(H, dtype=complex)

        finite_mask = np.isfinite(omega) & np.isfinite(H.real) & np.isfinite(H.imag)
        if not np.any(finite_mask):
            raise ValueError(
                "Die Nyquist-Ortskurve enthält im dargestellten Bereich keine endlichen Punkte. "
                "Prüfe Frequenzbereich und Systemeingabe."
            )

        plot_H_full = H.copy()
        scale = 1.0
        if normalized:
            finite_abs = np.abs(H[finite_mask])
            finite_abs = finite_abs[np.isfinite(finite_abs)]
            if finite_abs.size:
                scale = float(np.max(finite_abs))
            if not np.isfinite(scale) or scale <= np.finfo(float).tiny:
                scale = 1.0
            plot_H_full = H / scale

        # Nicht-endliche Punkte treten z. B. bei I-Anteil an ω=0 auf.
        # Sie dürfen nicht für Marker/Hover verwendet werden, sonst kann Matplotlib
        # beim Zeichnen der Hover-Annotation intern scheitern.
        plot_omega = omega[finite_mask]
        plot_H = plot_H_full[finite_mask]
        omitted_points = int(np.count_nonzero(~finite_mask))

        label = selected
        ax.plot(plot_H.real, plot_H.imag, linewidth=2, label=label)

        if self.show_negative_freq_var.get():
            # For real-rational systems with pure delay, H(-jω) is the complex conjugate of H(jω).
            ax.plot(
                plot_H.real,
                -plot_H.imag,
                linestyle="--",
                linewidth=1,
                label="gespiegelte neg. Frequenzen",
            )

        if self.show_critical_point_var.get() and self._is_open_loop_selection(selected) and not normalized:
            # Der kritische Punkt -1 gehört zur Nyquist-Ortskurve des offenen Kreises.
            # Wird die Kurve normiert, wird der kritische Punkt nicht angezeigt.
            critical_point = -1.0 / scale if normalized else -1.0
            critical_label = r"kritischer Punkt $-1$"
            ax.plot(critical_point, 0, "rx", markersize=10, label=critical_label)

        # Start/end markers: bei I-Anteil ist der echte Start bei ω=0 oft unendlich
        # und deshalb nicht plottbar. Dann markieren wir den ersten endlichen Punkt.
        first_is_zero = np.isclose(plot_omega[0], 0.0, rtol=0.0, atol=1e-14)
        start_label = r"$\omega=0$" if first_is_zero else rf"$\omega={plot_omega[0]:.3g}$"
        end_label = r"$\omega\to\infty$"
        ax.plot(plot_H.real[0], plot_H.imag[0], "o", markersize=7, label=start_label)
        ax.plot(plot_H.real[-1], plot_H.imag[-1], "d", markersize=6, label=end_label)

        # User-selected omega markers
        used_marker_indices = {0, len(plot_H) - 1} if normalized else set()
        for w_mark in markers:
            idx = int(np.argmin(np.abs(plot_omega - w_mark)))
            if idx in used_marker_indices:
                continue
            used_marker_indices.add(idx)
            marker_label = rf"$\omega={plot_omega[idx]:.3g}$"
            ax.plot(plot_H.real[idx], plot_H.imag[idx], "s", markersize=7, label=marker_label)
            if not normalized:
                ax.annotate(
                    rf"$\omega={plot_omega[idx]:.3g}$",
                    (plot_H.real[idx], plot_H.imag[idx]),
                    textcoords="offset points",
                    xytext=(7, 7),
                    fontsize=9,
                )

        self._draw_direction_markers(ax, plot_H, plot_omega)

        ax.axhline(0, color="black", linewidth=0.8)
        ax.axvline(0, color="black", linewidth=0.8)
        if normalized:
            ax.grid(False)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_xlabel("")
            ax.set_ylabel("")
        else:
            ax.grid(self.grid_var.get())
            ax.set_xlabel(r"$\Re\{H(j\omega)\}$")
            ax.set_ylabel(r"$\Im\{H(j\omega)\}$")
            if omitted_points:
                self._control_warnings.append(
                    f"Nyquist/Ortskurve: {omitted_points} nicht-endliche Punkte wurden ausgelassen."
                )

        if self.equal_axis_var.get():
            ax.axis("equal")

        title = "Normierte Nyquist-Ortskurve" if normalized else "Nyquist-Ortskurve"
        if not self._is_open_loop_selection(selected) and self.show_critical_point_var.get():
            title += " (kein endlicher kritischer Punkt)"
        ax.set_title(title)

        ax.legend(loc="best", fontsize=8)

        if normalized:
            # Im Logo-/Normierungsmodus bewusst keinen Hover verwenden:
            # keine Zahlen/Raster und keine dynamischen Messwertboxen.
            self._clear_hover_for_axes(ax)
        else:
            self._register_hover(ax, "nyquist", plot_H.real, plot_H.imag, omega=np.asarray(plot_omega))

        self.fig_nyquist.tight_layout()
        self.canvas_nyquist.draw_idle()
    def _draw_direction_markers(self, ax, H, omega):
        n = len(H)
        if n < 30:
            return

        indices = [int(np.argmin(np.abs(omega - w_arrow))) for w_arrow in self._parse_direction_arrow_settings()]
        used = set()

        for i in indices:
            i = max(0, min(n - 2, i))
            if i in used:
                continue
            used.add(i)

            dx = H.real[i + 1] - H.real[i]
            dy = H.imag[i + 1] - H.imag[i]
            if abs(dx) + abs(dy) < 1e-14:
                continue

            angle = np.degrees(np.arctan2(dy, dx))
            ax.plot(
                H.real[i],
                H.imag[i],
                marker=(3, 0, angle - 90),
                markersize=10,
                linestyle="None",
                color="black",
            )

    def _interpolate_at_log_frequency(self, omega, values, omega_target):
        log_w = np.log10(np.asarray(omega, dtype=float))
        return float(np.interp(np.log10(float(omega_target)), log_w, np.asarray(values, dtype=float)))

    def _find_level_crossings(self, omega, values, level, direction="any"):
        """
        Sucht Schnittfrequenzen y(ω)=level. Die Interpolation erfolgt in log10(ω),
        weil Bode-Diagramme logarithmisch skaliert sind.

        direction:
        - "any": alle Schnittpunkte
        - "down": nur Schnittpunkte von oben nach unten
        - "up": nur Schnittpunkte von unten nach oben

        Für die Phasenreserve ist bei einem klassischen offenen Kreis in der
        Regel die 0-dB-Durchtrittsfrequenz von oben nach unten relevant.
        """
        omega = np.asarray(omega, dtype=float)
        values = np.asarray(values, dtype=float)

        mask = np.isfinite(omega) & np.isfinite(values) & (omega > 0)
        omega = omega[mask]
        values = values[mask]

        if omega.size < 2:
            return []

        log_w = np.log10(omega)
        diff = values - level
        crossings = []

        for i in range(len(diff) - 1):
            d0 = diff[i]
            d1 = diff[i + 1]

            if d0 == 0:
                if direction == "any":
                    crossings.append(float(omega[i]))
                continue

            is_crossing = d0 * d1 < 0
            is_down = d0 > 0 and d1 < 0
            is_up = d0 < 0 and d1 > 0

            if not is_crossing:
                continue
            if direction == "down" and not is_down:
                continue
            if direction == "up" and not is_up:
                continue

            frac = -d0 / (d1 - d0)
            log_wc = log_w[i] + frac * (log_w[i + 1] - log_w[i])
            crossings.append(float(10 ** log_wc))

        if diff[-1] == 0 and direction == "any":
            crossings.append(float(omega[-1]))

        # numerisch doppelte Schnittpunkte entfernen
        unique = []
        for value in crossings:
            if not unique or not np.isclose(value, unique[-1], rtol=1e-5, atol=0):
                unique.append(value)
        return unique

    def _compute_bode_margins_from_response(self, omega, L):
        """
        Berechnet Amplitudenreserve und Phasenreserve aus dem exakt ausgewerteten
        offenen Kreis L(jω). Das funktioniert auch für reine Totzeiten, weil hier
        direkt im Frequenzbereich gearbeitet wird.

        Wichtig: Auch bei einem I-Anteil wird die Phasenreserve nicht gegen -90°,
        sondern weiterhin als Abstand zur kritischen -180°-Linie am
        Amplitudendurchtritt |L(jω_c)| = 1 bestimmt. Der I-Anteil verändert also
        die Interpretation, nicht die Grundformel.
        """
        mask = np.asarray(omega) > 0
        w = np.asarray(omega, dtype=float)[mask]
        L_w = np.asarray(L, dtype=complex)[mask]

        mag = np.maximum(np.abs(L_w), np.finfo(float).tiny)
        mag_db = 20.0 * np.log10(mag)
        phase_deg = np.unwrap(np.angle(L_w)) * 180.0 / np.pi

        gain_crossings = self._find_level_crossings(w, mag_db, 0.0, direction="down")
        phase_margin_candidates = []
        for wc in gain_crossings:
            phase_at_wc = self._interpolate_at_log_frequency(w, phase_deg, wc)
            # Klassische Phasenreserve: Abstand der offenen Kreisphase zur
            # kritischen -180°-Linie am Amplitudendurchtritt.
            # Das gilt auch für offene Kreise mit I-Anteil.
            pm = 180.0 + phase_at_wc
            phase_margin_candidates.append(
                {
                    "omega": wc,
                    "phase_deg": phase_at_wc,
                    "phase_margin_deg": pm,
                }
            )

        phase_min = float(np.nanmin(phase_deg))
        phase_max = float(np.nanmax(phase_deg))
        k_min = int(np.floor((-phase_max - 180.0) / 360.0)) - 1
        k_max = int(np.ceil((-phase_min - 180.0) / 360.0)) + 1

        gain_margin_candidates = []
        for k in range(k_min, k_max + 1):
            target_phase = -180.0 - 360.0 * k
            for wp in self._find_level_crossings(w, phase_deg, target_phase):
                mag_db_at_wp = self._interpolate_at_log_frequency(w, mag_db, wp)
                gm_db = -mag_db_at_wp
                gm = 10.0 ** (gm_db / 20.0)
                gain_margin_candidates.append(
                    {
                        "omega": wp,
                        "target_phase_deg": target_phase,
                        "mag_db": mag_db_at_wp,
                        "gain_margin": gm,
                        "gain_margin_db": gm_db,
                    }
                )

        phase_margin = None
        if phase_margin_candidates:
            positive = [c for c in phase_margin_candidates if c["phase_margin_deg"] >= 0]
            if positive:
                phase_margin = min(positive, key=lambda c: c["phase_margin_deg"])
            else:
                phase_margin = max(phase_margin_candidates, key=lambda c: c["phase_margin_deg"])

        gain_margin = None
        if gain_margin_candidates:
            stable_side = [c for c in gain_margin_candidates if c["gain_margin"] >= 1.0]
            if stable_side:
                gain_margin = min(stable_side, key=lambda c: c["gain_margin"])
            else:
                gain_margin = max(gain_margin_candidates, key=lambda c: c["gain_margin"])

        return {
            "gain_margin": gain_margin,
            "phase_margin": phase_margin,
        }

    def _annotate_inside_axes(self, ax, text, xy, fontsize=9):
        """
        Fügt eine statische Annotation mit automatischer Innenpositionierung ein.
        Die Box wird bevorzugt nach unten/links/rechts geklappt, falls oberhalb
        oder rechts zu wenig Platz ist.
        """
        try:
            x_disp, y_disp = ax.transData.transform(xy)
            bbox = ax.bbox
            x_frac = (x_disp - bbox.x0) / max(bbox.width, np.finfo(float).eps)
            y_frac = (y_disp - bbox.y0) / max(bbox.height, np.finfo(float).eps)

            dx = -12 if x_frac > 0.65 else 12
            dy = -18 if y_frac > 0.62 else 12
            ha = "right" if dx < 0 else "left"
            va = "top" if dy < 0 else "bottom"
        except Exception:
            dx, dy = 12, 12
            ha, va = "left", "bottom"

        return ax.annotate(
            text,
            xy=xy,
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=fontsize,
            ha=ha,
            va=va,
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#555555", "alpha": 0.9},
            arrowprops={"arrowstyle": "->", "color": "#555555"},
            annotation_clip=False,
        )


    def _plot_bode_margins(self, ax_mag, ax_phase, omega, L_open, sys_rational=None):
        margins = self._compute_bode_margins_from_response(omega, L_open)
        integrator_order = self._count_origin_integrators(sys_rational) if sys_rational is not None else 0
        use_hz = self.bode_frequency_unit_var.get() == self.BODE_UNIT_HZ
        gain_frequency_label = r"$f_\pi$ für $A_R$" if use_hz else r"$\omega_\pi$ für $A_R$"
        phase_frequency_label = r"$f_c$ für $\varphi_R$" if use_hz else r"$\omega_c$ für $\varphi_R$"

        ax_mag.axhline(0.0, linestyle=":", linewidth=1.0, color="black", label=r"$0\,\mathrm{dB}$")
        ax_phase.axhline(-180.0, linestyle=":", linewidth=1.0, color="black", label=r"$-180^\circ$")

        gm = margins["gain_margin"]
        if gm is not None:
            wp = gm["omega"]
            plot_wp = self._omega_to_bode_frequency(wp)
            mag_db_at_wp = gm["mag_db"]
            ax_mag.axvline(plot_wp, linestyle=":", linewidth=1.0, color="black")
            ax_phase.axvline(plot_wp, linestyle=":", linewidth=1.0, color="black")
            ax_mag.plot(
                plot_wp,
                mag_db_at_wp,
                "o",
                markersize=5,
                label=gain_frequency_label,
            )
            ax_phase.plot(
                plot_wp,
                gm["target_phase_deg"],
                "o",
                markersize=5,
                label=gain_frequency_label,
            )
            ax_mag.vlines(plot_wp, mag_db_at_wp, 0.0, linestyle=":", linewidth=1.2, color="black")
            gain_frequency_text = (
                rf"$f_\pi={plot_wp:.3g}\,\mathrm{{Hz}}$"
                if use_hz
                else rf"$\omega_\pi={plot_wp:.3g}\,\mathrm{{rad/s}}$"
            )
            self._annotate_inside_axes(
                ax_mag,
                rf"$A_R={gm['gain_margin']:.3g}$"
                "\n"
                rf"$={gm['gain_margin_db']:.2f}\,\mathrm{{dB}}$"
                "\n"
                + gain_frequency_text,
                xy=(plot_wp, mag_db_at_wp),
                fontsize=9,
            )

        pm = margins["phase_margin"]
        if pm is not None:
            wc = pm["omega"]
            plot_wc = self._omega_to_bode_frequency(wc)
            phase_at_wc = pm["phase_deg"]
            ax_mag.axvline(plot_wc, linestyle="--", linewidth=1.0, color="black")
            ax_phase.axvline(plot_wc, linestyle="--", linewidth=1.0, color="black")
            ax_mag.plot(
                plot_wc,
                0.0,
                "s",
                markersize=5,
                label=phase_frequency_label,
            )

            ax_phase.plot(
                plot_wc,
                phase_at_wc,
                "s",
                markersize=5,
                label=phase_frequency_label,
            )
            ax_phase.vlines(plot_wc, -180.0, phase_at_wc, linestyle="--", linewidth=1.2, color="black")
            phase_frequency_text = (
                rf"$f_c={plot_wc:.3g}\,\mathrm{{Hz}}$"
                if use_hz
                else rf"$\omega_c={plot_wc:.3g}\,\mathrm{{rad/s}}$"
            )
            self._annotate_inside_axes(
                ax_phase,
                rf"$\varphi_R={pm['phase_margin_deg']:.2f}^\circ$"
                "\n"
                + phase_frequency_text,
                xy=(plot_wc, phase_at_wc),
                fontsize=9,
            )

        if pm is None:
            self._control_warnings.append(
                "Bode: \u03c6_R nicht definiert, weil kein 0-dB-Durchtritt von oben nach unten "
                "im dargestellten Frequenzbereich gefunden wurde."
            )

        integrator_note = self._integrator_margin_note(integrator_order)
        if integrator_note:
            self._control_warnings.append(f"Bode: {integrator_note}")

        if gm is None and pm is None:
            self._control_warnings.append(
                "Bode: Keine Durchtrittsfrequenz im dargestellten Frequenzbereich gefunden.",
            )

    def _plot_bode(self, omega, H, L_open=None, sys_rational=None):
        ax_mag = self.ax_mag
        ax_phase = self.ax_phase

        self._clear_hover_for_axes(ax_mag, ax_phase)
        ax_mag.clear()
        ax_phase.clear()

        mask = omega > 0
        if not np.any(mask):
            raise ValueError("Für den Bode-Plot muss mindestens ein ω > 0 vorhanden sein.")

        w = omega[mask]
        H_w = H[mask]
        plot_frequency = self._omega_to_bode_frequency(w)
        frequency_unit = self.bode_frequency_unit_var.get()

        mag_db = 20.0 * np.log10(np.maximum(np.abs(H_w), np.finfo(float).tiny))
        phase_deg = np.unwrap(np.angle(H_w)) * 180.0 / np.pi

        ax_mag.semilogx(plot_frequency, mag_db, linewidth=2, label=self.bode_plot_system_var.get())
        ax_mag.set_title(f"Frequenzgang / Bode - {self.bode_plot_system_var.get()}")
        ax_mag.grid(self.grid_var.get(), which="both")

        ax_phase.semilogx(plot_frequency, phase_deg, linewidth=2, label=self.bode_plot_system_var.get())
        if frequency_unit == self.BODE_UNIT_HZ:
            ax_mag.set_ylabel(r"$|H(j2\pi f)|$ [dB]")
            ax_phase.set_xlabel(r"$f$ [Hz]")
            ax_phase.set_ylabel(r"$\arg H(j2\pi f)$ [deg]")
        else:
            ax_mag.set_ylabel(r"$|H(j\omega)|$ [dB]")
            ax_phase.set_xlabel(r"$\omega$ [rad/s]")
            ax_phase.set_ylabel(r"$\arg H(j\omega)$ [deg]")
        ax_phase.grid(self.grid_var.get(), which="both")

        ax_mag.set_xlim(left=float(plot_frequency[0]), right=float(plot_frequency[-1]))
        ax_phase.set_xlim(left=float(plot_frequency[0]), right=float(plot_frequency[-1]))

        if self.show_bode_margins_var.get():
            if self._is_open_loop_selection(self.bode_plot_system_var.get()) and L_open is not None:
                self._plot_bode_margins(ax_mag, ax_phase, omega, L_open, sys_rational)
            else:
                self._control_warnings.append(
                    "Bode: Reserven werden für den offenen Kreis L(jω) bestimmt.\n"
                    "Bitte im Bode-Tab den offenen Kreis auswählen.",
                )

        if ax_mag.get_legend_handles_labels()[0]:
            ax_mag.legend(loc="best", fontsize=8)
        if ax_phase.get_legend_handles_labels()[0]:
            ax_phase.legend(loc="best", fontsize=8)

        self._register_hover(
            ax_mag,
            "bode_mag",
            plot_frequency,
            mag_db,
            phase=phase_deg,
            frequency_unit=frequency_unit,
        )
        self._register_hover(
            ax_phase,
            "bode_phase",
            plot_frequency,
            phase_deg,
            magnitude=mag_db,
            frequency_unit=frequency_unit,
        )

        self.fig_bode.tight_layout()
        self.canvas_bode.draw_idle()

    @staticmethod
    def _sampled_stable_gain_text(gains, loci, tol=1e-9):
        gains = np.asarray(gains, dtype=float)
        loci = np.asarray(loci, dtype=complex)
        stable = np.all(np.isfinite(loci), axis=1) & np.all(loci.real < -tol, axis=1)

        ranges = []
        start = None
        for index, is_stable in enumerate(stable):
            if is_stable and start is None:
                start = index
            if start is not None and (not is_stable or index == len(stable) - 1):
                end = index if is_stable and index == len(stable) - 1 else index - 1
                ranges.append((gains[start], gains[end]))
                start = None

        if not ranges:
            return "Im abgetasteten K-Bereich wurde kein asymptotisch stabiler Abschnitt gefunden."

        parts = []
        for lower, upper in ranges:
            if np.isclose(lower, upper):
                parts.append(f"K ca. {lower:.4g}")
            else:
                parts.append(f"K ca. {lower:.4g} bis {upper:.4g}")
        return "Abgetastet stabil: " + "; ".join(parts)

    def _draw_root_locus_damping_grid(self, ax):
        if not self.root_locus_show_damping_var.get():
            return

        ratios = self._parse_root_locus_damping_ratios()
        if not ratios:
            return

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        radius = max(abs(xlim[0]), abs(xlim[1]), abs(ylim[0]), abs(ylim[1]), 1.0)
        x_values = np.linspace(-1.5 * radius, 0.0, 200)

        for ratio in ratios:
            slope = np.sqrt(1.0 - ratio**2) / ratio
            y_values = -x_values * slope
            ax.plot(x_values, y_values, ":", color="#999999", linewidth=0.8, zorder=0)
            ax.plot(x_values, -y_values, ":", color="#999999", linewidth=0.8, zorder=0)

            label_x = -0.55 * radius
            label_y = -label_x * slope
            if ylim[0] <= label_y <= ylim[1]:
                ax.text(
                    label_x,
                    label_y,
                    rf"$\zeta={ratio:g}$",
                    color="#777777",
                    fontsize=7.5,
                    ha="right",
                    va="bottom",
                    clip_on=True,
                )

        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    @staticmethod
    def _set_root_locus_limits(ax, loci, open_poles, open_zeros):
        values = [np.asarray(loci, dtype=complex).reshape(-1)]
        if open_poles.size:
            values.append(np.asarray(open_poles, dtype=complex).reshape(-1))
        if open_zeros.size:
            values.append(np.asarray(open_zeros, dtype=complex).reshape(-1))

        points = np.concatenate(values)
        finite = np.isfinite(points.real) & np.isfinite(points.imag)
        points = points[finite]
        if not points.size:
            raise ValueError("Die Wurzelortskurve enthält keine endlichen Punkte.")

        x_min = min(float(np.min(points.real)), 0.0)
        x_max = max(float(np.max(points.real)), 0.0)
        y_min = min(float(np.min(points.imag)), 0.0)
        y_max = max(float(np.max(points.imag)), 0.0)

        x_span = x_max - x_min
        y_span = y_max - y_min
        reference_span = max(x_span, y_span, 1.0)
        x_padding = 0.08 * max(x_span, 0.1 * reference_span)
        y_padding = 0.08 * max(y_span, 0.1 * reference_span)

        ax.set_xlim(x_min - x_padding, x_max + x_padding)
        ax.set_ylim(y_min - y_padding, y_max + y_padding)
        return x_span, y_span

    @staticmethod
    def _draw_root_locus_direction_arrows(ax, loci):
        for branch in range(loci.shape[1]):
            points = np.asarray(loci[:, branch], dtype=complex)
            finite = np.isfinite(points.real) & np.isfinite(points.imag)
            points = points[finite]
            if points.size < 2:
                continue

            segment_lengths = np.abs(np.diff(points))
            cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
            total_length = cumulative[-1]
            if not np.isfinite(total_length) or total_length <= np.finfo(float).eps:
                continue

            for fraction in (0.35, 0.7):
                center = fraction * total_length
                start_distance = max(0.0, center - 0.025 * total_length)
                end_distance = min(total_length, center + 0.025 * total_length)
                start = complex(
                    np.interp(start_distance, cumulative, points.real),
                    np.interp(start_distance, cumulative, points.imag),
                )
                end = complex(
                    np.interp(end_distance, cumulative, points.real),
                    np.interp(end_distance, cumulative, points.imag),
                )
                if abs(end - start) <= 1e-10 * max(total_length, 1.0):
                    continue

                ax.annotate(
                    "",
                    xy=(end.real, end.imag),
                    xytext=(start.real, start.imag),
                    arrowprops={
                        "arrowstyle": "-|>",
                        "color": "#1f77b4",
                        "linewidth": 1.3,
                        "mutation_scale": 12,
                        "shrinkA": 0,
                        "shrinkB": 0,
                    },
                    zorder=4,
                )

    @staticmethod
    def _group_pole_multiplicities(poles, rtol=2e-5, atol=1e-8):
        poles = np.asarray(poles, dtype=complex).reshape(-1)
        finite = np.isfinite(poles.real) & np.isfinite(poles.imag)
        poles = poles[finite]
        groups = []

        for pole in sorted(poles, key=lambda value: (value.real, value.imag)):
            for group in groups:
                center = group["sum"] / group["count"]
                tolerance = atol + rtol * max(1.0, abs(center), abs(pole))
                if abs(pole - center) <= tolerance:
                    group["sum"] += pole
                    group["count"] += 1
                    break
            else:
                groups.append({"sum": pole, "count": 1})

        return [
            (group["sum"] / group["count"], group["count"])
            for group in groups
        ]

    @staticmethod
    def _annotate_pole_multiplicities(ax, pole_groups, color, offset):
        for pole, multiplicity in pole_groups:
            if multiplicity <= 1:
                continue
            ax.annotate(
                rf"$\times {multiplicity}$",
                xy=(pole.real, pole.imag),
                xytext=offset,
                textcoords="offset points",
                color=color,
                fontsize=9,
                fontweight="bold",
                ha="left",
                va="bottom",
                zorder=7,
                annotation_clip=False,
            )

    def _root_locus_delay_note(self, delay, pade_order):
        if delay <= 0:
            return (
                "WOK-Modell: keine Totzeit vorhanden.",
                "#eef5ff",
                "#5b7fa3",
            )
        if not self.root_locus_include_delay_var.get():
            return (
                f"ACHTUNG: Totzeit T_t = {delay:.5g} s ist vorhanden, wird in der WOK "
                "aber nicht berücksichtigt. Aktivierung unter Einstellungen > Wurzelortskurve.",
                "#ffe5e5",
                "#b22222",
            )
        if pade_order <= 0:
            return (
                f"ACHTUNG: Totzeit T_t = {delay:.5g} s ist vorhanden, kann bei Padé-Ordnung 0 "
                "aber nicht in der WOK berücksichtigt werden.",
                "#ffe5e5",
                "#b22222",
            )
        return (
            f"WOK-Modell: Totzeit T_t = {delay:.5g} s wird mit Padé-Approximation "
            f"der Ordnung {pade_order} berücksichtigt.",
            "#fff4cc",
            "#9a6700",
        )

    def _plot_root_locus(self, sys_root_locus, gains, marker_gain, delay=0.0, pade_order=0):
        ax = self.ax_root_locus
        self._clear_hover_for_axes(ax)
        ax.clear()
        self._root_locus_click_data = None

        response = self._call_control(
            "root_locus_map",
            ct.root_locus_map,
            sys_root_locus,
            gains=np.asarray(gains, dtype=float),
        )
        loci = np.asarray(response.loci, dtype=complex)
        locus_gains = np.asarray(response.gains, dtype=float)
        if loci.ndim != 2 or loci.shape[0] != locus_gains.size:
            raise ValueError("Die Wurzelortskurve konnte nicht als zweidimensionales Polraster berechnet werden.")
        if loci.shape[1] == 0:
            raise ValueError("Für eine Wurzelortskurve muss der offene Kreis mindestens einen Pol besitzen.")
        self._root_locus_click_data = {
            "loci": loci,
            "gains": locus_gains,
        }

        for branch in range(loci.shape[1]):
            branch_values = loci[:, branch]
            finite = np.isfinite(branch_values.real) & np.isfinite(branch_values.imag)
            if np.any(finite):
                ax.plot(
                    branch_values.real[finite],
                    branch_values.imag[finite],
                    color="#1f77b4",
                    linewidth=1.6,
                    label="Wurzelortskurve" if branch == 0 else None,
                )
        self._draw_root_locus_direction_arrows(ax, loci)

        open_poles = np.asarray(response.poles, dtype=complex).reshape(-1)
        open_zeros = np.asarray(response.zeros, dtype=complex).reshape(-1)
        if open_poles.size:
            open_pole_groups = self._group_pole_multiplicities(open_poles)
            unique_open_poles = np.asarray([pole for pole, _multiplicity in open_pole_groups])
            ax.plot(
                unique_open_poles.real,
                unique_open_poles.imag,
                linestyle="none",
                marker="x",
                color="#d62728",
                markersize=9,
                markeredgewidth=2,
                label="Offene Pole",
            )
            self._annotate_pole_multiplicities(
                ax,
                open_pole_groups,
                color="#d62728",
                offset=(7, 5),
            )
        if open_zeros.size:
            ax.plot(
                open_zeros.real,
                open_zeros.imag,
                linestyle="none",
                marker="o",
                markerfacecolor="none",
                markeredgecolor="#2ca02c",
                markersize=8,
                markeredgewidth=1.8,
                label="Offene Nullstellen",
            )

        marker_index = int(np.argmin(np.abs(locus_gains - marker_gain)))
        marker_poles = loci[marker_index]
        finite_marker = np.isfinite(marker_poles.real) & np.isfinite(marker_poles.imag)
        marker_poles = marker_poles[finite_marker]
        if marker_poles.size:
            marker_pole_groups = self._group_pole_multiplicities(marker_poles)
            unique_marker_poles = np.asarray([pole for pole, _multiplicity in marker_pole_groups])
            ax.plot(
                unique_marker_poles.real,
                unique_marker_poles.imag,
                linestyle="none",
                marker="D",
                color="#ff7f0e",
                markersize=6,
                label=rf"Geschlossene Pole bei $K={marker_gain:.4g}$",
            )
            self._annotate_pole_multiplicities(
                ax,
                marker_pole_groups,
                color="#ff7f0e",
                offset=(7, -14),
            )

        ax.axvline(0.0, color="black", linewidth=1.0, linestyle="--", label="Stabilitätsgrenze")
        ax.axhline(0.0, color="#555555", linewidth=0.8)
        ax.set_xlabel(r"$\Re\{s\}$ [1/s]")
        ax.set_ylabel(r"$\Im\{s\}$ [1/s]")
        ax.set_title(r"Wurzelortskurve für $1 + K L_0(s) = 0$")
        ax.grid(self.grid_var.get(), which="both")
        x_span, y_span = self._set_root_locus_limits(ax, loci, open_poles, open_zeros)
        self._draw_root_locus_damping_grid(ax)

        span_ratio = max(x_span, y_span) / max(min(x_span, y_span), np.finfo(float).eps)
        use_equal_axis = self.root_locus_equal_axis_var.get() and span_ratio <= 8.0
        if use_equal_axis:
            ax.set_aspect("equal", adjustable="box")
        else:
            ax.set_aspect("auto")

        delay_note, _delay_note_background, _delay_note_border = self._root_locus_delay_note(
            delay,
            pade_order,
        )
        if delay > 0:
            self._control_warnings.append(delay_note)

        stability_lines = []
        if marker_poles.size and np.all(marker_poles.real < -1e-9):
            marker_status = "asymptotisch stabil"
        elif marker_poles.size and np.all(marker_poles.real <= 1e-9):
            marker_status = "grenzstabil im numerischen Raster"
        else:
            marker_status = "instabil"
        stability_lines.append(f"K = {marker_gain:.5g}: {marker_status}")
        stability_lines.append(self._sampled_stable_gain_text(locus_gains, loci))
        if self.root_locus_equal_axis_var.get() and not use_equal_axis:
            stability_lines.append(
                "Gleichskalierung wegen stark unterschiedlicher Achsbereiche automatisch deaktiviert."
            )
        stability_text = "\n".join(stability_lines)
        ax.text(
            0.02,
            0.02,
            stability_text,
            transform=ax.transAxes,
            fontsize=8.5,
            va="bottom",
            ha="left",
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#777777", "alpha": 0.9},
        )

        hover_x = []
        hover_y = []
        hover_gain = []
        for branch in range(loci.shape[1]):
            branch_values = loci[:, branch]
            finite = np.isfinite(branch_values.real) & np.isfinite(branch_values.imag)
            hover_x.extend(branch_values.real[finite])
            hover_y.extend(branch_values.imag[finite])
            hover_gain.extend(locus_gains[finite])
        self._register_hover(
            ax,
            "root_locus",
            np.asarray(hover_x),
            np.asarray(hover_y),
            gain=np.asarray(hover_gain),
        )

        ax.legend(loc="best", fontsize=8)
        self.fig_root_locus.subplots_adjust(left=0.09, right=0.98, bottom=0.11, top=0.92)
        self.canvas_root_locus.draw_idle()

    def _forced_response_output(self, label, system, t, input_signal):
        response = self._call_control(label, ct.forced_response, system, T=t, U=input_signal)
        if hasattr(response, "outputs"):
            return np.asarray(response.outputs, dtype=float).reshape(-1)
        return np.asarray(response[1], dtype=float).reshape(-1)

    @staticmethod
    def _settling_time_after_step(t, y, step_time, final_value, tolerance):
        t = np.asarray(t, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = t >= step_time
        indices = np.where(mask)[0]
        if not indices.size:
            return None

        within = np.abs(y - final_value) <= tolerance
        for index in indices:
            if np.all(within[index:]):
                return float(t[index] - step_time)
        return None

    def _plot_disturbance_response(self, data):
        ax_y = self.ax_dist_y
        ax_u = self.ax_dist_u
        self._clear_hover_for_axes(ax_y, ax_u)
        ax_y.clear()
        ax_u.clear()

        models = self._disturbance_time_models(data)
        t = data["t"]
        w_signal = np.full_like(t, data["step_amplitude"], dtype=float)
        d_signal = np.where(t >= data["disturbance_time"], data["disturbance_amplitude"], 0.0)
        if data["disturbance_end_time"] is not None:
            d_signal = np.where(t >= data["disturbance_end_time"], 0.0, d_signal)

        is_output_disturbance = data["disturbance_location"] == self.DISTURBANCE_OUTPUT
        disturbance_key = "dy" if is_output_disturbance else "du"
        disturbance_symbol = r"d_y" if is_output_disturbance else r"d_u"
        disturbance_location_text = "Streckenausgang" if is_output_disturbance else "Streckeneingang"

        y_w = self._forced_response_output("Störpfad Y/W", models["y_from_w"], t, w_signal)
        y_d = self._forced_response_output(
            f"Störpfad Y/{disturbance_symbol}",
            models[f"y_from_{disturbance_key}"],
            t,
            d_signal,
        )
        y_total = y_w + y_d

        ur_w = self._forced_response_output("Störpfad U_R/W", models["ur_from_w"], t, w_signal)
        ur_d = self._forced_response_output(
            f"Störpfad U_R/{disturbance_symbol}",
            models[f"ur_from_{disturbance_key}"],
            t,
            d_signal,
        )
        ur_total = ur_w + ur_d
        u_disturbance = self._forced_response_output(
            f"Störpfad U/{disturbance_symbol}",
            models[f"u_from_{disturbance_key}"],
            t,
            d_signal,
        )
        u_total = ur_w + u_disturbance

        ax_y.plot(t, y_total, linewidth=2, label=r"$y(t)$")
        if data["disturbance_show_reference_component"]:
            ax_y.plot(t, y_w, linestyle="--", linewidth=1.2, label=r"Führungsanteil $y_w$")
        if data["disturbance_show_disturbance_component"]:
            ax_y.plot(t, y_d, linestyle=":", linewidth=1.2, label=rf"Störanteil $y_{{{disturbance_symbol}}}$")
        ax_y.axvline(data["disturbance_time"], color="black", linestyle=":", linewidth=1.0, label=r"$t_d$")
        if data["disturbance_end_time"] is not None:
            ax_y.axvline(data["disturbance_end_time"], color="#666666", linestyle="--", linewidth=1.0, label=r"$t_e$")
        ax_y.set_ylabel(r"$y(t)$ [V]")
        ax_y.set_title(rf"Störaufschaltung ${disturbance_symbol}$ am {disturbance_location_text}")
        ax_y.grid(self.grid_var.get(), which="both")

        final_value = float(y_total[-1])
        baseline_index = max(0, int(np.searchsorted(t, data["disturbance_time"]) - 1))
        baseline_value = float(y_total[baseline_index])
        tolerance = max(
            data["disturbance_settling_tolerance"] / 100.0 * max(abs(baseline_value), abs(final_value), 1.0),
            1e-6,
        )
        settling_time = self._settling_time_after_step(
            t,
            y_total,
            data["disturbance_time"],
            final_value,
            tolerance,
        )
        if settling_time is None:
            settling_text = "Ausregelzeit: nicht im Simulationsfenster"
        else:
            settling_text = f"Ausregelzeit nach Störung: {settling_time:.4g} s"
        steady_error = final_value - baseline_value
        ax_y.text(
            0.02,
            0.04,
            settling_text + f"\nEndwertänderung y: {steady_error:.4g} V",
            transform=ax_y.transAxes,
            fontsize=8.5,
            va="bottom",
            ha="left",
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#777777", "alpha": 0.9},
        )

        ax_u.plot(t, ur_total, linewidth=1.8, label=r"Reglerausgang $u_R(t)$")
        ax_u.plot(t, d_signal, linewidth=1.4, linestyle=":", label=rf"Störung ${disturbance_symbol}(t)$")
        ax_u.plot(t, u_total, linewidth=1.8, linestyle="--", label=r"Streckeneingang $u(t)$")
        ax_u.axvline(data["disturbance_time"], color="black", linestyle=":", linewidth=1.0)
        if data["disturbance_end_time"] is not None:
            ax_u.axvline(data["disturbance_end_time"], color="#666666", linestyle="--", linewidth=1.0)
        ax_u.set_xlabel(r"$t$ [s]")
        ax_u.set_ylabel("[V]")
        ax_u.grid(self.grid_var.get(), which="both")

        if ax_y.get_legend_handles_labels()[0]:
            ax_y.legend(loc="best", fontsize=8)
        if ax_u.get_legend_handles_labels()[0]:
            ax_u.legend(loc="best", fontsize=8)

        self._register_hover(ax_y, "step", t, y_total, input_signal=w_signal + d_signal)
        self._register_hover(ax_u, "step", t, u_total, input_signal=d_signal)

        if hasattr(self, "disturbance_summary_label"):
            end_text = (
                f"t_e = {data['disturbance_end_time']:.6g} s, "
                if data["disturbance_end_time"] is not None
                else "t_e = offen, "
            )
            self.disturbance_summary_label.configure(
                text=(
                    f"{disturbance_symbol}0 = {data['disturbance_amplitude']:.6g} V, "
                    + f"t_d = {data['disturbance_time']:.6g} s, "
                    + end_text
                    + f"Toleranz = {data['disturbance_settling_tolerance']:.6g} %, "
                    + f"additiv am {disturbance_location_text}"
                )
            )

        self.fig_disturbance.tight_layout()
        self.canvas_disturbance.draw_idle()

    def _update_latex_preview(self, data):
        ax = self.ax_latex
        ax.clear()
        ax.axis("off")

        open_formula = self._open_loop_latex(data["sys_rational"], data["delay"])
        closed_formula = self._closed_loop_latex(data["sys_rational"], data["delay"])
        if data["prefilter_enabled"]:
            reference_formula = rf"\left({self._transfer_function_to_latex(data['prefilter'])}\right)\,{closed_formula}"
        else:
            reference_formula = closed_formula

        ax.text(
            0.0,
            0.72,
            rf"$L(s)=K(s)G(s) = {open_formula}$",
            ha="left",
            va="center",
            fontsize=12,
        )
        ax.text(
            0.0,
            0.28,
            rf"$Y(s)/W(s) = {reference_formula}$",
            ha="left",
            va="center",
            fontsize=12,
        )
        self.fig_latex.tight_layout(pad=0.1)
        self.canvas_latex.draw_idle()

    def _tf_num_den_arrays(self, sys_rational):
        """
        Liefert die Zähler-/Nennerkoeffizienten eines SISO-TransferFunction-Systems.
        Die Koeffizienten sind in absteigender Potenzreihenfolge.
        """
        sys_tf = ct.tf(sys_rational)
        num = np.trim_zeros(np.asarray(sys_tf.num[0][0], dtype=float), trim="f")
        den = np.trim_zeros(np.asarray(sys_tf.den[0][0], dtype=float), trim="f")

        if num.size == 0:
            num = np.array([0.0])
        if den.size == 0:
            den = np.array([1.0])

        return num, den

    def _open_loop_latex(self, sys_rational, delay):
        """
        Exakte Darstellung des eingegebenen offenen Kreises.

        Bei aktiver Totzeit wird der rationale Anteil mit e^{-Ts} multipliziert.
        """
        rational_formula = self._transfer_function_to_latex(sys_rational)
        if delay > 0:
            return rational_formula + rf"\,e^{{-{delay:.4g}s}}"
        return rational_formula

    def _closed_loop_latex(self, sys_rational, delay):
        """
        Exakte Darstellung des geschlossenen Kreises bei Einheitsrueckfuehrung.

        Ohne Totzeit ist G(s)=G0/(1+G0) wieder rational und wird mit
        python-control exakt als TransferFunction berechnet.

        Mit Totzeit ist der geschlossene Kreis im Allgemeinen nicht rational.
        Dann wird er dennoch exakt algebraisch dargestellt:

            G0(s) = N(s)/D(s) * e^{-Ts}
            G(s)  = N(s)e^{-Ts} / (D(s) + N(s)e^{-Ts})

        Für die Zeitbereichssimulation wird weiterhin separat die eingestellte
        Padé-Approximation verwendet.
        """
        if delay <= 0:
            try:
                closed_tf = self._call_control(
                    "feedback für Latex-Vorschau",
                    ct.feedback,
                    sys_rational,
                    1,
                )
                return self._transfer_function_to_latex(closed_tf)
            except Exception:
                return rf"\frac{{L(s)}}{{1+L(s)}}"

        try:
            num, den = self._tf_num_den_arrays(sys_rational)
            num_latex = self._poly_to_latex(num)
            den_latex = self._poly_to_latex(den)
        except Exception:
            return rf"\frac{{L(s)}}{{1+L(s)}}"

        delay_latex = rf"e^{{-{delay:.4g}s}}"

        if num_latex == "0":
            return "0"

        if num_latex == "1":
            numerator = delay_latex
            delayed_num = delay_latex
        elif num_latex == "-1":
            numerator = rf"-{delay_latex}"
            delayed_num = rf"-{delay_latex}"
        else:
            numerator = rf"\left({num_latex}\right)\,{delay_latex}"
            delayed_num = rf"\left({num_latex}\right)\,{delay_latex}"

        denominator = rf"\left({den_latex}\right)+{delayed_num}"
        return rf"\frac{{{numerator}}}{{{denominator}}}"

    def _transfer_function_to_latex(self, sys_rational):
        try:
            num = np.asarray(sys_rational.num[0][0], dtype=float)
            den = np.asarray(sys_rational.den[0][0], dtype=float)
        except Exception:
            escaped = str(sys_rational).replace("\\", r"\\").replace("_", r"\_")
            return r"\mathrm{" + escaped + "}"

        num_latex = self._poly_to_latex(num)
        den_latex = self._poly_to_latex(den)
        if den_latex == "1":
            return num_latex
        return rf"\frac{{{num_latex}}}{{{den_latex}}}"

    def _poly_to_latex(self, coeffs):
        coeffs = np.trim_zeros(np.asarray(coeffs, dtype=float), trim="f")
        if coeffs.size == 0:
            return "0"

        degree = coeffs.size - 1
        terms = []
        for i, coeff in enumerate(coeffs):
            if abs(coeff) < 1e-12:
                continue

            power = degree - i
            sign = "-" if coeff < 0 else "+"
            mag = abs(coeff)

            if power == 0:
                body = f"{mag:.6g}"
            elif power == 1:
                body = "s" if abs(mag - 1.0) < 1e-12 else rf"{mag:.6g}s"
            else:
                body = rf"s^{power}" if abs(mag - 1.0) < 1e-12 else rf"{mag:.6g}s^{power}"

            if not terms:
                terms.append(body if sign == "+" else "-" + body)
            else:
                terms.append(f" {sign} {body}")

        return "".join(terms) if terms else "0"

    def _plot_step(self, sys_time, t, step_amplitude):
        ax = self.ax_step
        self._clear_hover_for_axes(ax)
        ax.clear()

        try:
            tout, yout = self._call_control("step_response", ct.step_response, sys_time, T=t)
            y = step_amplitude * np.squeeze(yout)
            pre_duration = max(0.1 * float(tout[-1]), np.finfo(float).eps)
            pre_points = max(2, min(200, len(tout) // 10))
            t_before = np.linspace(-pre_duration, 0.0, pre_points, endpoint=False)

            t_plot = np.concatenate((t_before, tout))
            y_plot = np.concatenate((np.zeros_like(t_before), y))
            input_signal = np.concatenate(
                (np.zeros_like(t_before), np.full_like(tout, step_amplitude, dtype=float))
            )

            ax.plot(t_plot, y_plot, linewidth=2, label=r"$y(t)$")
            ax.step(
                t_plot,
                input_signal,
                where="post",
                color="black",
                linestyle="--",
                linewidth=1.4,
                label=r"$u(t)$",
            )
            self._register_hover(ax, "step", t_plot, y_plot, input_signal=input_signal)
        except Exception as exc:
            self._control_warnings.append(
                "Sprungantwort konnte nicht berechnet werden. Mögliche Ursachen: "
                "uneigentliche Übertragungsfunktion, numerisch problematische Padé-Ordnung "
                f"oder instabiles System. Details: {exc}"
            )

        ax.set_xlabel(r"$t$ [s]")
        ax.set_ylabel(r"$y(t)$")
        ax.set_title(f"Sprungantwort - {self.step_plot_system_var.get()}")
        ax.grid(self.grid_var.get())
        if ax.lines:
            ax.legend(loc="best")

        self.fig_step.tight_layout()
        self.canvas_step.draw_idle()

    def _update_info(self, data, omega, L, H_freq, sys_time):
        text_lines = []

        text_lines.append("Aktuelle Auswertung")
        text_lines.append("=" * 72)
        text_lines.append("")
        text_lines.append(f"Nyquist-System: {self.nyquist_plot_system_var.get()}")
        text_lines.append(f"Bode-System: {self.bode_plot_system_var.get()}")
        text_lines.append(f"Sprungantwort-System: {self.step_plot_system_var.get()}")
        root_locus_label = "Wurzelortskurve"
        if data["root_locus_gain_parameter"]:
            root_locus_label += f" (Gain-Parameter {data['root_locus_gain_parameter']})"
        root_locus_info = (
            root_locus_label + ": "
            f"K = {data['root_locus_gains'][0]:.6g} bis {data['root_locus_gains'][-1]:.6g}"
        )
        root_locus_info += f", geschlossene Pole markiert bei K = {data['root_locus_marker_gain']:.6g}"
        text_lines.append(root_locus_info)
        text_lines.append(f"Totzeit: {data['delay']:.8g} s")
        text_lines.append(f"Sprungfaktor w(t): {data['step_amplitude']:.8g}")
        disturbance_symbol = "d_y" if data["disturbance_location"] == self.DISTURBANCE_OUTPUT else "d_u"
        disturbance_location_text = "Streckenausgang" if disturbance_symbol == "d_y" else "Streckeneingang"
        text_lines.append(
            f"Störaufschaltung: {disturbance_symbol}(t) = {data['disturbance_amplitude']:.8g} ab "
            + f"t = {data['disturbance_time']:.8g} s am {disturbance_location_text}, "
            + (
                f"bis t = {data['disturbance_end_time']:.8g} s, "
                if data["disturbance_end_time"] is not None
                else "ohne Endzeit, "
            )
            + f"Toleranz {data['disturbance_settling_tolerance']:.8g} %"
        )
        text_lines.append(f"Padé-Ordnung für Zeitbereich und Wurzelortskurve: {data['pade_order']}")
        text_lines.append("")

        text_lines.append("Blockdefinitionen:")
        text_lines.append(f"  Vorfilter V(s): {'aktiv' if data['prefilter_enabled'] else 'inaktiv (V=1)'}")
        if data["prefilter_enabled"]:
            text_lines.append(str(data["prefilter"]))
        text_lines.append(f"  Regler K(s): {'aktiv' if data['controller_enabled'] else 'inaktiv (K=1)'}")
        if data["controller_enabled"]:
            text_lines.append(str(data["controller"]))
        text_lines.append("  Strecke G(s):")
        text_lines.append(str(data["plant"]))
        text_lines.append("")
        text_lines.append("Offener Kreis L(s)=K(s)G(s):")
        text_lines.append(str(data["sys_rational"]))
        text_lines.append("")

        closed_formula = self._closed_loop_latex(data["sys_rational"], data["delay"])
        if data["prefilter_enabled"]:
            reference_formula = rf"({self._transfer_function_to_latex(data['prefilter'])}) * {closed_formula}"
        else:
            reference_formula = closed_formula
        text_lines.append("Exakte Übertragungsfunktionen:")
        text_lines.append(f"  L(s)       = {self._open_loop_latex(data['sys_rational'], data['delay'])}")
        text_lines.append(f"  Y(s)/W(s)  = {reference_formula}")
        text_lines.append("  Y(s)/D(s)  = G(s)/(1 + K(s)G(s))")
        if data["delay"] > 0:
            text_lines.append(
                "  Hinweis: Wegen der Totzeit sind geschlossene Pfade nicht rational; "
                "Zeitantwort und optional die Wurzelortskurve verwenden die Padé-Näherung."
            )
        text_lines.append("")

        text_lines.append("Kritischer Punkt:")
        if self._is_open_loop_selection(self.nyquist_plot_system_var.get()):
            text_lines.append("  Für die Nyquist-Ortskurve des offenen Kreises ist der kritische Punkt -1 + 0j.")
        else:
            text_lines.append(
                "  Der Punkt -1 gehört zur Nyquist-Ortskurve des offenen Kreises L(jw). "
                "Bei der Darstellung von Y/W oder S=1/(1+L) gibt es keinen entsprechenden endlichen "
                "kritischen Punkt; L=-1 bildet sich auf eine Polstelle/Unendlichkeit ab."
            )
        text_lines.append("")

        integrator_order = self._count_origin_integrators(data["sys_rational"])
        text_lines.append("I-Anteil und Stabilitätsreserven:")
        if integrator_order > 0:
            text_lines.append(f"  Netto-I-Anteil erkannt: {integrator_order} Pol(e) im Ursprung.")
            text_lines.append(
                "  Die Phasenreserve wird weiterhin bei |L(jw_c)| = 1 als Abstand zur -180-Grad-Linie berechnet. "
                "Wegen des Pols im Ursprung ist der offene Kreis nicht asymptotisch stabil; die Reserve ist "
                "deshalb ein Entwurfs-/Robustheitsmaß, aber kein alleiniger Stabilitätsbeweis."
            )
        else:
            text_lines.append("  Kein Netto-I-Anteil im rationalen offenen Kreis erkannt.")
        text_lines.append("")

        if omega is not None and L is not None and len(omega) > 0:
            text_lines.append("Ausgewählte Werte des offenen Kreises L(j omega) mit exakter Totzeit:")
            for w_mark in data["markers"]:
                idx = int(np.argmin(np.abs(omega - w_mark)))
                val = L[idx]
                text_lines.append(
                    f"  omega = {omega[idx]:.6g}: "
                    f"L = {val.real:.6g} {val.imag:+.6g}j, "
                    f"|L| = {abs(val):.6g}, "
                    f"phase = {np.angle(val):.6g} rad"
                )

            last = L[-1]
            text_lines.append("")
            text_lines.append("Letzter berechneter Frequenzpunkt als numerische Kontrolle:")
            text_lines.append(
                f"  omega_max = {omega[-1]:.6g}: "
                f"L = {last.real:.6g} {last.imag:+.6g}j, "
                f"|L| = {abs(last):.6g}, "
                f"phase = {np.angle(last):.6g} rad"
            )

        text_lines.append("")
        text_lines.append("Grenzwerte für omega -> unendlich:")
        limits = self._frequency_limit_summary(data["sys_rational"], data["delay"])
        text_lines.append(f"  Offener Kreis L(jw): {limits['open']}")
        text_lines.append(f"  Führung ohne Vorfilter L/(1+L): {limits['closed']}")
        text_lines.append(f"  Sensitivität S(jw)=1/(1+L): {limits['sensitivity']}")

        text_lines.append("")
        text_lines.append("Für die Sprungantwort verwendetes rationales System:")
        text_lines.append(str(sys_time))
        text_lines.append("")

        try:
            scaled_sys_time = data["step_amplitude"] * sys_time
            info = self._call_control("step_info", ct.step_info, scaled_sys_time, T=data["t"])
            text_lines.append("Step-Info:")
            for key, value in info.items():
                text_lines.append(f"  {key}: {value}")
        except Exception as exc:
            text_lines.append(f"Step-Info nicht verfuegbar: {exc}")

        text_lines.append("")
        text_lines.append("Hinweis:")
        text_lines.append(
            "Nyquist und Bode verwenden die Totzeit exakt im Frequenzbereich. "
            "Sprungantwort, Störaufschaltung und optional die Wurzelortskurve verwenden "
            "stattdessen die eingestellte Padé-Approximation."
        )

        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0", "\n".join(text_lines))
        self.info_text.configure(state=tk.DISABLED)

    def _show_error_in_info(self, exc):
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(
            "1.0",
            "Fehler bei der Auswertung:\n\n"
            f"{exc}\n\n"
            "Traceback:\n"
            f"{traceback.format_exc()}",
        )
        self.info_text.configure(state=tk.DISABLED)

    def _example_snapshot(self):
        return {
            "format": "control-explorer-example",
            "version": 2,
            "parameters": self.params_text.get("1.0", tk.END).strip(),
            "plant": self.plant_text.get("1.0", tk.END).strip(),
            "controller": self.controller_text.get("1.0", tk.END).strip(),
            "prefilter": self.prefilter_text.get("1.0", tk.END).strip(),
            "delay": self.delay_var.get(),
            "settings": self._example_settings_snapshot(),
        }

    def _prepare_examples_directory(self):
        try:
            self.examples_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Beispielordner",
                "Der Ordner 'Control Explorer Examples' konnte nicht erstellt oder geoeffnet werden:\n\n"
                f"{self.examples_dir}\n\n{exc}",
                parent=self,
            )
            return False
        return True

    def _set_current_example_path(self, filename):
        path = Path(filename)
        self.current_example_path = path
        self.current_example_var.set(f"Aktuelles Beispiel: {path.name}\nPfad: {path}")

    def save_example(self):
        if not self._prepare_examples_directory():
            return

        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Beispiel speichern",
            initialdir=str(self.examples_dir),
            defaultextension=".json",
            filetypes=[("Control-Explorer-Beispiel", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not filename:
            return

        try:
            with Path(filename).open("w", encoding="utf-8") as handle:
                json.dump(self._example_snapshot(), handle, indent=2, ensure_ascii=False)
            self._set_current_example_path(filename)
            self.status_var.set(f"Beispiel gespeichert: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Beispiel speichern", f"Das Beispiel konnte nicht gespeichert werden:\n\n{exc}")

    def load_example(self):
        if not self._prepare_examples_directory():
            return

        filename = filedialog.askopenfilename(
            parent=self,
            title="Beispiel laden",
            initialdir=str(self.examples_dir),
            filetypes=[("Control-Explorer-Beispiel", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not filename:
            return

        try:
            with Path(filename).open("r", encoding="utf-8") as handle:
                example = json.load(handle)
            if example.get("format") != "control-explorer-example":
                raise ValueError("Die Datei ist kein Control-Explorer-Beispiel.")

            self.params_text.delete("1.0", tk.END)
            self.params_text.insert("1.0", example.get("parameters", ""))
            self.plant_text.delete("1.0", tk.END)
            self.plant_text.insert("1.0", example.get("plant", example.get("system", "")))
            self.controller_text.delete("1.0", tk.END)
            self.controller_text.insert("1.0", example.get("controller", "1"))
            self.prefilter_text.delete("1.0", tk.END)
            self.prefilter_text.insert("1.0", example.get("prefilter", "1"))
            self.delay_var.set(example.get("delay", "0"))

            settings = example.get("settings")
            if isinstance(settings, dict):
                self._apply_settings(self._settings_subset(settings, self.EXAMPLE_SETTING_KEYS))

            self._set_current_example_path(filename)
            self.status_var.set(f"Beispiel geladen: {Path(filename).name}")
            self.update_plots()
        except Exception as exc:
            messagebox.showerror("Beispiel laden", f"Das Beispiel konnte nicht geladen werden:\n\n{exc}")


if __name__ == "__main__":
    app = ControlExplorerApp()
    app.mainloop()
