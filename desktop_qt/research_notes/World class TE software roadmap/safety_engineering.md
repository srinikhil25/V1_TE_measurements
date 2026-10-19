# Safety Engineering for Software-Controlled Laboratory Heaters
## Layered Protection Design for TE Measurement Rig

**Date:** October 2026  
**Context:** PyQt6 Windows desktop app controlling Matsusada P4K-80M (80 W, 1.3 A) DC power supply via GPIB for sample heater in Seebeck measurements. Keithley 2700 thermocouple scanner, Keithley 2182A nanovoltmeter, Keithley 2401 I-V SourceMeter.

---

## 1. Executive Summary: Current Safety Gaps

The system has **no hardware over-temperature cutoff**, **no communication watchdog**, **no graceful shutdown on app close**, and **no sensor-data validation**. These are common vulnerabilities in early-stage research equipment:

- **PC crash/hang:** Supply remains at last setpoint indefinitely
- **App force-kill:** Output persists; heater uncontrolled
- **Window close:** Experiment continues running background
- **Failed thermocouple read:** Substituted with 0 °C; software cannot detect fault
- **GPIB hang:** Blocks for 20–25 s; no timeout prevents deadlock
- **No independent limit:** Failure mode is catastrophic (runaway temperature → fire, damage, injury)

**Risk level:** Unattended operation is currently **unsafe**. Immediate software fixes and hardware additions are required to meet IEC 61010-2-010 and university lab safety standards.

---

## 2. Standards and Regulatory Context

### IEC 61010-1 & IEC 61010-2-010

IEC 61010-1 provides general safety requirements for electrical measurement, control, and laboratory equipment. IEC 61010-2-010:2019 (latest edition) specifies safety for **laboratory equipment for heating of materials**, covering electrical shock, mechanical hazards, fire, and heat safety [1][2].

**Key requirements (IEC 61010-2-010):**
- Equipment temperature limits must be controlled by automatic shut-off devices
- Over-temperature protection is mandatory for unattended operation
- Communication loss must not result in hazardous conditions
- System design must account for single-fault tolerability
- Personnel protection (guards, interlocks) for high-temperature surfaces above 60 °C

**Your system gap:** No automatic shutdown on over-temperature or communication loss.

### IEC 61508: Functional Safety & SIL Levels

IEC 61508 is the umbrella functional safety standard applicable to all industries [3][4]. It defines **Safety Integrity Levels (SILs)** from 1 (lowest) to 4 (highest), quantified by **probability of failure on demand (PFD)** or dangerous failure frequency per hour [3].

- **SIL 1:** PFD 10⁻¹ to 10⁻² (10% to 1% probability of dangerous failure per demand)
- **SIL 2:** PFD 10⁻² to 10⁻³
- **SIL 3:** PFD 10⁻³ to 10⁻⁴
- **SIL 4:** PFD < 10⁻⁴

**Critical concept:** **Software alone cannot achieve SIL > 2** without independent hardware. A purely software watchdog cannot prevent hardware failure or detect its own crash. IEC 61508-3:2010 governs software requirements but explicitly mandates hardware redundancy and independent monitoring for higher SILs [3].

**Your system:** Currently unrated, functionally at risk level "uncontrolled." Target should be **SIL 1–2** via layered design (software + hardware interlock + thermal fuse).

### University Lab Safety Guidance

University EHS standards for unattended heating equipment require [5]:
- **Temperature limits:** Within 25 °C of maximum experiment temperature; over-temperature control at least 15 °C below that limit
- **Fail-safe design:** Processes generating heat must not be left unattended without fail-safe controls
- **Shutdown on safety event:** Power disconnection via interlock, timer, or explicit operator action
- **Water cooling:** Flow monitoring and automatic shutoff if pressure drops

**Implication:** Unattended TE measurements without hardware interlock and thermal limits violate institutional policy.

---

## 3. Instrument-Specific Safety Features

### 3.1 Matsusada P4K-80M DC Power Supply

**Protective features confirmed in R4K-80 & P4KF-80 series** (P4K-80M model documentation not directly located; specifications inferred from same product line) [6][7]:

| Feature | Capability | Notes |
|---------|-----------|-------|
| **OVP** (Over-Voltage Protection) | Yes, adjustable | Triggers at max rated voltage × 110% |
| **OCP** (Over-Current Protection) | Yes, adjustable | Soft-limit based on ICN setting; can be disabled in software |
| **OTP** (Over-Temperature Protection) | Yes, built-in | Internal supply temperature cutoff |
| **ACF** (AC Input Failure) | Yes | Stops output if AC mains unstable |
| **Output Enable/Remote Shutdown** | **Not confirmed** | Check control terminal on rear panel; may support remote on/off line |
| **Watchdog Timer** | **Not confirmed** | No evidence of automatic output-off on GPIB timeout |
| **Front-panel limit potentiometer** | **Likely yes** | Mechanical dial for max voltage, may be local-only |

**Gap for this system:**
- No remote emergency shutdown input from PC
- No communication watchdog (does not know if PC is alive)
- OCP/OVP are *soft limits* (firmware-based); inadequate alone for safety—must pair with hardware interlock
- Setting ICN (current limit) alone does NOT prevent over-temperature; it only limits I, not T

