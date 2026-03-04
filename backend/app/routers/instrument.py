from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import List, Dict, Any
import json
import asyncio
import pyvisa
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

@router.get("/discover")
async def discover_instruments() -> Dict[str, Any]:
    """
    Discover all available instruments on the GPIB bus.
    Returns a list of all found instruments with their addresses and identification.
    """
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        
        instruments = []
        
        for resource_name in resources:
            instrument_info = {
                "address": resource_name,
                "manufacturer": "Unknown",
                "model": "Unknown",
                "type": "Unknown",
                "idn": "N/A",
                "status": "unknown"
            }
            
            try:
                inst = rm.open_resource(resource_name)
                inst.timeout = 2000  # 2 second timeout
                
                try:
                    idn = inst.query("*IDN?")
                    instrument_info["idn"] = idn.strip()
                    
                    parts = idn.strip().split(',')
                    if len(parts) >= 2:
                        instrument_info["manufacturer"] = parts[0].strip()
                        instrument_info["model"] = parts[1].strip()
                        
                        # Identify instrument type
                        model_upper = instrument_info["model"].upper()
                        idn_upper = idn.upper()
                        
                        if "2182" in model_upper or "2182" in idn_upper:
                            instrument_info["type"] = "Keithley 2182A (Nanovoltmeter)"
                        elif "2700" in model_upper or "2700" in idn_upper:
                            instrument_info["type"] = "Keithley 2700 (Multimeter/Scanner)"
                        elif "6221" in model_upper or "6221" in idn_upper:
                            instrument_info["type"] = "Keithley 6221 (SourceMeter)"
                        elif "PK160" in model_upper or "PK160" in idn_upper:
                            instrument_info["type"] = "PK160 (Power Supply)"
                        elif "KEITHLEY" in instrument_info["manufacturer"].upper():
                            instrument_info["type"] = f"Keithley {instrument_info['model']}"
                    
                    instrument_info["status"] = "connected"
                except Exception as e:
                    instrument_info["status"] = f"error: {str(e)}"
                
                inst.close()
            except Exception as e:
                instrument_info["status"] = f"error: {str(e)}"
            
            instruments.append(instrument_info)
        
        return {
            "success": True,
            "count": len(instruments),
            "instruments": instruments,
            "recommended_addresses": {
                "ADDR_2182A": next((inst["address"] for inst in instruments if "2182" in inst["model"].upper() or "2182" in inst["idn"].upper()), "GPIB0::7::INSTR"),
                "ADDR_2700": next((inst["address"] for inst in instruments if "2700" in inst["model"].upper() or "2700" in inst["idn"].upper()), "GPIB0::16::INSTR"),
                "ADDR_6221": next((inst["address"] for inst in instruments if "6221" in inst["model"].upper() or "6221" in inst["idn"].upper()), "GPIB0::18::INSTR"),
                "ADDR_PK160": next((inst["address"] for inst in instruments if "PK160" in inst["model"].upper() or "PK160" in inst["idn"].upper()), "GPIB0::15::INSTR")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover instruments: {str(e)}")

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