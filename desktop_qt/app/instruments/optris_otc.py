"""
Optris OTC SDK 10.x bindings for the Qt desktop app.

Stripped to temperature-data-only — no cv2 / JPEG dependency.
False-colour rendering is done by the Qt widget (iron colormap).

Set OTC_SDK_DIR env-var to the SDK root if it is not in the default path:
  C:\\Program Files\\Optris\\otcsdk
"""

import os
import sys
import threading

import numpy as np

_DEFAULT_OTC_SDK_DIR = os.environ.get("OTC_SDK_DIR", r"C:\Program Files\Optris\otcsdk")
_BINDINGS_PATH = os.path.join(_DEFAULT_OTC_SDK_DIR, "bindings", "python3")

_otc = None
_otc_import_error = None


def _ensure_otc():
    global _otc, _otc_import_error
    if _otc is not None:
        return _otc
    if _otc_import_error is not None:
        raise _otc_import_error
    if _BINDINGS_PATH not in sys.path:
        sys.path.insert(0, _BINDINGS_PATH)
    try:
        os.environ.setdefault("OTC_SDK_DIR", _DEFAULT_OTC_SDK_DIR)
        import optris.otcsdk as otc
        _otc = otc
        return otc
    except Exception as e:
        _otc_import_error = e
        raise


def is_available() -> bool:
    """Return True if the OTC SDK Python bindings can be imported."""
    try:
        _ensure_otc()
        return True
    except Exception:
        return False


def _make_client_class(otc):
    """Build an IRImagerClient subclass that stores the latest thermal frame."""
    base = getattr(otc, "IRImagerClient", object)
    if base is object:
        class _Fallback:
            pass
        base = _Fallback

    class OTCImagerClient(base):
        def __init__(self, imager, serial_number=0):
            if base is not object:
                try:
                    super().__init__()
                except Exception:
                    pass
            self._imager          = imager
            self._lock            = threading.Lock()
            self._thermal_frame   = None
            self._thermal_updated = False
            self._running         = True
            imager.connect(serial_number)
            imager.addClient(self)

        def onThermalFrame(self, thermal, meta):
            # Keep callback minimal — SDK FailSafeWatchdog fires at 150 ms.
            with self._lock:
                self._thermal_frame   = thermal
                self._thermal_updated = True

        def onFlagStateChange(self, flag_state):
            pass

        def onConnectionLost(self):
            self._running = False

        def onConnectionTimeout(self):
            self._running = False

        def get_latest_frame(self):
            """Return a cloned thermal frame or None if not yet available."""
            with self._lock:
                if not self._thermal_updated or self._thermal_frame is None:
                    return None
                try:
                    if self._thermal_frame.isEmpty():
                        return None
                except Exception:
                    pass
                self._thermal_updated = False
                return self._thermal_frame.clone()

        def force_flag(self):
            """Trigger NUC. Returns (True, None) or (False, error_message)."""
            try:
                self._imager.forceFlagEvent()
                return True, None
            except Exception as e:
                return False, str(e)

        def stop(self):
            self._running = False
            try:
                self._imager.stopRunning()
            except Exception:
                pass

    return OTCImagerClient


def create_otc_camera_manager(serial_number: int = 0):
    """
    Initialise OTC SDK and start the acquisition thread.

    Returns (client, imager, thread).
    """
    otc = _ensure_otc()
    otc.Sdk.init(otc.Verbosity_Warning, otc.Verbosity_Off, "seebeck_ir")
    try:
        otc.EnumerationManager.getInstance().addEthernetDetector("192.168.0.0/24")
    except Exception:
        pass
    imager = otc.IRImagerFactory.getInstance().create("native")
    OTCImagerClient = _make_client_class(otc)
    client = OTCImagerClient(imager, serial_number)
    thread = threading.Thread(target=imager.run, daemon=True)
    thread.start()
    return client, imager, thread


def frame_to_celsius(thermal) -> np.ndarray | None:
    """
    Convert an OTC thermal frame object to a (H, W) float32 °C array.
    Returns None on failure.
    """
    try:
        if thermal is None or thermal.isEmpty():
            return None
        w    = thermal.getWidth()
        h    = thermal.getHeight()
        size = thermal.getSize()
        buf  = np.empty(size, dtype=np.float32)
        thermal.copyTemperaturesTo(buf)
        return buf.reshape((h, w))
    except Exception:
        return None
