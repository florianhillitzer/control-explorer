
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import traceback
import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import control as ct


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
        "t_max": "20",
        "t_points": "2000",
        "step_amplitude": "1",
        "pade_order": "6",
        "marker_omega": "0, 1",
        "plot_system": SYSTEM_OPEN,
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
        self._sisotool_result = None

        appdata = Path(os.environ.get("APPDATA", Path.home()))
        self.settings_path = appdata / "ControlExplorer" / "settings.json"
        self.examples_dir = Path(__file__).resolve().parent / "examples"

        self._create_variables()
        self._load_settings()
        self._create_menu()
        self._create_layout()
        self._bind_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.schedule_update()

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
        app_dir = Path(__file__).resolve().parent
        png_path = app_dir / "control_explorer_icon.png"
        ico_path = app_dir / "control_explorer.ico"

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

        self.t_max_var = tk.StringVar(value=defaults["t_max"])
        self.t_points_var = tk.StringVar(value=defaults["t_points"])
        self.step_amplitude_var = tk.StringVar(value=defaults["step_amplitude"])

        self.pade_order_var = tk.StringVar(value=defaults["pade_order"])
        self.marker_omega_var = tk.StringVar(value=defaults["marker_omega"])

        self.plot_system_var = tk.StringVar(value=defaults["plot_system"])
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
            "t_max": self.t_max_var,
            "t_points": self.t_points_var,
            "step_amplitude": self.step_amplitude_var,
            "pade_order": self.pade_order_var,
            "marker_omega": self.marker_omega_var,
            "plot_system": self.plot_system_var,
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
        plot_frame = ttk.Frame(parent)
        plot_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        plot_frame.columnconfigure(1, weight=1)
        ttk.Label(plot_frame, text="Plot-System").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            plot_frame,
            textvariable=self.plot_system_var,
            values=[self.SYSTEM_OPEN, self.SYSTEM_CLOSED, self.SYSTEM_SENS],
            state="readonly",
        ).grid(row=0, column=1, sticky="ew")

        ttk.Checkbutton(parent, text="Auto-Update", variable=self.auto_update_var, command=self.schedule_update).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="Grid anzeigen", variable=self.grid_var, command=self.schedule_update).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Button(parent, text="SISO Tool öffnen", command=self.open_sisotool).grid(row=3, column=0, sticky="w", pady=(12, 0))

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

        ttk.Label(parent, text="Parametercode").grid(row=1, column=0, sticky="w")
        self.params_text = ScrolledText(parent, height=7, width=48, wrap=tk.NONE)
        self.params_text.grid(row=2, column=0, sticky="nsew", pady=(2, 8))
        self.params_text.insert(
            "1.0",
            "K_R = 2.0\n"
            "T_t = np.pi / 4\n"
            "\n"
            "# Beispiele:\n"
            "# T1 = 1.0\n"
            "# Kp = 1.5\n"
        )

        ttk.Label(parent, text="Rationaler Anteil G_0,rational(s)").grid(row=3, column=0, sticky="w")
        self.system_text = ScrolledText(parent, height=5, width=48, wrap=tk.WORD)
        self.system_text.grid(row=4, column=0, sticky="nsew", pady=(2, 8))
        self.system_text.insert("1.0", "K_R / (s**3 + 3*s**2 + 3*s + 1)")

        self.fig_latex = Figure(figsize=(4.6, 0.75), dpi=100)
        self.ax_latex = self.fig_latex.add_subplot(111)
        self.ax_latex.axis("off")
        self.canvas_latex = FigureCanvasTkAgg(self.fig_latex, master=parent)
        self.canvas_latex.get_tk_widget().grid(row=5, column=0, sticky="ew", pady=(0, 8))

        delay_frame = ttk.Frame(parent)
        delay_frame.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        delay_frame.columnconfigure(1, weight=1)
        ttk.Label(delay_frame, text="Totzeit T_t [s]").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.delay_var = tk.StringVar(value="T_t")
        ttk.Entry(delay_frame, textvariable=self.delay_var).grid(row=0, column=1, sticky="ew")

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=7, column=0, sticky="ew", pady=(4, 8))
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
        ttk.Label(parent, text=help_text, justify="left", foreground="#555555").grid(row=8, column=0, sticky="w", pady=(4, 0))

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

        self.info_text = ScrolledText(self.tab_info, wrap=tk.WORD)
        self.info_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.info_text.configure(state=tk.DISABLED)

    def _embed_figure(self, parent, fig):
        canvas = FigureCanvasTkAgg(fig, master=parent)
        toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.TOP, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        return canvas

    def _register_hover(self, ax, kind, x, y, **extra):
        annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#555555", "alpha": 0.95},
            arrowprops={"arrowstyle": "->", "color": "#555555"},
            fontsize=9,
            zorder=20,
        )
        annotation.set_visible(False)
        self._hover_annotations[ax] = annotation
        self._hover_data[ax] = {
            "kind": kind,
            "x": np.asarray(x),
            "y": np.asarray(y),
            **extra,
        }

    def _on_plot_hover(self, event):
        ax = event.inaxes
        if ax not in self._hover_data or event.xdata is None or event.ydata is None:
            changed_canvases = set()
            for annotation in self._hover_annotations.values():
                if annotation.get_visible():
                    annotation.set_visible(False)
                    changed_canvases.add(annotation.figure.canvas)
            for canvas in changed_canvases:
                canvas.draw_idle()
            return

        data = self._hover_data[ax]
        x = data["x"]
        y = data["y"]
        if not x.size:
            return

        if data["kind"].startswith("bode") and event.xdata > 0:
            idx = int(np.argmin(np.abs(np.log10(x) - np.log10(event.xdata))))
        else:
            x_span = max(abs(ax.get_xlim()[1] - ax.get_xlim()[0]), np.finfo(float).eps)
            y_span = max(abs(ax.get_ylim()[1] - ax.get_ylim()[0]), np.finfo(float).eps)
            idx = int(np.argmin(((x - event.xdata) / x_span) ** 2 + ((y - event.ydata) / y_span) ** 2))

        kind = data["kind"]
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

        changed_canvases = {event.canvas}
        for hover_ax, annotation in self._hover_annotations.items():
            should_be_visible = hover_ax is ax
            if annotation.get_visible() != should_be_visible:
                annotation.set_visible(should_be_visible)
                changed_canvases.add(annotation.figure.canvas)

        annotation = self._hover_annotations[ax]
        annotation.xy = (x[idx], y[idx])
        annotation.set_text(text)
        for canvas in changed_canvases:
            canvas.draw_idle()

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

    def _selected_frequency_system(self, L):
        selected = self.plot_system_var.get()
        if selected == self.SYSTEM_OPEN:
            return L
        if selected == self.SYSTEM_CLOSED:
            return L / (1.0 + L)
        if selected == self.SYSTEM_SENS:
            return 1.0 / (1.0 + L)
        raise ValueError(f"Unbekannte Systemauswahl: {selected}")

    def _time_domain_system_with_pade(self, sys_rational, delay, pade_order):
        if delay > 0 and pade_order > 0:
            num_delay, den_delay = self._call_control("pade", ct.pade, delay, pade_order)
            delay_tf = self._call_control("tf fuer Pade-Totzeit", ct.tf, num_delay, den_delay)
            L_time = sys_rational * delay_tf
        else:
            L_time = sys_rational

        selected = self.plot_system_var.get()
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

            if active_tab in (0, 3):
                omega_out, L = self._frequency_response_exact_delay(data["sys_rational"], data["omega"], data["delay"])
                H_freq = self._selected_frequency_system(L)
            elif active_tab == 1:
                omega_out, L = self._frequency_response_exact_delay(data["sys_rational"], data["bode_omega"], data["delay"])
                H_freq = self._selected_frequency_system(L)
            else:
                omega_out = L = H_freq = None

            if active_tab in (2, 3):
                sys_time = self._time_domain_system_with_pade(data["sys_rational"], data["delay"], data["pade_order"])
            else:
                sys_time = None

            if active_tab == 0:
                self._plot_nyquist(omega_out, H_freq, data["markers"])
            elif active_tab == 1:
                self._plot_bode(omega_out, H_freq)
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

        plot_H = H
        normalized = self.normalized_nyquist_var.get()
        if normalized:
            scale = np.max(np.abs(H))
            if scale > np.finfo(float).tiny:
                plot_H = H / scale

        label = self.plot_system_var.get()
        ax.plot(plot_H.real, plot_H.imag, linewidth=2, label=label)

        if self.show_negative_freq_var.get():
            # For real-rational systems with pure delay, H(-jω) is the complex conjugate of H(jω).
            ax.plot(plot_H.real, -plot_H.imag, linestyle="--", linewidth=1, label="gespiegelte neg. Frequenzen")

        if self.show_critical_point_var.get() and not normalized:
            ax.plot(-1, 0, "rx", markersize=10, label=r"kritischer Punkt $-1$")

        # Start/end markers
        ax.plot(plot_H.real[0], plot_H.imag[0], "o", markersize=7, label="_nolegend_")
        ax.plot(plot_H.real[-1], plot_H.imag[-1], "d", markersize=6, label="_nolegend_")

        # User-selected omega markers
        used_marker_indices = set()
        for w_mark in markers:
            idx = int(np.argmin(np.abs(omega - w_mark)))
            if idx in used_marker_indices:
                continue
            used_marker_indices.add(idx)
            marker_label = "_nolegend_" if normalized else rf"$\omega={omega[idx]:.3g}$"
            ax.plot(plot_H.real[idx], plot_H.imag[idx], "s", markersize=7, label=marker_label)
            if not normalized:
                ax.annotate(
                    rf"$\omega={omega[idx]:.3g}$",
                    (plot_H.real[idx], plot_H.imag[idx]),
                    textcoords="offset points",
                    xytext=(7, 7),
                    fontsize=9,
                )

        self._draw_direction_markers(ax, plot_H, omega)

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

        if self.equal_axis_var.get():
            ax.axis("equal")

        ax.set_title("Normierte Nyquist-Ortskurve" if normalized else "Nyquist-Ortskurve")
        if not normalized:
            ax.legend(loc="best", fontsize=8)
        self._register_hover(ax, "nyquist", plot_H.real, plot_H.imag, omega=np.asarray(omega))
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

    def _plot_bode(self, omega, H):
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

        ax_mag.semilogx(w, mag_db, linewidth=2)
        ax_mag.set_ylabel(r"$|H(j\omega)|$ [dB]")
        ax_mag.set_title("Frequenzgang / Bode")
        ax_mag.grid(self.grid_var.get(), which="both")

        ax_phase.semilogx(w, phase_deg, linewidth=2)
        ax_phase.set_xlabel(r"$\omega$ [rad/s]")
        ax_phase.set_ylabel(r"$\arg H(j\omega)$ [deg]")
        ax_phase.grid(self.grid_var.get(), which="both")

        ax_mag.set_xlim(left=float(w[0]), right=float(w[-1]))
        ax_phase.set_xlim(left=float(w[0]), right=float(w[-1]))

        self._register_hover(ax_mag, "bode_mag", w, mag_db, phase=phase_deg)
        self._register_hover(ax_phase, "bode_phase", w, phase_deg, magnitude=mag_db)

        self.fig_bode.tight_layout()
        self.canvas_bode.draw_idle()

    def _update_latex_preview(self, data):
        ax = self.ax_latex
        ax.clear()
        ax.axis("off")

        formula = self._transfer_function_to_latex(data["sys_rational"])
        if data["delay"] > 0:
            formula = formula + rf"\,e^{{-{data['delay']:.4g}s}}"

        ax.text(0.5, 0.5, rf"$G_0(s) = {formula}$", ha="center", va="center", fontsize=12)
        self.fig_latex.tight_layout(pad=0.1)
        self.canvas_latex.draw_idle()

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
        ax.set_title("Sprungantwort")
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
        text_lines.append(f"Plot-System: {self.plot_system_var.get()}")
        text_lines.append(f"Totzeit: {data['delay']:.8g} s")
        text_lines.append(f"Sprungfaktor: {data['step_amplitude']:.8g}")
        text_lines.append(f"Padé-Ordnung für Zeitbereich: {data['pade_order']}")
        text_lines.append("")
        text_lines.append("Rationaler Anteil:")
        text_lines.append(str(data["sys_rational"]))
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
        text_lines.append("Für den Zeitbereich verwendetes rationales System:")
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
