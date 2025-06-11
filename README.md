# Seebeck Measurement System

This repository contains the frontend and backend components for a Seebeck Measurement System application.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the Application](#running-the-application)
  - [Local Development](#local-development)
  - [Using a Tunnel (ngrok or Serveo)](#using-a-tunnel-ngrok-or-serveo)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before you begin, ensure you have the following installed on your machine:

*   **Python 3.8+**: For the backend (FastAPI).
    *   [Download Python](https://www.python.org/downloads/)
*   **Node.js (LTS recommended)** and **npm**: For the frontend (React with Vite).
    *   [Download Node.js](https://nodejs.org/en/download/)
*   **Git**: For cloning the repository.
    *   [Download Git](https://git-scm.com/downloads)
*   **ngrok (Optional, for external access)**: If you need to expose your local backend to the internet.
    *   [Download ngrok](https://ngrok.com/download) and follow their setup instructions to set up your authtoken.
*   **SSH Client (Optional, for Serveo)**: Typically built into Linux/macOS, for Windows you might use Git Bash or PuTTY.

## Backend Setup

The backend is built with FastAPI.

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    python -m venv venv
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the FastAPI server:**
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The backend API will be accessible at `http://localhost:8000/api/` (e.g., `http://localhost:8000/api/seebeck/start`). Keep this terminal window open.

## Frontend Setup

The frontend is built with React and Vite.

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```

2.  **Install Node.js dependencies:**
    ```bash
    npm install
    ```

3.  **Create a `.env` file:**
    In the `frontend` directory, create a file named `.env`. This file will store environment variables for the frontend.

    *   For **local development**, add this line:
        ```
        VITE_API_BASE_URL=http://localhost:8000
        ```
    *   If you plan to use a **tunneling service (ngrok/Serveo)**, you will update this URL later with the tunnel's public address.

4.  **Run the Vite development server:**
    ```bash
    npm run dev
    ```
    The frontend application will be accessible at `http://localhost:5173`. Keep this terminal window open.

## Running the Application

### Local Development

1.  Follow the [Backend Setup](#backend-setup) steps and run the backend server.
2.  Follow the [Frontend Setup](#frontend-setup) steps, ensuring your `frontend/.env` has `VITE_API_BASE_URL=http://localhost:8000`, and run the frontend server.
3.  Open `http://localhost:5173` in your browser.

### Using a Tunnel (ngrok or Serveo)

This is useful if you need to access your local application from another device, or if you're troubleshooting CORS issues with external services.

#### Using ngrok

1.  Ensure you have ngrok installed and your authtoken configured (`ngrok authtoken <your_token>`).
2.  **Create or modify your ngrok configuration file.** This file is typically located at `C:\Users\<YourUsername>\.ngrok2\ngrok.yml` on Windows, or `~/.ngrok2/ngrok.yml` on Linux/macOS.

    Add the following content to `ngrok.yml`. **Replace `your_auth_token_here` with your actual ngrok token.**

    ```yaml
    version: "2"
    authtoken: your_auth_token_here
    tunnels:
      backend:
        addr: 8000
        proto: http
        schemes:
          - https
        headers:
          - "Access-Control-Allow-Origin: http://localhost:5173"
          - "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS, PATCH"
          - "Access-Control-Allow-Headers: Content-Type, Authorization, Accept, Origin, X-Requested-With, Access-Control-Request-Method, Access-Control-Request-Headers"
          - "Access-Control-Allow-Credentials: true"
    ```

3.  **Start your backend server** (as per [Backend Setup](#backend-setup)).
4.  **Start ngrok** in a new terminal, navigating to your ngrok executable directory first:
    ```bash
    # Example for Windows:
    cd C:\Users\<YourUsername>\Downloads\ngrok-v3-stable-windows-amd64
    ngrok start backend
    ```
    Ngrok will provide a public HTTPS URL (e.g., `https://xxxx-xx-xxx-xx.ngrok-free.app`). **Copy this URL.**
5.  **Update your frontend's `.env` file:**
    ```
    VITE_API_BASE_URL=https://<your-ngrok-url>.ngrok-free.app
    ```
6.  **Restart your frontend development server** (if it was already running).
7.  Open `http://localhost:5173` in your browser. The frontend will now communicate with your backend via the ngrok tunnel.

#### Using Serveo (alternative to ngrok)

1.  **Start your backend server** (as per [Backend Setup](#backend-setup)).
2.  **Start Serveo** in a new terminal. You need an SSH client for this.
    ```bash
    ssh -R 80:localhost:8000 serveo.net
    ```
    Serveo will provide a public HTTPS URL (e.g., `https://your-random-subdomain.serveo.net`). **Copy this URL.**
3.  **Update your frontend's `.env` file:**
    ```
    VITE_API_BASE_URL=https://<your-serveo-url>.serveo.net
    ```
4.  **Restart your frontend development server** (if it was already running).
5.  Open `http://localhost:5173` in your browser.

## Troubleshooting

*   **`415 Unsupported Media Type`**: Ensure your frontend is sending the request body as JSON and with `Content-Type: application/json` header, and that the payload matches the `MeasurementParams` model in the backend.
*   **CORS Errors (`Access-Control-Allow-Origin` missing)**:
    *   Verify your backend's `backend/app/main.py` CORS middleware is configured correctly (e.g., `allow_origins=["*"]` for development).
    *   If using ngrok, ensure your `ngrok.yml` includes the necessary `headers` to pass CORS headers, or that you've configured CORS in the ngrok dashboard.
    *   If using Serveo, the default behavior should be fine for simple CORS, but double-check your frontend's `VITE_API_BASE_URL`.
    *   Check your browser's developer console for network errors.
*   **`Network Error` / `ERR_CONNECTION_REFUSED`**:
    *   Ensure both your backend and tunneling service (if used) are running.
    *   Verify the `VITE_API_BASE_URL` in your frontend's `.env` matches the active URL of your backend or tunnel.
    *   Check if firewalls are blocking ports (8000 for backend, 5173 for frontend).
*   **"Bad Request" from backend for OPTIONS requests**: This is usually handled by FastAPI's `CORSMiddleware`. If it persists, ensure your backend logs (from `uvicorn` terminal) are checked for more specific errors.

If you encounter persistent issues, carefully review the console outputs from both your frontend and backend terminals, and check your browser's developer console for network requests and error messages. 