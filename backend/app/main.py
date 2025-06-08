from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import instrument
from .routers import seebeck

app = FastAPI(
    title="Seebeck Measurement System",
    description="Backend API for Keithley 2700 Seebeck measurement system",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    instrument.router,
    prefix="/api/instrument",
    tags=["instrument"]
)
app.include_router(
    seebeck.router,
    prefix="/api/seebeck",
    tags=["seebeck"]
)

@app.get("/")
async def root():
    """Root endpoint returning API information."""
    return {
        "message": "Seebeck Measurement System API",
        "version": "1.0.0",
        "documentation": "/docs"
    } 