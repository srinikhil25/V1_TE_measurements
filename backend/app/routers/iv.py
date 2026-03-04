from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import time

from ..core.instrument import SeebeckSystem

router = APIRouter()


class IVParams(BaseModel):
    start_voltage: float
    stop_voltage: float
    points: int
    delay_ms: float = 50.0
    current_limit: float = 0.1
    voltage_limit: float = 21.0
    length: Optional[float] = None  # meters
    width: Optional[float] = None   # meters
    thickness: Optional[float] = None  # meters


class IVPointOut(BaseModel):
    voltage: Optional[float] = None
    current: Optional[float] = None
    resistance: Optional[float] = None
    resistivity: Optional[float] = None
    conductivity: Optional[float] = None


class IVResponse(BaseModel):
    data: List[IVPointOut]


@router.post("/run", response_model=IVResponse)
def run_iv(params: IVParams) -> IVResponse:
    """
    Run an I-V sweep using the Keithley 6221 SourceMeter.

    Returns a list of points with voltage (V), current (A), resistance (Ohm),
    and optional resistivity/conductivity if sample dimensions are provided.
    """
    system = SeebeckSystem()

    if params.points < 2:
        raise HTTPException(status_code=400, detail="points must be >= 2")

    # Compute the sweep voltages
    step = (params.stop_voltage - params.start_voltage) / (params.points - 1)
    voltages = [params.start_voltage + i * step for i in range(params.points)]

    # Connect instruments
    if not system.connect_all():
        raise HTTPException(status_code=500, detail="Failed to connect to instruments (including 6221).")

    results: List[IVPointOut] = []
    try:
        # Configure 6221 in voltage source mode with protection limits
        vmax = max(abs(params.start_voltage), abs(params.stop_voltage), abs(params.voltage_limit))
        system.k6221.configure_voltage_source(voltage_limit=vmax, current_limit=params.current_limit)
        system.k6221.output_on()

        for v in voltages:
            system.k6221.set_voltage(v)
            time.sleep(params.delay_ms / 1000.0)
            meas = system.k6221.read_measurement()
            if meas is None:
                results.append(IVPointOut(voltage=v))
                continue

            i = meas.get("current")
            mv = meas.get("voltage", v)  # measured voltage
            r = meas.get("resistance")

            resistivity = None
            conductivity = None
            if r is not None and params.length and params.width and params.thickness:
                area = params.width * params.thickness
                if area > 0 and params.length > 0:
                    resistivity = r * area / params.length
                    if resistivity != 0:
                        conductivity = 1.0 / resistivity

            results.append(
                IVPointOut(
                    voltage=mv,
                    current=i,
                    resistance=r,
                    resistivity=resistivity,
                    conductivity=conductivity,
                )
            )

        return IVResponse(data=results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IV sweep failed: {str(e)}")
    finally:
        try:
            system.k6221.output_off()
        finally:
            system.disconnect_all()

