"""'Save data…' / 'Save graphs…' — one implementation for every page.

File naming, formats and the Run sheet come from ``app.services.run_export``;
this module only adds the dialogs. The folder of the last save is remembered for
the session so consecutive exports land together.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ...services.run_export import (
    RunTable,
    default_filename,
    with_extension,
    write_csv,
    write_xlsx,
)

DATA_FILTER = "Excel workbook (*.xlsx);;CSV file (*.csv)"
NO_DATA = "There is no data to save yet."

_last_dir = ""


def _suggest(name: str) -> str:
    return os.path.join(_last_dir, name) if _last_dir else name


def _remember(path: str) -> None:
    global _last_dir
    _last_dir = os.path.dirname(os.path.abspath(path))


def chart_png(widget: QWidget) -> Optional[bytes]:
    """The widget as it is on screen, PNG-encoded; None if it has no pixels."""
    pix = widget.grab()
    if pix.isNull():
        return None
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(buf.data().data())


def save_data(parent: QWidget, table: RunTable, *, kind: str, run_id: Optional[int] = None,
              sample: Optional[str] = None,
              charts: Sequence[Tuple[str, QWidget]] = ()) -> Optional[str]:
    """Ask for a file and write ``table`` as .xlsx (with ``charts`` embedded and
    a Run sheet) or .csv (readings only). Returns the path written, or None."""
    if not table.rows:
        QMessageBox.information(parent, "Save data", NO_DATA)
        return None
    path, selected = QFileDialog.getSaveFileName(
        parent, "Save data", _suggest(default_filename(kind, run_id=run_id, sample=sample)),
        DATA_FILTER)
    if not path:
        return None
    path, fmt = with_extension(path, selected)
    embedded = True
    try:
        if fmt == "csv":
            write_csv(path, table)
        else:
            images = [(title, png) for title, w in charts if (png := chart_png(w))]
            embedded = write_xlsx(path, table, images)
    except Exception as exc:
        QMessageBox.critical(parent, "Save data", f"Could not save the file:\n{exc}")
        return None
    _remember(path)
    msg = f"Saved to:\n{path}"
    if fmt == "csv":
        msg += "\n\nCSV holds the readings only; the Excel file also has the run details and charts."
    elif not embedded:
        msg += "\n\nThe charts were not embedded (the Pillow package is missing)."
    QMessageBox.information(parent, "Save data", msg)
    return path


def save_graphs(parent: QWidget, charts: Sequence[Tuple[QWidget, str]], *, kind: str,
                run_id: Optional[int] = None, sample: Optional[str] = None,
                has_data: bool = True) -> List[str]:
    """Save each (widget, suffix) as PNG. One chart: ask for its file name;
    several: ask for a base name and append ``_<suffix>.png`` to each."""
    title = "Save graph" if len(charts) == 1 else "Save graphs"
    if not has_data:
        QMessageBox.information(parent, title, NO_DATA)
        return []
    if len(charts) == 1:
        suggestion = default_filename(kind, run_id=run_id, sample=sample,
                                      what=charts[0][1], ext="png")
    else:
        suggestion = default_filename(kind, run_id=run_id, sample=sample, what="graphs", ext="")
    path, _ = QFileDialog.getSaveFileName(parent, title, _suggest(suggestion), "PNG image (*.png)")
    if not path:
        return []
    root, ext = os.path.splitext(path)
    if len(charts) == 1:
        targets = [(charts[0][0], path if ext.lower() == ".png" else path + ".png")]
    else:
        targets = [(w, f"{root}_{suffix}.png") for w, suffix in charts]
    saved, empty = [], []
    try:
        for widget, target in targets:
            png = chart_png(widget)
            if png is None:
                empty.append(os.path.basename(target))
                continue
            with open(target, "wb") as f:
                f.write(png)
            saved.append(target)
    except OSError as exc:
        QMessageBox.critical(parent, title, f"Could not save:\n{exc}")
        return saved
    if saved:
        _remember(saved[0])
    msg = ("Saved to:\n" + saved[0]) if len(saved) == 1 else (
        f"Saved in {os.path.dirname(saved[0])}:\n"
        + "\n".join(os.path.basename(p) for p in saved)) if saved else "Nothing was saved."
    if empty:
        msg += "\n\nEmpty (not shown on screen): " + ", ".join(empty)
    QMessageBox.information(parent, title, msg)
    return saved
