# IR Camera Calibration – Matching IR PIX Connect Quality

This guide explains how to get **IR PIX Connect–level** temperature accuracy and image quality when using the Optris camera with this application.

---

## 0. Official Optris SDK (OTC SDK)

- **Download & binaries:** [GitHub – Optris/otcsdk_downloads](https://github.com/Optris/otcsdk_downloads)  
  Official download area for the **Optris Thermal Camera SDK (OTC SDK)**. Use this for the latest Windows/Linux binaries, release notes, and documentation.
- **Documentation & overview:** [Thermal Camera SDK – Overview](https://optris.github.io/otcsdk_downloads/)  
  Explains what the SDK does (thermal data, °C conversion, false color, USB/Ethernet streaming, camera setup, PIF). Start with **Example Applications** and **First Steps** (Basic Usage).

**Suggestions:**

| Goal | Suggestion |
|------|------------|
| **Latest SDK & calibration** | Get the current OTC SDK (e.g. 10.1.1) from [otcsdk_downloads releases](https://github.com/Optris/otcsdk_downloads). Use the same calibration path and config as PIX Connect (or as in the SDK examples). |
| **Better NUC / control** | OTC SDK 10.x supports camera control and streaming; if you move from the older IrDirectSDK to OTC SDK, you can use the official API for NUC, emissivity, and reference calibration. |
| **Python integration** | This app uses **pyOptris** (binding to the Direct SDK). If you switch to OTC SDK 10.x, you may need a Python binding for that SDK or to call the new DLL/API from Python; contact [direct-sdk@optris.com](mailto:direct-sdk@optris.com) for binding or integration support. |
| **Docs & examples** | API docs ship with the SDK; online docs are linked from [optris.github.io/otcsdk_downloads](https://optris.github.io/otcsdk_downloads/). Run the **Simple View** example and follow **First Steps** before changing this app’s integration. |

**Current app:** If the **OTC SDK** is installed (e.g. `C:\Program Files\Optris\otcsdk`), the app uses its Python bindings and **NUC** is available via **Trigger NUC** (`forceFlagEvent`). Otherwise the backend falls back to `C:/lib/IrDirectSDK/` and **pyOptris**. Set **`OTC_SDK_DIR`** to your SDK root if it is not in the default path (e.g. `C:\Program Files\Optris\otcsdk`).

---

## 0.1 Using Your Installed OTC SDK

If the SDK is installed at **`C:\Program Files\Optris\otcsdk`** (with **`C:\Program Files\Optris\otcsdk\examples\python3`** and bindings at **`...\otcsdk\bindings\python3`**):

- The app will **use the OTC SDK automatically** when the backend starts and a camera is used: it tries the OTC Python API first, then falls back to the legacy IrDirectSDK/pyOptris if the OTC SDK is not available.
- **Trigger NUC** in the UI calls the SDK’s `forceFlagEvent()` so you can calibrate from the app.
- To use a **different SDK root** (e.g. another drive), set the environment variable **`OTC_SDK_DIR`** to that path (e.g. `D:\Optris\otcsdk`) before starting the backend.

No code changes are required when the SDK is in the default location.

**Checking which backend is in use:** When IR Camera is enabled, the UI shows either **“OTC SDK (NUC available)”** or **“Legacy SDK (NUC not available)”**. When legacy is used, the UI also shows the **reason** (e.g. why OTC failed to load). The backend exposes **`GET /api/ir_camera/backend`**, which returns:
- `{"backend": "otc"}` when using the OTC SDK, or
- `{"backend": "legacy", "reason": "..."}` when using the legacy SDK; **`reason`** is the exception message from the failed OTC init (e.g. import error, “No device found”).

**If OTC does not load:** Check the **reason** in the UI next to “Legacy SDK” or the backend log:  
`IR camera: OTC SDK not used, falling back to legacy. Reason: ...`  
Fix the cause (e.g. set **`OTC_SDK_DIR`** if the SDK is not at `C:\Program Files\Optris\otcsdk`, ensure the camera is connected, restart the backend so the singleton is created with the camera present).

**FailSafeWatchdog (150 ms):** The OTC SDK logs `Processing chain endpoint thermal frame failed to meet expected timing of 150 ms` when the pipeline is occasionally slower than 150 ms. The app keeps the thermal callback minimal and uses a 10 FPS stream rate for OTC to reduce load. If you still see these errors under load, they are warnings (“Fail safe: Inactive”); the stream continues. You can close other heavy apps or lower the camera frame rate in the SDK config if needed.

---

## 1. Use the Same Configuration as PIX Connect

### Calibration files

- **PIX Connect** uses calibration files that match your camera (serial number, temperature range, field of view). The Direct SDK loads them via the XML config.
- **In this app** the camera is initialized with:
  - `generic.xml`: `C:/lib/IrDirectSDK/generic.xml`
- **Action:** Use the **same** `generic.xml` (and calibration path) as in PIX Connect, or copy the config PIX Connect uses.
  - Default calibration path in the SDK is often `C:\lib\IrDirectSDK\cali` or `C:\Users\<user>\AppData\Roaming\Imager\Cali` (or see SDK docs). Calibration files are named like `Cali-<serial>-<mintemp>-M<midtemp>-<maxtemp>.dat`. An optional extended file `CaliExt-<serial>.xml` may be used if provided by Optris; if missing, the SDK may log “Failed to open file … CaliExt-…” but will still run with the main calibration.
  - In PIX Connect: download/install calibration files for your PI/Xi camera (e.g. **Software Tutorials → download calibration files**). Then ensure the **same path** is set in your `generic.xml` so the Direct SDK (and this app) load the same calibration.

### Temperature range in XML

- The temperature range in `generic.xml` determines which calibration file is selected. It must match the range you use in PIX Connect (e.g. -20°C to 100°C, or 0°C to 250°C).
- Edit `generic.xml` (in the SDK folder) so that **temperature range and calibration path** match PIX Connect.

---

## 2. NUC (Non-Uniformity Correction)

- **What it is:** NUC corrects pixel-to-pixel differences and drift (e.g. from sensor temperature). The camera uses a shutter flag to take a “dark” reference and then corrects the thermal image. IR PIX Connect typically runs NUC automatically or on demand.
- **In this app:** The backend can trigger NUC if the SDK exposes it (see “Trigger NUC from the app” below). If not, run NUC from **PIX Connect** before starting this app:
  1. Open **IR PIX Connect**.
  2. Run **NUC** (e.g. menu or toolbar “NUC” / “Trigger NUC”).
  3. Wait until NUC finishes.
  4. Close PIX Connect (or leave the camera connected) and start this application.
- **When to NUC:** After warm-up (e.g. 5–10 min), when ambient temperature changes, or if the image looks non-uniform or “noisy.”

---

## 3. Emissivity

- **What it is:** Emissivity (ε) of the measured surface affects the temperature reading. PIX Connect lets you set emissivity (e.g. **PIX Connect → How to set up emissivity**).
- **In this app:** Temperature is computed from the SDK thermal values as `(raw - 1000) / 10` °C. If the SDK already applies emissivity (via config or API), no extra step is needed. If the SDK uses a fixed ε (e.g. 1.0) and your material has lower ε, then:
  - Either set emissivity in the **camera/SDK config** (if your `generic.xml` or SDK supports it), or
  - Use the same emissivity setting in PIX Connect and ensure the same config is used by this app.
- **Typical values:** e.g. 0.95 for many non-metals, 0.3–0.5 for polished metals. Match PIX Connect for comparable readings.

---

## 4. Reference Temperature Calibration (Optional)

- For **traceable accuracy**, Optris supports calibration to an external reference (e.g. **BR 20AR** black body). The SDK provides functions such as `setReferenceTemperature()` (Expert API).
- **In PIX Connect:** Use the reference calibration / external probe procedure as in the manual.
- **In this app:** Not implemented by default. To match PIX Connect after a reference calibration, either:
  - Perform the reference calibration in PIX Connect (or with the SDK) and then use this app with the same camera/config, or
  - Integrate the SDK’s reference-temperature API into the backend if you need to run reference calibration from this app.

---

## 5. Checklist to Match PIX Connect

| Step | Action |
|------|--------|
| **Calibration files** | Install calibration files (e.g. via PIX Connect) and set the same calibration path in `generic.xml` used by this app. |
| **Temperature range** | Set the same temperature range in `generic.xml` as in PIX Connect. |
| **NUC** | Run NUC in PIX Connect before using this app, or use “Trigger NUC” in this app if available. |
| **Emissivity** | Set emissivity in PIX Connect and, if possible, in the same config (e.g. `generic.xml`) used by this app. |
| **Reference calibration** | If you use a reference source, perform that in PIX Connect (or SDK) and then use this app with the same config. |

---

## 6. Trigger NUC from the App

If your Optris SDK exposes a NUC trigger (e.g. `trigger_nuc` or similar), you can run NUC from the UI:

- In the **IR Camera** panel, use the **“Trigger NUC”** button (if shown). This calls the backend, which invokes the SDK NUC once. Wait a few seconds for the camera to complete NUC before relying on temperatures.

If the button is not available, the SDK binding in use does not expose NUC; run NUC from PIX Connect as above.

---

## 7. Where Things Are in Code

- **Backend choice:** The app tries **OTC SDK** first (`backend/app/core/optris_otc.py`), then falls back to **legacy** (pyOptris / IrDirectSDK). See `backend/app/routers/ir_camera.py` — `OptrisCameraManager.__init__`.
- **Legacy path:** Uses `C:/lib/IrDirectSDK/generic.xml` and `get_thermal_image()`; temperature: `(thermal - 1000) / 10` °C.
- **OTC path:** Uses the installed OTC SDK Python bindings; NUC is triggered via `forceFlagEvent()`.
- **Config path (legacy):** Change `C:/lib/IrDirectSDK/generic.xml` (and calibration path inside it) to match your PIX Connect setup if needed.

Using the same calibration files, temperature range, NUC, and emissivity as in IR PIX Connect will give you the closest match in quality and temperature accuracy.
