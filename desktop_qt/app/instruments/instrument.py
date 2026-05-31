import pyvisa
import time
from typing import Optional, Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADDR_2182A = "GPIB0::7::INSTR"
ADDR_2700 = "GPIB0::16::INSTR"
ADDR_PK480M = "GPIB0::15::INSTR"   # Matsusada PK4-80M heater supply (was PK160)
ADDR_PK160 = ADDR_PK480M           # backward-compat alias
ADDR_6221 = "GPIB0::24::INSTR"  # Default address, will be updated after discovery

# Keithley 2700 thermocouple channels for the two Seebeck geometries.
# In-plane uses scanner-card positions 2 & 4; out-of-plane uses positions 3 & 5.
# Convention: T1 = hot channel, T2 = cold channel (ΔT = T2 − T1).
# If an out-of-plane run shows an inverted ΔT/S sign, swap the two OUTPLANE
# values below — that is the only change required.
CH_INPLANE_T1 = 102
CH_INPLANE_T2 = 104
CH_OUTPLANE_T1 = 103
CH_OUTPLANE_T2 = 105

# 2700 channel that monitors the PK4-80M heater-supply output voltage (DC volts,
# HI/LO across the supply output). Read alongside the thermocouples.
CH_HEATER_VOLT = 116

# ── Per-geometry heater limits (PK4-80M) ──────────────────────────────────────
# Current-controlled (constant-current) drive with a per-mode voltage compliance
# ceiling. The trapezoid is a CURRENT ramp; voltage = I × R_heater is the result
# (monitored on CH_HEATER_VOLT). Compliance = operating range + headroom.
#   In-plane : heater ≈10 Ω, ≤1.0 A, 0–10 V   → compliance 12 V
#   Out-plane: heater higher-R, ≤1.3 A, 0–50 V → compliance 50 V
HEATER_LIMITS = {
    "in_plane":  {"current_max_A": 1.0, "voltage_compliance_V": 12.0},
    "out_plane": {"current_max_A": 1.3, "voltage_compliance_V": 50.0},
}

class Keithley2182A:
    def __init__(self, resource_name: str = ADDR_2182A):
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False
    def connect(self, rm=None):
        # Disconnect first if already connected
        if self.connected and self.instrument:
            try:
                self.disconnect()
            except:
                pass
        
        try:
            if rm is None:
                rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.resource_name)
            self.instrument.timeout = 20000
            self.connected = True
            logger.info(f"Connected to Keithley 2182A at {self.resource_name}")
            print(f"Connected to Keithley 2182A at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to Keithley 2182A: {error_str}")
            print(f"Failed to connect to Keithley 2182A: {error_str}")
            
            # Provide helpful error messages
            if "VI_ERROR_ALLOC" in error_str or "-1073807300" in error_str:
                logger.error("VI_ERROR_ALLOC: Resource allocation failed. Possible causes:")
                logger.error("  1. Another process is using this instrument")
                logger.error("  2. Previous connections weren't closed properly")
                logger.error("  3. Try restarting the backend server or closing other applications")
            
            self.connected = False
            self.instrument = None
            return False
    def disconnect(self):
        if self.instrument:
            try:
                self.instrument.close()
            except Exception as e:
                logger.warning(f"Error closing 2182A connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected Keithley 2182A")
                print("Disconnected Keithley 2182A")
    def configure(self, nplc: float = 5.0):
        if not self.connected:
            return False
        self.instrument.write("*RST")
        self.instrument.write(":CONF:VOLT")
        self.instrument.write(":VOLT:DIGITS 8")
        self.instrument.write(f":VOLT:NPLC {max(0.01, min(10, nplc))}")
        logger.info("Configured Keithley 2182A")
        print("Configured Keithley 2182A")
        return True

    def set_nplc(self, nplc: float) -> bool:
        """Set voltage measurement integration (NPLC). Used for IV sweep."""
        if not self.connected:
            return False
        try:
            n = max(0.01, min(10, nplc))
            self.instrument.write(f":VOLT:NPLC {n}")
            return True
        except Exception as e:
            logger.error("2182A set_nplc: %s", e)
            return False

    def read_voltage(self) -> Optional[float]:
        try:
            if not self.connected:
                return None
            response = self.instrument.query(":READ?")
            value_str = response.split(',')[0].split('_')[0].strip()
            value = float(value_str)
            logger.info(f"2182A Voltage: {value}")
            print(f"2182A Voltage: {value}")
            return value
        except Exception as e:
            logger.error(f"Failed to read voltage from 2182A: {str(e)}")
            print(f"Failed to read voltage from 2182A: {str(e)}")
            return None