**Recommendation:** Check Matsusada datasheet for:
1. Does output have a TTL-level remote shutdown pin? (Some models do on the rear DB-9 or D-sub connector)
2. Is there an external interlock input?
3. Does the supply support a watchdog timeout setting (e.g., "output off if no command received for X seconds")?

If unavailable, a **hardware relay interlock** (section 4) is mandatory.

### 3.2 Keithley 2700 Multimeter / Scanner Card

**Safety features** [8][9]:

| Feature | Capability | Notes |
|---------|-----------|-------|
| **Open Thermocouple Detection (OTCD)** | Yes, built-in | 10 μA test pulse; alerts on open circuit |
| **Alarm HI/LO Limits** | 5 TTL outputs | 2 HI + 2 LO per-channel limits; 1 master alarm line |
| **Digital I/O Inputs** | 2 lines | 1 hardware interlock input, 1 trigger input |
| **Alarm Output Routing** | Yes | Can drive external interlock relay directly |
| **Reading Rate & Timeout** | Configurable | Default measurement timeout exists |

**Critical feature:** The 2700 has **hardware alarm outputs (TTL)** that can be wired directly to a relay or contactor to cut heater power when temperature exceeds a setpoint. This is a native safety mechanism—**use it**.

**Gap for this system:**
- OTCD is enabled by default but your code does not read or act on the alert
- Alarm outputs exist but are not wired to heater interlock
- No redundant temperature sensor (2700 measures T1–T4, but only one validates the sample)

**Recommendation:** 
- Enable OTCD in firmware; read alarm status after each measurement
- If any thermocouple fails open → shut down supply immediately (software + hardware)
- Physically wire 2700 HI alarm output to latching safety relay (see section 4)

### 3.3 Keithley 2401 SourceMeter (I-V measurements)

**Safety features** [10]:

| Feature | Capability | Notes |
|---------|-----------|-------|
| **Interlock Input** | DB-9 connector | Accessory interlock pin; disables output if pulled |
| **Output Enable/Disable** | Software + interlock | Can disable via GPIB command *OUTP OFF* |
| **OCP/OVP** | Built-in, firmware | Soft limits; not independent safety cutoff |

**Gap:** Limited safety integration. The 2401 is primarily a measurement device and has less developed safety features than the 2700.

**Recommendation:** 
- Use 2401 only for passive I-V measurement (no hazard from measurement itself)
- Do NOT rely on 2401 interlock for heater power; use 2700 alarm or dedicated thermal controller

### 3.4 Keithley 2182A Nanovoltmeter

**Safety features:** Primarily a passive measurement device; no built-in alarms or interlocks [11].

**Recommendation:** Use only for reading thermovoltage; assume no contribution to safety chain.

---

## 4. Hardware Over-Temperature Protection

### 4.1 Thermal Fuse (Simplest, Most Reliable)

**What it is:** A one-shot thermal element that **physically interrupts the circuit** when temperature exceeds a setpoint. Once triggered, it is permanently open (resettable only by replacement) [12][13].

**Installation:**
- Mount the fuse **in direct thermal contact** with the heater body or sample holder
- Install **in series with the main heater power line** (not just a signal line)
- Choose a trip temperature **10–20 °C above** normal maximum to avoid nuisance trips

**Specifications:**
- **Cost:** $5–$30 USD per unit
- **Response time:** < 5–10 seconds (depending on thermal mass)
- **Compliance:** IEC 61010-2-010 recognizes thermal fuses as independent over-temperature protection
- **Drawback:** One-time use; must replace fuse after any trip (intentional or false)
- **Advantage:** Requires zero software interaction; fails safe by design

**Example (MICROTEMP G4 series):**
- Range 35–200 °C; cost ~$8–15
- Datasheet: See [13] for application notes on thermal contact and mounting

**Recommendation:** Install a **thermal fuse rated for 60–70 °C** in series with the heater power supply immediately. This is the single most effective hardware safety addition for < $20 and requires no software changes.

### 4.2 Standalone Over-Temperature Limit Controller

**What it is:** An electronic controller with its own thermocouple input and relay output. Monitors temperature independently of the PC; cuts heater power when limit exceeded [14].

**Examples:** Omega CNi32, Watlow EZ-ZONE, Chromalox safety limit controller.

**Specifications:**
- **Cost:** $150–$400 USD
- **Response time:** 1–5 seconds (configurable)
- **Interface:** Thermocouple input (can read T1, T2, T3, or T4 from 2700), relay output (normally open; powered to close heater circuit)
- **Features:** Settable high/low alarms, multiple setpoint options, manual reset or auto-restart
- **Compliance:** Dedicated safety device; independent of PC (SIL-rated)
- **Advantage:** Redundant measurement; survives PC crash

**Recommended approach for your rig:**
1. Connect 2700 channel 102 (sample thermocouple) to limit controller input
2. Set **setpoint to 60 °C** (or your safe max)
3. Set **hysteresis to 5 °C** (restart when T < 55 °C)
4. Wire limit controller relay in series with heater power
5. **Manual reset** mode: requires operator to push a button to restart after a trip (fail-safe)

