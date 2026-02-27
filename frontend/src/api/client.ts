import axios from 'axios';
import { getApiBase } from './config';

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
  baseURL: getApiBase(),
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