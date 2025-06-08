import pyvisa
import time
from typing import Optional, Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADDR_2182A = "GPIB0::7::INSTR"
ADDR_2700 = "GPIB0::16::INSTR"
ADDR_PK160 = "GPIB0::15::INSTR"

class Keithley2182A:
    def __init__(self, resource_name: str = ADDR_2182A):
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False
    def connect(self, rm=None):
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
            logger.error(f"Failed to connect to Keithley 2182A: {str(e)}")
            print(f"Failed to connect to Keithley 2182A: {str(e)}")
            self.connected = False
            return False
    def disconnect(self):
        if self.instrument:
            self.instrument.close()
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
            logger.error(f"Failed to connect to PK160: {str(e)}")
            print(f"Failed to connect to PK160: {str(e)}")
            self.connected = False
            return False
    def disconnect(self):
        if self.instrument:
            self.instrument.close()
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
        if not self.connected:
            return False
        self.instrument.write(f"#1 ISET{value}")
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
            logger.error(f"Failed to connect to Keithley 2700: {str(e)}")
            print(f"Failed to connect to Keithley 2700: {str(e)}")
            self.connected = False
            return False
    def disconnect(self):
        if self.instrument:
            self.instrument.close()
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
            time.sleep(0.1)
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

class SeebeckSystem:
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.k2182a = Keithley2182A()
        self.k2700 = Keithley2700()
        self.pk160 = PK160()
        self.connected = False
    def connect_all(self):
        ok = self.k2182a.connect(self.rm) and self.k2700.connect(self.rm) and self.pk160.connect(self.rm)
        self.connected = ok
        return ok
    def disconnect_all(self):
        self.k2182a.disconnect()
        self.k2700.disconnect()
        self.pk160.disconnect()
        self.connected = False
    def initialize_all(self):
        self.k2182a.configure()
        self.k2700.configure_measurement()
        self.pk160.initialize()
    def set_current(self, value: float):
        self.pk160.set_current(value)
    def output_off(self):
        self.pk160.output_off()
    def measure_all(self, temp1_channel=102, temp2_channel=104) -> Dict[str, Optional[float]]:
        # Measure voltage (TEMF)
        temf = self.k2182a.read_voltage()
        # Measure temperatures
        temp1 = self.k2700.take_measurement(channel=temp1_channel)
        temp2 = self.k2700.take_measurement(channel=temp2_channel)
        return {
            "TEMF_mV": temf * 1000 if temf is not None else None,
            "Temp1_C": temp1,
            "Temp2_C": temp2
        } 