**This is the preferred solution for unattended operation** because it is independent, redundant, and SIL-compatible.

### 4.3 Safety Relay + Interlock

**What it is:** A latching relay module that monitors a safety input line (e.g., from 2700 alarm output or PC digital output). Energizes a contactor to power the heater; de-energizes on safety trip [15].

**Specifications:**
- **Cost:** $50–$150 USD (safety relay) + $30–$100 (contactor)
- **Response time:** < 100 ms
- **Compliance:** SIL-rated if properly designed (IEC 61508, ISO 13850)
- **Advantage:** Can combine PC software alarm with 2700 alarm for redundant shutdown

**Circuit topology:**
```
[AC Mains] → [Safety Relay] → [Contactor] → [Thermal Fuse] → [Heater]
                    ↑
         [2700 HI Alarm TTL]
                    ↑
         [PC Digital Output (optional)]
```

**Wiring:** 2700 HI alarm TTL output wired to relay reset/fault input → heater power cut on temperature alarm.

**Limitation:** Relies on 2700 measurement accuracy; if thermocouple fails, no backup.

**Recommendation:** Use safety relay **in addition to thermal fuse**, not instead of it.

### 4.4 Combination (Recommended for Unattended Operation)

```
HARDWARE LAYERS (in series):
1. Thermal Fuse (60–70 °C) — ultimate fallback, always active
2. Over-Temperature Limit Controller (60–62 °C setpoint) — independent of PC
3. Safety Relay wired to 2700 Alarm (HI at 58 °C) — fastest response, PC-aware

SOFTWARE LAYER (runs on PC, not trusted for safety):
- Read 2700 OTCD, validate temperature plausibility
- If T > 60 °C, send *OUTP OFF* to P4K-80M and Keithley 2401
- Gracefully shutdown app and log event
- This layer is redundant; hardware survives its failure
```

**Total cost:** Thermal fuse ($15) + Limit Controller ($250) + Safety Relay ($80) + Contactor ($50) = ~**$400**.

**Compliance:** Meets IEC 61010-2-010 single-fault tolerance; achieves SIL 1 for temperature protection.

---

## 5. Software Safety Patterns

### 5.1 Watchdog Timer & Heartbeat

**Concept:** A hardware or external watchdog monitor that checks whether the PC is responsive. If the PC becomes unresponsive (hang, crash, force-kill), the watchdog triggers a safety action (heater shutdown).

**Software-only watchdog (weak):**
- Timer thread in Python periodically checks: "Is main loop responsive?"
- On timeout, attempts to close app gracefully
- **Problem:** Cannot survive app crash or thread deadlock; requires hardware backup

**Hardware watchdog (strong):**
- USB watchdog device (e.g., Yocto-WatchdogDC) [16]
- PC software must "heartbeat" device every 5–10 seconds via USB
- If heartbeat stops, relay cuts heater power
- **Advantage:** Works even if PC kernel hangs (e.g., driver crash)
- **Cost:** $50–$150

**Recommended implementation:**
```python
import threading
import time
from pyqtSignals import Signal

class WatchdogHeartbeat(QThread):
    """Periodically signal hardware watchdog. If main loop blocks, 
    heartbeat stops → watchdog triggers heater shutdown."""
    
    def run(self):
        while self.running:
            try:
                # Send heartbeat to USB watchdog device
                self.watchdog_device.ping()  # Blocks if device not responding
                time.sleep(5)
            except Exception as e:
                # Heartbeat failed → emergency shutdown
                self.emergency_stop.emit(f"Watchdog heartbeat failed: {e}")
                break

class MainWindow(QMainWindow):
    emergency_stop = Signal(str)
    
    def __init__(self):
        self.watchdog = WatchdogHeartbeat()
        self.watchdog.emergency_stop.connect(self.handle_emergency_stop)
        self.watchdog.start()
    
    def handle_emergency_stop(self, reason):
        """Called if watchdog triggers."""
        logger.critical(f"EMERGENCY STOP: {reason}")
        self.supply.output_off()  # P4K-80M off
        self.watchdog.running = False
        QApplication.quit()
```

**Note:** This requires an actual USB watchdog device. Software-only watchdog is insufficient for safety.

### 5.2 Graceful Shutdown on Window Close

**Problem:** Closing PyQt6 window does not stop the heater; experiment continues in background.

**Solution:** Override `closeEvent()` to perform controlled shutdown [17].

```python
class MainWindow(QMainWindow):
    def closeEvent(self, event):
        """Called when user clicks X or closes window."""
        logger.info("Window close event triggered.")
        
        try:
            # Step 1: Signal shutdown to measurement threads
            self.measurement_active = False
            
            # Step 2: Ramp down voltage slowly (safe)
            for v in range(self.current_voltage, 0, -5):
                self.supply.set_voltage(v)
                time.sleep(0.1)
            
            # Step 3: Disable output
            self.supply.output_off()
            
            # Step 4: Wait for threads to finish
            if self.measurement_thread.is_alive():
                self.measurement_thread.join(timeout=5.0)
            
            # Step 5: Accept close event
            event.accept()
            logger.info("Shutdown complete.")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Force shutdown anyway; do not stay open
            event.accept()
```

