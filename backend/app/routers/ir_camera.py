from fastapi import APIRouter, WebSocket
import base64
import asyncio
import cv2
import threading
import numpy as np
import json

router = APIRouter()

# HD output: scale so longest side reaches this (720p). Use LANCZOS and high JPEG quality.
TARGET_HD_LONG_SIDE = 1280   # 720p-style width; use 1920 for 1080p (higher bandwidth)
JPEG_QUALITY_HD = 98
UPSAMPLE_INTERPOLATION = cv2.INTER_LANCZOS4  # sharper than INTER_CUBIC for upscaling

# Singleton Optris camera manager (OTC SDK 10.x if installed, else legacy pyOptris/IrDirectSDK)
class OptrisCameraManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.lock = threading.Lock()
        self._use_otc = False
        self._otc_client = None
        self._otc_builder = None
        self._otc_fallback_reason = None  # why OTC was not used (for API/UI)
        # Try OTC SDK first (e.g. C:\Program Files\Optris\otcsdk)
        try:
            from ..core.optris_otc import (
                is_available,
                create_otc_camera_manager,
                process_thermal_frame_to_jpeg,
            )
            if is_available():
                _client, _imager, _thread, _builder = create_otc_camera_manager(0)
                self._use_otc = True
                self._otc_client = _client
                self._otc_builder = _builder
                return
        except Exception as e:
            import logging
            self._otc_fallback_reason = str(e)
            logging.getLogger(__name__).warning("IR camera: OTC SDK not used, falling back to legacy. Reason: %s", e)
        # Fallback: legacy IrDirectSDK / pyOptris
        import pyOptris
        self._pyOptris = pyOptris
        DLL_path = "C:/lib/IrDirectSDK/sdk/x64/libirimager.dll"
        pyOptris.load_DLL(DLL_path)
        pyOptris.usb_init('C:/lib/IrDirectSDK/generic.xml')
        pyOptris.set_palette(pyOptris.ColouringPalette.IRON)
        self.w, self.h = pyOptris.get_palette_image_size()
        self.last_min = None
        self.last_max = None

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = OptrisCameraManager()
            return cls._instance

    def get_frame_and_temps(self):
        if self._use_otc:
            from ..core.optris_otc import process_thermal_frame_to_jpeg
            result = process_thermal_frame_to_jpeg(
                self._otc_client, self._otc_builder,
                TARGET_HD_LONG_SIDE, JPEG_QUALITY_HD,
            )
            if result is not None:
                return result
            # No frame yet; return a minimal placeholder so the stream doesn't break
            blank = np.zeros((100, 100, 3), dtype=np.uint8)
            _, jpeg = cv2.imencode(".jpg", blank, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            return jpeg.tobytes(), 0.0, 0.0, 0.0, [[0.0]]
        with self.lock:
            thermal = self._pyOptris.get_thermal_image(self.w, self.h)
            temps = ((thermal.astype(np.float32) - 1000.0) / 10.0)
            avg = float(np.mean(temps))
            tmin = float(np.min(temps))
            tmax = float(np.max(temps))
            temps_2d = np.round(temps, 1).tolist()

            # Smooth min/max over time (moving average)
            alpha = 0.2
            if self.last_min is None:
                self.last_min = tmin
                self.last_max = tmax
            else:
                self.last_min = alpha * tmin + (1 - alpha) * self.last_min
                self.last_max = alpha * tmax + (1 - alpha) * self.last_max

            # Dynamic normalization using smoothed min/max
            norm = np.clip((temps - self.last_min) * (255 / (self.last_max - self.last_min + 1e-6)), 0, 255).astype(np.uint8)

            # Optional: mild CLAHE
            clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
            norm = clahe.apply(norm)

            frame = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
            frame = cv2.fastNlMeansDenoisingColored(frame, None, 8, 8, 7, 15)  # slightly lighter denoise for sharper HD
            # Scale to HD: longest side = TARGET_HD_LONG_SIDE (e.g. 1280 for 720p)
            h, w = frame.shape[:2]
            scale = TARGET_HD_LONG_SIDE / max(w, h) if max(w, h) > 0 else 1.0
            if scale > 1.0:
                new_w, new_h = int(round(w * scale)), int(round(h * scale))
                frame = cv2.resize(frame, (new_w, new_h), interpolation=UPSAMPLE_INTERPOLATION)
            elif scale < 1.0 and (w > TARGET_HD_LONG_SIDE or h > TARGET_HD_LONG_SIDE):
                new_w = int(round(w * scale))
                new_h = int(round(h * scale))
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            frame = cv2.filter2D(frame, -1, kernel)
            _, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY_HD])
            return jpeg.tobytes(), avg, tmin, tmax, temps_2d

    def trigger_nuc(self):
        """Trigger NUC (Non-Uniformity Correction). Returns (ok: bool, message: str|None)."""
        if self._use_otc and self._otc_client:
            return self._otc_client.force_flag()
        with self.lock:
            for name in ("trigger_nuc", "do_nuc", "nuc", "triggerNUC", "doNUC"):
                fn = getattr(self._pyOptris, name, None)
                if callable(fn):
                    try:
                        fn()
                        return True, None
                    except Exception as e:
                        pass
            return False, "NUC not exposed by legacy SDK binding (pyOptris/IrDirectSDK). Use OTC SDK for NUC."

    # Optionally, add a close method for backend shutdown
    def close(self):
        if self._use_otc and self._otc_client:
            self._otc_client.stop()
            return
        with self.lock:
            self._pyOptris.terminate()


@router.get("/api/ir_camera/backend")
def ir_camera_backend():
    """Report which IR camera backend is in use (otc = OTC SDK 10.x with NUC; legacy = pyOptris/IrDirectSDK, no NUC)."""
    try:
        camera = OptrisCameraManager.get_instance()
        out = {"backend": "otc" if camera._use_otc else "legacy"}
        if not camera._use_otc and getattr(camera, "_otc_fallback_reason", None):
            out["reason"] = camera._otc_fallback_reason
        return out
    except Exception as e:
        return {"backend": "error", "message": str(e)}


@router.post("/api/ir_camera/nuc")
def ir_camera_trigger_nuc():
    """Trigger camera NUC for calibration. Use same config/calibration as IR PIX Connect for matching quality."""
    try:
        camera = OptrisCameraManager.get_instance()
        ok, msg = camera.trigger_nuc()
        if ok:
            return {"ok": True, "message": "NUC triggered. Wait a few seconds for the camera to stabilize."}
        return {"ok": False, "message": msg or "NUC not available in this SDK binding."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.websocket("/api/ir_camera/ws")
async def ir_camera_ws(websocket: WebSocket):
    await websocket.accept()
    camera = OptrisCameraManager.get_instance()
    try:
        while True:
            frame, avg, tmin, tmax, temps_2d = camera.get_frame_and_temps()
            b64_frame = base64.b64encode(frame).decode('utf-8')
            await websocket.send_text(json.dumps({
                "image": b64_frame,
                "avg": avg,
                "min": tmin,
                "max": tmax,
                "temps": temps_2d
            }))
            # OTC SDK has a 150 ms FailSafeWatchdog; use 10 FPS to reduce load and avoid timing errors
            await asyncio.sleep(0.1 if camera._use_otc else 0.05)
    except Exception as e:
        print("WebSocket connection closed:", e)
    # Do NOT call terminate here; keep camera open for other clients 