class PK480M:
    """Matsusada PK4-80M programmable DC supply (0–110 V), constant-current heater drive.

    Command protocol (Matsusada PK/RK family, device address #1):
        #1 REN              remote enable
        #1 VSET <volts>     output voltage setpoint — in CC mode acts as the
                            voltage COMPLIANCE ceiling (absolute volts)
        #1 ISET <amps>      output current setpoint (absolute AMPERES)
        #1 OCP  <percent>   over-current protection
        #1 SW1 / #1 SW0     output on / off
        #1 VMON / #1 IMON   read back actual output V / I (12-bit hex)

    ⚠ BENCH-VERIFY before a real run: confirm the front panel shows the commanded
      current when you send ``set_current_amps(0.5)`` (it should read ~0.5 A, not
      0.5 mA and not 500 A). The previous PK160 driver scaled current to mA; this
      driver sends AMPERES — the fail-safe direction (a wrong guess under-drives
      and simply fails to heat, rather than over-driving the supply).
    """

    def __init__(self, resource_name: str = ADDR_PK480M):
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False
    def connect(self, rm=None):
        # Disconnect first if already connected
        if self.connected and self.instrument:
            try:
                self.disconnect()
            except:
                pass
        
        try:
            if rm is None:
                rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.resource_name)
            self.instrument.timeout = 20000
            self.connected = True
            logger.info(f"Connected to PK4-80M at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to PK4-80M: {error_str}")
            if "VI_ERROR_ALLOC" in error_str or "-1073807300" in error_str:
                logger.error("VI_ERROR_ALLOC: Resource allocation failed. Check for other processes using this instrument.")
            self.connected = False
            self.instrument = None
            return False
    def disconnect(self):
        if self.instrument:
            try:
                self.instrument.close()
            except Exception as e:
                logger.warning(f"Error closing PK4-80M connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected PK4-80M")
    def initialize(self, voltage_compliance_V: float = 12.0, ocp_percent: float = 100.0):
        """Prepare the supply for a constant-current heater run.

        voltage_compliance_V : voltage ceiling (absolute volts) — set per geometry
                               (in-plane ~12 V, out-plane ~50 V).
        ocp_percent          : over-current protection, percent of rating.
        """
        if not self.connected:
            return False
        self.instrument.write("#1 REN")
        self.instrument.write(f"#1 VSET {voltage_compliance_V}")   # voltage compliance (volts)
        self.instrument.write(f"#1 OCP {ocp_percent}")
        self.instrument.write("#1 ISET 0")                         # start at zero current
        self.instrument.write("#1 SW1")                            # output on (0 A → no heating)
        logger.info("Initialized PK4-80M (V-compliance=%s V, OCP=%s%%)",
                    voltage_compliance_V, ocp_percent)
        return True
    def set_current_amps(self, amps: float):
        """Set the output current setpoint in AMPERES (ISET takes absolute amps)."""
        if not self.connected:
            return False
        self.instrument.write(f"#1 ISET {amps}")
        logger.info(f"PK4-80M set current: {amps} A")
        return True
    # Backward-compat: old callers used set_current(mA). Route to amps.
    def set_current(self, value: float):
        return self.set_current_amps(value)
    def output_off(self):
        if not self.connected:
            return False
        self.instrument.write("#1 SW0")
        logger.info("PK4-80M output off")
        return True


# Backward-compatibility alias — existing imports of ``PK160`` keep working.
PK160 = PK480M

