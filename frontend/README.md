# Seebeck Measurement System Frontend

This is the React frontend for the Seebeck measurement system. It provides a modern, responsive interface for controlling the Keithley 2700 instrument and visualizing measurements in real-time.

## Features

- Real-time instrument control
- Live measurement visualization
- Configurable measurement parameters
- WebSocket-based real-time updates
- Responsive Material-UI design

## Prerequisites

- Node.js 16+ and npm
- Backend server running (FastAPI)

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

The application will be available at http://localhost:5173

## Development

- Built with React + TypeScript
- Uses Material-UI for components
- Recharts for data visualization
- React Query for data fetching
- WebSocket for real-time updates

## Building for Production

```bash
npm run build
```

The built files will be in the `dist` directory.
