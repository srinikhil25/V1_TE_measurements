# Seebeck & I‑V Measurement System — Plain‑Language Guide

This guide explains what the system does, the hardware you need, and simple steps to run it. It is written to be understandable by non‑technical readers.

---
## What this system does
- Talks to laboratory instruments (Keithley 2182A, 2700, 2401, PK160) over GPIB to:
  - Measure Seebeck effect (temperature difference vs. voltage).
  - Run I‑V (current–voltage) sweeps and compute resistance and resistivity.
- Shows live graphs in a web browser.
- Lets you export data and graphs into a single Excel file.

---
## What you need
Hardware
- Keithley instruments connected via GPIB:
  - 2182A (nanovoltmeter)
  - 2700 (DMM/scanner)
  - 2401 (SourceMeter for I‑V)
  - PK160 (power supply)
- A PC with a GPIB interface and the VISA driver (NI‑VISA or pyvisa‑py).

Software
- Python 3.10 or newer.
- Node.js 18 or newer.
- Git (to get the code).

---
## How to set up (once per machine)
1) Backend (API)
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

2) Frontend (web UI)
```bash
cd frontend
npm install
```

3) Set frontend API address  
Create `frontend/.env` with:
```
VITE_API_BASE_URL=http://localhost:8080/api
```

---
## How to run
1) Start the backend API
```bash
cd backend
venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
# API will be at http://localhost:8080/api
```

2) Start the frontend
```bash
cd frontend
npm run dev
# Open http://localhost:5173 in your browser
```

---
## Instrument addresses (defaults)
- 2182A: `GPIB0::7::INSTR`
- 2700: `GPIB0::16::INSTR`
- PK160: `GPIB0::15::INSTR`
- 2401: `GPIB0::24::INSTR` (change if discovery shows a different address)

Find/confirm addresses:
```bash
cd backend
python find_instruments.py
```
If instruments are locked, try:
```bash
python check_instruments.py
# If still locked:
python fix_instrument_locks.py
```

---
## Using the web app (browser)
### Seebeck page
- Enter measurement parameters, start, view live data and graphs.
- Data table shows time, TEMF, temperatures, delta‑T.
- Export available on that page (CSV/Excel if present in UI).

### I‑V page
- Set start/stop voltage, number of points, delay, current/voltage limits.
- (Optional) enter sample dimensions to compute resistivity.
- Choose units (V/mV/µV, A/mA/µA/nA) and graph format (scatter or scatter + linear fit).
- Run sweep to see:
  - I–V curve
  - Resistance vs Voltage
- Export: “Save (data + graphs)” creates an Excel file with data and embedded screenshots of both graphs.

---
## Key API endpoints (for reference)
Base URL: `/api`
- Seebeck: `/seebeck/start`, `/seebeck/stop`, `/seebeck/status`, `/seebeck/data`
- I‑V: `/iv/run`
- Instruments: `/instrument/discover`

---
## Troubleshooting (plain language)
- Instruments not found or locked: stop other VISA/GPIB apps (LabVIEW, visa32), power‑cycle instruments, run `check_instruments.py`, or `fix_instrument_locks.py`.
- 404 errors from frontend: ensure `VITE_API_BASE_URL` ends with `/api` and paths are `/seebeck/...` or `/iv/run` (no double `/api/api`).
- No graphs in export: make sure graphs are visible on screen before clicking “Save (data + graphs)”.
- CORS/local dev: backend allows `http://localhost:5173`; keep frontend and backend on the same machine/URL during dev.

---
## What to tell a new user
- Plug in and power the instruments; confirm GPIB addresses with `find_instruments.py`.
- Start backend, then frontend, then open `http://localhost:5173`.
- Use the Seebeck or I‑V page to run measurements; export results with graphs via the provided Save button.