class Keithley2700:
    def __init__(self, resource_name: str = ADDR_2700):
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False
        self.measurement_data = []
    def connect(self, rm=None):
        # Disconnect first if already connected
        if self.connected and self.instrument:
            try:
                self.disconnect()
            except:
                pass
        
        try:
            if rm is None:
                rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.resource_name)
            self.instrument.timeout = 20000
            self.connected = True
            logger.info(f"Connected to Keithley 2700 at {self.resource_name}")
            print(f"Connected to Keithley 2700 at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to Keithley 2700: {error_str}")
            print(f"Failed to connect to Keithley 2700: {error_str}")
            
            if "VI_ERROR_ALLOC" in error_str or "-1073807300" in error_str:
                logger.error("VI_ERROR_ALLOC: Resource allocation failed. Check for other processes using this instrument.")
            
            self.connected = False
            self.instrument = None
            return False
    def disconnect(self):
        if self.instrument:
            try:
                self.instrument.close()
            except Exception as e:
                logger.warning(f"Error closing 2700 connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected Keithley 2700")
                print("Disconnected Keithley 2700")
    def configure_measurement(self, channel: int = 101, nplc: float = 1.0):
        if not self.connected:
            return False
        self.instrument.write("*RST")
        time.sleep(0.1)
        self.instrument.write(f":ROUT:CLOS (@{channel})")
        self.instrument.write(":CONF:TEMP")
        self.instrument.write(":UNIT:TEMP C")
        self.instrument.write(":TEMP:TRAN TC")
        self.instrument.write(":TEMP:TC:TYPE K")
        self.instrument.write(":TEMP:TC:RJUN:RSEL EXT")
        self.instrument.write(f":TEMP:NPLC {nplc}")
        logger.info(f"Configured Keithley 2700 for channel {channel}")
        print(f"Configured Keithley 2700 for channel {channel}")
        return True
    def take_measurement(self, channel: int = 101) -> Optional[float]:
        try:
            if not self.connected:
                return None
            self.instrument.write(f":ROUT:CLOS (@{channel})")
            time.sleep(0.05)  # reduced from 0.1 s to improve V–T correspondence (staggered acquisition error)
            response = self.instrument.query(":READ?")
            value_str = response.split(',')[0].split('_')[0].strip()
            value = float(value_str)
            self.measurement_data.append({
                'timestamp': time.time(),
                'value': value,
                'channel': channel
            })
            logger.info(f"2700 Measurement on channel {channel}: {value}")
            print(f"2700 Measurement on channel {channel}: {value}")
            return value
        except Exception as e:
            logger.error(f"Failed to take measurement on 2700: {str(e)}")
            print(f"Failed to take measurement on 2700: {str(e)}")
            return None
    def read_dc_voltage(self, channel: int = CH_HEATER_VOLT) -> Optional[float]:
        """Read a DC-volts channel (e.g. ch116 heater-supply monitor).

        Assigns the DCV function to this channel only, then closes + reads it.
        The thermocouple channels keep their TEMP function (per-channel :FUNC),
        so this does not disturb the temperature reads. Fully guarded: any
        failure returns None and the measurement loop carries on.
        """
        try:
            if not self.connected:
                return None
            self.instrument.write(f":SENS:FUNC 'VOLT:DC',(@{channel})")
            self.instrument.write(f":ROUT:CLOS (@{channel})")
            time.sleep(0.05)
            response = self.instrument.query(":READ?")
            value = float(response.split(',')[0].split('_')[0].strip())
            return value
        except Exception as e:
            logger.error(f"Failed to read DC voltage on 2700 ch{channel}: {e}")
            return None

    def multi_channel_measurement(self, channels: List[int]) -> Dict[int, Optional[float]]:
        results = {}
        for ch in channels:
            results[ch] = self.take_measurement(channel=ch)
        logger.info(f"2700 Multi-channel measurement results: {results}")
        print(f"2700 Multi-channel measurement results: {results}")
        return results
    def get_measurements(self) -> List[Dict]:
        return self.measurement_data
    def clear_measurements(self):
        self.measurement_data = []
        logger.info("Cleared all stored measurements on 2700.")
        print("Cleared all stored measurements on 2700.")
    def get_status(self) -> Dict:
        try:
            if not self.connected:
                return {"connected": False}
            status = {
                "connected": True,
                "resource_name": self.resource_name,
                "measurement_count": len(self.measurement_data)
            }
            logger.info(f"2700 Instrument status: {status}")
            print(f"2700 Instrument status: {status}")
            return status
        except Exception as e:
            logger.error(f"Failed to get status on 2700: {str(e)}")
            print(f"Failed to get status on 2700: {str(e)}")
            return {"connected": False}

