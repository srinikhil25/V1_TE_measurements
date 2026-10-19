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


def main() -> None:
    from pathlib import Path  # noqa: F401  (kept for potential future use)

    log_path = _setup_file_logging()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont

    from app.core.database import init_db
    from app.ui.login_window import LoginWindow
    from app.ui.theme import QSS

    app = QApplication(sys.argv)
    app.setApplicationName("TE Measurement")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("IkedaLab")

    # Fusion style fully respects QSS — the default Windows style ignores
    # background-color on QPushButton, making styled buttons invisible.
    app.setStyle("Fusion")

    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(QSS)

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
