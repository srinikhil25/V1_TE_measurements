import pyvisa
import time
from typing import Optional, Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Keithley2700:
    def __init__(self, resource_name: str = "GPIB0::16::INSTR"):
        """Initialize connection to Keithley 2700."""
        self.resource_name = resource_name
        self.instrument = None
        self.connected = False
        self.measurement_data = []
        
    def connect(self) -> bool:
        """Establish connection to the instrument."""
        try:
            rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.resource_name)
            self.instrument.timeout = 20000  # 20 second timeout
            self.connected = True
            logger.info(f"Connected to instrument at {self.resource_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to instrument: {str(e)}")
            self.connected = False
            return False

    def disconnect(self):
        """Close connection to the instrument."""
        if self.instrument:
            self.instrument.close()
            self.connected = False
            logger.info("Disconnected from instrument")

    def configure_measurement(self, 
                            channel: int = 101, 
                            nplc: float = 1.0,
                            auto_zero: bool = True) -> bool:
        """Configure the instrument for measurement."""
        try:
            if not self.connected:
                return False
                
            # Reset instrument
            self.instrument.write("*RST")
            time.sleep(0.1)
            
            # Configure channel
            self.instrument.write(f":ROUT:CLOS (@{channel})")
            
            # Configure measurement settings
            self.instrument.write(":CONF:VOLT:DC")
            self.instrument.write(f":VOLT:DC:NPLC {nplc}")
            self.instrument.write(f":VOLT:DC:AZER {'ON' if auto_zero else 'OFF'}")
            
            logger.info(f"Configured measurement for channel {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to configure measurement: {str(e)}")
            return False

    def take_measurement(self) -> Optional[float]:
        """Take a single measurement."""
        try:
            if not self.connected:
                return None
                
            # Trigger and read measurement
            self.instrument.write(":INIT")
            time.sleep(0.1)
            value = float(self.instrument.query(":FETCH?"))
            
            # Store measurement
            self.measurement_data.append({
                'timestamp': time.time(),
                'value': value
            })
            
            return value
        except Exception as e:
            logger.error(f"Failed to take measurement: {str(e)}")
            return None

    def get_measurements(self) -> List[Dict]:
        """Get all stored measurements."""
        return self.measurement_data

    def clear_measurements(self):
        """Clear stored measurements."""
        self.measurement_data = []

    def get_status(self) -> Dict:
        """Get instrument status."""
        try:
            if not self.connected:
                return {"connected": False}
                
            return {
                "connected": True,
                "resource_name": self.resource_name,
                "measurement_count": len(self.measurement_data)
            }
        except Exception as e:
            logger.error(f"Failed to get status: {str(e)}")
            return {"connected": False} 