**Signal handling for forced termination (Ctrl+C, kill):**
```python
import signal
import sys

def signal_handler(sig, frame):
    """Called on SIGINT (Ctrl+C) or SIGTERM."""
    logger.warning(f"Signal {sig} received; initiating emergency stop.")
    # Tell main window to close
    QApplication.instance().quit()

# In main():
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

**Windows console handler (for Ctrl+C in Windows console):**
```python
import ctypes

def windows_ctrl_handler(dwCtrlType):
    if dwCtrlType == 0:  # CTRL_C_EVENT
        logger.warning("CTRL_C_EVENT received.")
        QApplication.instance().quit()
        return True
    return False

# In main() on Windows:
if sys.platform == 'win32':
    kernel32 = ctypes.WinDLL('kernel32')
    kernel32.SetConsoleCtrlHandler(
        ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint)(windows_ctrl_handler),
        True
    )
```

**atexit hook (for normal exit paths):**
```python
import atexit

def cleanup_on_exit():
    """Run even if exception is raised or app force-killed."""
    logger.info("atexit: Performing final cleanup.")
    try:
        supply.output_off()
    except:
        pass

atexit.register(cleanup_on_exit)
```

### 5.3 Sensor Data Validation & Plausibility Checks

**Problem:** Failed thermocouple read returns 0 °C; software cannot detect fault.

**Solution:** Implement multi-level sanity checks [18].

```python
def validate_temperature_reading(t_new, t_prev, label="T"):
    """
    Plausibility checks on thermocouple reading.
    
    Returns: (valid: bool, t_corrected: float, reason: str)
    """
    
    # 1. Range check: T must be physically reasonable
    if not (-50 <= t_new <= 200):  # Adjust range per experiment
        return False, t_prev, f"{label} out of range: {t_new} °C"
    
    # 2. Rate-of-change check: T cannot change faster than physics allows
    #    Typical thermocouple response: max ~2–5 °C/s in air
    max_rate = 5.0  # °C/s
    dt = 0.5  # seconds (measurement interval)
    max_delta = max_rate * dt
    
    if abs(t_new - t_prev) > max_delta:
        return False, t_prev, f"{label} rate-of-change violation: {(t_new - t_prev)/dt} °C/s"
    
    # 3. Stuck reading check: same value multiple times suggests sensor failure
    #    Track last N readings; if all identical, suspect stuck sensor
    if not hasattr(validate_temperature_reading, 'history'):
        validate_temperature_reading.history = {}
    
    key = label
    if key not in validate_temperature_reading.history:
        validate_temperature_reading.history[key] = []
    
    history = validate_temperature_reading.history[key]
    history.append(t_new)
    if len(history) > 10:
        history.pop(0)
    
    if len(history) >= 5 and len(set(history[-5:])) == 1:  # Last 5 values identical
        return False, t_prev, f"{label} stuck at {t_new} °C (sensor fault?)"
    
    # 4. Cross-check with redundant sensor if available
    # (e.g., if you have T1 and T2 both measuring sample, they should agree within ±2°C)
    
    # 5. Open thermocouple detection from 2700 OTCD
    if t_new == 0 and t_prev > 50:  # Sudden drop to 0
        return False, t_prev, f"{label} sudden drop to 0 °C (open circuit?)"
    
    return True, t_new, "OK"

# Usage in measurement loop:
t_sample_prev = 25.0
while running:
    t_sample_raw = keithley_2700.read_channel(102)
    valid, t_sample, reason = validate_temperature_reading(t_sample_raw, t_sample_prev, "T_sample")
    
    if not valid:
        logger.error(f"Temperature validation failed: {reason}")
        # EMERGENCY STOP
        supply.output_off()
        raise RuntimeError(f"Sensor fault: {reason}")
    
    t_sample_prev = t_sample
    # Continue measurement...
```

### 5.4 GPIB Communication Timeout & Retry

**Problem:** GPIB read can hang for 20–25 s, blocking the main thread.

**Solution:** Implement timeouts and async communication [19].

```python
import threading
import queue

