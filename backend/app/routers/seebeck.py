from fastapi import APIRouter, HTTPException
from ..core.session_manager import MeasurementSessionManager
from pydantic import BaseModel, field_validator, model_validator
from typing import Dict, Optional, Literal

router = APIRouter()
session_manager = MeasurementSessionManager()


class MeasurementParams(BaseModel):
    """Seebeck measurement session parameters. start_volt/stop_volt are current setpoints I₀ and I (in mA or A per pk160_current_unit), not voltage. inc_rate/dec_rate are current rate in mA/s or A/s. PK160 is driven by current (ISET), not voltage."""
    interval: int
    pre_time: int
    start_volt: float   # I₀: current setpoint (mA or A)
    stop_volt: float    # I: peak current setpoint (mA or A)
    inc_rate: float     # current ramp rate (mA/s or A/s)
    dec_rate: float     # current ramp rate (mA/s or A/s)
    hold_time: int
    # Optional metadata and realistic options
    sample_id: Optional[str] = None
    operator: Optional[str] = None
    notes: Optional[str] = None
    target_T0_K: Optional[float] = None
    probe_arrangement: Optional[Literal["2-probe", "4-probe"]] = None
    cooling_target_delta_t: Optional[float] = 5.0
    cooling_timeout_s: Optional[int] = 600
    stabilization_delay_s: Optional[float] = 0.0
    pk160_current_unit: Optional[Literal["mA", "A"]] = "mA"

    @field_validator("interval")
    @classmethod
    def interval_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("interval must be positive (seconds between measurements)")
        return v

    @field_validator("pre_time", "hold_time")
    @classmethod
    def non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be non-negative")
        return v

    @field_validator("inc_rate", "dec_rate")
    @classmethod
    def rate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("inc_rate and dec_rate must be positive")
        return v

    @model_validator(mode="after")
    def start_before_stop(self) -> "MeasurementParams":
        if self.start_volt > self.stop_volt:
            raise ValueError("start_volt must be <= stop_volt")
        return self


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
    ok = session_manager.start_session(params.model_dump())
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
    data = session_manager.get_data()
    analysis = session_manager.get_binned_analysis()
    metadata = session_manager.get_session_metadata()
    return {"data": data, "analysis": analysis, "metadata": metadata}

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