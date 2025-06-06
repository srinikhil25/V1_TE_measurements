# Seebeck Measurement Backend

This is the FastAPI backend for the Seebeck measurement system.

## Setup

1. Create and activate a virtual environment (already done):
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Server

Start the FastAPI server with Uvicorn:

```
uvicorn main:app --reload
```

The server will be available at http://localhost:8000

## Next Steps
- Implement instrument communication endpoints
- Add WebSocket support for real-time data 