from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MeasurementData(BaseModel):
    timestamp: float
    value: float

class MeasurementConfig(BaseModel):
    channel: int = 101
    nplc: float = 1.0
    auto_zero: bool = True

class MeasurementResponse(BaseModel):
    success: bool
    value: Optional[float] = None
    error: Optional[str] = None

class MeasurementHistory(BaseModel):
    measurements: List[MeasurementData]

class InstrumentStatus(BaseModel):
    connected: bool
    resource_name: Optional[str] = None
    measurement_count: Optional[int] = None
    error: Optional[str] = None 