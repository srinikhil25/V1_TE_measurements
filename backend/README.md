# Seebeck Measurement Backend

This is the FastAPI backend for the Seebeck measurement system.

## Setup

1. Create and activate a virtual environment (already done):
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Server

Start the FastAPI server with Uvicorn:

```
python -m uvicorn app.main:app --reload --port 8080
```

The server will be available at http://localhost:8080

## Finding Instrument GPIB Addresses

If you need to find the correct GPIB addresses for your instruments:

### Method 1: Using the Python Script (Recommended)

Run the discovery script:

```bash
python find_instruments.py
```

This will:
- List all available instruments on the GPIB bus
- Identify each instrument by querying its *IDN? command
- Show recommended addresses for Keithley 2182A, 2700, and PK160
- Display the current configuration

### Method 2: Using the API Endpoint

Once the backend is running, you can call:

```bash
curl http://localhost:8080/api/instrument/discover
```

Or visit in your browser:
```
http://localhost:8080/api/instrument/discover
```

### Method 3: Manual Check

1. Open NI-MAX (National Instruments Measurement & Automation Explorer) or Keysight Connection Expert
2. Look for your instruments in the device list
3. Note the GPIB addresses (format: `GPIB0::X::INSTR` where X is the address)

### Updating Addresses

After finding the correct addresses, update them in `backend/app/core/instrument.py`:

```python
ADDR_2182A = "GPIB0::7::INSTR"   # Replace with your actual address
ADDR_2700 = "GPIB0::16::INSTR"   # Replace with your actual address
ADDR_PK160 = "GPIB0::15::INSTR"  # Replace with your actual address
```

## Troubleshooting

### Quick Diagnostic

Before starting the backend, run the diagnostic script:

```bash
python check_instruments.py
```

This will:
- Check if instruments are detected
- Test connections to each instrument
- Identify specific error codes
- Provide recommendations for fixing issues

### Common Issues

**If no instruments are found:**
- Ensure all instruments are powered on
- Check GPIB/USB cable connections
- Verify VISA drivers are installed (NI-VISA or Keysight IO Libraries)
- Make sure GPIB interface card is recognized by Windows
- Check Device Manager for instrument recognition

**If you get `VI_ERROR_ALLOC` errors (-1073807300):**

This error means "Insufficient system resources" and typically indicates:

1. **Another process is using the instruments:**
   - Close LabVIEW, TSPLink, or other applications
   - Check Task Manager for processes using VISA resources
   - Stop the backend server if it's running

2. **Previous connections weren't closed:**
   - Restart the Python interpreter/backend server
   - Run `check_instruments.py` to verify resources are free

3. **Resource leaks:**
   - Restart the instruments (power cycle)
   - Unplug and replug GPIB/USB cables
   - Restart Windows if the problem persists

**Steps to fix VI_ERROR_ALLOC:**

```bash
# Step 1: Stop everything
# - Stop backend server (Ctrl+C)
# - Close LabVIEW, TSPLink, or other VISA applications
# - Close all Python terminals

# Step 2: Run diagnostic
python check_instruments.py

# Step 3: If still locked, try force close
python fix_instrument_locks.py

# Step 4: Check Task Manager for processes using VISA
# - Look for LabVIEW.exe, TSPLink.exe, visa.exe
# - End these processes

# Step 5: Restart instruments (power cycle)
# - Turn off all instruments
# - Wait 30 seconds
# - Turn on one by one, wait for boot

# Step 6: Check Device Manager
# - Open Device Manager
# - Find GPIB interface
# - Disable then Enable the device

# Step 7: Test again
python check_instruments.py

# Step 8: If successful, start backend
python -m uvicorn app.main:app --reload --port 8080
```

**If still failing after all steps:**
- Restart Windows (this clears all VISA resource locks)
- Check GPIB interface card drivers
- Verify instruments are properly connected and powered

## Next Steps
- Implement instrument communication endpoints
- Add WebSocket support for real-time data 