import axios from 'axios';

export interface IVParams {
  start_voltage: number;
  stop_voltage: number;
  points: number;
  delay_ms?: number;
  current_limit?: number;
  voltage_limit?: number;
  length?: number;
  width?: number;
  thickness?: number;
}

export interface IVPoint {
  voltage: number | null;
  current: number | null;
  resistance: number | null;
  resistivity?: number | null;
  conductivity?: number | null;
}

import { getApiBase } from './config';

const api = axios.create({
  baseURL: getApiBase(),
  headers: { 'Content-Type': 'application/json' },
  timeout: 20000,
});

export async function runIVSweep(params: IVParams): Promise<IVPoint[]> {
  const resp = await api.post<{ data: IVPoint[] }>('/iv/run', params);
  return resp.data.data;
}

