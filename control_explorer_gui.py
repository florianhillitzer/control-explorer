
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import traceback
import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import control as ct

from PIL import Image, ImageDraw, ImageTk
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
    - Step response uses a Pade approximation of the delay
    """

    SYSTEM_OPEN = r"Offener Kreis G_0(s)"
    SYSTEM_CLOSED = r"Geschlossener Kreis G(s)"
    SYSTEM_SENS = "Sensitivitaet S(s)"

    DEFAULT_SETTINGS = {
        "omega_min": "0",
        "omega_max": "30",
        "n_points": "6000",
        "bode_x_min": "1e-1",
        "bode_x_max": "1e3",
        "show_bode_margins": False,
        "t_max": "20",
        "t_points": "2000",
        "step_amplitude": "1",
        "pade_order": "6",
        "marker_omega": "0, 1",
        "nyquist_plot_system": SYSTEM_OPEN,
        "bode_plot_system": SYSTEM_OPEN,
        "step_plot_system": SYSTEM_CLOSED,
        "auto_update": True,
        "grid": True,
        "equal_axis": True,
        "show_negative_freq": False,
        "show_critical_point": True,
        "normalized_nyquist": False,
        "direction_arrow_omegas": "1, 5, 10, 20",
    }

    def __init__(self):
        self._set_windows_app_id()
        super().__init__()
        self._native_icon_handles = []

        self.title("Control Explorer - Nyquist, Bode, Sprungantwort")
        self._set_window_icon()
        self.geometry("1300x820")
        self.minsize(1050, 650)

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
        self._hover_after_id = None
        self._pending_hover = None
        self._last_hover_target = (None, None)
        self._sisotool_result = None

        appdata = Path(os.environ.get("APPDATA", Path.home()))
        self.settings_path = appdata / "ControlExplorer" / "settings.json"
        if getattr(sys, "frozen", False):
            self.examples_dir = Path.home() / "Documents" / "Control Explorer Examples"
        else:
            self.examples_dir = Path(__file__).resolve().parent / "examples"

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
        self.show_bode_margins_var = tk.BooleanVar(value=defaults["show_bode_margins"])

        self.t_max_var = tk.StringVar(value=defaults["t_max"])
        self.t_points_var = tk.StringVar(value=defaults["t_points"])
        self.step_amplitude_var = tk.StringVar(value=defaults["step_amplitude"])

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
            "show_bode_margins": self.show_bode_margins_var,
            "t_max": self.t_max_var,
            "t_points": self.t_points_var,
            "step_amplitude": self.step_amplitude_var,
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

    def _settings_snapshot(self):
        return {key: variable.get() for key, variable in self._settings_variables().items()}

    def _apply_settings(self, settings):
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
                raise ValueError("Die Einstellungsdatei enthaelt kein JSON-Objekt.")
            self._apply_settings(settings)
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
                json.dump(self._settings_snapshot(), handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.status_var.set(f"Einstellungen konnten nicht gespeichert werden: {exc}")

    def _schedule_settings_save(self):
        if self._loading_settings:
            return
        if self._settings_save_after_id is not None:
            self.after_cancel(self._settings_save_after_id)
        self._settings_save_after_id = self.after(500, self._save_settings)

    def reset_settings(self):
        if not messagebox.askyesno("Werkseinstellungen", "Alle Einstellungen auf Werkseinstellungen zuruecksetzen?"):
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
        settings_menu.add_separator()
        settings_menu.add_command(label="SISO Tool öffnen", command=self.open_sisotool)

        menu_bar.add_cascade(label="Einstellungen", menu=settings_menu)
        self.config(menu=menu_bar)

    def _open_direction_arrow_settings(self):
        self._open_settings_window()

    def _open_settings_window(self):
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return

        dialog = tk.Toplevel(self)
        self._settings_window = dialog
        dialog.title("Einstellungen")
        dialog.transient(self)
        dialog.geometry("540x470")
        dialog.minsize(500, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings_window(dialog))

        notebook = ttk.Notebook(dialog)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        tab_general = ttk.Frame(notebook, padding=10)
        tab_freq = ttk.Frame(notebook, padding=10)
        tab_step = ttk.Frame(notebook, padding=10)
        tab_nyquist = ttk.Frame(notebook, padding=10)

        notebook.add(tab_general, text="Allgemein")
        notebook.add(tab_freq, text="Frequenz")
        notebook.add(tab_step, text="Sprung")
        notebook.add(tab_nyquist, text="Ortskurve")

        for tab in (tab_general, tab_freq, tab_step, tab_nyquist):
            tab.columnconfigure(0, weight=1)

        self._create_general_settings(tab_general)
        self._create_frequency_settings(tab_freq)
        self._create_step_settings(tab_step)
        self._create_nyquist_settings(tab_nyquist)

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        button_frame.columnconfigure(0, weight=1)
        ttk.Button(button_frame, text="Aktualisieren", command=self.update_plots).grid(row=0, column=0, sticky="w")
        ttk.Button(button_frame, text="Werkseinstellungen", command=self.reset_settings).grid(row=0, column=1, padx=6)
        ttk.Button(button_frame, text="Schliessen", command=lambda: self._close_settings_window(dialog)).grid(row=0, column=2, sticky="e")

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
        ttk.Button(parent, text="SISO Tool öffnen", command=self.open_sisotool).grid(
            row=2, column=0, sticky="w", pady=(12, 0)
        )

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
        ttk.Label(
            bode_box,
            text="Beispiel: 1e-1 bis 1e3 entspricht 10^-1 bis 10^3 rad/s.",
            foreground="#555555",
        ).grid(row=2, column=0, sticky="w", padx=6, pady=(2, 6))

        marker_frame = ttk.Frame(parent)
        marker_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=3)
        marker_frame.columnconfigure(1, weight=1)
        ttk.Label(marker_frame, text="Marker-omega").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(marker_frame, textvariable=self.marker_omega_var).grid(row=0, column=1, sticky="ew")

    def _create_step_settings(self, parent):
        self._add_entry(parent, "t_max", self.t_max_var, 0, 0)
        self._add_entry(parent, "Punkte", self.t_points_var, 1, 0)
        self._add_entry(parent, "Sprungfaktor A", self.step_amplitude_var, 2, 0)
        self._add_entry(parent, "Pade-Ordnung", self.pade_order_var, 3, 0)
        ttk.Label(
            parent,
            text=(
                "Die Pade-Ordnung ersetzt die Totzeit fuer Zeitbereich und SISO Tool durch eine rationale Naeherung. "
                "Kleine Werte rechnen schneller, bilden die Totzeit aber grober ab. Groessere Werte sind im relevanten "
                "Frequenzbereich genauer, erhoehen jedoch Systemordnung, Rechenzeit und das Risiko numerischer Probleme. "
                "Werte zwischen 3 und 8 sind meist ein sinnvoller Ausgangspunkt."
            ),
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).grid(row=4, column=0, sticky="w", padx=6, pady=(10, 0))

    def _create_nyquist_settings(self, parent):
        ttk.Checkbutton(parent, text="axis equal", variable=self.equal_axis_var, command=self.schedule_update).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(
            parent,
            text="Gleiche Skalierung: Eine Einheit auf Real- und Imaginaerachse wird gleich lang dargestellt; die Ortskurve wird nicht geometrisch verzerrt.",
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

    def _create_layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=6)

        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self._create_left_panel(left)
        self._create_right_panel(right)

        self.status_var = tk.StringVar(value="Bereit.")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN, padding=(6, 3))
        status.grid(row=1, column=0, sticky="ew")

    def _create_left_panel(self, parent):
        parent.columnconfigure(0, weight=1)

        title = ttk.Label(parent, text="Eingaben", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        ttk.Label(
            parent,
            text="Rationaler Anteil G₀(s)"
        ).grid(row=1, column=0, sticky="w")
        self.system_text = ScrolledText(parent, height=5, width=48, wrap=tk.WORD)
        self.system_text.grid(row=2, column=0, sticky="nsew", pady=(2, 8))
        self.system_text.insert("1.0", "K_R / (s**3 + 3*s**2 + 3*s + 1)")

        ttk.Label(parent, text="Parametercode").grid(row=3, column=0, sticky="w")
        self.params_text = ScrolledText(parent, height=7, width=48, wrap=tk.NONE)
        self.params_text.grid(row=4, column=0, sticky="nsew", pady=(2, 8))
        self.params_text.insert(
            "1.0",
            "K_R = 2.0\n"
            "T_t = np.pi / 4\n"
            "\n"
            "# Beispiele:\n"
            "# T1 = 1.0\n"
            "# Kp = 1.5\n"
        )
        ttk.Label(parent, text="Übertragungsfunktionen").grid(row=6, column=0, sticky="w")
        self.fig_latex = Figure(figsize=(4.8, 1.65), dpi=100)
        self.ax_latex = self.fig_latex.add_subplot(111)
        self.ax_latex.axis("off")
        self.canvas_latex = FigureCanvasTkAgg(self.fig_latex, master=parent)
        self.canvas_latex.get_tk_widget().grid(row=7, column=0, sticky="ew", pady=(0, 8))

        delay_frame = ttk.Frame(parent)
        delay_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        delay_frame.columnconfigure(1, weight=1)
        ttk.Label(delay_frame, text="Totzeit T_t [s]").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.delay_var = tk.StringVar(value="T_t")
        ttk.Entry(delay_frame, textvariable=self.delay_var).grid(row=0, column=1, sticky="ew")

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=8, column=0, sticky="ew", pady=(4, 8))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Button(button_frame, text="Aktualisieren", command=self.update_plots).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))
        ttk.Button(button_frame, text="Einstellungen", command=self._open_settings_window).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4))
        ttk.Button(button_frame, text="Beispiel speichern", command=self.save_example).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(4, 0))
        ttk.Button(button_frame, text="Beispiel laden", command=self.load_example).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(4, 0))

        help_text = (
            "Eingabehinweise:\n"
            "- s ist als ct.TransferFunction.s definiert.\n"
            "- Parameter koennen im oberen Feld definiert werden.\n"
            "- Frequenzplots nutzen die Totzeit exakt.\n"
            "- Sprungantworten nutzen Pade fuer die Totzeit.\n"
            "- Frequenzbereich, Sprungantwort und Optionen liegen im Einstellungsfenster."
        )
        ttk.Label(parent, text=help_text, justify="left", foreground="#555555").grid(row=9, column=0, sticky="w", pady=(4, 0))

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
        self.tab_step = ttk.Frame(self.notebook)
        self.tab_info = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_nyquist, text="Nyquist / Ortskurve")
        self.notebook.add(self.tab_bode, text="Frequenzgang / Bode")
        self.notebook.add(self.tab_step, text="Sprungantwort")
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

        self._create_tab_plot_system_selector(
            self.tab_step,
            self.step_plot_system_var,
            "Standard: geschlossener Kreis",
        )

        self.fig_nyquist = Figure(figsize=(7, 6), dpi=100)
        self.ax_nyquist = self.fig_nyquist.add_subplot(111)
        self.canvas_nyquist = self._embed_figure(self.tab_nyquist, self.fig_nyquist)

        self.fig_bode = Figure(figsize=(7, 6), dpi=100)
        self.ax_mag = self.fig_bode.add_subplot(211)
        self.ax_phase = self.fig_bode.add_subplot(212)
        self.canvas_bode = self._embed_figure(self.tab_bode, self.fig_bode)

        self.fig_step = Figure(figsize=(7, 6), dpi=100)
        self.ax_step = self.fig_step.add_subplot(111)
        self.canvas_step = self._embed_figure(self.tab_step, self.fig_step)

        for canvas in (self.canvas_nyquist, self.canvas_bode, self.canvas_step):
            canvas.mpl_connect("motion_notify_event", self._on_plot_hover)
            canvas.mpl_connect("draw_event", self._cache_hover_backgrounds)

        self.info_text = ScrolledText(self.tab_info, wrap=tk.WORD)
        self.info_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.info_text.configure(state=tk.DISABLED)

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

        Wichtig: Hover-Annotationen werden bewusst ohne Pfeil gezeichnet.
        Matplotlib kann bei schnell bewegten Annotationen mit Pfeil und sehr
        nahe/ungültigen Punkten intern in split_path_inout(...) einen
        StopIteration-Fehler werfen. Ohne Pfeil bleibt die Box stabil,
        schnell und wird weiterhin dynamisch neben dem Datenpunkt positioniert.
        """
        annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            annotation_clip=False,
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#555555", "alpha": 0.95},
            arrowprops={"arrowstyle": "->", "color": "#555555"},
            fontsize=9,
            zorder=20,
        )
        annotation.set_visible(False)
        annotation.set_clip_on(False)
        if annotation.get_bbox_patch() is not None:
            annotation.get_bbox_patch().set_clip_on(False)
        if annotation.arrow_patch is not None:
            annotation.arrow_patch.set_clip_on(False)

        self._hover_annotations[ax] = annotation
        self._hover_data[ax] = {
            "kind": kind,
            "x": np.asarray(x, dtype=float),
            "y": np.asarray(y, dtype=float),
            **extra,
        }
    def _cache_hover_backgrounds(self, event):
        canvas = event.canvas
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
        self._pending_hover = (event.inaxes, event.xdata, event.ydata, event.canvas)
        if self._hover_after_id is None:
            self._hover_after_id = self.after(25, self._process_plot_hover)

    def _process_plot_hover(self):
        self._hover_after_id = None
        if self._pending_hover is None:
            return

        ax, xdata, ydata, canvas = self._pending_hover
        self._pending_hover = None

        if ax not in self._hover_data or xdata is None or ydata is None:
            changed_axes = []
            for annotation in self._hover_annotations.values():
                if annotation.get_visible():
                    annotation.set_visible(False)
                    changed_axes.append(annotation.axes)
            self._last_hover_target = (None, None)
            self._draw_hover_axes(changed_axes)
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
            text = (
                rf"$\omega = {x[idx]:.5g}\,\mathrm{{rad/s}}$" "\n"
                rf"$\left|H(j\omega)\right| = {y[idx]:.5g}\,\mathrm{{dB}}$" "\n"
                rf"$\varphi(\omega) = {data['phase'][idx]:.5g}^\circ$"
            )
        elif kind == "bode_phase":
            text = (
                rf"$\omega = {x[idx]:.5g}\,\mathrm{{rad/s}}$" "\n"
                rf"$\varphi(\omega) = {y[idx]:.5g}^\circ$" "\n"
                rf"$\left|H(j\omega)\right| = {data['magnitude'][idx]:.5g}\,\mathrm{{dB}}$"
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
            variable.trace_add("write", lambda *_: self._on_setting_changed())

        self.delay_var.trace_add("write", lambda *_: self.schedule_update())

        self.params_text.bind("<KeyRelease>", lambda _event: self.schedule_update())
        self.system_text.bind("<KeyRelease>", lambda _event: self.schedule_update())

        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self.schedule_update())

    def _on_setting_changed(self):
        if self._loading_settings:
            return
        self._schedule_settings_save()
        self.schedule_update()

    # ------------------------------------------------------------------
    # Parsing and computation
    # ------------------------------------------------------------------
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

    def _parse_user_input(self):
        env = self._base_eval_environment()

        params_code = self.params_text.get("1.0", tk.END).strip()
        system_expr = self.system_text.get("1.0", tk.END).strip()
        delay_expr = self.delay_var.get().strip() or "0"

        if params_code:
            exec(params_code, env, env)

        if not system_expr:
            raise ValueError("Es wurde keine Übertragungsfunktion eingegeben.")

        sys_rational = eval(system_expr, env, env)
        sys_rational = self._ensure_lti(sys_rational)

        delay = float(eval(delay_expr, env, env))
        if delay < 0:
            raise ValueError("Die Totzeit muss >= 0 sein.")

        omega_min = float(eval(self.omega_min_var.get(), env, env))
        omega_max = float(eval(self.omega_max_var.get(), env, env))
        n_points = int(float(eval(self.n_points_var.get(), env, env)))
        bode_x_min = float(eval(self.bode_x_min_var.get(), env, env))
        bode_x_max = float(eval(self.bode_x_max_var.get(), env, env))

        t_max = float(eval(self.t_max_var.get(), env, env))
        t_points = int(float(eval(self.t_points_var.get(), env, env)))
        step_amplitude = float(eval(self.step_amplitude_var.get(), env, env))

        pade_order = int(float(eval(self.pade_order_var.get(), env, env)))

        if omega_max <= omega_min:
            raise ValueError("ω_max muss größer als ω_min sein.")
        if n_points < 10:
            raise ValueError("Die Anzahl der Frequenzpunkte muss mindestens 10 sein.")
        if bode_x_min <= 0 or bode_x_max <= bode_x_min:
            raise ValueError("Die Bode-Grenzen muessen 0 < links < rechts erfuellen.")
        if t_max <= 0:
            raise ValueError("t_max muss > 0 sein.")
        if t_points < 10:
            raise ValueError("Die Anzahl der Zeitpunkte muss mindestens 10 sein.")
        if not np.isfinite(step_amplitude):
            raise ValueError("Der Sprungfaktor muss eine endliche Zahl sein.")
        if pade_order < 0:
            raise ValueError("Die Padé-Ordnung muss >= 0 sein.")

        omega = np.linspace(omega_min, omega_max, n_points)
        bode_omega = np.logspace(np.log10(bode_x_min), np.log10(bode_x_max), n_points)
        t = np.linspace(0.0, t_max, t_points)

        markers = self._parse_marker_frequencies(env)

        return {
            "env": env,
            "params_code": params_code,
            "system_expr": system_expr,
            "sys_rational": sys_rational,
            "delay": delay,
            "omega": omega,
            "bode_omega": bode_omega,
            "bode_x_min": bode_x_min,
            "bode_x_max": bode_x_max,
            "t": t,
            "step_amplitude": step_amplitude,
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

    def _frequency_response_exact_delay(self, sys_rational, omega, delay):
        mag, phase, omega_out = self._call_control("frequency_response", ct.frequency_response, sys_rational, omega)
        response = np.squeeze(mag) * np.exp(1j * np.squeeze(phase))

        if response.ndim != 1:
            raise ValueError("Der Frequenzgang ist nicht eindimensional. Bitte ein SISO-System verwenden.")

        delay_response = np.exp(-1j * omega_out * delay)
        L = response * delay_response
        return omega_out, L

    def _selected_frequency_system(self, L, selected):
        if selected == self.SYSTEM_OPEN:
            return L
        if selected == self.SYSTEM_CLOSED:
            return L / (1.0 + L)
        if selected == self.SYSTEM_SENS:
            return 1.0 / (1.0 + L)
        raise ValueError(f"Unbekannte Systemauswahl: {selected}")

    def _is_open_loop_selection(self, selected):
        return selected == self.SYSTEM_OPEN

    def _count_origin_integrators(self, sys_rational, tol=1e-10):
        """
        Bestimmt die Anzahl der Netto-Integratoren im offenen Kreis.

        Ein I-Anteil entspricht einem Pol im Ursprung. Falls im Zaehler ebenfalls
        Nullstellen im Ursprung liegen, werden diese als algebraische Kuerzung
        beruecksichtigt. Rueckgabe ist daher die Netto-Anzahl der Faktoren 1/s.
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
        Grenzwert des rationalen Anteils fuer s -> infinity.

        Rueckgabe:
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
        Bestimmt die Grenzwerte fuer omega -> infinity soweit eindeutig.

        Bei nichtverschwindendem rationalem Grenzwert und positiver Totzeit
        existiert wegen exp(-j omega T) kein komplexer Grenzwert.
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
                "open": "|G_0(jω)| → ∞",
                "closed": "G(jω) → 1",
                "sensitivity": "S(jω) → 0",
            }

        rational_limit = complex(rational_limit)

        if delay > 0 and abs(rational_limit) > 1e-14:
            return {
                "open": (
                    "kein komplexer Grenzwert; "
                    f"|G_0(jω)| → {abs(rational_limit):.6g} "
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

    def _time_domain_system_with_pade(self, sys_rational, delay, pade_order, selected):
        if delay > 0 and pade_order > 0:
            num_delay, den_delay = self._call_control("pade", ct.pade, delay, pade_order)
            delay_tf = self._call_control("tf fuer Pade-Totzeit", ct.tf, num_delay, den_delay)
            L_time = sys_rational * delay_tf
        else:
            L_time = sys_rational

        if selected == self.SYSTEM_OPEN:
            return L_time
        if selected == self.SYSTEM_CLOSED:
            return self._call_control("feedback fuer G(s)", ct.feedback, L_time, 1)
        if selected == self.SYSTEM_SENS:
            one = self._call_control("tf fuer Sensitivitaet", ct.tf, [1], [1])
            return self._call_control("feedback fuer S(s)", ct.feedback, one, L_time)
        raise ValueError(f"Unbekannte Systemauswahl: {selected}")

    def open_sisotool(self):
        if not hasattr(ct, "sisotool"):
            messagebox.showinfo("SISO Tool", "Diese python-control-Version stellt ct.sisotool nicht bereit.")
            return

        self._control_warnings = []
        try:
            data = self._parse_user_input()
            sys_for_tool = data["sys_rational"]

            if data["delay"] > 0:
                if data["pade_order"] <= 0:
                    self._control_warnings.append(
                        "sisotool: Totzeit wurde nicht beruecksichtigt, weil die Pade-Ordnung 0 ist."
                    )
                else:
                    num_delay, den_delay = self._call_control("pade fuer sisotool", ct.pade, data["delay"], data["pade_order"])
                    delay_tf = self._call_control("tf fuer sisotool-Totzeit", ct.tf, num_delay, den_delay)
                    sys_for_tool = sys_for_tool * delay_tf

            self._sisotool_result = self._call_control(
                "sisotool",
                ct.sisotool,
                sys_for_tool,
                omega_limits=[data["bode_x_min"], data["bode_x_max"]],
                tvect=data["t"],
            )
            plt.show(block=False)
            self._show_control_warnings_if_needed()
        except Exception as exc:
            messagebox.showerror("SISO Tool", f"ct.sisotool konnte nicht gestartet werden:\n\n{exc}")

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
            return

        warning_text = "\n".join(dict.fromkeys(self._control_warnings))
        if warning_text == self._last_warning_text:
            return

        self._last_warning_text = warning_text
        messagebox.showwarning(
            "Warnung von python-control",
            "python-control hat Warnungen ausgegeben. Die Ergebnisse koennen dadurch ungenau oder irrefuehrend sein:\n\n"
            f"{warning_text}",
        )

    def update_plots(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = None
        self._is_updating = True
        self._control_warnings = []

        try:
            data = self._parse_user_input()
            self._update_latex_preview(data)
            active_tab = self.notebook.index(self.notebook.select())

            if active_tab == 0:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(L, self.nyquist_plot_system_var.get())
            elif active_tab == 1:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["bode_omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(L, self.bode_plot_system_var.get())
            elif active_tab == 3:
                omega_out, L = self._frequency_response_exact_delay(
                    data["sys_rational"], data["omega"], data["delay"]
                )
                H_freq = self._selected_frequency_system(L, self.nyquist_plot_system_var.get())
            else:
                omega_out = L = H_freq = None

            if active_tab in (2, 3):
                sys_time = self._time_domain_system_with_pade(
                    data["sys_rational"],
                    data["delay"],
                    data["pade_order"],
                    self.step_plot_system_var.get(),
                )
            else:
                sys_time = None

            if active_tab == 0:
                self._plot_nyquist(omega_out, H_freq, data["markers"])
            elif active_tab == 1:
                self._plot_bode(omega_out, H_freq, L, data["sys_rational"])
            elif active_tab == 2:
                self._plot_step(sys_time, data["t"], data["step_amplitude"])
            else:
                self._update_info(data, omega_out, L, H_freq, sys_time)

            if self._control_warnings:
                self.status_var.set("Aktualisiert mit Warnung.")
            else:
                self.status_var.set("Aktualisiert.")
            self._show_control_warnings_if_needed()

        except Exception as exc:
            self.status_var.set(f"Fehler: {exc}")
            self._show_error_in_info(exc)

        finally:
            self._is_updating = False

    def _plot_nyquist(self, omega, H, markers):
        ax = self.ax_nyquist
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
            # Der kritische Punkt -1 gehoert zur Nyquist-Ortskurve des offenen Kreises.
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
                ax.text(
                    0.02,
                    0.98,
                    f"{omitted_points} nicht-endliche Punkte ausgelassen",
                    transform=ax.transAxes,
                    va="top",
                    ha="left",
                    fontsize=8,
                    bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#aaaaaa", "alpha": 0.85},
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
            self._hover_data.pop(ax, None)
            annotation = self._hover_annotations.pop(ax, None)
            if annotation is not None:
                annotation.set_visible(False)
            self._hover_backgrounds.pop(ax, None)
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

        ax_mag.axhline(0.0, linestyle=":", linewidth=1.0, color="black", label=r"$0\,\mathrm{dB}$")
        ax_phase.axhline(-180.0, linestyle=":", linewidth=1.0, color="black", label=r"$-180^\circ$")

        gm = margins["gain_margin"]
        if gm is not None:
            wp = gm["omega"]
            mag_db_at_wp = gm["mag_db"]
            ax_mag.axvline(wp, linestyle=":", linewidth=1.0, color="black")
            ax_phase.axvline(wp, linestyle=":", linewidth=1.0, color="black")
            ax_mag.plot(
                wp,
                mag_db_at_wp,
                "o",
                markersize=5,
                label=r"$\omega_\pi$ für $A_R$",
            )
            ax_phase.plot(
                wp,
                gm["target_phase_deg"],
                "o",
                markersize=5,
                label=r"$\omega_\pi$ für $A_R$",
            )
            ax_mag.vlines(wp, mag_db_at_wp, 0.0, linestyle=":", linewidth=1.2, color="black")
            self._annotate_inside_axes(
                ax_mag,
                rf"$A_R={gm['gain_margin']:.3g}$"
                "\n"
                rf"$={gm['gain_margin_db']:.2f}\,\mathrm{{dB}}$"
                "\n"
                rf"$\omega_\pi={wp:.3g}$",
                xy=(wp, mag_db_at_wp),
                fontsize=9,
            )

        pm = margins["phase_margin"]
        if pm is not None:
            wc = pm["omega"]
            phase_at_wc = pm["phase_deg"]
            ax_mag.axvline(wc, linestyle="--", linewidth=1.0, color="black")
            ax_phase.axvline(wc, linestyle="--", linewidth=1.0, color="black")
            ax_mag.plot(
                wc,
                0.0,
                "s",
                markersize=5,
                label=r"$\omega_c$ für $\varphi_R$",
            )

            ax_phase.plot(
                wc,
                phase_at_wc,
                "s",
                markersize=5,
                label=r"$\omega_c$ für $\varphi_R$",
            )
            ax_phase.vlines(wc, -180.0, phase_at_wc, linestyle="--", linewidth=1.2, color="black")
            self._annotate_inside_axes(
                ax_phase,
                rf"$\varphi_R={pm['phase_margin_deg']:.2f}^\circ$"
                "\n"
                rf"$\omega_c={wc:.3g}$",
                xy=(wc, phase_at_wc),
                fontsize=9,
            )

        note_y = 0.04
        if pm is None:
            ax_phase.text(
                0.02,
                note_y,
                "\u03c6_R nicht definiert: kein 0-dB-Durchtritt von oben nach unten\n"
                "im dargestellten Frequenzbereich gefunden.",
                transform=ax_phase.transAxes,
                fontsize=9,
                va="bottom",
                ha="left",
                bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#777777", "alpha": 0.9},
            )
            note_y += 0.15

        integrator_note = self._integrator_margin_note(integrator_order)
        if integrator_note:
            ax_phase.text(
                0.02,
                note_y,
                integrator_note,
                transform=ax_phase.transAxes,
                fontsize=8.5,
                va="bottom",
                ha="left",
                bbox={"boxstyle": "round,pad=0.35", "fc": "#fff7df", "ec": "#b8860b", "alpha": 0.92},
            )

        if gm is None and pm is None:
            ax_mag.text(
                0.02,
                0.04,
                "Keine Durchtrittsfrequenz im dargestellten Frequenzbereich gefunden.",
                transform=ax_mag.transAxes,
                fontsize=9,
                va="bottom",
                ha="left",
                bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#777777", "alpha": 0.9},
            )

    def _plot_bode(self, omega, H, L_open=None, sys_rational=None):
        ax_mag = self.ax_mag
        ax_phase = self.ax_phase

        ax_mag.clear()
        ax_phase.clear()

        mask = omega > 0
        if not np.any(mask):
            raise ValueError("Für den Bode-Plot muss mindestens ein ω > 0 vorhanden sein.")

        w = omega[mask]
        H_w = H[mask]

        mag_db = 20.0 * np.log10(np.maximum(np.abs(H_w), np.finfo(float).tiny))
        phase_deg = np.unwrap(np.angle(H_w)) * 180.0 / np.pi

        ax_mag.semilogx(w, mag_db, linewidth=2, label=self.bode_plot_system_var.get())
        ax_mag.set_ylabel(r"$|H(j\omega)|$ [dB]")
        ax_mag.set_title(f"Frequenzgang / Bode - {self.bode_plot_system_var.get()}")
        ax_mag.grid(self.grid_var.get(), which="both")

        ax_phase.semilogx(w, phase_deg, linewidth=2, label=self.bode_plot_system_var.get())
        ax_phase.set_xlabel(r"$\omega$ [rad/s]")
        ax_phase.set_ylabel(r"$\arg H(j\omega)$ [deg]")
        ax_phase.grid(self.grid_var.get(), which="both")

        ax_mag.set_xlim(left=float(w[0]), right=float(w[-1]))
        ax_phase.set_xlim(left=float(w[0]), right=float(w[-1]))

        if self.show_bode_margins_var.get():
            if self.bode_plot_system_var.get() == self.SYSTEM_OPEN and L_open is not None:
                self._plot_bode_margins(ax_mag, ax_phase, omega, L_open, sys_rational)
            else:
                ax_mag.text(
                    0.02,
                    0.04,
                    "Reserven werden für den offenen Kreis L(jω) bestimmt.\n"
                    "Bitte im Bode-Tab den offenen Kreis auswählen.",
                    transform=ax_mag.transAxes,
                    fontsize=9,
                    va="bottom",
                    ha="left",
                    bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#777777", "alpha": 0.9},
                )

        if ax_mag.get_legend_handles_labels()[0]:
            ax_mag.legend(loc="best", fontsize=8)
        if ax_phase.get_legend_handles_labels()[0]:
            ax_phase.legend(loc="best", fontsize=8)

        self._register_hover(ax_mag, "bode_mag", w, mag_db, phase=phase_deg)
        self._register_hover(ax_phase, "bode_phase", w, phase_deg, magnitude=mag_db)

        self.fig_bode.tight_layout()
        self.canvas_bode.draw_idle()

    def _update_latex_preview(self, data):
        ax = self.ax_latex
        ax.clear()
        ax.axis("off")

        open_formula = self._open_loop_latex(data["sys_rational"], data["delay"])
        closed_formula = self._closed_loop_latex(data["sys_rational"], data["delay"])

        ax.text(
            0.0,
            0.72,
            rf"$G_0(s) = {open_formula}$",
            ha="left",
            va="center",
            fontsize=14,
        )
        ax.text(
            0.0,
            0.28,
            rf"$G(s) = {closed_formula}$",
            ha="left",
            va="center",
            fontsize=14,
        )
        self.fig_latex.tight_layout(pad=0.1)
        self.canvas_latex.draw_idle()

    def _tf_num_den_arrays(self, sys_rational):
        """
        Liefert die Zaehler-/Nennerkoeffizienten eines SISO-TransferFunction-Systems.
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

        Fuer die Zeitbereichssimulation wird weiterhin separat die eingestellte
        Pade-Approximation verwendet.
        """
        if delay <= 0:
            try:
                closed_tf = self._call_control(
                    "feedback fuer Latex-Vorschau",
                    ct.feedback,
                    sys_rational,
                    1,
                )
                return self._transfer_function_to_latex(closed_tf)
            except Exception:
                return rf"\frac{{G_0(s)}}{{1+G_0(s)}}"

        try:
            num, den = self._tf_num_den_arrays(sys_rational)
            num_latex = self._poly_to_latex(num)
            den_latex = self._poly_to_latex(den)
        except Exception:
            return rf"\frac{{G_0(s)}}{{1+G_0(s)}}"

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
        ax.clear()
        self._hover_data.pop(ax, None)
        self._hover_annotations.pop(ax, None)

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
            self._control_warnings.append(f"step_response: {exc}")
            ax.text(
                0.05,
                0.95,
                "Sprungantwort konnte nicht berechnet werden.\n"
                "Mögliche Ursachen: uneigentliche Übertragungsfunktion,\n"
                "numerisch problematische Padé-Ordnung oder instabiles System.\n\n"
                f"{exc}",
                transform=ax.transAxes,
                va="top",
                ha="left",
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
        text_lines.append(f"Totzeit: {data['delay']:.8g} s")
        text_lines.append(f"Sprungfaktor: {data['step_amplitude']:.8g}")
        text_lines.append(f"Padé-Ordnung für Zeitbereich: {data['pade_order']}")
        text_lines.append("")
        text_lines.append("Rationaler Anteil:")
        text_lines.append(str(data["sys_rational"]))
        text_lines.append("")
        text_lines.append("Exakte Übertragungsfunktionen:")
        text_lines.append(f"  G_0(s) = {self._open_loop_latex(data['sys_rational'], data['delay'])}")
        text_lines.append(f"  G(s)   = {self._closed_loop_latex(data['sys_rational'], data['delay'])}")
        if data["delay"] > 0:
            text_lines.append(
                "  Hinweis: Wegen der Totzeit ist G(s) nicht rational; die Darstellung mit exp(-Ts) ist exakt. "
                "Nur Zeitantwort und sisotool verwenden die Padé-Näherung."
            )
        text_lines.append("")

        text_lines.append("Kritischer Punkt:")
        if self._is_open_loop_selection(self.nyquist_plot_system_var.get()):
            text_lines.append("  Für die Nyquist-Ortskurve des offenen Kreises ist der kritische Punkt -1 + 0j.")
        else:
            text_lines.append(
                "  Der Punkt -1 gehört zur Nyquist-Ortskurve des offenen Kreises L(jω). "
                "Bei der Darstellung des geschlossenen Kreises G=L/(1+L) oder der Sensitivität S=1/(1+L) "
                "gibt es keinen entsprechenden endlichen kritischen Punkt; L=-1 bildet sich auf eine Polstelle/Unendlichkeit ab."
            )
        text_lines.append("")

        integrator_order = self._count_origin_integrators(data["sys_rational"])
        text_lines.append("I-Anteil und Stabilitätsreserven:")
        if integrator_order > 0:
            text_lines.append(f"  Netto-I-Anteil erkannt: {integrator_order} Pol(e) im Ursprung.")
            text_lines.append(
                "  Die Phasenreserve wird weiterhin bei |G_0(jω_c)| = 1 als Abstand zur -180°-Linie berechnet; "
                "sie wird also nicht gegen -90° gemessen. Wegen des Pols im Ursprung ist der offene Kreis "
                "nicht asymptotisch stabil; die Reserve ist deshalb ein Entwurfs-/Robustheitsmaß, aber kein "
                "alleiniger Stabilitätsbeweis. Für Stabilität zusätzlich Nyquist/geschlossene Pole prüfen."
            )
        else:
            text_lines.append("  Kein Netto-I-Anteil im rationalen offenen Kreis erkannt.")
        text_lines.append("")

        # A few characteristic values for the open loop G_0(j omega)
        text_lines.append("Ausgewaehlte Werte des offenen Kreises G_0(j omega) mit exakter Totzeit:")
        for w_mark in data["markers"]:
            idx = int(np.argmin(np.abs(omega - w_mark)))
            val = L[idx]
            text_lines.append(
                f"  ω = {omega[idx]:.6g}: "
                f"G_0 = {val.real:.6g} {val.imag:+.6g}j, "
                f"|L| = {abs(val):.6g}, "
                f"phase = {np.angle(val):.6g} rad"
            )

        text_lines.append("")
        text_lines.append("Grenzwerte für ω -> ∞:")
        limits = self._frequency_limit_summary(data["sys_rational"], data["delay"])
        text_lines.append(f"  Offener Kreis G_0(jω): {limits['open']}")
        text_lines.append(f"  Geschlossener Kreis G(jω)=G_0/(1+G_0): {limits['closed']}")
        text_lines.append(f"  Sensitivität S(jω)=1/(1+G_0): {limits['sensitivity']}")

        if omega is not None and L is not None and len(omega) > 0:
            last = L[-1]
            text_lines.append("")
            text_lines.append("Letzter berechneter Frequenzpunkt als numerische Kontrolle:")
            text_lines.append(
                f"  ω_max = {omega[-1]:.6g}: "
                f"G_0 = {last.real:.6g} {last.imag:+.6g}j, "
                f"|L| = {abs(last):.6g}, "
                f"phase = {np.angle(last):.6g} rad"
            )

        text_lines.append("")
        text_lines.append("Für die Sprungantwort verwendetes rationales System:")
        text_lines.append(str(sys_time))
        text_lines.append("")

        # Step response information
        try:
            scaled_sys_time = data["step_amplitude"] * sys_time
            info = self._call_control("step_info", ct.step_info, scaled_sys_time, T=data["t"])
            text_lines.append("Step-Info:")
            for key, value in info.items():
                text_lines.append(f"  {key}: {value}")
        except Exception as exc:
            text_lines.append(f"Step-Info nicht verfügbar: {exc}")

        text_lines.append("")
        text_lines.append("Hinweis:")
        text_lines.append(
            "Nyquist und Bode verwenden die Totzeit exakt im Frequenzbereich. "
            "Die Sprungantwort verwendet stattdessen die eingestellte Padé-Approximation."
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
            "version": 1,
            "parameters": self.params_text.get("1.0", tk.END).strip(),
            "system": self.system_text.get("1.0", tk.END).strip(),
            "delay": self.delay_var.get(),
            "settings": self._settings_snapshot(),
        }

    def save_example(self):
        try:
            self.examples_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Beispiel speichern",
            initialdir=str(self.examples_dir if self.examples_dir.exists() else Path(__file__).resolve().parent),
            defaultextension=".json",
            filetypes=[("Control-Explorer-Beispiel", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not filename:
            return

        try:
            with Path(filename).open("w", encoding="utf-8") as handle:
                json.dump(self._example_snapshot(), handle, indent=2, ensure_ascii=False)
            self.status_var.set(f"Beispiel gespeichert: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Beispiel speichern", f"Das Beispiel konnte nicht gespeichert werden:\n\n{exc}")

    def load_example(self):
        filename = filedialog.askopenfilename(
            parent=self,
            title="Beispiel laden",
            initialdir=str(self.examples_dir if self.examples_dir.exists() else Path(__file__).resolve().parent),
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
            self.system_text.delete("1.0", tk.END)
            self.system_text.insert("1.0", example.get("system", ""))
            self.delay_var.set(example.get("delay", "0"))

            settings = example.get("settings")
            if isinstance(settings, dict):
                self._apply_settings(settings)
                self._save_settings()

            self.status_var.set(f"Beispiel geladen: {Path(filename).name}")
            self.update_plots()
        except Exception as exc:
            messagebox.showerror("Beispiel laden", f"Das Beispiel konnte nicht geladen werden:\n\n{exc}")


if __name__ == "__main__":
    app = ControlExplorerApp()
    app.mainloop()