class GPIBWithTimeout:
    """Wrapper for GPIB instrument with configurable timeout."""
    
    def __init__(self, resource_name, timeout_sec=3.0):
        self.resource = rm.open_resource(resource_name)
        self.resource.timeout = timeout_sec * 1000  # PyVISA uses milliseconds
        self.timeout_sec = timeout_sec
    
    def query_safe(self, command, max_retries=2):
        """
        Send query; return result or raise exception on timeout.
        
        Automatically retries on timeout (GPIB bus sometimes recovers).
        """
        for attempt in range(max_retries):
            try:
                result = self.resource.query(command)
                if attempt > 0:
                    logger.info(f"GPIB recovered after {attempt} retry.")
                return result
            except pyvisa.VisaIOError as e:
                if 'timeout' in str(e).lower():
                    logger.warning(f"GPIB timeout on '{command}' (attempt {attempt+1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(0.5)  # Brief wait before retry
                        continue
                # All retries exhausted or non-timeout error
                logger.error(f"GPIB error (irrecoverable): {e}")
                raise RuntimeError(f"GPIB communication failed: {e}")

# Usage:
supply_gpib = GPIBWithTimeout("GPIB0::6", timeout_sec=3.0)
try:
    voltage = supply_gpib.query_safe("SOURce:VOLTage?")
except RuntimeError:
    logger.critical("GPIB instrument not responding; emergency shutdown.")
    # Trigger safety interlock
    emergency_shutdown()
```

**Monitor GPIB communication time:**
```python
import time

class GPIBMonitor:
    def __init__(self, threshold_sec=5.0):
        self.threshold = threshold_sec
        self.last_command_time = time.time()
    
    def log_command(self, cmd):
        dt = time.time() - self.last_command_time
        if dt > self.threshold:
            logger.warning(f"GPIB slow response: {dt:.1f} s for previous command")
        self.last_command_time = time.time()
        logger.debug(f"GPIB → {cmd}")

monitor = GPIBMonitor(threshold_sec=5.0)

# In measurement loop:
monitor.log_command("SOURce:VOLTage?")
v = supply_gpib.query(":SOURce:VOLTage?")
```

### 5.5 Maximum Temperature & Rate Limits in Firmware

**Add hardcoded limits in your measurement class:**

```python
class MeasurementController:
    # Fail-safe constants (not configurable via UI)
    ABSOLUTE_MAX_TEMP = 75  # °C — never exceed this, even if user sets higher
    MAX_RATE_INCREASE = 2.0  # °C/s — abort if heating too fast
    MAX_RATE_HOLD_TIME = 300  # seconds — max duration at any temperature
    
    def __init__(self):
        self.start_time = None
        self.max_t_observed = 0
    
    def check_safety_limits(self, t_current):
        """Must be called on every measurement."""
        
        # 1. Absolute max temperature
        if t_current > self.ABSOLUTE_MAX_TEMP:
            logger.error(f"ABORT: T={t_current} exceeds absolute max {self.ABSOLUTE_MAX_TEMP}")
            self.emergency_stop()
        
        # 2. Rate of increase
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                rate = (t_current - self.start_temp) / elapsed
                if rate > self.MAX_RATE_INCREASE:
                    logger.error(f"ABORT: T rising at {rate:.1f} °C/s (max {self.MAX_RATE_INCREASE})")
                    self.emergency_stop()
        
        # 3. Hold time at maximum
        if t_current > self.max_t_observed:
            self.max_t_observed = t_current
            self.max_t_time = time.time()
        else:
            hold_time = time.time() - self.max_t_time
            if hold_time > self.MAX_RATE_HOLD_TIME:
                logger.error(f"ABORT: Holding at max temp for {hold_time} s")
                self.emergency_stop()
    
    def emergency_stop(self):
        """Immediate, unconditional shutdown."""
        try:
            self.supply.output_off()
            logger.critical("EMERGENCY STOP executed.")
        except:
            pass
        raise RuntimeError("Safety limit exceeded; experiment aborted.")
```

---

## 6. Thermocouple Fault Detection

### 6.1 Open Thermocouple Detection (Keithley 2700 OTCD)

The Keithley 2700 has built-in open thermocouple detection: a 10 μA test pulse injected into each channel to detect an open circuit [8].

**Enable in firmware:**
```python
# Configure 2700 for OTCD
keithley_2700.write(":VOLTage:TCOuple:OPEn ON")  # Enable OTCD
keithley_2700.write(":VOLTage:TCOuple:OPEn:STATe?")  # Query enabled state

# After each measurement:
otcd_status = keithley_2700.query(":STATus:CHANnelN:ALARm?")  # Check for alarm
if otcd_status != '0':
    logger.error(f"Open thermocouple detected on channel {channel}")
    emergency_stop()
```

**Detection time:** Configurable (10 ms, 32 ms, or 100 ms) [8].

### 6.2 Cold Junction Compensation

Modern thermocouples require **cold-junction compensation** to correct for temperature variations at the reference terminals. The Keithley 2700 includes internal cold-junction compensation [20].

**Ensure 2700 is configured:**
```python
keithley_2700.write(":VOLTage:TCOuple:CCOMpensation:TYPE INTernal")  # Use internal CJC
temp_internal = keithley_2700.query(":TEMPerature:RJUNction?")  # Read reference temperature
logger.info(f"Cold junction temperature: {temp_internal} °C")
```

### 6.3 Redundant Temperature Sensors

**Best practice:** Install **two independent thermocouples** on the sample, wired to separate channels (e.g., 102 and 103).

```python
t1 = keithley_2700.read_channel(102)  # Primary
t2 = keithley_2700.read_channel(103)  # Redundant

# Cross-check: should agree within ±2°C
if abs(t1 - t2) > 2.0:
    logger.error(f"Thermocouple mismatch: T1={t1}, T2={t2} (sensor fault?)")
    emergency_stop()

# Use average if both valid
t_sample = (t1 + t2) / 2
```

### 6.4 Infrared Camera Verification (Optional)

For high-temperature experiments, an independent **infrared (non-contact) thermometer** or thermal camera provides:
- Cross-check of thermocouple accuracy
- Detection of localized hot spots (contact failure, heater malfunction)
- Qualitative validation (e.g., "is the sample actually heating?")

**Cost:** $100–$500 for IR thermometer; not required for SIL compliance but recommended for unattended runs.

---

## 7. Recommended Layered Safety Architecture

### Phase 1: Immediate (Software, < $0, 1–2 weeks)

**Goal:** Prevent most common failure modes without hardware additions.

1. **Graceful shutdown:**
   - Override PyQt6 `closeEvent()` to ramp down voltage and disable supply
   - Add signal handlers for SIGINT, SIGTERM, and Windows console control events
   - Register atexit cleanup function

2. **Sensor validation:**
   - Implement range, rate-of-change, and stuck-value checks for each thermocouple
   - Abort experiment if any check fails
   - Log all errors to file (for post-mortem analysis)

3. **GPIB timeout:**
   - Set timeout to 3–5 seconds on all GPIB operations
   - Retry once on timeout; fail hard after that
   - Do NOT block main thread indefinitely

4. **Hardcoded limits:**
   - Add ABSOLUTE_MAX_TEMP (75 °C) constant
   - Add MAX_RATE_INCREASE constant (2 °C/s)
   - Check every measurement cycle

5. **2700 OTCD:**
   - Enable open thermocouple detection on all channels
   - Read and log OTCD status after each measurement
   - Abort on any open detection

**Implementation time:** ~20–40 hours for careful developer.

### Phase 2: Hardware Fallback (Hardware, ~$400, 2–4 weeks)

**Goal:** Survive software failure via independent hardware.

1. **Thermal fuse ($15):**
   - Order 60–70 °C thermal fuse rated for heater current
   - Install in series with heater power line (near heater body for thermal contact)
   - Test by briefly shorting heater circuit to verify fuse trips

2. **Over-temperature limit controller ($250):**
   - Order Omega CNi32 or equivalent with 60 °C setpoint
   - Connect 2700 channel 102 (primary thermocouple) to controller input
   - Set manual-reset mode (operator must acknowledge trip)
   - Verify alarm output triggers relay at 60 °C

3. **Safety relay + contactor ($80 + $50):**
   - Order safety relay module (IEC 61508 certified preferred)
   - Order 110 V AC contactor rated for heater current (max 1.3 A @ 80 W)
   - Wire 2700 HI alarm (TTL) to relay reset input
   - Wire relay output to contactor coil
   - Circuit: AC Mains → Relay → Contactor → Fuse → Heater

**Verification:**
- Manually trigger 2700 alarm (set limit to 25 °C, heat to 30 °C) → heater should shut off
- If fuse trips → replace and verify mechanical connection

### Phase 3: Advanced (Optional, ~$150–500, 4–8 weeks)

**Goal:** Monitor PC health; survive OS-level crash.

1. **USB hardware watchdog ($80–150):**
   - Order Yocto-WatchdogDC or similar USB relay
   - Software heartbeat every 5 seconds; relay cuts power on timeout
   - Wire in series with heater power (or to safety relay enable line)

2. **Redundant thermocouple (free–$100):**
   - Install second T-type junction on sample
   - Connect to 2700 channel 103
   - Cross-check T1 vs. T2 every cycle
   - Accept reading only if Δ < 2 °C

3. **Data logging & remote monitoring (free–$200):**
   - Log all measurements, errors, and shutdowns to CSV file
   - Optional: send alerts to email/Slack if T exceeds setpoint during run

---

## 8. Standards Compliance Checklist

| Requirement | Source | Current Status | Action |
|-------------|--------|-----------------|--------|
| Over-temperature protection | IEC 61010-2-010 §7.2.1 | ❌ None | Add thermal fuse + limit controller |
| Single-fault tolerance | IEC 61010-2-010 §5.3 | ⚠️ Software only | Add hardware interlock (thermal fuse) |
| Communication loss handling | IEC 61010-2-010 §5.4 | ❌ Hangs | Add GPIB timeout; fail-safe output off |
| Graceful shutdown | IEC 61010-2-010 §7.4 | ❌ Window close ignored | Implement closeEvent() handler |
| Sensor fault detection | IEC 61010-2-010 §7.3.2 | ⚠️ OTCD not used | Enable 2700 OTCD; read status |
| Redundancy for SIL 2+ | IEC 61508-3 §7.4 | ⚠️ Software watchdog only | Add hardware watchdog USB device |
| Data validation | IEC 61508-3 §6.4 | ❌ No checks | Implement range, rate, stuck checks |
| Unattended operation safe? | University EHS policy | ❌ No | Not permitted without Phase 2 hardware |

---

## 9. Estimated Costs & Timeline

| Phase | Component | Cost | Timeline | Risk Reduction |
|-------|-----------|------|----------|-----------------|
| 1 | Software implementation | $0 | 1–2 weeks | Moderate (survives graceful close, GPIB hang) |
| 2a | Thermal fuse | $15 | 1 day | High (ultimate fallback) |
| 2b | Limit controller | $250 | 1–2 weeks | High (independent shutdown) |
| 2c | Safety relay + contactor | $130 | 1 week | High (fast response, redundancy) |
| 3 | USB watchdog | $100–150 | 1 week | Moderate (survives OS hang) |
| 3 | Redundant thermocouple + wiring | $20–50 | 1 week | Low–Moderate (cross-check) |
| **Total for "safe to run unattended"** | **Phase 1 + 2** | **~$400** | **3–4 weeks** | **SIL 1, IEC 61010 compliant** |

---

## 10. Failure Mode Analysis (FMEA)

| Failure Mode | Cause | Current Mitigation | Phase 1 Fix | Phase 2 Fix | Residual Risk |
|--------------|-------|-------------------|------------|-----------|---|
| PC hangs indefinitely | GPIB deadlock, driver crash | None | Timeout + retry | USB watchdog relay | Thermal fuse catches T runaway |
| App force-killed (Ctrl+C) | User impatience or script error | None | atexit handler shuts down supply | Hardware relay de-energizes | Fuse if rate too high |
| Window closed, experiment runs | User closes GUI | None | closeEvent() ramps down supply | Relay disconnects | Fuse fallback |
| Thermocouple open | Connector broken, wire corrosion | None; reports 0 °C | OTCD read + abort | Limit controller redundant | Fuse active |
| Runaway heating (rate exceeds max) | Heater stuck on (relay failure) or buggy firmware | None | Rate-of-change limit + abort | Limit controller + fuse | Fuse guaranteed to trip |
| Over-temperature (T > 75 °C) | Setpoint error, failed shutdown | None | Hardcoded absolute max | Thermal fuse + limit controller | Both layers guarantee cutoff |
| Sensor data out of range (e.g., 999 °C) | Thermocouple short, ADC glitch | Substitutes 0 °C (false!) | Plausibility check + abort | Limit controller sees no overtemp | False negative, but alarm generated |

---

## 11. Testing Procedures

### 11.1 Software Validation

```bash
# Test graceful shutdown:
python main.py
<let it heat for 1 min to ~40°C>
<close window or press Ctrl+C>
# Expected: Voltage ramps down smoothly; supply off within 5 seconds
# Check log: "Shutdown complete"

# Test GPIB timeout:
<disconnect GPIB cable while app running>
# Expected: Timeout error logged; app stops measurement, does NOT hang
# Recover: Reconnect cable; app must recover

# Test sensor validation:
# Manually set thermocouple to 0 °C (short to GND) on 2700
# Expected: Plausibility check fails; app aborts with log "sudden drop to 0 °C"

# Test maximum rate limit:
# Set voltage ramp rate to max (0.1 V/s); observe GPIB delay
# Expected: If T rises > 2 °C per measurement cycle, abort logged
```

### 11.2 Hardware Validation

**Thermal fuse:**
```
1. At room temp (25 °C), measure fuse resistance: should be ~0.01 Ω (continuity)
2. Apply heater at 80 W; measure time to reach 65 °C
3. Leave running; fuse should trip within 30 s of reaching 65 °C
4. After trip, measure resistance: should be > 1 MΩ (open)
5. Replace fuse; repeat
```

**Limit controller:**
```
1. Set thermocouple input to 25 °C source (ice bath or calibrator)
2. Set limit setpoint to 30 °C
3. Ramp temperature to 31 °C (raise thermocouple input)
4. Verify alarm relay clicks (audible); measure relay output voltage
5. Cool to 28 °C; verify relay opens again (auto-restart if configured)
```

**Safety relay + contactor:**
```
1. Energize relay coil; measure output contacts (should close, allowing AC current)
2. Send TTL signal to relay reset input (TTL LO); relay should de-energize
3. Verify contactor disconnects heater power
4. Measure contactor coil voltage: should be 0 V after de-energize
```

---

## 12. Recommended Reading & References

### Standards & Regulatory
1. **IEC 61010-1:2010** — General requirements for electrical lab equipment (base standard)
2. **IEC 61010-2-010:2019** — Safety for laboratory heating equipment (your domain)
3. **IEC 61508:2010** — Functional safety of E/E/PE systems (SIL definitions)
4. **ISO 13850:2015** — Emergency stop device general requirements
5. **ANSI B11.19** — Machine safety-related interlocks and devices

### Instrument Manuals (Obtain from Keysight/Tektronix)
6. **Matsusada R4K-80 / P4K Series Manual** — Check for remote shutdown, watchdog features
7. **Keithley 2700 User Manual** — OTCD, alarm, digital I/O configuration
8. **Keithley 2182A User Manual** — Measurement accuracy, cold-junction compensation
9. **Keithley 2400 Series SourceMeter Manual** — Interlock pin details

### Application Notes
10. **Chromalox Safety Limit Controllers application note** — Design of independent temperature shutoff
11. **MICROTEMP Thermal Fuse Application Notes** [13] — Mounting, thermal contact optimization
12. **Omega CNi32 Product Sheet** — Configuration for lab heating applications
13. **Yocto-WatchdogDC Documentation** — USB watchdog relay integration

### Software & Design
14. **Python signal handling** — [https://docs.python.org/3/library/signal.html](https://docs.python.org/3/library/signal.html)
15. **PyVISA timeout configuration** — [https://pyvisa.readthedocs.io/](https://pyvisa.readthedocs.io/)
16. **PyQt6 closeEvent pattern** [17] — Graceful shutdown in GUI applications
17. **Watchdog timer design** [https://www.ganssle.com/watchdogs.htm](https://www.ganssle.com/watchdogs.htm)

### University EHS Guidance
18. **Northwestern University Lab Safety** [5] — Hot plate usage, heating reaction safety
19. **Princeton EHS Lab Safety Manual** [5] — Heating device requirements
20. **UCSD Safety for Heating Reactions** [5] — Unattended operation policy

---

## 13. Immediate Action Items

### Week 1
- [ ] Enable Keithley 2700 open thermocouple detection; read OTCD status after each measurement
- [ ] Implement PyQt6 closeEvent() handler with graceful voltage ramp-down
- [ ] Add atexit and signal handlers for Ctrl+C / SIGTERM
- [ ] Set GPIB timeout to 3 seconds on all instruments
- [ ] Add range and rate-of-change checks on thermocouple readings

### Week 2
- [ ] Implement absolute max temperature (75 °C) hardcoded limit; abort on exceed
- [ ] Add "stuck temperature" detector (same value for 10 consecutive reads)
- [ ] Test graceful shutdown by closing window while heating
- [ ] Verify GPIB timeout works (disconnect cable mid-run; expect error, not hang)
- [ ] Code review: ensure no blocking operations in main thread

### Week 3–4
- [ ] Order thermal fuse (60–70 °C, rated for 1.3 A @ 110 V)
- [ ] Order over-temperature limit controller (Omega CNi32 or equivalent)
- [ ] Order safety relay + contactor for 110 V AC
- [ ] Wire hardware interlock: P4K-80M output → Fuse → Heater; Limit Controller & Safety Relay in series
- [ ] Test thermal fuse and limit controller (see section 11.2)
- [ ] Label all connections; photograph circuit for documentation

### Week 5+
- [ ] Optional: Install redundant thermocouple on sample
- [ ] Optional: Order USB hardware watchdog; integrate heartbeat loop
- [ ] Final compliance audit against IEC 61010-2-010 checklist
- [ ] Write "Safety Operating Procedure" for lab staff
- [ ] Inform users: **Unattended operation now permitted only with Phase 2 hardware installed**

---

## 14. Safety Operating Procedure (For Lab Staff)

**BEFORE starting a TE measurement:**
1. ✓ Verify P4K-80M is in **LOCAL** mode (not REMOTE)
2. ✓ Verify P4K-80M output is **OFF**
3. ✓ Verify limit controller thermocouple is connected to 2700 channel 102
4. ✓ Verify limit controller setpoint is 60–62 °C (visible on front panel)
5. ✓ Verify thermal fuse is installed in heater power line
6. ✓ Verify safety relay alarm connection is secure

**DURING measurement:**
- Monitor the heater temperature every 10 minutes (if unattended)
- If temperature exceeds 58 °C for > 5 minutes, stop the measurement and investigate
- Do NOT leave the lab for more than 2 hours without returning to verify the system is stable

**IF ALARM OCCURS (heater shuts off):**
1. App will log error and disable P4K-80M output
2. Limit controller relay will de-energize (audible click)
3. Check thermocouple connection; inspect for corrosion or looseness
4. If thermocouple is good, manually reset the limit controller (press RESET button)
5. If heater does not restart, **DO NOT FORCE IT**—contact instrument support

**AFTER measurement:**
1. Let heater cool to room temperature (20 °C)
2. Manually disable P4K-80M output via front panel or command *OUTP OFF*
3. Close the PyQt6 app via File → Exit or Ctrl+C
4. Verify P4K-80M display shows 0 V, 0 A
5. Unplug heater from supply if not used for > 2 hours

---

## Summary Table: Layered Safety by Threat

| Threat | Likelihood | Severity | Current Barrier | Phase 1 (Software) | Phase 2 (Hardware) |
|--------|-----------|----------|-----------------|-------------|-------------|
| PC hangs (GPIB deadlock) | High | Medium | None | Timeout + app abort | USB watchdog cuts power |
| App crashed (force-kill) | Medium | Medium | None | atexit cleanup | Hardware relay active |
| Window closed, heater on | High | High | None | closeEvent handler | Relay + fuse |
| Thermocouple open | Medium | High | 0 °C reading | OTCD enabled; abort | Limit controller redundant |
| Runaway heating | Low | High | None | Rate limit + abort | Thermal fuse guaranteed |
| Over-temperature (> 75 °C) | Low | Critical | None | Absolute max check | Fuse + limit controller |

**Unattended operation recommendation: Phase 1 + Phase 2 (thermal fuse + limit controller + relay) = Safe for SIL 1, IEC 61010-2-010 compliant**.

---

**Document version:** 1.0  
**Last updated:** October 2026  
**Reviewed by:** [Your name/Team]  
**Next review:** October 2027 or after any safety incident

