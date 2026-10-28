"""Camera regions of interest (ROIs) — what the operator watches on the IR image,
and what each Seebeck reading records from the camera.

Regions are rectangles in *sensor* pixels (column x, row y of the camera
frame), so they do not depend on how the view is rotated or scaled. A spot is
a 3 × 3 box. At most two regions: R1 (always) and R2 (optional, e.g. the cold
side, giving a camera ΔT).

The set of regions is shared between the live view (which edits it) and the
measurement thread (which records ``snapshot()`` with every reading), so it is
guarded by a lock. Regions are remembered per sample geometry in
``ir_regions.json`` next to the database.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MAX_REGIONS = 2
SPOT = 3                       # a spot is SPOT × SPOT pixels
#: A frame older than this is not recorded (camera stalled or disconnected).
MAX_FRAME_AGE_S = 2.0


@dataclass
class Region:
    name: str                  # "R1" / "R2"
    label: str                 # what the operator calls it
    x: int
    y: int
    w: int
    h: int

    @property
    def is_spot(self) -> bool:
        return self.w <= SPOT and self.h <= SPOT

    def clipped(self, shape: Tuple[int, int]) -> "Region":
        """This region kept inside a frame of ``shape`` = (rows, cols)."""
        rows, cols = shape
        w, h = max(1, min(self.w, cols)), max(1, min(self.h, rows))
        x = int(min(max(self.x, 0), cols - w))
        y = int(min(max(self.y, 0), rows - h))
        return Region(self.name, self.label, x, y, w, h)


def region_key(name: str) -> str:
    """Column name of a region's mean in a data row."""
    return f"IR {name} [oC]"


def stats(frame: np.ndarray, r: Region) -> Optional[Dict[str, float]]:
    """min / mean / max of ``frame`` inside ``r`` (None if it has no finite pixel)."""
    c = r.clipped(frame.shape[:2])
    px = frame[c.y:c.y + c.h, c.x:c.x + c.w]
    px = px[np.isfinite(px)]
    if px.size == 0:
        return None
    return {"min": float(px.min()), "mean": float(px.mean()), "max": float(px.max())}


def default_regions(shape: Tuple[int, int] = (288, 382)) -> List[Region]:
    """R1 in the middle of the frame — where the sample usually is."""
    rows, cols = shape
    w, h = max(SPOT, cols // 12), max(SPOT, rows // 12)
    return [Region("R1", "sample centre", (cols - w) // 2, (rows - h) // 2, w, h)]


class RegionStore:
    """The current regions, per geometry, shared across threads."""

    def __init__(self, path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._path = path
        self._by_geometry: Dict[str, List[Region]] = {}
        self._geometry = "in_plane"
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._by_geometry = {g: [Region(**r) for r in rs][:MAX_REGIONS]
                                 for g, rs in raw.items()}
        except Exception as exc:             # a bad file must not stop the app
            logger.warning("Ignoring %s: %s", self._path, exc)
            self._by_geometry = {}

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.write_text(json.dumps(
                {g: [asdict(r) for r in rs] for g, rs in self._by_geometry.items()},
                indent=1), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not save camera regions: %s", exc)

    # ── access ───────────────────────────────────────────────────────────────
    def set_geometry(self, geometry: str) -> None:
        with self._lock:
            self._geometry = geometry

    @property
    def geometry(self) -> str:
        return self._geometry

    def regions(self) -> List[Region]:
        with self._lock:
            rs = self._by_geometry.get(self._geometry)
            return [Region(**asdict(r)) for r in (rs or default_regions())]

    def set_regions(self, regions: List[Region]) -> None:
        with self._lock:
            self._by_geometry[self._geometry] = [Region(**asdict(r))
                                                 for r in regions[:MAX_REGIONS]]
            self._save()

    # ── recording ────────────────────────────────────────────────────────────
    def snapshot(self, frame: Optional[np.ndarray], age_s: float = 0.0) -> Dict[str, float]:
        """``{"IR R1 [oC]": mean, ...}`` for a data row; empty without a fresh frame."""
        if frame is None or age_s > MAX_FRAME_AGE_S:
            return {}
        out = {}
        for r in self.regions():
            st = stats(frame, r)
            if st is not None:
                out[region_key(r.name)] = round(st["mean"], 3)
        return out


_store: Optional[RegionStore] = None
_store_lock = threading.Lock()


def get_store() -> RegionStore:
    """The app's region store (created on first use)."""
    global _store
    with _store_lock:
        if _store is None:
            try:
                from ..core.paths import get_app_dir
                path: Optional[Path] = get_app_dir() / "ir_regions.json"
            except Exception:
                path = None
            _store = RegionStore(path)
        return _store


def camera_snapshot(t_hot: Optional[float] = None,
                    t_cold: Optional[float] = None) -> Dict[str, float]:
    """Region means from the live camera frame, for the reading being taken now.
    Empty when the camera is not connected or its frame is stale.

    ``t_hot`` / ``t_cold`` are the thermocouple temperatures of this reading;
    only the simulated camera uses them (its sample follows the run)."""
    try:
        from .ir_camera_service import IrCameraService
        svc = IrCameraService()
        if not svc.is_connected():
            return {}
        svc.set_sim_temperatures(t_hot, t_cold)
        frame, age = svc.latest()
        return get_store().snapshot(frame, age)
    except Exception as exc:                 # the camera must never break a run
        logger.debug("camera snapshot failed: %s", exc)
        return {}
