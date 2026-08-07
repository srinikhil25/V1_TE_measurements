"""Runtime detection of external hardware prerequisites.

NI-VISA and the Optris IR-camera SDK are SYSTEM installs — they are not bundled
with the application (see installer/PREREQUISITES.txt). This module reports which
are present so the UI can warn the user which hardware features are unavailable.

Detection is fast and side-effect free (file/registry probes only — it does not
open a VISA session or load the Optris DLL).

An acknowledgement file in %APPDATA%\\TEMeasurement\\ remembers when the user has
ticked "Don't remind me again", so the post-login warning is not shown every time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from .paths import get_app_dir

# Legacy IrDirectSDK default locations — kept in sync with
# app.services.ir_camera_service.IrCameraConfig.
_LEGACY_DLL = r"C:\IrDirectSDK\sdk\x64\libirimager.dll"
_LEGACY_CFG = r"C:\IrDirectSDK\generic.xml"
_OTC_DEFAULT = r"C:\Program Files\Optris\otcsdk"

_ACK_FILE = "prereq_ack.json"


@dataclass
class PrereqStatus:
    ni_visa: bool
    optris: bool
    optris_backend: Optional[str]  # "otc" | "legacy" | None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _ni_visa_present() -> bool:
    # 1) VISA implementation DLL in System32 (visa64.dll / visa32.dll).
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(sysroot, "System32")
    if any(os.path.isfile(os.path.join(sys32, d)) for d in ("visa64.dll", "visa32.dll")):
        return True
    # 2) NI-VISA registry key (both registry views).
    try:
        import winreg
        for view in (getattr(winreg, "KEY_WOW64_64KEY", 0),
                     getattr(winreg, "KEY_WOW64_32KEY", 0)):
            try:
                k = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\National Instruments\NI-VISA",
                    0, winreg.KEY_READ | view)
                k.Close()
                return True
            except OSError:
                continue
    except Exception:
        pass
    return False


def _optris_backend() -> Optional[str]:
    otc = os.environ.get("OTC_SDK_DIR", _OTC_DEFAULT)
    if os.path.isdir(os.path.join(otc, "bindings", "python3")):
        return "otc"
    if os.path.isfile(_LEGACY_DLL) and os.path.isfile(_LEGACY_CFG):
        return "legacy"
    return None


def check_prerequisites() -> PrereqStatus:
    """Probe the machine and return which prerequisites are installed."""
    backend = _optris_backend()
    return PrereqStatus(
        ni_visa=_ni_visa_present(),
        optris=backend is not None,
        optris_backend=backend,
    )


def missing_items(status: PrereqStatus) -> List[Tuple[str, str, str]]:
    """Return [(key, title, description)] for each missing prerequisite."""
    items: List[Tuple[str, str, str]] = []
    if not status.ni_visa:
        items.append((
            "ni_visa",
            "NI-VISA runtime + GPIB driver",
            "Required for the Keithley 2401 / 2182A / 2700 and the Matsusada P4K-80M. "
            "Without it the app cannot connect to any instrument. "
            "Download from ni.com (search \"NI-VISA\").",
        ))
    if not status.optris:
        items.append((
            "optris",
            "Optris IR camera SDK",
            "Only needed for the thermal camera (OTC SDK 10.x or the legacy IrDirectSDK). "
            "All other measurements work without it.",
        ))
    return items


# ---------------------------------------------------------------------------
# "Don't remind me again" acknowledgement
# ---------------------------------------------------------------------------

def _ack_path():
    return get_app_dir() / _ACK_FILE


def load_acked() -> Set[str]:
    try:
        return set(json.loads(_ack_path().read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_acked(items: Set[str]) -> None:
    try:
        _ack_path().write_text(json.dumps(sorted(items)), encoding="utf-8")
    except Exception:
        pass
