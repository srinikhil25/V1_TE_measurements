"""Live-chart data helpers for long runs (UI-2).

The full data always stays in the run (and in exports); only what is *drawn*
is reduced:

* :class:`ColumnBuffer` — append-only float columns in a growing numpy
  array, so a 1 s poll converts only the rows that arrived since the last
  poll instead of rebuilding Python lists of every row.
* :func:`fast_time_curve` — for time-series curves (x increasing): pyqtgraph
  draws at most a few points per pixel ("peak" keeps each chunk's min and
  max, so spikes and the auto-range stay intact) and skips points outside
  the visible x-range once the user zooms in.
* :func:`thin` — for parametric curves such as TEMF vs ΔT, where x is not
  monotonic and pixel-based downsampling does not apply: an even stride
  that always keeps the newest point.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np

#: Upper bound on points drawn for parametric (x not monotonic) curves.
MAX_PARAMETRIC_POINTS = 3000


class ColumnBuffer:
    """Append-only table of float columns; ``None`` is stored as NaN."""

    def __init__(self, n_cols: int, capacity: int = 1024):
        self._n_cols = n_cols
        self._a = np.empty((max(16, capacity), n_cols), dtype=float)
        self._n = 0

    def __len__(self) -> int:
        return self._n

    def clear(self) -> None:
        self._n = 0

    def append(self, values: Sequence) -> None:
        if self._n == len(self._a):
            grown = np.empty((len(self._a) * 2, self._n_cols), dtype=float)
            grown[: self._n] = self._a[: self._n]
            self._a = grown
        row = self._a[self._n]
        for i, v in enumerate(values):
            row[i] = np.nan if v is None else v
        self._n += 1

    def extend(self, rows: Iterable[Sequence]) -> None:
        for r in rows:
            self.append(r)

    def col(self, i: int) -> np.ndarray:
        """Read-only view of column ``i`` (valid until the next append)."""
        v = self._a[: self._n, i]
        v.flags.writeable = False
        return v

    def last(self) -> Tuple[float, ...] | None:
        return tuple(self._a[self._n - 1]) if self._n else None


def fast_time_curve(item):
    """Configure a PlotDataItem whose x increases (a time series).

    Call it after the item is in its ViewBox: pyqtgraph 0.14 raises
    ``AttributeError: autoRangeEnabled`` if a clip-to-view item that already
    holds data is added to a ViewBox (it briefly sees the PlotWidget as its view).
    """
    item.setDownsampling(auto=True, method="peak")
    item.setClipToView(True)
    return item


def thin(x: np.ndarray, y: np.ndarray, max_points: int = MAX_PARAMETRIC_POINTS):
    """Every k-th point so at most ``max_points`` remain; the last point is kept."""
    n = len(x)
    if n <= max_points:
        return x, y
    step = int(np.ceil(n / max_points))
    idx = np.arange(n - 1, -1, -step)[::-1]
    return x[idx], y[idx]
