"""
Optris OTC SDK 10.x backend for IR camera.

Uses the official Python bindings from the installed OTC SDK
(e.g. C:\\Program Files\\Optris\\otcsdk\\bindings\\python3).

Set OTC_SDK_DIR to the SDK root (e.g. C:\\Program Files\\Optris\\otcsdk) so the DLLs in bin/ are found.
"""

import sys
import os
import threading
import numpy as np
import cv2

# Default OTC SDK install path (Windows)
_DEFAULT_OTC_SDK_DIR = os.environ.get("OTC_SDK_DIR", r"C:\Program Files\Optris\otcsdk")
_BINDINGS_PATH = os.path.join(_DEFAULT_OTC_SDK_DIR, "bindings", "python3")

_otc = None
_otc_import_error = None


def _ensure_otc():
    """Import optris.otcsdk; set _otc and _otc_import_error."""
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


def is_available():
    """Return True if the OTC SDK Python bindings can be imported."""
    try:
        _ensure_otc()
        return True
    except Exception:
        return False


def _make_client_class(otc):
    """Build a client class that the OTC SDK will accept for addClient (argument 2).
    The SDK binding typically expects a subclass of otc.IRImagerClient, not a plain Python class."""
    base = getattr(otc, "IRImagerClient", object)
    if base is object:
        # No IRImagerClient in bindings; use plain class (may still fail with "argument 2")
        class _OTCImagerClientBase:
            pass
        base = _OTCImagerClientBase

    class OTCImagerClient(base):
        """IRImagerClient that stores the latest thermal frame for polling."""

        def __init__(self, imager, serial_number=0):
            if base is not object:
                try:
                    super().__init__()
                except Exception:
                    pass
            self._imager = imager
            self._lock = threading.Lock()
            self._thermal_frame = None
            self._thermal_updated = False
            self._flag_state = None
            self._running = True
            # Connect first so the imager is initialized; then addClient (order can matter for bindings)
            imager.connect(serial_number)
            imager.addClient(self)

        def onThermalFrame(self, thermal, meta):
            # Keep callback minimal so SDK's FailSafeWatchdog (150 ms) is not exceeded.
            with self._lock:
                self._thermal_frame = thermal
                self._thermal_updated = True

        def onFlagStateChange(self, flag_state):
            with self._lock:
                self._flag_state = flag_state

        def onConnectionLost(self):
            self._running = False

        def onConnectionTimeout(self):
            self._running = False

        def get_latest_frame(self):
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
            """Trigger NUC (force flag event). Returns (True, None) or (False, error_message)."""
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


def create_otc_camera_manager(serial_number=0):
    """
    Initialize OTC SDK, create imager and client, start run thread.
    Returns (client, imager, thread, builder) or raises.
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
    builder = otc.ImageBuilder(colorFormat=otc.ColorFormat_BGR, widthAlignment=otc.WidthAlignment_OneByte)
    thread = threading.Thread(target=imager.run, daemon=True)
    thread.start()
    return client, imager, thread, builder


def process_thermal_frame_to_jpeg(client, builder, target_long_side=1280, jpeg_quality=98):
    """
    Get latest thermal frame from client, build false-color image, resize to HD, return (jpeg_bytes, avg, tmin, tmax, temps_2d).
    """
    thermal = client.get_latest_frame()
    if thermal is None or thermal.isEmpty():
        return None
    w, h = thermal.getWidth(), thermal.getHeight()
    size = thermal.getSize()
    temps_1d = np.empty(size, dtype=np.float32)
    thermal.copyTemperaturesTo(temps_1d)
    temps = temps_1d.reshape((h, w))
    avg = float(np.mean(temps))
    tmin = float(np.min(temps))
    tmax = float(np.max(temps))
    temps_2d = np.round(temps, 1).tolist()

    builder.setThermalFrame(thermal)
    builder.convertTemperatureToPaletteImage()
    frame = np.empty((builder.getHeight(), builder.getWidth(), 3), dtype=np.uint8)
    builder.copyImageDataTo(frame)
    # frame is BGR false-color from SDK; scale to HD
    scale = target_long_side / max(frame.shape[1], frame.shape[0]) if max(frame.shape[1], frame.shape[0]) > 0 else 1.0
    if scale > 1.0:
        nw, nh = int(round(frame.shape[1] * scale)), int(round(frame.shape[0] * scale))
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    _, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    return jpeg.tobytes(), avg, tmin, tmax, temps_2d
