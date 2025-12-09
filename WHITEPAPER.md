# Seebeck & I‑V Measurement System — Technical Brief / “White Paper”

## 1. Purpose
Provide a unified software stack to automate Seebeck and I‑V characterization using Keithley instruments over GPIB, with browser-based control, live visualization, and exportable reports (data + embedded graphs).

## 2. Hardware & Interfaces
- Instruments (default GPIB addresses):
  - Keithley 2182A nanovoltmeter (`GPIB0::7::INSTR`)
  - Keithley 2700 DMM/scanner (`GPIB0::16::INSTR`)
  - Keithley 2401 SourceMeter (`GPIB0::24::INSTR`) — update if discovery differs
  - PK160 supply (`GPIB0::15::INSTR`)
- PC with GPIB interface + VISA stack (NI‑VISA or pyvisa‑py).
- Optional: Thermocouples / temperature channels via 2700 multiplexer.

## 3. Software Stack
- Backend: FastAPI (Python), Uvicorn, PyVISA for instrument control.
- Frontend: React + Vite (TypeScript), Recharts for plotting.
- Export: ExcelJS + html2canvas + file-saver (data + chart images).

## 4. High-Level Data Flow
1) Browser (frontend) sends HTTP requests to FastAPI (`/api/...`).
2) Backend routes call instrument layer:
   - Seebeck: uses 2182A, 2700, PK160
   - I‑V: uses 2401 (and optionally dimensions for resistivity)
3) Measurements streamed back → displayed as tables + charts.
4) Export: frontend captures charts (PNG), packages data + images into Excel, user downloads.

## 5. Algorithms
### 5.1 Seebeck Measurement Loop (session)
Inputs: interval, pre_time, start_volt, stop_volt, inc_rate, dec_rate, hold_time.
Procedure:
1) Connect all instruments (2182A, 2700, PK160); init 2700 channels and PK160.
2) Compute segment counts (pre, ramp-up, hold, ramp-down) based on interval and rates.
3) Loop over steps:
   - Set current via PK160 per step profile.
   - Measure TEMF (mV) via 2182A; measure temperatures (Temp1, Temp2) via 2700.
   - Compute ΔT = Temp1 − Temp2; record (time, TEMF, Temp1, Temp2, ΔT).
   - Wait remaining time in interval.
4) Stop conditions: end of programmed steps or user stop or instrument error.
5) On completion/stop: output_off (PK160), disconnect_all.

### 5.2 I‑V Sweep (2401)
Inputs: start_voltage, stop_voltage, points, delay_ms, current_limit, voltage_limit, optional length/width/thickness.
Procedure:
1) Connect instruments; configure 2401 in voltage source mode with limits.
2) Generate voltage setpoints (linear sweep across `points`).
3) For each V:
   - Set V, wait delay_ms, read (measured V, measured I) from 2401.
   - Compute R = V / I (guard for I ≈ 0).
   - If dimensions provided: resistivity ρ = R * (A / L), conductivity σ = 1 / ρ (guard for zero).
4) Collect arrays of (V, I, R, ρ, σ); return to UI.
5) Turn output off; disconnect_all.

### 5.3 Unit Scaling (frontend)
- Voltage selectable: V / mV / µV (scales chart axis).
- Current selectable: A / mA / µA / nA (scales chart axis).

### 5.4 Linear Fit (I‑V)
- Simple least-squares on displayed (scaled) I‑V points to draw optional fit line.

## 6. Key API Endpoints (base `/api`)
- Seebeck: `POST /seebeck/start`, `POST /seebeck/stop`, `GET /seebeck/status`, `GET /seebeck/data`
- I‑V: `POST /iv/run`
- Instruments: `GET /instrument/discover`

## 7. Frontend UX Highlights
- Seebeck page: start/stop, status, data table, live plots.
- I‑V page:
  - Measurement parameters (like legacy UI: start/stop V, points, delay, limits).
  - Data Handling: unit selectors for V/I.
  - Graph Format: scatter or scatter + linear fit.
  - Data Table: V, I, R, optional resistivity.
  - Export: Excel with data + embedded screenshots of both charts (I‑V, R‑V).
  - Filename field; “Save (data + graphs)” triggers Excel export.

## 8. Safety & Reliability Considerations
- Limits: current_limit and voltage_limit enforced in 2401 config.
- Guard zero/near-zero current when computing resistance to avoid division blow-ups.
- try/finally ensures outputs off and disconnect_all on errors.
- Address detection: use `find_instruments.py` to align code with actual GPIB addresses.

## 9. Common Failure Modes & Remedies
- VI_ERROR_ALLOC: another process holding VISA; close LabVIEW/visa32, power-cycle instruments, run `check_instruments.py` or `fix_instrument_locks.py`.
- 404 from frontend: ensure `VITE_API_BASE_URL` ends with `/api` and routes use `/seebeck/...` or `/iv/run` (avoid `/api/api`).
- Charts missing in export: ensure charts are rendered/visible before saving.
- CORS: backend allows `http://localhost:5173` for dev; keep same host/port or update CORS if changed.

## 10. Deployment / Run Steps (summary)
Backend:
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```
Frontend:
```bash
cd frontend
npm install
echo VITE_API_BASE_URL=http://localhost:8080/api > .env
npm run dev   # http://localhost:5173
```

## 11. Extensibility
- Add more instrument profiles by extending `core/instrument.py` and wiring new routes.
- Additional exports (PDF) could reuse html2canvas output.
- More sweep profiles (log steps, bipolar, pulsed) can be added in `/iv/run` logic.

## 12. For Non‑Technical Readers — How to Operate
1) Start backend, then frontend; open `http://localhost:5173`.
2) Check instruments are powered and addresses match discovery.
3) For Seebeck: set parameters, click Start, watch graphs; Stop when done.
4) For I‑V: set voltages, points, delay, limits; optionally enter sample size for resistivity; Run.
5) Click “Save (data + graphs)” to get an Excel with data and both charts.

