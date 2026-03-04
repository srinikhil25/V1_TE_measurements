# Software Architecture Document
## V1 Thermoelectric Measurement System
**Ikeda-Hamasaki Laboratory**  
Version 1.0 — March 2026

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Backend Architecture](#3-backend-architecture)
4. [Frontend Architecture](#4-frontend-architecture)
5. [Hardware & Instrument Layer](#5-hardware--instrument-layer)
6. [IR Camera Subsystem](#6-ir-camera-subsystem)
7. [Data Flow Diagrams](#7-data-flow-diagrams)
8. [API Reference](#8-api-reference)
9. [Key Dependencies](#9-key-dependencies)
10. [Deployment](#10-deployment)
11. [Design Decisions & Trade-offs](#11-design-decisions--trade-offs)

---

## 1. System Overview

The **V1 Thermoelectric Measurement System** is a full-stack laboratory automation application that drives Keithley GPIB instruments to perform two primary electrical characterization workflows:

| Workflow | Instruments | Measured Quantities |
|---|---|---|
| **Seebeck Coefficient** | 2182A, 2700, PK160 | TEMF, T₁, T₂, ΔT, S (µV/K) |
| **I-V / Resistivity** | 6221 | V, I, R (Ω), ρ (Ω·m), σ (S/m) |

Additionally, an **Optris IR camera** subsystem streams live thermal imagery over WebSocket.

The system is structured as a **decoupled two-tier application**:

- **Backend** — Python FastAPI server running on the lab PC, controlling instruments via PyVISA over GPIB.
- **Frontend** — React (TypeScript/Vite) SPA that communicates with the backend over HTTP REST and WebSocket, and can be served locally or deployed to Firebase Hosting.

---

## 2. High-Level Architecture

```mermaid
graph TB
    subgraph Browser["Browser / Client"]
        FE["React SPA\n(Vite · TypeScript)"]
    end

    subgraph Network["Network Layer"]
        HTTP["HTTP REST\n/api/…"]
        WS["WebSocket\n/api/ir_camera/ws\n/api/instrument/ws"]
    end

    subgraph Backend["FastAPI Backend  :8080"]
        direction TB
        APP["app/main.py\nFastAPI + CORS + logging"]

        subgraph Routers["API Routers"]
            RS["seebeck.py\n/api/seebeck/…"]
            RIV["iv.py\n/api/iv/…"]
            RI["instrument.py\n/api/instrument/…"]
            RIR["ir_camera.py\n/api/ir_camera/…"]
        end

        subgraph Core["Core Layer"]
            SM["session_manager.py\nMeasurementSessionManager"]
            INST["instrument.py\nSeebeckSystem\n+ instrument classes"]
            SA["seebeck_analysis.py\nbinned S computation"]
            OTC["optris_otc.py\nOTC SDK wrapper"]
        end

        APP --> Routers
        RS --> SM
        RIV --> INST
        RI --> INST
        RIR --> OTC
        SM --> INST
        SM --> SA
    end

    subgraph VISA["VISA / GPIB Stack"]
        PV["PyVISA 1.15"]
        GPIB["GPIB-USB Controller\n(NI-VISA or pyvisa-py)"]
        PV --> GPIB
    end

    subgraph Instruments["Lab Instruments"]
        K2182A["Keithley 2182A\nNanovoltmeter\nGPIB::7"]
        K2700["Keithley 2700\nDMM / Scanner\nGPIB::16"]
        PK160["PK160\nCurrent Supply\nGPIB::15"]
        K6221["Keithley 6221\nSourceMeter\nGPIB::24"]
    end

    subgraph IRCamera["IR Camera"]
        OPTRIS["Optris PI / Xi\nUSB Thermal Camera"]
        OTC_SDK["OTC SDK 10.x\n(or legacy pyOptris)"]
        OPTRIS --> OTC_SDK
    end

    FE <-->|REST| HTTP
    FE <-->|WebSocket| WS
    HTTP <--> APP
    WS <--> APP
    INST --> PV
    PV --> K2182A
    PV --> K2700
    PV --> PK160
    PV --> K6221
    OTC --> OTC_SDK
```

---

## 3. Backend Architecture

### 3.1 Module Structure

```
backend/
├── app/
│   ├── main.py                   # FastAPI app factory, CORS, middleware, router registration
│   ├── __init__.py
│   ├── routers/
│   │   ├── seebeck.py            # POST /seebeck/start|stop  GET /seebeck/status|data
│   │   ├── iv.py                 # POST /iv/run
│   │   ├── instrument.py         # GET /instrument/discover  WS /instrument/ws
│   │   └── ir_camera.py          # WS /api/ir_camera/ws  POST /api/ir_camera/nuc
│   ├── core/
│   │   ├── instrument.py         # Instrument driver classes + SeebeckSystem façade
│   │   ├── session_manager.py    # Threaded Seebeck session state machine
│   │   ├── seebeck_analysis.py   # Binned S linear-fit analysis
│   │   └── optris_otc.py         # Optris OTC SDK 10.x integration
│   └── models/
│       ├── measurement.py        # Pydantic models: MeasurementConfig, MeasurementResponse, …
│       └── __init__.py
├── requirements.txt
├── find_instruments.py           # Utility: auto-discover GPIB addresses
├── check_instruments.py          # Utility: check VISA lock state
└── fix_instrument_locks.py       # Utility: release stale VISA locks
```

### 3.2 Class Diagram

```mermaid
classDiagram
    class SeebeckSystem {
        +ResourceManager rm
        +Keithley2182A k2182a
        +Keithley2700 k2700
        +PK160 pk160
        +Keithley6221 k6221
        +str pk160_current_unit
        +connect_all() bool
        +disconnect_all()
        +initialize_all()
        +set_current(value)
        +output_off()
        +measure_all() dict
        +measure_resistivity(...) dict
    }

    class Keithley2182A {
        +str resource_name
        +connect(rm) bool
        +disconnect()
        +configure()
        +read_voltage() float
    }

    class Keithley2700 {
        +str resource_name
        +list measurement_data
        +connect(rm) bool
        +disconnect()
        +configure_measurement(channel, nplc)
        +take_measurement(channel) float
        +multi_channel_measurement(channels) dict
        +get_status() dict
    }

    class PK160 {
        +str resource_name
        +connect(rm) bool
        +disconnect()
        +initialize()
        +set_current(value)
        +output_off()
    }

    class Keithley6221 {
        +str resource_name
        +connect(rm) bool
        +disconnect()
        +configure_voltage_source(v_limit, i_limit)
        +configure_current_source(i_limit, v_limit)
        +set_voltage(voltage)
        +set_current(current)
        +output_on()
        +output_off()
        +read_measurement() dict
        +get_status() dict
    }

    class MeasurementSessionManager {
        +bool session_active
        +Thread session_thread
        +list session_data
        +str session_status
        +dict session_params
        +SeebeckSystem seebeck_system
        +Lock lock
        +str session_phase
        +int session_step
        +int session_total_steps
        +dict session_metadata
        +start_session(params) bool
        +stop_session()
        +get_data() list
        +get_status() dict
        +get_binned_analysis() list
        +_run_session(params)
    }

    class OptrisCameraManager {
        +bool _use_otc
        +get_instance()$
        +get_frame_and_temps() tuple
        +trigger_nuc() tuple
        +close()
    }

    SeebeckSystem "1" *-- "1" Keithley2182A
    SeebeckSystem "1" *-- "1" Keithley2700
    SeebeckSystem "1" *-- "1" PK160
    SeebeckSystem "1" *-- "1" Keithley6221
    MeasurementSessionManager "1" *-- "1" SeebeckSystem
```

### 3.3 Application Startup & Routing

`app/main.py` creates the FastAPI app and registers four routers:

| Router file | URL prefix | Transport | Purpose |
|---|---|---|---|
| `instrument.py` | `/api/instrument` | HTTP + WebSocket | GPIB discovery, 2700 single measure, WS broadcast |
| `seebeck.py` | `/api/seebeck` | HTTP | Start/stop/status/data for Seebeck sessions |
| `iv.py` | `/api/iv` | HTTP | Single-shot IV sweep |
| `ir_camera.py` | *(no prefix — paths embedded)* | HTTP + WebSocket | Thermal frame stream, NUC control |

CORS is configured to allow:
- `http://localhost:5173` (local dev)
- `https://seebeck-web.web.app` (Firebase production)
- Any `*.trycloudflare.com` tunnel
- Any other HTTP/HTTPS origin via regex (for Tailscale / remote access)

---

## 4. Frontend Architecture

### 4.1 Module Structure

```
frontend/
├── index.html
├── vite.config.ts
├── src/
│   ├── main.tsx                  # React root, renders <App />
│   ├── App.tsx                   # BrowserRouter, theme, AppBar, route table
│   ├── App.css / index.css
│   ├── components/
│   │   ├── NavigationTabs.tsx    # Tab bar  (Seebeck | I-V | Seebeck+Resistivity)
│   │   ├── SeebeckMeasurementPanel.tsx   # Route: /seebeck
│   │   ├── IVMeasurementPanel.tsx        # Route: /iv
│   │   ├── SeebeckResistivityPanel.tsx   # Route: /seebeck-resistivity
│   │   ├── MeasurementPanel.tsx          # Shared measurement UI primitives
│   │   └── MeasurementDiagramForm.tsx    # Sample dimension form
│   └── api/
│       ├── client.ts             # Axios instance (VITE_API_BASE_URL)
│       ├── config.ts             # Base URL helper
│       └── iv.ts                 # Typed IV API call wrappers
├── package.json
├── firebase.json / .firebaserc   # Firebase Hosting deployment config
└── .gitignore
```

### 4.2 Component Hierarchy

```mermaid
graph TD
    ROOT["main.tsx\nReactDOM.createRoot"]
    QCP["QueryClientProvider\n@tanstack/react-query"]
    TP["ThemeProvider\nMUI dark/light"]
    BR["BrowserRouter\nreact-router-dom"]
    APP["App.tsx"]

    APPBAR["AppBar + Toolbar"]
    NAVTABS["NavigationTabs"]

    ROUTES["Routes"]
    R1["/ or /seebeck\nSeebeckMeasurementPanel"]
    R2["/iv\nIVMeasurementPanel"]
    R3["/seebeck-resistivity\nSeebeckResistivityPanel"]

    ROOT --> QCP --> TP --> BR --> APP
    APP --> APPBAR
    APP --> ROUTES
    APPBAR --> NAVTABS
    ROUTES --> R1
    ROUTES --> R2
    ROUTES --> R3
```

### 4.3 State Management & Data Fetching

- **@tanstack/react-query** manages server-state: polling `/seebeck/status` and `/seebeck/data` during an active Seebeck session (configurable refetch interval).
- **Axios** (`api/client.ts`) provides the HTTP transport layer; the base URL is injected via the `VITE_API_BASE_URL` environment variable.
- **React `useState` / `useEffect`** manage local UI state (form fields, unit selectors, chart data for IV).

### 4.4 Chart & Export Pipeline

```mermaid
flowchart LR
    DATA["Measurement\nData (JSON)"] -->|"state update"| CHART["Recharts\n(LineChart / ScatterChart)"]
    CHART -->|"html2canvas\ncapture PNG"| PNG["In-memory PNG\nBuffer"]
    DATA --> EXL["ExcelJS\nworkbook"]
    PNG --> EXL
    EXL -->|"file-saver\nBlob"| DL["Browser Download\n.xlsx"]
```

---

## 5. Hardware & Instrument Layer

### 5.1 Instrument Roles

| Instrument | GPIB Address (default) | Role in System |
|---|---|---|
| Keithley 2182A | `GPIB0::7::INSTR` | Nanovoltmeter — measures thermoelectric EMF (TEMF) in the Seebeck loop |
| Keithley 2700 | `GPIB0::16::INSTR` | DMM/Scanner with thermocouple card — reads T₁ and T₂ via K-type TCs on channels 102 and 104 |
| PK160 | `GPIB0::15::INSTR` | Programmable current supply — heats the sample by ramping current through the heater element |
| Keithley 6221 | `GPIB0::24::INSTR` | SourceMeter — sources voltage (or current) and measures I for I-V sweeps and resistivity |

### 5.2 Instrument Communication Sequence

```mermaid
sequenceDiagram
    participant SM as SessionManager
    participant SYS as SeebeckSystem
    participant RM as pyvisa.ResourceManager
    participant K2182A as Keithley 2182A
    participant K2700 as Keithley 2700
    participant PK160 as PK160

    SM->>SYS: connect_all()
    SYS->>RM: open_resource(ADDR_2182A)
    RM-->>SYS: instrument handle
    SYS->>RM: open_resource(ADDR_2700)
    RM-->>SYS: instrument handle
    SYS->>RM: open_resource(ADDR_PK160)
    RM-->>SYS: instrument handle

    SM->>SYS: initialize_all()
    SYS->>K2182A: RST, CONF:VOLT, VOLT:NPLC 5
    SYS->>K2700: RST, CONF:TEMP, TEMP:TRAN TC, TC:TYPE K
    SYS->>PK160: REN, VCN 100, OCP 100, SW1

    loop Every interval (s)
        SM->>SYS: set_current(volt)
        SYS->>PK160: ISET {value}
        SM->>SYS: measure_all()
        SYS->>K2182A: READ?
        K2182A-->>SYS: TEMF (V)
        SYS->>K2700: ROUT:CLOS(@102) then READ?
        K2700-->>SYS: Temp1 (°C)
        SYS->>K2700: ROUT:CLOS(@104) then READ?
        K2700-->>SYS: Temp2 (°C)
        SM->>SM: compute delta-T, S, append row
    end

    SM->>SYS: output_off()
    SYS->>PK160: #1 SW0
    SM->>SYS: disconnect_all()
```

### 5.3 I-V Sweep Sequence (Keithley 6221)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant IV as iv.py router
    participant SYS as SeebeckSystem
    participant K6221 as Keithley 6221

    FE->>IV: POST /api/iv/run {params}
    IV->>SYS: connect_all()
    IV->>K6221: configure_voltage_source(v_limit, i_limit)
    Note over K6221: RST, set SOUR:FUNC VOLT, apply current protection limit
    IV->>K6221: output_on()

    loop For each voltage setpoint
        IV->>K6221: set_voltage(v)
        IV->>K6221: INIT then FETCH?
        K6221-->>IV: measured (I, V)
        IV->>IV: R = V/I, compute resistivity if dims provided
    end

    IV->>K6221: output_off()
    IV->>SYS: disconnect_all()
    IV-->>FE: [{voltage, current, resistance, resistivity, conductivity}, …]
```

---

## 6. IR Camera Subsystem

### 6.1 Overview

The IR camera subsystem provides a real-time thermal video feed from an **Optris PI/Xi USB camera**. It supports two SDK backends selected automatically at startup:

| Backend | Condition | Capabilities |
|---|---|---|
| **OTC SDK 10.x** (`optris_otc.py`) | `C:\Program Files\Optris\otcsdk` present | Full NUC (Non-Uniformity Correction), callback-based frame delivery |
| **Legacy pyOptris / IrDirectSDK** | OTC unavailable | Frame polling via `get_thermal_image()`; NUC not supported |

### 6.2 IR Camera Architecture

```mermaid
graph TB
    subgraph ir_camera_router["ir_camera.py (router)"]
        WS_EP["WebSocket endpoint\n/api/ir_camera/ws"]
        NUC_EP["POST /api/ir_camera/nuc"]
        BACKEND_EP["GET /api/ir_camera/backend"]
    end

    subgraph manager["OptrisCameraManager (singleton)"]
        INIT["__init__()\ndetect SDK backend"]
        GFF["get_frame_and_temps()\nreturns (jpeg, avg, min, max, temps_2d)"]
        NUC_FN["trigger_nuc()"]
    end

    subgraph otc_path["OTC SDK Path"]
        OTC_MOD["optris_otc.py"]
        OTC_CLIENT["OTCImagerClient\n(IRImagerClient subclass)"]
        OTC_BUILDER["ImageBuilder\n(false-color rendering)"]
        OTC_THREAD["imager.run()\n(daemon thread)"]
        OTC_CLIENT -->|"onThermalFrame()"| THERMAL_FRAME["latest ThermalFrame\n(thread-safe lock)"]
        OTC_MOD --> OTC_CLIENT
        OTC_MOD --> OTC_BUILDER
        OTC_MOD --> OTC_THREAD
    end

    subgraph legacy_path["Legacy Path"]
        PYOPTRIS["pyOptris\n(IrDirectSDK DLL)"]
        GET_THERMAL["get_thermal_image(w,h)"]
        CLAHE["OpenCV CLAHE\n+ colormap INFERNO\n+ denoise"]
        PYOPTRIS --> GET_THERMAL --> CLAHE
    end

    subgraph image_pipeline["Image Pipeline (both paths)"]
        RESIZE["Resize to HD\n(longest side = 1280px\nLANCZOS4)"]
        ENCODE["cv2.imencode .jpg\nquality = 98"]
        B64["base64 encode"]
    end

    INIT -->|"OTC available"| OTC_MOD
    INIT -->|"OTC unavailable"| PYOPTRIS
    GFF --> THERMAL_FRAME
    GFF --> CLAHE
    GFF --> RESIZE --> ENCODE --> B64

    WS_EP -->|"0.1 s loop"| GFF
    WS_EP -->|"send_text(JSON)"| FE["Frontend\n(WebSocket client)"]
    NUC_EP --> NUC_FN
```

### 6.3 WebSocket Frame Format

Each WebSocket message is a JSON object:

```json
{
  "image": "<base64-encoded JPEG string>",
  "avg":   23.5,
  "min":   21.0,
  "max":   45.2,
  "temps": [[21.0, 21.1, ...], ...]
}
```

---

## 7. Data Flow Diagrams

### 7.1 Seebeck Measurement — End-to-End Flow

```mermaid
flowchart TD
    USER(["User"]) -->|"fill form + click Start"| FE_START["SeebeckMeasurementPanel\nPOST /api/seebeck/start"]
    FE_START --> SESSION_MGR["MeasurementSessionManager\nstart_session(params)"]
    SESSION_MGR -->|"spawn thread"| THREAD["_run_session(params)\n(background thread)"]

    THREAD --> CONNECT["SeebeckSystem.connect_all()\nSeebeckSystem.initialize_all()"]
    CONNECT --> LOOP_START{{"Loop\n(while session_active)"}}

    LOOP_START --> PHASE_CALC["Compute phase\n(pre / ramp_up / hold / ramp_down / cooling_tail)\nbased on kaisuu counter"]
    PHASE_CALC -->|"not cooling_tail"| SET_I["SeebeckSystem.set_current(volt)\n→ PK160 ISET"]
    PHASE_CALC -->|"cooling_tail"| OUTPUT_OFF["output_off()\n→ PK160 SW0"]

    SET_I --> MEASURE["SeebeckSystem.measure_all()\n2182A :READ? → TEMF\n2700 ch102 :READ? → T₁\n2700 ch104 :READ? → T₂"]
    OUTPUT_OFF --> MEASURE

    MEASURE --> COMPUTE["Compute:\nΔT = T₂ − T₁\nT₀ = (T₁+T₂)/2\nS = TEMF(µV) / ΔT\nbranch = heating|cooling"]
    COMPUTE --> APPEND["append row to session_data\n(thread-safe Lock)"]
    APPEND --> COOLING_CHECK{{"phase ==\ncooling_tail?"}}
    COOLING_CHECK -->|"yes: |ΔT| < target\nor timeout"| DONE["disconnect_all()\nstatus = finished"]
    COOLING_CHECK -->|"no: wait remaining interval"| LOOP_START

    FE_POLL["Frontend polled\nGET /api/seebeck/status\nGET /api/seebeck/data"] -->|"refetch ~2s"| GET_DATA["session_manager.get_data()\n+ get_binned_analysis()"]
    GET_DATA --> FE_RENDER["Update table + Recharts\nSeebeck S chart, ΔT chart"]
```

### 7.2 Seebeck Session State Machine

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> running : POST /seebeck/start\n(instruments connect OK)
    idle --> error : POST /seebeck/start\n(connection failed)

    running --> pre : step 1..kaisuu1\n(I = I₀)
    pre --> ramp_up : step kaisuu1+1\n(I increasing)
    ramp_up --> hold : step kaisuu1+kaisuu2+1\n(I = I_peak)
    hold --> ramp_down : step kaisuu1+kaisuu2+kaisuu3+1\n(I decreasing)
    ramp_down --> cooling_tail : steps exhausted\n(output_off)
    cooling_tail --> finished : |ΔT| < target\nor timeout

    running --> stopped : POST /seebeck/stop
    running --> error : instrument exception
    finished --> idle : next start_session
    stopped --> idle : next start_session
```

### 7.3 I-V Measurement — End-to-End Flow

```mermaid
flowchart LR
    USER(["User"]) -->|"set params + Run"| FE_IV["IVMeasurementPanel\nPOST /api/iv/run"]
    FE_IV --> IV_ROUTER["iv.py\nrun_iv(params)"]
    IV_ROUTER -->|"compute linspace voltages"| SWEEP_LOOP{{"Loop N points"}}

    SWEEP_LOOP -->|"set V, wait delay_ms"| MEAS["6221 :INIT; :FETCH?\n→ (V_meas, I_meas)"]
    MEAS --> CALC["R = V/I\nif dims: ρ = R·A/L\nσ = 1/ρ"]
    CALC --> SWEEP_LOOP

    SWEEP_LOOP -->|"all points done"| OUTPUT_OFF2["output_off()\ndisconnect_all()"]
    OUTPUT_OFF2 --> FE_RESULT["Return IVResponse\n[{V, I, R, ρ, σ}, …]"]
    FE_RESULT -->|"render"| CHARTS["Recharts\nI-V + R-V charts"]
    CHARTS -->|"Save (data+graphs)"| EXPORT["html2canvas → PNG\nExcelJS → .xlsx\nfile-saver → download"]
```

---

## 8. API Reference

Base URL: `http://<host>:8080/api`

### 8.1 Seebeck Endpoints

| Method | Path | Body / Response | Description |
|---|---|---|---|
| `POST` | `/seebeck/start` | `MeasurementParams` → `{status}` | Start a Seebeck session in a background thread |
| `POST` | `/seebeck/stop` | — → `{status}` | Gracefully stop the running session |
| `GET` | `/seebeck/status` | — → `SessionStatus` | Session state, phase, step, ETA, metadata |
| `GET` | `/seebeck/data` | — → `{data, analysis, metadata}` | All measurement rows + binned S analysis |
| `POST` | `/seebeck/resistivity` | `ResistivityParams` → resistivity dict | One-shot resistivity measurement via 6221 |

#### MeasurementParams Schema

```json
{
  "interval":       2,
  "pre_time":       60,
  "start_volt":     0.0,
  "stop_volt":      200.0,
  "inc_rate":       2.0,
  "dec_rate":       2.0,
  "hold_time":      300,
  "sample_id":      "S-001",
  "operator":       "Hamasaki",
  "notes":          "Optional notes",
  "target_T0_K":    300.0,
  "probe_arrangement": "4-probe",
  "cooling_target_delta_t": 5.0,
  "cooling_timeout_s": 600,
  "stabilization_delay_s": 0.0,
  "pk160_current_unit": "mA"
}
```

> **Note on naming:** `start_volt` / `stop_volt` / `inc_rate` / `dec_rate` are legacy parameter names. Their values represent **current setpoints (mA or A)** and ramp **rates (mA/s or A/s)** sent to the PK160, not voltages.

### 8.2 I-V Endpoints

| Method | Path | Body / Response | Description |
|---|---|---|---|
| `POST` | `/iv/run` | `IVParams` → `IVResponse` | Run a linear V-sweep on the Keithley 6221 |

#### IVParams Schema

```json
{
  "start_voltage":  -1.0,
  "stop_voltage":    1.0,
  "points":          101,
  "delay_ms":        50.0,
  "current_limit":   0.1,
  "voltage_limit":  21.0,
  "length":          0.005,
  "width":           0.002,
  "thickness":       0.001
}
```

### 8.3 Instrument Endpoints

| Method | Path | Response | Description |
|---|---|---|---|
| `GET` | `/instrument/discover` | instrument list + recommended addresses | Queries all GPIB resources via `*IDN?` |
| `POST` | `/instrument/connect` | `InstrumentStatus` | Connect to Keithley 2700 |
| `POST` | `/instrument/disconnect` | message | Disconnect from 2700 |
| `POST` | `/instrument/configure` | `MeasurementResponse` | Configure 2700 channel / NPLC |
| `POST` | `/instrument/measure` | `MeasurementResponse` | Take one 2700 measurement; broadcasts over WS |
| `GET` | `/instrument/measurements` | `MeasurementHistory` | All buffered 2700 readings |
| `DELETE` | `/instrument/measurements` | message | Clear measurement buffer |
| `GET` | `/instrument/status` | `InstrumentStatus` | 2700 connection status |
| `WS` | `/instrument/ws` | JSON broadcast | Real-time measurement push |

### 8.4 IR Camera Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/ir_camera/backend` | Report active SDK (`otc` or `legacy`) |
| `POST` | `/api/ir_camera/nuc` | Trigger NUC on camera |
| `WS` | `/api/ir_camera/ws` | Stream `{image, avg, min, max, temps}` at ~10 FPS |

---

## 9. Key Dependencies

### 9.1 Backend

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115 | Web framework, async routes, OpenAPI docs at `/docs` |
| `uvicorn` | 0.34 | ASGI server |
| `pydantic` | 2.11 | Request/response validation with `field_validator` |
| `PyVISA` | 1.15 | GPIB instrument communication (wraps NI-VISA or pyvisa-py) |
| `numpy` | 2.3 | Array operations for IR frame processing |
| `opencv-python-headless` | 4.11 | Image processing: CLAHE, colormap, resize, JPEG encode |
| `pyOptris` | git@9cae1ce | Legacy Optris IrDirectSDK Python bindings |
| `websockets` | 15.0 | WebSocket support for IR camera stream |

### 9.2 Frontend

| Package | Version | Purpose |
|---|---|---|
| `react` | 18.2 | UI framework |
| `vite` | 5.1 | Build tool and dev server |
| `typescript` | 5.2 | Type safety |
| `@mui/material` | 7.1 | Component library (AppBar, Tabs, inputs) |
| `@tanstack/react-query` | 5.80 | Server-state polling and caching |
| `axios` | 1.9 | HTTP client |
| `recharts` | 2.15 | SVG charts (Seebeck S-T, I-V, R-V) |
| `exceljs` | 4.4 | Excel workbook generation in-browser |
| `html2canvas` | 1.4 | Screenshot chart DOM nodes to PNG |
| `file-saver` | 2.0 | Trigger browser file download |
| `react-router-dom` | 6.30 | Client-side routing |

---

## 10. Deployment

### 10.1 Local Development

```
PC (Windows, NI-VISA installed)
├── Terminal A: uvicorn backend on :8080
└── Terminal B: vite dev server on :5173
```

```bash
# Backend
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Frontend
cd frontend
echo VITE_API_BASE_URL=http://localhost:8080/api > .env
npm install && npm run dev
```

### 10.2 Production / Remote Access

```mermaid
graph LR
    LABPC["Lab PC\n(FastAPI :8080)"] -->|"Cloudflare Tunnel\nor Tailscale VPN"| INTERNET["Internet"]
    INTERNET --> BROWSER["Remote Browser"]
    FIREBASE["Firebase Hosting\n(seebeck-web.web.app)"] --> BROWSER
    BROWSER -->|"CORS-allowed\nHTTP + WS"| LABPC
```

- The **React SPA is hosted on Firebase** (`firebase deploy`); it is a static build.
- The **FastAPI backend remains on the lab PC** with instruments attached.
- Remote access is possible via **Cloudflare Tunnel** (any `*.trycloudflare.com` domain) or **Tailscale** (private VPN). Both are whitelisted in CORS.

### 10.3 Environment Variables

| Variable | Where | Default | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | `frontend/.env` | `http://localhost:8080/api` | Backend base URL used by the SPA |
| `OTC_SDK_DIR` | OS env / shell | `C:\Program Files\Optris\otcsdk` | Root directory of the Optris OTC SDK |

---

## 11. Design Decisions & Trade-offs

### 11.1 Threaded Seebeck Session vs. Async

The Seebeck measurement loop runs in a **`threading.Thread`** rather than an async coroutine. This is intentional: PyVISA's GPIB calls are synchronous and blocking; running them in a thread avoids blocking the FastAPI event loop while preserving simple sequential instrument-control code. A `threading.Lock` serializes writes to `session_data`.

### 11.2 Staggered vs. Simultaneous Acquisition

The current acquisition order is **V → T₁ → T₂** (sequential). Per NIST recommendations for accurate Seebeck measurement, voltage and temperature should be acquired simultaneously. The 0.05 s inter-channel delay has been minimized but cannot be eliminated without hardware triggering (e.g., via a triggering card on the 2700 or an external trigger bus). This introduces a small staggered-acquisition error at high ramp rates.

### 11.3 IV Sweep: Blocking HTTP Request

The `/iv/run` endpoint blocks until the entire sweep completes. For typical sweep sizes (≤200 points, 50 ms delay) this takes ≤10 s and is acceptable. For longer sweeps, a session-based approach (like Seebeck) with polling would be preferable.

### 11.4 IR Camera: Singleton Pattern

`OptrisCameraManager` is a **singleton** (`get_instance()`) to ensure only one process owns the camera SDK handle at a time. The OTC SDK's FailSafeWatchdog requires the `onThermalFrame` callback to complete within 150 ms; the callback stores only a reference and returns immediately to avoid watchdog trips.

### 11.5 Parameter Naming Legacy

The Seebeck API parameters `start_volt`, `stop_volt`, `inc_rate`, `dec_rate` use "volt/rate" names inherited from an earlier UI design. In reality these are **current setpoints** (I₀ and I in mA or A) and ramp rates (mA/s or A/s) for the PK160 current supply. The unit is selected via `pk160_current_unit` (`"mA"` or `"A"`); when set to `"A"`, values are multiplied by 1000 before being sent to the supply's `ISET` command (which expects mA).

### 11.6 Resistivity Calculation

The 4-point (van der Pauw) probe arrangement is noted in metadata but the resistivity formula used is the simple **2-probe bar formula**:

```
ρ = R × (width × thickness) / length    [Ω·m]
```

Users selecting `4-probe` in the UI should be aware that the geometric correction factor is not applied automatically. A dedicated 4-probe mode with separate source/sense connections would require routing different 6221 terminals.
