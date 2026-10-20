"""TE Measurement Desktop — application entry point."""

import sys
import logging

# IMPORTANT — keep top-level imports lightweight (no Qt, no heavy C extensions).
# Python's multiprocessing uses the 'spawn' start method on Windows, which
# reimports __main__ (this file) in every worker subprocess.  Loading Qt DLLs
# in the subprocess corrupts the DirectShow/WMF device state before the IR
# camera worker can call usb_init, causing null-pointer crashes in set_palette.
# All Qt and app-level imports are deferred into main() / __main__ guard below.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def _setup_file_logging() -> str:
    """Always write logs to a file, even when launched without a console
    (pythonw.exe). Returns the log file path."""
    import os
    from pathlib import Path
    try:
        base = Path(os.environ.get("APPDATA", Path.home())) / "TEMeasurement"
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path.home()
    log_path = base / "app.log"
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(fh)
    root.setLevel(logging.INFO)

    # Capture any uncaught exception to the log file too.
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.getLogger("uncaught").critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    logging.getLogger("startup").info("==== TE Measurement started — log at %s ====", log_path)
    return str(log_path)


def _install_signal_handlers(app) -> None:
    """Ctrl+C / Ctrl+Break / console close → orderly quit (heater off via aboutToQuit).

    Qt's event loop does not return to Python on its own, so a short timer lets
    the interpreter run pending signal handlers. A force-kill (Task Manager,
    power loss) cannot be caught — that is what the hardware interlock is for.
    """
    import signal
    from PyQt6.QtCore import QTimer

    def _quit(signum, _frame):
        logging.getLogger("startup").warning("Signal %s received — shutting down", signum)
        app.quit()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _quit)
            except (ValueError, OSError):
                pass
    timer = QTimer(app)
    timer.timeout.connect(lambda: None)
    timer.start(250)


def main() -> None:
    from pathlib import Path  # noqa: F401  (kept for potential future use)

    log_path = _setup_file_logging()

    from PyQt6.QtWidgets import QApplication

    from app.core.database import init_db
    from app.ui.login_window import LoginWindow
    from app.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("TE Measurement")
    from app.version import APP_VERSION
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("IkedaLab")

    # Fusion style + palette + fonts + global style sheet (see app/ui/theme.py).
    apply_theme(app)

    from PyQt6.QtCore import QLockFile
    from PyQt6.QtWidgets import QMessageBox
    from app.core.paths import get_app_dir

    # One instance only: two copies would fight over the same GPIB
    # instruments, and the second would mark the first's live run as
    # interrupted in the database.
    lock = QLockFile(str(get_app_dir() / "te_measurement.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, "TE Measurement",
                            "TE Measurement is already running on this PC.")
        sys.exit(1)

    try:
        init_db()
    except Exception as exc:
        logging.getLogger("startup").exception("Database initialisation failed")
        QMessageBox.critical(
            None, "Database error",
            "The measurement database could not be opened or upgraded:\n\n"
            f"{exc}\n\nNo changes were kept. A backup copy is in the "
            "application data folder (if an upgrade was attempted).\n"
            f"Log file: {log_path}")
        sys.exit(1)

    from app.core.config import config_path, get_config, load_warnings
    get_config()
    if load_warnings():
        QMessageBox.warning(
            None, "Configuration problem",
            f"{config_path()} has problems, so built-in defaults are in use:\n\n"
            + "\n".join(load_warnings()[:12])
            + "\n\nFix them in Settings (saving rewrites the file) or edit the file.")

    # Backstop for every exit path that still runs the event loop to the end
    # (window close is guarded by MainWindow.closeEvent with a confirmation).
    from app.services.measurement_service import stop_all_measurements
    app.aboutToQuit.connect(lambda: stop_all_measurements(timeout_s=30))
    # Windows log-off / shutdown: stop runs before the session ends.
    app.commitDataRequest.connect(lambda _mgr: stop_all_measurements(timeout_s=30))
    _install_signal_handlers(app)

    from app.core import audit
    from app.version import APP_VERSION
    audit.record("app_started", use_current_user=False,
                 details={"version": APP_VERSION, "log": log_path})

    window = LoginWindow()
    window.show()

    code = app.exec()
    stop_all_measurements(timeout_s=30)
    lock.unlock()
    sys.exit(code)


if __name__ == "__main__":
    # MUST be the first call. When frozen (PyInstaller), the IR-camera worker is
    # started with multiprocessing 'spawn', which relaunches this same .exe. Without
    # freeze_support() every spawned worker would fall through and open a new GUI
    # window (fork-bomb). freeze_support() intercepts the child bootstrap, runs the
    # worker target, and exits — a no-op in the normal (unfrozen) interpreter.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
