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


def main() -> None:
    from pathlib import Path  # noqa: F401  (kept for potential future use)

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

    init_db()

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
