from fastapi import APIRouter, HTTPException
from ..core.session_manager import MeasurementSessionManager
from pydantic import BaseModel
from typing import Dict, Optional

router = APIRouter()
session_manager = MeasurementSessionManager()

class MeasurementParams(BaseModel):
    interval: int
    pre_time: int
    start_volt: float
    stop_volt: float
    inc_rate: float
    dec_rate: float
    hold_time: int

class ResistivityParams(BaseModel):
    length: float  # meters
    width: float  # meters
    thickness: float  # meters
    voltage: Optional[float] = None  # volts (if None, uses current source)
    current: Optional[float] = None  # amperes (default 0.01A if voltage is None)

@router.post("/start")
def start_measurement(params: MeasurementParams):
    if session_manager.session_active:
        raise HTTPException(status_code=400, detail="Measurement session already running.")
    ok = session_manager.start_session(params.dict())
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to start measurement session.")
    return {"status": "started"}

@router.post("/stop")
def stop_measurement():
    if not session_manager.session_active:
        raise HTTPException(status_code=400, detail="No active measurement session.")
    session_manager.stop_session()
    return {"status": "stopped"}

@router.get("/status")
def get_status():
    return session_manager.get_status()

@router.get("/data")
def get_data():
    return {"data": session_manager.get_data()}

@router.post("/resistivity")
def measure_resistivity(params: ResistivityParams):
    """
    Measure electrical resistivity using Keithley 2401 SourceMeter.
    
    Requires sample dimensions (length, width, thickness) and either voltage or current.
    If voltage is provided, uses voltage source mode.
    If voltage is None, uses current source mode with specified current (default 0.01A).
    """
    try:
        result = session_manager.seebeck_system.measure_resistivity(
            length=params.length,
            width=params.width,
            thickness=params.thickness,
            voltage=params.voltage,
            current=params.current
        )
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to measure resistivity: {str(e)}") 