import axios from 'axios';

const API_BASE_URL = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'}/api`;

export interface MeasurementConfig {
  channel: number;
  nplc: number;
  auto_zero: boolean;
}

export interface MeasurementData {
  timestamp: number;
  value: number;
}

export interface InstrumentStatus {
  connected: boolean;
  resource_name?: string;
  measurement_count?: number;
  error?: string;
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const instrumentApi = {
  connect: async (): Promise<InstrumentStatus> => {
    const response = await api.post('/instrument/connect');
    return response.data;
  },

  disconnect: async (): Promise<void> => {
    await api.post('/instrument/disconnect');
  },

  configure: async (config: MeasurementConfig): Promise<void> => {
    await api.post('/instrument/configure', config);
  },

  takeMeasurement: async (): Promise<MeasurementData> => {
    const response = await api.post('/instrument/measure');
    return response.data;
  },

  getMeasurements: async (): Promise<MeasurementData[]> => {
    const response = await api.get('/instrument/measurements');
    return response.data.measurements;
  },

  clearMeasurements: async (): Promise<void> => {
    await api.delete('/instrument/measurements');
  },

  getStatus: async (): Promise<InstrumentStatus> => {
    const response = await api.get('/instrument/status');
    return response.data;
  },
}; 