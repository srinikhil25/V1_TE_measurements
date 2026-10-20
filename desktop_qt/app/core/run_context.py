"""Settings snapshot stored with every run (reproducibility / ALCOA+ 'complete').

Captures what produced the data: application version, host, library versions,
the full rig configuration in force, and the identity (*IDN?) of each
instrument that supports it. Stored in ``Measurement.params_json`` under
``"run_context"`` and written into HDF5/NeXus exports.
"""

from __future__ import annotations

import platform
import socket
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..version import APP_VERSION


def _lib_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def build_run_context(instruments: Optional[Dict[str, Any]] = None,
                      cfg=None) -> Dict[str, Any]:
    from .config import config_path, get_config
    cfg = cfg or get_config()
    return {
        "software": {
            "name": "TE Measurement",
            "version": APP_VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "python": platform.python_version(),
            "pyvisa": _lib_version("PyVISA"),
            "numpy": _lib_version("numpy"),
        },
        "host": {
            "computer": socket.gethostname(),
            "os": platform.platform(),
        },
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_file": str(config_path()),
        "config": cfg.to_dict(),
        "instruments": instruments or {},
    }
