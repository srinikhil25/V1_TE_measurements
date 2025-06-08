from fastapi import APIRouter, HTTPException
from ..core.session_manager import MeasurementSessionManager
from pydantic import BaseModel
from typing import Dict

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