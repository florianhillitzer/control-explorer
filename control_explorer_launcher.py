import queue
import threading
import tkinter as tk
import traceback
from tkinter import ttk


def _show_boot_splash():
    root = tk.Tk()
    root.withdraw()

    splash = tk.Toplevel(root)
    splash.title("Control Explorer startet")
    splash.resizable(False, False)
    splash.overrideredirect(True)

    frame = ttk.Frame(splash, padding=(24, 18))
    frame.grid(row=0, column=0, sticky="nsew")
    ttk.Label(frame, text="Control Explorer", font=("TkDefaultFont", 14, "bold")).grid(
        row=0,
        column=0,
        sticky="w",
    )
    ttk.Label(frame, text="Anwendung wird geladen...").grid(row=1, column=0, sticky="w", pady=(10, 0))
    progress = ttk.Progressbar(frame, mode="indeterminate", length=260)
    progress.grid(row=2, column=0, sticky="ew", pady=(14, 0))
    progress.start(12)

    splash.update_idletasks()
    width = max(340, splash.winfo_reqwidth())
    height = max(120, splash.winfo_reqheight())
    x = int((splash.winfo_screenwidth() - width) / 2)
    y = int((splash.winfo_screenheight() - height) / 2)
    splash.geometry(f"{width}x{height}+{x}+{y}")
    splash.deiconify()
    splash.lift()
    splash.update()
    return root, splash


def _import_app(result_queue):
    try:
        from control_explorer_gui import ControlExplorerApp
    except BaseException as exc:
        result_queue.put((None, exc, traceback.format_exc()))
    else:
        result_queue.put((ControlExplorerApp, None, None))


def _poll_import(root, result_queue):
    try:
        result = result_queue.get_nowait()
    except queue.Empty:
        root.after(50, _poll_import, root, result_queue)
        return
    root._control_explorer_import_result = result
    root.quit()


def _load_app_with_boot_splash():
    boot_root, boot_splash = _show_boot_splash()
    result_queue = queue.Queue()
    threading.Thread(target=_import_app, args=(result_queue,), daemon=True).start()
    boot_root.after(50, _poll_import, boot_root, result_queue)
    boot_root.mainloop()

    result = getattr(boot_root, "_control_explorer_import_result", None)
    try:
        boot_splash.destroy()
        boot_root.destroy()
    except tk.TclError:
        pass

    if result is None:
        raise RuntimeError("Control Explorer konnte nicht geladen werden.")
    app_class, exc, formatted_traceback = result
    if exc is not None:
        raise RuntimeError(f"Control Explorer konnte nicht geladen werden.\n{formatted_traceback}") from exc
    return app_class


def main():
    ControlExplorerApp = _load_app_with_boot_splash()
    app = ControlExplorerApp(show_startup_splash=True)
    app.mainloop()


if __name__ == "__main__":
    main()
