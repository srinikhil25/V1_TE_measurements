from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import List
import json
import asyncio
from ..core.instrument import Keithley2700
from ..models.measurement import (
    MeasurementConfig,
    MeasurementResponse,
    MeasurementHistory,
    InstrumentStatus
)

router = APIRouter()
instrument = Keithley2700()
connected_clients: List[WebSocket] = []

async def broadcast_measurement(measurement: dict):
    """Broadcast measurement to all connected WebSocket clients."""
    for client in connected_clients:
        try:
            await client.send_json(measurement)
        except:
            connected_clients.remove(client)

@router.post("/connect", response_model=InstrumentStatus)
async def connect_instrument():
    """Connect to the Keithley 2700 instrument."""
    success = instrument.connect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect to instrument")
    return instrument.get_status()

@router.post("/disconnect")
async def disconnect_instrument():
    """Disconnect from the instrument."""
    instrument.disconnect()
    return {"message": "Disconnected from instrument"}

@router.post("/configure", response_model=MeasurementResponse)
async def configure_measurement(config: MeasurementConfig):
    """Configure the instrument for measurement."""
    success = instrument.configure_measurement(
        channel=config.channel,
        nplc=config.nplc,
        auto_zero=config.auto_zero
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to configure instrument")
    return MeasurementResponse(success=True)

@router.post("/measure", response_model=MeasurementResponse)
async def take_measurement():
    """Take a single measurement."""
    value = instrument.take_measurement()
    if value is None:
        raise HTTPException(status_code=500, detail="Failed to take measurement")
    
    measurement = {
        "timestamp": instrument.measurement_data[-1]["timestamp"],
        "value": value
    }
    await broadcast_measurement(measurement)
    
    return MeasurementResponse(success=True, value=value)

@router.get("/measurements", response_model=MeasurementHistory)
async def get_measurements():
    """Get all stored measurements."""
    return MeasurementHistory(measurements=instrument.get_measurements())

@router.delete("/measurements")
async def clear_measurements():
    """Clear all stored measurements."""
    instrument.clear_measurements()
    return {"message": "Measurements cleared"}

@router.get("/status", response_model=InstrumentStatus)
async def get_status():
    """Get instrument status."""
    return instrument.get_status()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time measurements."""
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            # You can add command handling here if needed
    except WebSocketDisconnect:
        connected_clients.remove(websocket) 