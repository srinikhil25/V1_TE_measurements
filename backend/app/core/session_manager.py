import threading
import time
import logging
from typing import Optional, Dict, List
from .instrument import SeebeckSystem

logger = logging.getLogger(__name__)

class MeasurementSessionManager:
    def __init__(self):
        self.session_active = False
        self.session_thread = None
        self.session_data = []
        self.session_status = "idle"
        self.session_params = None
        self.session_start_time = None
        self.seebeck_system = SeebeckSystem()
        self.lock = threading.Lock()

    def start_session(self, params: Dict):
        if self.session_active:
            return False  # Already running
        self.session_active = True
        self.session_data = []
        self.session_status = "running"
        self.session_params = params
        self.session_start_time = time.time()
        self.session_thread = threading.Thread(target=self._run_session, args=(params,))
        self.session_thread.start()
        return True

    def stop_session(self):
        self.session_active = False
        self.session_status = "stopped"
        if self.session_thread:
            self.session_thread.join(timeout=2)
        self.seebeck_system.output_off()
        self.seebeck_system.disconnect_all()

    def get_data(self) -> List[Dict]:
        with self.lock:
            return list(self.session_data)

    def get_status(self) -> Dict:
        return {
            "active": self.session_active,
            "status": self.session_status,
            "params": self.session_params,
            "start_time": self.session_start_time,
            "data_count": len(self.session_data)
        }

    def _run_session(self, params: Dict):
        try:
            # Connect to all instruments
            if not self.seebeck_system.connect_all():
                self.session_status = "error: Failed to connect to one or more instruments. Please check instrument connections and try again."
                self.session_active = False
                logger.error("Failed to connect to instruments. Session aborted.")
                return
            
            # Initialize all instruments
            try:
                self.seebeck_system.initialize_all()
            except Exception as e:
                self.session_status = f"error: Failed to initialize instruments: {str(e)}"
                self.session_active = False
                logger.error(f"Failed to initialize instruments: {str(e)}")
                self.seebeck_system.disconnect_all()
                return
            interval = params["interval"]
            pre_time = params["pre_time"]
            start_volt = params["start_volt"]
            stop_volt = params["stop_volt"]
            inc_rate = params["inc_rate"]
            dec_rate = params["dec_rate"]
            hold_time = params["hold_time"]

            kaisuu1 = int(pre_time // interval) if pre_time % interval == 0 else int(pre_time // interval + 1)
            kaisuu2 = int(((stop_volt - start_volt) / inc_rate) // interval) if ((stop_volt - start_volt) / inc_rate) % interval == 0 else int(((stop_volt - start_volt) / inc_rate) // interval + 1)
            kaisuu3 = int(hold_time // interval) if hold_time % interval == 0 else int(hold_time // interval + 1)
            kaisuu4 = int(((stop_volt - start_volt) / dec_rate) // interval) if ((stop_volt - start_volt) / dec_rate) % interval == 0 else int(((stop_volt - start_volt) / dec_rate) // interval + 1)
            while stop_volt - inc_rate * kaisuu2 * interval < 0:
                kaisuu2 -= 1
            while stop_volt - dec_rate * kaisuu4 * interval < 0:
                kaisuu4 -= 1

            volt = start_volt
            kaisuu = 1
            start_time = time.time()

            while self.session_active:
                loop_start = time.time()
                elapsed_time = int(time.time() - start_time)
                # Voltage logic
                if 1 <= kaisuu <= kaisuu1:
                    volt = start_volt
                elif kaisuu1 + 1 <= kaisuu <= kaisuu1 + kaisuu2:
                    volt += inc_rate * interval
                elif kaisuu1 + kaisuu2 + 1 <= kaisuu <= kaisuu1 + kaisuu2 + kaisuu3:
                    volt = stop_volt
                elif kaisuu1 + kaisuu2 + kaisuu3 + 1 <= kaisuu <= kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4:
                    volt -= dec_rate * interval
                else:
                    volt = start_volt

                self.seebeck_system.set_current(volt)
                result = self.seebeck_system.measure_all()
                row = {
                    "Time [s]": elapsed_time,
                    "TEMF [mV]": result["TEMF_mV"],
                    "Temp1 [oC]": result["Temp1_C"],
                    "Temp2 [oC]": result["Temp2_C"],
                    "Delta Temp [oC]": (result["Temp1_C"] if result["Temp1_C"] is not None else 0) - (result["Temp2_C"] if result["Temp2_C"] is not None else 0)
                }
                with self.lock:
                    self.session_data.append(row)
                kaisuu += 1
                if kaisuu > (kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4):
                    break
                elapsed = time.time() - loop_start
                remaining = max(0, interval - elapsed)
                for _ in range(int(remaining * 10)):
                    if not self.session_active:
                        break
                    time.sleep(0.1)
            self.seebeck_system.output_off()
            self.seebeck_system.disconnect_all()
            self.session_status = "finished"
            self.session_active = False
        except Exception as e:
            self.session_status = f"error: {str(e)}"
            self.session_active = False 