class Keithley6221:
    """Keithley 6221 SourceMeter for current-voltage measurements and resistivity calculations."""
    def __init__(self, resource_name: str = ADDR_6221):
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False

    def connect(self, rm=None):
        # Disconnect first if already connected
        if self.connected and self.instrument:
            try:
                self.disconnect()
            except:
                pass
        try:
            if rm is None:
                rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.resource_name)
            self.instrument.timeout = 20000
            self.connected = True
            logger.info(f"Connected to Keithley 6221 at {self.resource_name}")
            print(f"Connected to Keithley 6221 at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to Keithley 6221: {error_str}")
            print(f"Failed to connect to Keithley 6221: {error_str}")
            if "VI_ERROR_ALLOC" in error_str or "-1073807300" in error_str:
                logger.error("VI_ERROR_ALLOC: Resource allocation failed. Check for other processes using this instrument.")
            self.connected = False
            self.instrument = None
            return False

    def disconnect(self):
        if self.instrument:
            try:
                self.instrument.close()
            except Exception as e:
                logger.warning(f"Error closing 6221 connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected Keithley 6221")
                print("Disconnected Keithley 6221")

    def configure_voltage_source(self, voltage_limit: float = 1.0, current_limit: float = 0.1):
        """Configure 6221 as voltage source with limits."""
        if not self.connected:
            return False
        try:
            self.instrument.write("*RST")
            time.sleep(0.5)
            self.instrument.write(":SOUR:FUNC VOLT")
            self.instrument.write(":SOUR:VOLT:LEV 0")
            self.instrument.write(f":SOUR:VOLT:RANG {abs(voltage_limit)}")
            self.instrument.write(f":SENS:CURR:PROT {abs(current_limit)}")
            self.instrument.write(":SENS:FUNC 'CURR'")
            self.instrument.write(":SENS:CURR:RANG:AUTO ON")
            self.instrument.write(":FORM:ELEM CURR, VOLT")
            logger.info(f"Configured 6221: V_limit={voltage_limit}V, I_limit={current_limit}A")
            print(f"Configured 6221: V_limit={voltage_limit}V, I_limit={current_limit}A")
            return True
        except Exception as e:
            logger.error(f"Failed to configure 6221: {str(e)}")
            print(f"Failed to configure 6221: {str(e)}")
            return False

    def configure_current_source(self, current_limit: float = 0.01, voltage_limit: float = 1.0):
        """Configure 6221 as current source with limits."""
        if not self.connected:
            return False
        try:
            self.instrument.write("*RST")
            time.sleep(0.5)
            self.instrument.write(":SOUR:FUNC CURR")
            self.instrument.write(":SOUR:CURR:LEV 0")
            self.instrument.write(f":SOUR:CURR:RANG {abs(current_limit)}")
            self.instrument.write(f":SENS:VOLT:PROT {abs(voltage_limit)}")
            self.instrument.write(":SENS:FUNC 'VOLT'")
            self.instrument.write(":SENS:VOLT:RANG:AUTO ON")
            self.instrument.write(":FORM:ELEM VOLT, CURR")
            logger.info(f"Configured 6221: I_limit={current_limit}A, V_limit={voltage_limit}V")
            print(f"Configured 6221: I_limit={current_limit}A, V_limit={voltage_limit}V")
            return True
        except Exception as e:
            logger.error(f"Failed to configure 6221: {str(e)}")
            print(f"Failed to configure 6221: {str(e)}")
            return False

    def set_voltage(self, voltage: float):
        if not self.connected:
            return False
        try:
            self.instrument.write(f":SOUR:VOLT:LEV {voltage}")
            logger.info(f"6221 set voltage: {voltage}V")
            return True
        except Exception as e:
            logger.error(f"Failed to set voltage on 6221: {str(e)}")
            return False

    def set_current(self, current: float):
        if not self.connected:
            return False
        try:
            self.instrument.write(f":SOUR:CURR:LEV {current}")
            logger.info(f"6221 set current: {current}A")
            return True
        except Exception as e:
            logger.error(f"Failed to set current on 6221: {str(e)}")
            return False

    def output_on(self):
        if not self.connected:
            return False
        try:
            self.instrument.write(":OUTP ON")
            logger.info("6221 output ON")
            return True
        except Exception as e:
            logger.error(f"Failed to turn on 6221 output: {str(e)}")
            return False

    def output_off(self):
        if not self.connected:
            return False
        try:
            self.instrument.write(":OUTP OFF")
            logger.info("6221 output OFF")
            return True
        except Exception as e:
            logger.error(f"Failed to turn off 6221 output: {str(e)}")
            return False

    def read_measurement(self) -> Optional[Dict[str, float]]:
        if not self.connected:
            return None
        try:
            self.instrument.write(":INIT")
            time.sleep(0.1)
            response = self.instrument.query(":FETCH?")
            values = response.strip().split(',')
            if len(values) >= 2:
                try:
                    val1 = float(values[0])
                    val2 = float(values[1])
                    # Heuristic: larger magnitude likely voltage
                    if abs(val1) > abs(val2) or abs(val1) < 0.001:
                        voltage = val1
                        current = val2
                    else:
                        current = val1
                        voltage = val2
                    resistance = voltage / current if abs(current) > 1e-12 else None
                    return {
                        "voltage": voltage,
                        "current": current,
                        "resistance": resistance,
                    }
                except ValueError:
                    logger.error(f"Failed to parse 6221 response: {response}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to read measurement from 6221: {str(e)}")
            print(f"Failed to read measurement from 6221: {str(e)}")
            return None

    def get_status(self) -> Dict:
        try:
            if not self.connected:
                return {"connected": False}
            return {
                "connected": True,
                "resource_name": self.resource_name
            }
        except Exception as e:
            logger.error(f"Failed to get status on 6221: {str(e)}")
            return {"connected": False}

