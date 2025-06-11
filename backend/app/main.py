from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from .routers import instrument
from .routers import seebeck

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Seebeck Measurement System",
    description="Backend API for Keithley 2700 Seebeck measurement system",
    version="1.0.0"
)

# Configure CORS - More permissive for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming Request: {request.method} {request.url}")
    logger.info(f"Request Headers: {request.headers}")
    
    # For OPTIONS requests, the body is typically empty
    if request.method != "OPTIONS":
        try:
            body = await request.body()
            if body:
                logger.info(f"Request Body: {body.decode()}")
        except Exception as e:
            logger.error(f"Error reading body: {e}")
    else:
        logger.info("OPTIONS request (preflight) received.")

    response = await call_next(request)
    logger.info(f"Response Status: {response.status_code}")
    logger.info(f"Response Headers: {response.headers}")
    return response

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