import pyvisa
import time
from typing import Optional, Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADDR_2182A = "GPIB0::7::INSTR"
ADDR_2700 = "GPIB0::16::INSTR"
ADDR_PK160 = "GPIB0::15::INSTR"
ADDR_2401 = "GPIB0::24::INSTR"  # Default address, will be updated after discovery

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
    def configure(self):
        if not self.connected:
            return False
        self.instrument.write("*RST")
        self.instrument.write(":CONF:VOLT")
        self.instrument.write(":VOLT:DIGITS 8")
        self.instrument.write(":VOLT:NPLC 5")
        logger.info("Configured Keithley 2182A")
        print("Configured Keithley 2182A")
        return True
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

class PK160:
    def __init__(self, resource_name: str = ADDR_PK160):
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
            logger.info(f"Connected to PK160 at {self.resource_name}")
            print(f"Connected to PK160 at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to PK160: {error_str}")
            print(f"Failed to connect to PK160: {error_str}")
            
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
                logger.warning(f"Error closing PK160 connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected PK160")
                print("Disconnected PK160")
    def initialize(self):
        if not self.connected:
            return False
        self.instrument.write("#1 REN")
        self.instrument.write("#1 VCN 100")
        self.instrument.write("#1 OCP 100")
        self.instrument.write("#1 SW1")
        logger.info("Initialized PK160")
        print("Initialized PK160")
        return True
    def set_current(self, value: float):
        """Set current setpoint. Value in mA sent to ISET (current setpoint, not voltage)."""
        if not self.connected:
            return False
        self.instrument.write(f"#1 ISET {value}")
        logger.info(f"PK160 set current: {value}")
        print(f"PK160 set current: {value}")
        return True
    def output_off(self):
        if not self.connected:
            return False
        self.instrument.write("#1 SW0")
        logger.info("PK160 output off")
        print("PK160 output off")
        return True

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

class Keithley2401:
    """Keithley 2401 SourceMeter for current-voltage measurements and resistivity calculations."""
    def __init__(self, resource_name: str = ADDR_2401):
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
            logger.info(f"Connected to Keithley 2401 at {self.resource_name}")
            print(f"Connected to Keithley 2401 at {self.resource_name}")
            return True
        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to connect to Keithley 2401: {error_str}")
            print(f"Failed to connect to Keithley 2401: {error_str}")
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
                logger.warning(f"Error closing 2401 connection: {str(e)}")
            finally:
                self.instrument = None
                self.connected = False
                logger.info("Disconnected Keithley 2401")
                print("Disconnected Keithley 2401")

    def configure_voltage_source(self, voltage_limit: float = 1.0, current_limit: float = 0.1):
        """Configure 2401 as voltage source with limits."""
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
            logger.info(f"Configured 2401: V_limit={voltage_limit}V, I_limit={current_limit}A")
            print(f"Configured 2401: V_limit={voltage_limit}V, I_limit={current_limit}A")
            return True
        except Exception as e:
            logger.error(f"Failed to configure 2401: {str(e)}")
            print(f"Failed to configure 2401: {str(e)}")
            return False

    def configure_current_source(self, current_limit: float = 0.01, voltage_limit: float = 1.0):
        """Configure 2401 as current source with limits."""
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
            logger.info(f"Configured 2401: I_limit={current_limit}A, V_limit={voltage_limit}V")
            print(f"Configured 2401: I_limit={current_limit}A, V_limit={voltage_limit}V")
            return True
        except Exception as e:
            logger.error(f"Failed to configure 2401: {str(e)}")
            print(f"Failed to configure 2401: {str(e)}")
            return False

    def set_voltage(self, voltage: float):
        if not self.connected:
            return False
        try:
            self.instrument.write(f":SOUR:VOLT:LEV {voltage}")
            logger.info(f"2401 set voltage: {voltage}V")
            return True
        except Exception as e:
            logger.error(f"Failed to set voltage on 2401: {str(e)}")
            return False

    def set_current(self, current: float):
        if not self.connected:
            return False
        try:
            self.instrument.write(f":SOUR:CURR:LEV {current}")
            logger.info(f"2401 set current: {current}A")
            return True
        except Exception as e:
            logger.error(f"Failed to set current on 2401: {str(e)}")
            return False

    def output_on(self):
        if not self.connected:
            return False
        try:
            self.instrument.write(":OUTP ON")
            logger.info("2401 output ON")
            return True
        except Exception as e:
            logger.error(f"Failed to turn on 2401 output: {str(e)}")
            return False

    def output_off(self):
        if not self.connected:
            return False
        try:
            self.instrument.write(":OUTP OFF")
            logger.info("2401 output OFF")
            return True
        except Exception as e:
            logger.error(f"Failed to turn off 2401 output: {str(e)}")
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
                    logger.error(f"Failed to parse 2401 response: {response}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to read measurement from 2401: {str(e)}")
            print(f"Failed to read measurement from 2401: {str(e)}")
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
            logger.error(f"Failed to get status on 2401: {str(e)}")
            return {"connected": False}