class SeebeckSystem:
    def __init__(self):
        # The VISA ResourceManager is created fresh on every connect_all() and
        # closed on every disconnect_all(). Reusing a single long-lived RM does
        # not fully release the GPIB resources between runs — recreating it is
        # the in-process equivalent of restarting the application.
        self.rm = None
        self.k2182a = Keithley2182A()
        self.k2700 = Keithley2700()
        self.pk = PK480M()
        self.pk160 = self.pk          # backward-compat alias
        self.k6221 = Keithley6221()
        self.connected = False
        self.pk160_current_unit = "mA"  # UI/params unit (mA or A); converted to amps before ISET

        # Per-geometry heater limits, set by the session manager before a run.
        self.heater_voltage_compliance_V = HEATER_LIMITS["in_plane"]["voltage_compliance_V"]
        self.heater_current_max_A = HEATER_LIMITS["in_plane"]["current_max_A"]
        self.probe_mode = "in_plane"
    def connect_all(self):
        """Connect to all instruments. Returns True only if all connections succeed."""
        # Always start from a fresh ResourceManager so no stale VISA state
        # from a previous run can lock the instruments.
        if self.rm is not None:
            try:
                self.rm.close()
            except Exception:
                pass
            self.rm = None
        try:
            self.rm = pyvisa.ResourceManager()
        except Exception as e:
            logger.error(f"Failed to create VISA ResourceManager: {e}")
            self.connected = False
            return False

        results = {
            'k2182a': self.k2182a.connect(self.rm),
            'k2700': self.k2700.connect(self.rm),
            'pk160': self.pk160.connect(self.rm),
            'k6221': self.k6221.connect(self.rm)
        }

        # Log connection status for each instrument
        for name, success in results.items():
            if not success:
                logger.error(f"Failed to connect to {name}")
            else:
                logger.info(f"Successfully connected to {name}")

        ok = all(results.values())
        self.connected = ok

        if not ok:
            # Release the instruments that DID connect, otherwise they stay
            # locked to this process and the next attempt fails.
            logger.error(f"Connection results: {results}. Not all instruments "
                         f"connected; releasing partial connections.")
            self.disconnect_all()

        return ok
    def disconnect_all(self):
        self.k2182a.disconnect()
        self.k2700.disconnect()
        self.pk160.disconnect()
        self.k6221.disconnect()
        self.connected = False
        # Fully release the VISA layer — closing only the instrument sessions
        # is not enough to free the GPIB resources for the next run.
        if self.rm is not None:
            try:
                self.rm.close()
            except Exception as e:
                logger.warning(f"Error closing VISA ResourceManager: {e}")
            self.rm = None
    def set_heater_mode(self, probe_mode: str):
        """Apply per-geometry heater limits (and route the relay) before a run.

        Sets the voltage-compliance ceiling and current cap for the selected
        geometry, and actuates the in-plane/out-plane relay. Call this BEFORE
        initialize_all() so the compliance is applied at output-on.
        """
        mode = "out_plane" if str(probe_mode).lower() == "out_plane" else "in_plane"
        limits = HEATER_LIMITS[mode]
        self.probe_mode = mode
        self.heater_voltage_compliance_V = limits["voltage_compliance_V"]
        self.heater_current_max_A = limits["current_max_A"]
        self.set_relay(mode)

    def set_relay(self, probe_mode: str):
        """Route the heater relay to the in-plane or out-plane setup.

        ⚠ STUB — the relay is not wired yet. Today the operator connects the
        correct setup manually. When the relay control path exists (2700 digital
        I/O, a serial relay board, etc.), issue the select command here. The rest
        of the system already calls this at the right point in the start sequence.
        """
        logger.info("Heater relay select: %s (relay not yet wired — manual setup)",
                    probe_mode)

    def initialize_all(self):
        self.k2182a.configure()
        self.k2700.configure_measurement()
        # Apply the per-geometry voltage compliance at output-on.
        self.pk.initialize(voltage_compliance_V=self.heater_voltage_compliance_V)
    def set_current(self, value: float):
        # value is the setpoint in the UI unit (mA or A); convert to AMPERES.
        # PK4-80M ISET takes absolute amps (e.g. 1.0 = 1 A). The current cap is
        # also enforced in the UI per geometry.
        unit = getattr(self, "pk160_current_unit", "mA")
        amps = (value / 1000.0) if unit == "mA" else value
        # Safety clamp to the per-mode current ceiling.
        cap = getattr(self, "heater_current_max_A", None)
        if cap is not None and amps > cap:
            amps = cap
        self.pk.set_current_amps(amps)
    def output_off(self):
        self.pk.output_off()
    def measure_all(self, temp1_channel=102, temp2_channel=104) -> Dict[str, Optional[float]]:
        # Acquisition order: V then T1 then T2 (staggered). For best accuracy, V and T
        # should be simultaneous; staggered acquisition can introduce several-% error in S.
        temf = self.k2182a.read_voltage()
        temp1 = self.k2700.take_measurement(channel=temp1_channel)
        temp2 = self.k2700.take_measurement(channel=temp2_channel)
        heater_v = self.k2700.read_dc_voltage(channel=CH_HEATER_VOLT)
        return {
            "TEMF_mV": temf * 1000 if temf is not None else None,
            "Temp1_C": temp1,
            "Temp2_C": temp2,
            "HeaterV_V": heater_v,
        }
    
    # -------------------------------------------------------------------------
    # I-V measurement: 4-probe (6221 current source + 2182A voltmeter)
    # -------------------------------------------------------------------------

    def prepare_iv_4probe(
        self,
        voltage_limit: float = 1.0,
        current_limit: float = 0.1,
        nplc: float = 5.0,
    ) -> bool:
        """Configure 6221 as current source and 2182A for voltage. Call before measure_iv_point_4probe."""
        if not self.k6221.connected or not self.k2182a.connected:
            return False
        self.k2182a.configure(nplc=nplc)
        ok = self.k6221.configure_current_source(
            current_limit=abs(current_limit),
            voltage_limit=abs(voltage_limit),
        )
        if ok:
            self.k6221.output_on()
        return ok

    def measure_iv_point_4probe(
        self, current_A: float, delay_s: float
    ) -> Optional[Dict[str, float]]:
        """Set current on 6221, wait delay_s, read voltage from 2182A. Returns {current, voltage, resistance}."""
        if not self.k6221.set_current(current_A):
            return None
        time.sleep(delay_s)
        v = self.k2182a.read_voltage()
        if v is None:
            return None
        r = v / current_A if abs(current_A) > 1e-12 else None
        return {
            "current": current_A,
            "voltage": v,
            "resistance": r,
        }

    def get_temperature_avg_c(self, ch1: int = 102, ch2: int = 104) -> Optional[float]:
        """Read 2700 channels ch1 and ch2, return average temperature in °C (for IV metadata)."""
        if not self.k2700.connected:
            return None
        t1 = self.k2700.take_measurement(channel=ch1)
        t2 = self.k2700.take_measurement(channel=ch2)
        if t1 is None and t2 is None:
            return None
        if t1 is None:
            return t2
        if t2 is None:
            return t1
        return (t1 + t2) / 2.0

    def measure_resistivity(self, length: float, width: float, thickness: float, 
                           voltage: Optional[float] = None, current: Optional[float] = None) -> Dict[str, Optional[float]]:
        """
        Measure electrical resistivity using 6221 SourceMeter.
        
        Parameters:
            length: Sample length in meters
            width: Sample width in meters  
            thickness: Sample thickness in meters
            voltage: Applied voltage (V). If None, uses current source mode.
            current: Applied current (A). If None and voltage is None, uses default 0.01A.
        
        Returns:
            Dictionary with voltage, current, resistance, resistivity, and conductivity
        """
        if not self.k6221.connected:
            logger.error("Keithley 6221 not connected")
            return {
                "voltage": None,
                "current": None,
                "resistance": None,
                "resistivity": None,
                "conductivity": None,
                "error": "Keithley 6221 not connected"
            }
        
        try:
            # Configure based on input
            if voltage is not None:
                # Voltage source mode
                self.k6221.configure_voltage_source(voltage_limit=abs(voltage) * 1.2, current_limit=0.1)
                self.k6221.set_voltage(voltage)
            else:
                # Current source mode
                applied_current = current if current is not None else 0.01
                self.k6221.configure_current_source(current_limit=abs(applied_current) * 1.2, voltage_limit=1.0)
                self.k6221.set_current(applied_current)
            
            # Turn on output
            self.k6221.output_on()
            time.sleep(0.5)  # Wait for stabilization
            
            # Read measurement
            measurement = self.k6221.read_measurement()
            
            # Turn off output
            self.k6221.output_off()
            
            if measurement is None:
                return {
                    "voltage": None,
                    "current": None,
                    "resistance": None,
                    "resistivity": None,
                    "conductivity": None,
                    "error": "Failed to read measurement"
                }
            
            v = measurement.get("voltage")
            i = measurement.get("current")
            r = measurement.get("resistance")
            
            # Calculate resistivity: ρ = R * A / L
            # where A = width * thickness (cross-sectional area)
            # and L = length
            resistivity = None
            conductivity = None
            
            if r is not None and r > 0:
                cross_sectional_area = width * thickness  # m²
                if cross_sectional_area > 0 and length > 0:
                    resistivity = r * cross_sectional_area / length  # Ω·m
                    if resistivity > 0:
                        conductivity = 1.0 / resistivity  # S/m
            
            return {
                "voltage": v,
                "current": i,
                "resistance": r,
                "resistivity": resistivity,  # Ω·m
                "conductivity": conductivity,  # S/m
                "length": length,  # m
                "width": width,  # m
                "thickness": thickness,  # m
                "cross_sectional_area": width * thickness  # m²
            }
            
        except Exception as e:
            logger.error(f"Failed to measure resistivity: {str(e)}")
            self.k6221.output_off()
            return {
                "voltage": None,
                "current": None,
                "resistance": None,
                "resistivity": None,
                "conductivity": None,
                "error": str(e)
            } 