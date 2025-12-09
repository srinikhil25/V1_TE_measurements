# Seebeck / I‑V Measurement System

Full-stack app (FastAPI + React/Vite) for Seebeck measurements and I‑V characterization using Keithley instruments (2700/2182A/2401/PK160) with data export and embedded charts.

## Requirements
- Python 3.10+ (FastAPI backend)
- Node.js 18+ (Vite/React frontend)
- Git
- VISA stack for instruments (NI-VISA or pyvisa-py)

## Project Structure
- `backend/` FastAPI app, instrument control, IV/Seebeck routes
- `frontend/` React/Vite UI (Seebeck + I‑V pages)

## Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Run API
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
# API base: http://localhost:8080/api
```

### Instrument addresses (default)
- 2182A: `GPIB0::7::INSTR`
- 2700: `GPIB0::16::INSTR`
- PK160: `GPIB0::15::INSTR`
- 2401: `GPIB0::24::INSTR` (update if discovery shows a different address)

Use `backend/find_instruments.py` to detect and update addresses. If instruments are locked, use `backend/check_instruments.py` or `backend/fix_instrument_locks.py`.

## Frontend Setup
```bash
cd frontend
npm install

# .env (frontend/.env)
VITE_API_BASE_URL=http://localhost:8080/api

npm run dev   # http://localhost:5173
```

## Features
- Seebeck measurements: start/stop/status/data via Keithley 2700/2182A/PK160
- I‑V characterization: Keithley 2401 sweep with resistance/resistivity calculation
- Unit scaling (V/mV/µV, A/mA/µA/nA)
- Graphs: I‑V, Resistance vs Voltage; optional linear fit overlay
- Export: Excel with data and embedded graphs (I‑V + R‑V)
- API discovery for instrument addresses

## Key API Endpoints (base `/api`)
- `POST /seebeck/start` — start Seebeck session
- `POST /seebeck/stop` — stop session
- `GET  /seebeck/status` — session status
- `GET  /seebeck/data` — measurement data
- `POST /iv/run` — run I‑V sweep (2401)
- `GET  /instrument/discover` — list instruments and recommended addresses

## Usage Notes
- Frontend uses `/api` as base; endpoints include `/seebeck/...` and `/iv/run`.
- Ensure instruments are powered and not locked by other apps (LabVIEW, visa32).
- For CORS/local dev, backend allows `http://localhost:5173`.

## Export (data + graphs)
- On the I‑V page, “Save (data + graphs)” exports Excel containing:
  - Data table (V, I, R, resistivity)
  - Embedded screenshots of I‑V and Resistance vs Voltage charts

## Troubleshooting
- `VI_ERROR_ALLOC`: close other VISA users, restart backend, use `check_instruments.py`.
- 404 on Seebeck: ensure base URL is `/api` and path `/seebeck/...` (avoid double `/api/api`).
- If graphs missing in export: ensure charts rendered/visible before saving.