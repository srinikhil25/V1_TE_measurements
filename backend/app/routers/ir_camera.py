from fastapi import APIRouter, WebSocket
import base64
import asyncio
import cv2
import pyOptris
import threading
import numpy as np
import json

router = APIRouter()

# Singleton Optris camera manager
class OptrisCameraManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        DLL_path = "C:/lib/IrDirectSDK/sdk/x64/libirimager.dll"
        pyOptris.load_DLL(DLL_path)
        pyOptris.usb_init('C:/lib/IrDirectSDK/generic.xml')
        pyOptris.set_palette(pyOptris.ColouringPalette.IRON)
        self.w, self.h = pyOptris.get_palette_image_size()
        self.lock = threading.Lock()
        self.last_min = None
        self.last_max = None

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = OptrisCameraManager()
            return cls._instance

    def get_frame_and_temps(self):
        with self.lock:
            thermal = pyOptris.get_thermal_image(self.w, self.h)
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
            frame = cv2.fastNlMeansDenoisingColored(frame, None, 10, 10, 7, 21)
            upscale_factor = 1.5
            frame = cv2.resize(
                frame,
                (int(frame.shape[1]*upscale_factor), int(frame.shape[0]*upscale_factor)),
                interpolation=cv2.INTER_CUBIC
            )
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            frame = cv2.filter2D(frame, -1, kernel)
            _, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            return jpeg.tobytes(), avg, tmin, tmax, temps_2d

    # Optionally, add a close method for backend shutdown
    def close(self):
        with self.lock:
            pyOptris.terminate()

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
            await asyncio.sleep(0.05)  # ~20 FPS
    except Exception as e:
        print("WebSocket connection closed:", e)
    # Do NOT call terminate here; keep camera open for other clients 