class SeebeckSystem:
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.k2182a = Keithley2182A()
        self.k2700 = Keithley2700()
        self.pk160 = PK160()
        self.k2401 = Keithley2401()
        self.connected = False
        self.pk160_current_unit = "mA"  # UI and params in mA; if "A", we convert when sending to PK160
    def connect_all(self):
        """Connect to all instruments. Returns True only if all connections succeed."""
        results = {
            'k2182a': self.k2182a.connect(self.rm),
            'k2700': self.k2700.connect(self.rm),
            'pk160': self.pk160.connect(self.rm),
            'k2401': self.k2401.connect(self.rm)
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
            logger.error(f"Connection results: {results}. Not all instruments connected successfully.")
        
        return ok
    def disconnect_all(self):
        self.k2182a.disconnect()
        self.k2700.disconnect()
        self.pk160.disconnect()
        self.k2401.disconnect()
        self.connected = False
    def initialize_all(self):
        self.k2182a.configure()
        self.k2700.configure_measurement()
        self.pk160.initialize()
    def set_current(self, value: float):
        # value is current in mA or A per pk160_current_unit. PK160 ISET expects current in mA (sending 200 = 200 mA).
        # If we sent Amps (0.2) the supply would set 0.2 mA and temperature would not rise.
        unit = getattr(self, "pk160_current_unit", "mA")
        send_value_mA = (value * 1000.0) if unit == "A" else value
        self.pk160.set_current(send_value_mA)
    def output_off(self):
        self.pk160.output_off()
    def measure_all(self, temp1_channel=102, temp2_channel=104) -> Dict[str, Optional[float]]:
        # Acquisition order: V then T1 then T2 (staggered). For best accuracy, V and T
        # should be simultaneous; staggered acquisition can introduce several-% error in S.
        temf = self.k2182a.read_voltage()
        temp1 = self.k2700.take_measurement(channel=temp1_channel)
        temp2 = self.k2700.take_measurement(channel=temp2_channel)
        return {
            "TEMF_mV": temf * 1000 if temf is not None else None,
            "Temp1_C": temp1,
            "Temp2_C": temp2
        }
    
    def measure_resistivity(self, length: float, width: float, thickness: float, 
                           voltage: Optional[float] = None, current: Optional[float] = None) -> Dict[str, Optional[float]]:
        """
        Measure electrical resistivity using 2401 SourceMeter.
        
        Parameters:
            length: Sample length in meters
            width: Sample width in meters  
            thickness: Sample thickness in meters
            voltage: Applied voltage (V). If None, uses current source mode.
            current: Applied current (A). If None and voltage is None, uses default 0.01A.
        
        Returns:
            Dictionary with voltage, current, resistance, resistivity, and conductivity
        """
        if not self.k2401.connected:
            logger.error("Keithley 2401 not connected")
            return {
                "voltage": None,
                "current": None,
                "resistance": None,
                "resistivity": None,
                "conductivity": None,
                "error": "Keithley 2401 not connected"
            }
        
        try:
            # Configure based on input
            if voltage is not None:
                # Voltage source mode
                self.k2401.configure_voltage_source(voltage_limit=abs(voltage) * 1.2, current_limit=0.1)
                self.k2401.set_voltage(voltage)
            else:
                # Current source mode
                applied_current = current if current is not None else 0.01
                self.k2401.configure_current_source(current_limit=abs(applied_current) * 1.2, voltage_limit=1.0)
                self.k2401.set_current(applied_current)
            
            # Turn on output
            self.k2401.output_on()
            time.sleep(0.5)  # Wait for stabilization
            
            # Read measurement
            measurement = self.k2401.read_measurement()
            
            # Turn off output
            self.k2401.output_off()
            
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
            self.k2401.output_off()
            return {
                "voltage": None,
                "current": None,
                "resistance": None,
                "resistivity": None,
                "conductivity": None,
                "error": str(e)
            } 