import React, { useState, useRef, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress, Alert, Switch, FormControlLabel, TextField, FormControl, InputLabel, Select, MenuItem
} from '@mui/material';
import axios from 'axios';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import MeasurementDiagramForm from './MeasurementDiagramForm';
import html2canvas from 'html2canvas';
import ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import { getWsBase } from '../api/config';

interface DataRow {
  "Time [s]": number;
  "TEMF [mV]": number;
  "Temp1 [oC]": number;
  "Temp2 [oC]": number;
  "Delta Temp [oC]": number;
  "T0 [oC]"?: number;
  "T0 [K]"?: number;
  "delta_T_over_T0"?: number | null;
  "S [µV/K]"?: number | null;
  branch?: "heating" | "cooling";
}

interface BinnedAnalysisRow {
  T0_center_K: number;
  T0_min_K: number;
  T0_max_K: number;
  S_uV_per_K: number;
  S_uncertainty_uV_per_K?: number | null;
  n_points: number;
}

// Normalize API base: default to '/api', then append '/seebeck'
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const API_BASE_URL = `${API_BASE}/seebeck`;
const IR_CAMERA_BASE = `${API_BASE}/ir_camera`;

// Create a custom axios instance for the API
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  withCredentials: false,
  timeout: 10000,
});

// Add request interceptor to handle CORS preflight
api.interceptors.request.use(
  (config) => {
    if (config.method === 'get') {
      config.params = { ...config.params, _t: Date.now() };
    }
    // Ensure content type is set for POST requests
    if (config.method === 'post') {
      config.headers['Content-Type'] = 'application/json';
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Engineering notation formatter for axis
function engFormat(val: number): string {
  if (val === 0) return '0';
  const abs = Math.abs(val);
  if (abs < 1e-6) return (val * 1e9).toPrecision(3) + ' n';
  if (abs < 1e-3) return (val * 1e6).toPrecision(3) + ' μ';
  if (abs < 1) return (val * 1e3).toPrecision(3) + ' m';
  return val.toPrecision(3);
}

interface IRStreamPanelProps {
  enabled: boolean;
}

const IRStreamPanel: React.FC<IRStreamPanelProps> = ({ enabled }) => {
  const [imgSrc, setImgSrc] = useState('');
  const [avgTemp, setAvgTemp] = useState('--');
  const [minTemp, setMinTemp] = useState('--');
  const [maxTemp, setMaxTemp] = useState('--');
  const [temps, setTemps] = useState<number[][] | null>(null);
  const [hoverTemp, setHoverTemp] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{x: number, y: number} | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!enabled) {
      // Disconnect if disabled
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setImgSrc('');
      setAvgTemp('--');
      setMinTemp('--');
      setMaxTemp('--');
      setTemps(null);
      setConnectionStatus('disconnected');
      return;
    }

    let ws: WebSocket | null = null;
    let reconnectTimeout: number | null = null;

    const connect = () => {
      if (!enabled) return; // Don't connect if disabled

      const wsUrl = `${getWsBase()}/ir_camera/ws`;

      setConnectionStatus('connecting');
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionStatus('connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setImgSrc('data:image/jpeg;base64,' + data.image);
          setAvgTemp(data.avg.toFixed(1));
          setMinTemp(data.min.toFixed(1));
          setMaxTemp(data.max.toFixed(1));
          setTemps(data.temps);
          setConnectionStatus('connected');
        } catch {
          setImgSrc('data:image/jpeg;base64,' + event.data);
          setConnectionStatus('connected');
        }
      };
      
      ws.onerror = () => {
        setConnectionStatus('error');
        ws && ws.close();
      };
      
      ws.onclose = () => {
        setConnectionStatus('disconnected');
        if (enabled) {
          // Only reconnect if still enabled
          reconnectTimeout = window.setTimeout(connect, 1000);
        }
      };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [enabled]);

  // Mouse move handler
  const handleMouseMove = (e: React.MouseEvent<HTMLImageElement, MouseEvent>) => {
    if (!imgRef.current || !temps) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Map to original temperature array coordinates
    const imgWidth = imgRef.current.width;
    const imgHeight = imgRef.current.height;
    const arrHeight = temps.length;
    const arrWidth = temps[0]?.length || 0;
    const arrX = Math.floor(x * arrWidth / imgWidth);
    const arrY = Math.floor(y * arrHeight / imgHeight);
    if (
      arrX >= 0 && arrX < arrWidth &&
      arrY >= 0 && arrY < arrHeight
    ) {
      setHoverTemp(`${temps[arrY][arrX].toFixed(1)}°C`);
      setTooltipPos({ x, y });
    } else {
      setHoverTemp(null);
      setTooltipPos(null);
    }
  };

  const handleMouseLeave = () => {
    setHoverTemp(null);
    setTooltipPos(null);
  };

  return (
    <Box sx={{ width: '100%', mb: 2, position: 'relative' }}>
      <Typography variant="h6" gutterBottom>
        IR Camera Live Stream {!enabled && '(Disabled)'}
      </Typography>
      {!enabled && (
        <Alert severity="info" sx={{ mb: 2 }}>
          IR camera is disabled. Seebeck measurements will work without it.
        </Alert>
      )}
      {enabled && connectionStatus === 'connecting' && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Connecting to IR camera...
        </Alert>
      )}
      {enabled && connectionStatus === 'error' && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          IR camera connection failed. Retrying...
        </Alert>
      )}
      <Box sx={{ position: 'relative', width: '100%' }}>
        {imgSrc ? (
          <img
            ref={imgRef}
            src={imgSrc}
            alt="IR Camera Stream"
            style={{ width: '100%', maxHeight: 720, objectFit: 'contain', borderRadius: 8, border: '1px solid #ccc', display: 'block' }}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          />
        ) : (
          <Box
            sx={{
              width: '100%',
              height: 480,
              minHeight: 420,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px dashed #ccc',
              borderRadius: 2,
              color: '#888',
              background: '#fafafa',
            }}
          >
            {enabled ? 'Connecting to IR camera...' : 'IR camera disabled'}
          </Box>
        )}
        {/* Tooltip */}
        {hoverTemp && tooltipPos && (
          <Box
            sx={{
              position: 'absolute',
              left: tooltipPos.x,
              top: tooltipPos.y,
              transform: 'translate(-50%, -120%)',
              pointerEvents: 'none',
              bgcolor: 'rgba(0,0,0,0.75)',
              color: '#fff',
              px: 1.2,
              py: 0.5,
              borderRadius: 1,
              fontSize: 15,
              zIndex: 10,
              whiteSpace: 'nowrap',
            }}
          >
            {hoverTemp}
          </Box>
        )}
      </Box>
      {/* Temperature stats below the image */}
      <Box sx={{ mt: 1, textAlign: 'center', fontSize: 16, color: '#444' }}>
        Avg: {avgTemp}°C &nbsp;|&nbsp; Min: {minTemp}°C &nbsp;|&nbsp; Max: {maxTemp}°C
      </Box>
    </Box>
  );
};

const SeebeckMeasurementPanel: React.FC = () => {
  const [interval, setIntervalVal] = useState(2);
  const [preTime, setPreTime] = useState(1);
  const [startVolt, setStartVolt] = useState('0');
  const [stopVolt, setStopVolt] = useState('1');
  const [incRate, setIncRate] = useState('1');
  const [decRate, setDecRate] = useState('1');
  const [holdTime, setHoldTime] = useState(600);
  const [fileName, setFileName] = useState('seebeck_results.csv');
  const [sampleId, setSampleId] = useState('');
  const [operator, setOperator] = useState('');
  const [notes, setNotes] = useState('');
  const [targetT0K, setTargetT0K] = useState<number | ''>('');
  const [probeArrangement, setProbeArrangement] = useState<'2-probe' | '4-probe' | ''>('');
  const [coolingTargetDeltaT, setCoolingTargetDeltaT] = useState(5);
  const [coolingTimeoutMin, setCoolingTimeoutMin] = useState(10);
  const [stabilizationDelayS, setStabilizationDelayS] = useState(0);
  const [pk160Unit, setPk160Unit] = useState<'mA' | 'A'>('mA');
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<DataRow[]>([]);
  const [analysis, setAnalysis] = useState<BinnedAnalysisRow[]>([]);
  const [metadata, setMetadata] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [irCameraEnabled, setIrCameraEnabled] = useState(false);
  const [irCameraBackend, setIrCameraBackend] = useState<'otc' | 'legacy' | null>(null);
  const [irCameraBackendReason, setIrCameraBackendReason] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const liveGraphRef = useRef<HTMLDivElement>(null);
  const deltaGraphRef = useRef<HTMLDivElement>(null);
  const seebeckGraphRef = useRef<HTMLDivElement>(null);

  // Poll session status and data
  useEffect(() => {
    if (running) {
      timerRef.current = setInterval(async () => {
        try {
          console.log('API_BASE_URL:', API_BASE_URL);
          const statusResp = await api.get('/status');
          setStatus(statusResp.data);
          const dataResp = await api.get('/data');
          const payload = dataResp.data?.data != null ? dataResp.data : { data: dataResp.data };
          const arr = Array.isArray(payload.data) ? payload.data : [];
          setData(arr);
          setAnalysis(Array.isArray(payload.analysis) ? payload.analysis : []);
          setMetadata(payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {});
          if (statusResp.data.status === 'finished' || statusResp.data.status === 'stopped' || statusResp.data.status?.startsWith('error')) {
            setRunning(false);
            setLoading(false);
            if (timerRef.current) clearInterval(timerRef.current);
          }
        } catch (err: any) {
          console.error('Error fetching data:', err);
          if (err.response?.status === 0) {
            setError('Network error or CORS issue. Please check your connection and try again.');
          } else {
            setError(err.message || 'Failed to fetch session status/data');
          }
          setRunning(false);
          setLoading(false);
          if (timerRef.current) clearInterval(timerRef.current);
        }
      }, 1000);
      return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }
  }, [running]);

  // Auto-scroll to bottom of table when data changes
  useEffect(() => {
    if (tableContainerRef.current) {
      tableContainerRef.current.scrollTop = tableContainerRef.current.scrollHeight;
    }
  }, [data]);

  // Fetch IR camera backend (otc vs legacy) when IR is enabled
  useEffect(() => {
    if (!irCameraEnabled) {
      setIrCameraBackend(null);
      setIrCameraBackendReason(null);
      return;
    }
    let cancelled = false;
    axios.get<{ backend: string; reason?: string }>(`${IR_CAMERA_BASE}/backend`).then(r => {
      if (!cancelled && r.data?.backend) {
        setIrCameraBackend(r.data.backend as 'otc' | 'legacy');
        setIrCameraBackendReason(r.data.reason ?? null);
      }
    }).catch(() => { if (!cancelled) setIrCameraBackend(null); setIrCameraBackendReason(null); });
    return () => { cancelled = true; };
  }, [irCameraEnabled]);

  const handleStart = async () => {
    setError(null);
    setData([]);
    // Client-side validation to match backend rules
    if (interval <= 0) {
      setError('Measurement interval must be positive (seconds).');
      return;
    }
    if (preTime < 0 || holdTime < 0) {
      setError('Pre time and hold time must be non-negative.');
      return;
    }
    const incRateNum = parseFloat(incRate);
    const decRateNum = parseFloat(decRate);
    if (!Number.isFinite(incRateNum) || incRateNum <= 0 || !Number.isFinite(decRateNum) || decRateNum <= 0) {
      setError('Inc. rate and Dec. rate must be positive numbers.');
      return;
    }
    const startNum = parseFloat(startVolt);
    const stopNum = parseFloat(stopVolt);
    if (!Number.isFinite(startNum) || !Number.isFinite(stopNum)) {
      setError('Start (I₀) and Stop (I) must be valid numbers.');
      return;
    }
    if (startNum > stopNum) {
      setError('Start value (I₀) must be ≤ stop value (I).');
      return;
    }
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        interval,
        pre_time: preTime,
        start_volt: startNum,
        stop_volt: stopNum,
        inc_rate: incRateNum,
        dec_rate: decRateNum,
        hold_time: holdTime,
        cooling_target_delta_t: coolingTargetDeltaT,
        cooling_timeout_s: coolingTimeoutMin * 60,
        stabilization_delay_s: stabilizationDelayS,
        pk160_current_unit: pk160Unit,
      };
      if (sampleId.trim()) params.sample_id = sampleId.trim();
      if (operator.trim()) params.operator = operator.trim();
      if (notes.trim()) params.notes = notes.trim();
      if (targetT0K !== '') params.target_T0_K = Number(targetT0K);
      if (probeArrangement) params.probe_arrangement = probeArrangement;
      
      // Debug log
      console.log('API_BASE_URL:', API_BASE_URL);
      console.log('Sending params:', params);
      console.log('Full URL will be:', `${API_BASE_URL}/start`);
      
      const response = await api.post('/start', params);
      
      console.log('Response:', response);
      console.log('Response data:', response.data);
      
      if (response.data && response.data.status === 'started') {
        setRunning(true);
        setLoading(false);
      } else {
        setError('Failed to start measurement: Unexpected response');
        setLoading(false);
      }
    } catch (err: any) {
      console.error('Start error:', err);
      console.error('Error message:', err.message);
      console.error('Error response:', err.response);
      console.error('Request URL:', err.config?.url);
      console.error('Request baseURL:', err.config?.baseURL);
      console.error('Request data:', err.config?.data);
      
      let errorMessage = 'Failed to start measurement';
      if (err.response) {
        errorMessage = err.response.data?.detail || err.response.data?.message || errorMessage;
      } else if (err.request) {
        errorMessage = 'Network error: Could not reach the server. Please check if the backend is running.';
      } else {
        errorMessage = err.message || errorMessage;
      }
      
      setError(errorMessage);
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/stop', {}, {
        headers: {
          'Content-Type': 'application/json',
        }
      });
      setRunning(false);
      setLoading(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to stop measurement');
      setLoading(false);
    }
  };

  // Handlers for new buttons
  const handleDownloadGraphsPng = async () => {
    if (!liveGraphRef.current || !deltaGraphRef.current) {
      alert('Graphs are not rendered yet.');
      return;
    }
    const liveCanvas = await html2canvas(liveGraphRef.current, { backgroundColor: null });
    const deltaCanvas = await html2canvas(deltaGraphRef.current, { backgroundColor: null });
    liveCanvas.toBlob(blob => {
      if (blob) saveAs(blob, 'live_graph.png');
    });
    deltaCanvas.toBlob(blob => {
      if (blob) saveAs(blob, 'temf_vs_delta_temp.png');
    });
    if (seebeckGraphRef.current) {
      const seebeckCanvas = await html2canvas(seebeckGraphRef.current, { backgroundColor: null });
      seebeckCanvas.toBlob(blob => {
        if (blob) saveAs(blob, 'seebeck_vs_temperature.png');
      });
    }
  };

  const handleDownloadExcelWithGraph = async () => {
    // Require that key graphs are rendered before exporting
    if (!liveGraphRef.current || !deltaGraphRef.current) {
      alert('Graphs are not rendered yet.');
      return;
    }

    // Capture all three graphs as PNG (live, TEMF vs ΔT, Seebeck vs T₀)
    const [liveCanvas, deltaCanvas, seebeckCanvas] = await Promise.all([
      html2canvas(liveGraphRef.current, { backgroundColor: '#ffffff' }),
      html2canvas(deltaGraphRef.current, { backgroundColor: '#ffffff' }),
      seebeckGraphRef.current
        ? html2canvas(seebeckGraphRef.current, { backgroundColor: '#ffffff' })
        : Promise.resolve(null as HTMLCanvasElement | null),
    ]);

    const liveImgData = liveCanvas.toDataURL('image/png');
    const deltaImgData = deltaCanvas.toDataURL('image/png');
    const seebeckImgData = seebeckCanvas ? seebeckCanvas.toDataURL('image/png') : null;

    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet('Data');

    const safeData = Array.isArray(data) ? data : [];
    const safeAnalysis = Array.isArray(analysis) ? analysis : [];

    // Metadata block at top (session metadata + key measurement parameters)
    sheet.addRow(['Metadata']);
    let metaRowCount = 1;
    if (metadata?.sample_id) {
      sheet.addRow(['Sample ID', metadata.sample_id]);
      metaRowCount += 1;
    }
    if (metadata?.operator) {
      sheet.addRow(['Operator', metadata.operator]);
      metaRowCount += 1;
    }
    if (metadata?.target_T0_K != null) {
      sheet.addRow(['Target T₀ (K)', metadata.target_T0_K]);
      metaRowCount += 1;
    }
    if (metadata?.probe_arrangement) {
      sheet.addRow(['Probe arrangement', metadata.probe_arrangement]);
      metaRowCount += 1;
    }
    if (metadata?.notes) {
      sheet.addRow(['Notes', metadata.notes]);
      metaRowCount += 1;
    }

    // Additional measurement parameters from the current UI state
    sheet.addRow(['Interval (s)', interval]);
    sheet.addRow(['Pre time (s)', preTime]);
    sheet.addRow(['Hold time (s)', holdTime]);
    sheet.addRow(['Start current I₀', `${startVolt} ${pk160Unit}`]);
    sheet.addRow(['Stop current I', `${stopVolt} ${pk160Unit}`]);
    sheet.addRow(['Inc. rate', `${incRate} ${pk160Unit}/s`]);
    sheet.addRow(['Dec. rate', `${decRate} ${pk160Unit}/s`]);
    sheet.addRow(['Cooling target ΔT (°C)', coolingTargetDeltaT]);
    sheet.addRow(['Cooling timeout (s)', coolingTimeoutMin * 60]);
    sheet.addRow(['Stabilization delay (s)', stabilizationDelayS]);
    metaRowCount += 10;

    sheet.addRow([]);
    sheet.addRow([
      'Time [s]',
      'TEMF [mV]',
      'Temp1 [oC]',
      'Temp2 [oC]',
      'Delta Temp [°C]',
      'T0 [°C]',
      'T0 [K]',
      'ΔT/T₀',
      'S [µV/K]',
    ]);

    safeData.forEach(row => {
      sheet.addRow([
        row['Time [s]'],
        row['TEMF [mV]'],
        row['Temp1 [oC]'],
        row['Temp2 [oC]'],
        row['Delta Temp [oC]'],
        row['T0 [oC]'],
        row['T0 [K]'],
        row['delta_T_over_T0'] != null ? row['delta_T_over_T0'] : '',
        row['S [µV/K]'] != null ? row['S [µV/K]'] : '',
      ]);
    });

    // Place all three graphs below the data table on the same sheet
    const firstImageRow = metaRowCount + 2 + safeData.length + 2;
    const liveImageId = workbook.addImage({ base64: liveImgData, extension: 'png' });
    sheet.addImage(liveImageId, {
      tl: { col: 0, row: firstImageRow },
      ext: { width: 600, height: 300 },
    });

    const deltaImageId = workbook.addImage({ base64: deltaImgData, extension: 'png' });
    sheet.addImage(deltaImageId, {
      tl: { col: 0, row: firstImageRow + 22 },
      ext: { width: 600, height: 300 },
    });

    if (seebeckImgData) {
      const seebeckImageId = workbook.addImage({ base64: seebeckImgData, extension: 'png' });
      sheet.addImage(seebeckImageId, {
        tl: { col: 0, row: firstImageRow + 44 },
        ext: { width: 600, height: 300 },
      });
    }

    // Binned S (fit) sheet
    if (safeAnalysis.length > 0) {
      const sheetFit = workbook.addWorksheet('Binned S (fit)');
      sheetFit.addRow(['T0_center_K', 'T0_min_K', 'T0_max_K', 'S [µV/K]', 'S uncertainty [µV/K]', 'n_points']);
      safeAnalysis.forEach(r => {
        sheetFit.addRow([r.T0_center_K, r.T0_min_K, r.T0_max_K, r.S_uV_per_K, r.S_uncertainty_uV_per_K ?? '', r.n_points]);
      });
    }

    const buffer = await workbook.xlsx.writeBuffer();
    saveAs(new Blob([buffer]), 'data_sheet.xlsx');
  };

  // Defensive: ensure data is always an array
  const safeData = Array.isArray(data) ? data : [];
  // TEMF vs ΔT: use a proper numeric x-axis scale (ΔT from 0 to max), not point order
  const deltaTempExtent = safeData.reduce<[number, number]>(
    (acc, row) => {
      const d = row["Delta Temp [oC]"];
      if (typeof d === 'number' && !Number.isNaN(d)) {
        return [Math.min(acc[0], d), Math.max(acc[1], d)];
      }
      return acc;
    },
    [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]
  );
  const deltaTempDomain: [number, number] =
    deltaTempExtent[1] >= deltaTempExtent[0] && Number.isFinite(deltaTempExtent[0])
      ? [Math.max(0, Math.floor(deltaTempExtent[0])), Math.ceil(deltaTempExtent[1]) + 1]
      : [0, 1];

  return (
    <Box sx={{ width: '100%' }}>
      {/* Top: Measurement Parameters/Diagram and IR Camera side by side */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, width: '100%', alignItems: 'stretch', flexWrap: 'wrap' }}>
        {/* Left: Measurement Parameters/Diagram */}
        <Box sx={{ flex: 1.2, minWidth: 320, display: 'flex' }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 420, height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <Typography variant="h6" gutterBottom>
              Measurement Parameters / 測定パラメータ
            </Typography>
            <MeasurementDiagramForm
              interval={interval} setIntervalVal={setIntervalVal}
              preTime={preTime} setPreTime={setPreTime}
              startVolt={startVolt} setStartVolt={setStartVolt}
              stopVolt={stopVolt} setStopVolt={setStopVolt}
              incRate={incRate} setIncRate={setIncRate}
              decRate={decRate} setDecRate={setDecRate}
              holdTime={holdTime} setHoldTime={setHoldTime}
              fileName={fileName} setFileName={setFileName}
              currentUnit={pk160Unit}
            />
            <Typography variant="subtitle2" sx={{ mt: 1.5 }}>Metadata & options</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mt: 0.5 }}>
              <TextField size="small" label="Sample ID" value={sampleId} onChange={e => setSampleId(e.target.value)} />
              <TextField size="small" label="Operator" value={operator} onChange={e => setOperator(e.target.value)} />
              <TextField size="small" label="Target T₀ (K)" type="number" value={targetT0K} onChange={e => setTargetT0K(e.target.value === '' ? '' : Number(e.target.value))} />
              <FormControl size="small">
                <InputLabel>Probe</InputLabel>
                <Select value={probeArrangement || ''} label="Probe" onChange={e => setProbeArrangement((e.target.value as '2-probe' | '4-probe') || '')}>
                  <MenuItem value="">—</MenuItem>
                  <MenuItem value="2-probe">2-probe</MenuItem>
                  <MenuItem value="4-probe">4-probe</MenuItem>
                </Select>
              </FormControl>
              <TextField size="small" label="Cooling target ΔT (°C)" type="number" value={coolingTargetDeltaT} onChange={e => setCoolingTargetDeltaT(Number(e.target.value) || 5)} />
              <TextField size="small" label="Cooling timeout (min)" type="number" value={coolingTimeoutMin} onChange={e => setCoolingTimeoutMin(Number(e.target.value) || 10)} />
              <TextField size="small" label="Stabilization delay (s)" type="number" value={stabilizationDelayS} onChange={e => setStabilizationDelayS(Number(e.target.value) || 0)} />
              <FormControl size="small">
                <InputLabel>PK160 unit</InputLabel>
                <Select value={pk160Unit} label="PK160 unit" onChange={e => setPk160Unit(e.target.value as 'mA' | 'A')}>
                  <MenuItem value="mA">mA</MenuItem>
                  <MenuItem value="A">A</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <TextField fullWidth size="small" label="Notes" value={notes} onChange={e => setNotes(e.target.value)} multiline minRows={1} sx={{ mt: 1 }} />
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 2 }}>
              <Button variant="contained" color="primary" onClick={handleStart} disabled={running || loading}>
                Start Measurement / 始める
              </Button>
              <Button variant="outlined" color="secondary" onClick={handleStop} disabled={!running}>
                Stop Measurement / 停止
              </Button>
              {/*
              <CSVLink data={safeData} filename={fileName} style={{ textDecoration: 'none' }}>
                <Button variant="outlined" disabled={safeData.length === 0}>Download CSV / CSVダウンロード</Button>
              </CSVLink>
              */}
              <Button variant="outlined" onClick={handleDownloadGraphsPng} disabled={safeData.length === 0}>
                Download Graphs as PNG / グラフPNGダウンロード
              </Button>
              <Button variant="outlined" onClick={handleDownloadExcelWithGraph} disabled={safeData.length === 0}>
                Download data sheet / データシートダウンロード
              </Button>
            </Box>
            {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            {status?.warn_large_gradient && (
              <Alert severity="warning" sx={{ mt: 2 }}>ΔT/T₀ is large in some points; differential method assumes small gradient (ΔT/T₀ ≪ 1).</Alert>
            )}
            {status && status.status && (
              <Alert severity="info" sx={{ mt: 2 }}>
                Status: {status.status}
                {status.estimated_total_s != null && status.hold_time_s != null && (
                  <> • Total run ~{status.estimated_total_s} s (hold at peak: {status.hold_time_s} s only)</>
                )}
                {status.phase != null && (
                  <> • Phase: <strong>{status.phase === 'ramp_up' ? 'Ramp up' : status.phase === 'hold' ? 'Hold' : status.phase === 'ramp_down' ? 'Ramp down' : status.phase === 'cooling_tail' ? 'Cooling (ΔT→0)' : status.phase}</strong></>
                )}
                {status.step != null && status.total_steps != null && (
                  <> • Step {status.step}/{status.total_steps}</>
                )}
                {status.estimated_remaining_s != null && status.estimated_remaining_s > 0 && (
                  <> • ~{status.estimated_remaining_s} s left (let it finish to see cooling curve)</>
                )}
              </Alert>
            )}
          </Paper>
        </Box>
        {/* Right: IR Camera Panel (wider) */}
        <Box sx={{ flex: 1.8, minWidth: 340, display: 'flex' }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 420, height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <Box sx={{ mb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
              <Typography variant="h6" sx={{ flex: 1 }}>
                IR Camera (Optional)
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={irCameraEnabled}
                    onChange={(e) => setIrCameraEnabled(e.target.checked)}
                    color="primary"
                  />
                }
                label={irCameraEnabled ? "Enabled" : "Disabled"}
                sx={{ ml: 1 }}
              />
              {irCameraEnabled && irCameraBackend && (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                  <Typography variant="caption" sx={{ color: irCameraBackend === 'otc' ? 'success.main' : 'warning.main' }}>
                    {irCameraBackend === 'otc' ? 'OTC SDK (NUC available)' : 'Legacy SDK (NUC not available)'}
                  </Typography>
                  {irCameraBackend === 'legacy' && irCameraBackendReason && (
                    <Typography variant="caption" sx={{ color: 'text.secondary', maxWidth: 280 }} title={irCameraBackendReason}>
                      {irCameraBackendReason.length > 45 ? `${irCameraBackendReason.slice(0, 45)}…` : irCameraBackendReason}
                    </Typography>
                  )}
                </Box>
              )}
              {irCameraEnabled && (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={async () => {
                    try {
                      const r = await axios.post<{ ok: boolean; message?: string }>(`${IR_CAMERA_BASE}/nuc`);
                      if (r.data?.ok) alert('NUC triggered. Wait a few seconds for the camera to stabilize.');
                      else if (r.data?.message) alert(r.data.message);
                    } catch (e: any) {
                      alert(e?.response?.data?.message || e?.message || 'Failed to trigger NUC');
                    }
                  }}
                >
                  Trigger NUC
                </Button>
              )}
            </Box>
            {irCameraEnabled ? (
              <IRStreamPanel enabled={true} />
            ) : (
              <Box
                sx={{
                  width: '100%',
                  height: 480,
                  minHeight: 420,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px dashed #ccc',
                  borderRadius: 2,
                  color: '#888',
                  background: '#fafafa',
                }}
              >
                IR camera disabled
              </Box>
            )}
          </Paper>
        </Box>
      </Box>
      {/* Bottom: Graphs and Data Table side by side */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, width: '100%', mt: 3 }}>
        {/* Left: Graphs */}
        <Box sx={{ flex: 1, minWidth: 350, display: 'flex' }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 400, height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <Typography variant="h6" gutterBottom>
              Live Graph / ライブグラフ
            </Typography>
            <Box sx={{ height: 250, mb: 2 }} ref={liveGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={safeData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="Time [s]" />
                  <YAxis yAxisId="left" label={{ value: 'TEMF [mV]', angle: -90, position: 'insideLeft' }} />
                  <YAxis yAxisId="right" orientation="right" label={{ value: 'Temp [°C]', angle: 90, position: 'insideRight' }} />
                  <Tooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="TEMF [mV]" stroke="#1976d2" dot={false} name="TEMF [mV]" />
                  <Line yAxisId="right" type="monotone" dataKey="Temp1 [oC]" stroke="#388e3c" dot={false} name="Temp1 [°C]" />
                  <Line yAxisId="right" type="monotone" dataKey="Temp2 [oC]" stroke="#d32f2f" dot={false} name="Temp2 [°C]" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            <Typography variant="h6" gutterBottom>
              TEMF vs Delta Temp (Δt) / TEMF vs 差温度
            </Typography>
            <Box sx={{ height: 250 }} ref={deltaGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={safeData.map(row => ({
                    ...row,
                    "TEMF heating [mV]": row.branch !== "cooling" ? row["TEMF [mV]"] : undefined,
                    "TEMF cooling [mV]": row.branch === "cooling" ? row["TEMF [mV]"] : undefined,
                  }))}
                  margin={{ top: 10, right: 40, left: 40, bottom: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="Delta Temp [oC]"
                    domain={deltaTempDomain}
                    label={{ value: 'Delta Temp (Δt) / 差温度 [°C]', position: 'insideBottom', offset: -5 }}
                    tickFormatter={engFormat}
                    tick={{ fontSize: 12 }}
                    tickCount={8}
                  />
                  <YAxis label={{ value: 'TEMF [mV]', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend verticalAlign="bottom" align="center" />
                  <Line type="monotone" dataKey="TEMF heating [mV]" stroke="#ed6c02" dot={false} name="Heating (ΔT↑)" connectNulls={false} />
                  <Line type="monotone" dataKey="TEMF cooling [mV]" stroke="#1976d2" dot={false} name="Cooling (ΔT↓)" connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
              Seebeck coefficient S vs average temperature T₀
            </Typography>
            <Box sx={{ height: 250 }} ref={seebeckGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={safeData.filter(row => row["S [µV/K]"] != null && row["T0 [K]"] != null)}
                  margin={{ top: 10, right: 40, left: 40, bottom: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="T0 [K]"
                    label={{ value: 'T₀ [K]', position: 'insideBottom', offset: -5 }}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis label={{ value: 'S [µV/K]', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend verticalAlign="bottom" align="center" />
                  <Line type="monotone" dataKey="S [µV/K]" stroke="#9c27b0" dot={false} name="S [µV/K]" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            {loading && <CircularProgress sx={{ mt: 2 }} />}
          </Paper>
        </Box>
        {/* Middle: Data Table */}
        <Box sx={{ flex: 1, mb: { xs: 2, md: 0 }, display: 'flex' }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 400, height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <Typography variant="h6" gutterBottom>
              Data Table / データ表
            </Typography>
            <TableContainer ref={tableContainerRef} sx={{ maxHeight: 600, overflowY: 'auto', width: '100%' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>Time [s]</TableCell>
                    <TableCell>TEMF [mV]</TableCell>
                    <TableCell>Temp1 [°C]</TableCell>
                    <TableCell>Temp2 [°C]</TableCell>
                    <TableCell>ΔT [°C]</TableCell>
                    <TableCell>ΔT/T₀</TableCell>
                    <TableCell>T₀ [°C]</TableCell>
                    <TableCell>T₀ [K]</TableCell>
                    <TableCell>S [µV/K]</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {safeData.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{row["Time [s]"]}</TableCell>
                      <TableCell>{row["TEMF [mV]"] != null ? row["TEMF [mV]"].toFixed(3) : '—'}</TableCell>
                      <TableCell>{row["Temp1 [oC]"] != null ? row["Temp1 [oC]"].toFixed(2) : '—'}</TableCell>
                      <TableCell>{row["Temp2 [oC]"] != null ? row["Temp2 [oC]"].toFixed(2) : '—'}</TableCell>
                      <TableCell>{row["Delta Temp [oC]"] != null ? row["Delta Temp [oC]"].toFixed(2) : '—'}</TableCell>
                      <TableCell>{row["delta_T_over_T0"] != null ? row["delta_T_over_T0"].toFixed(4) : '—'}</TableCell>
                      <TableCell>{row["T0 [oC]"] != null ? row["T0 [oC]"].toFixed(2) : '—'}</TableCell>
                      <TableCell>{row["T0 [K]"] != null ? row["T0 [K]"].toFixed(2) : '—'}</TableCell>
                      <TableCell>{row["S [µV/K]"] != null && row["S [µV/K]"] !== undefined ? row["S [µV/K]"]!.toFixed(2) : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {analysis.length > 0 && (
              <>
                <Typography variant="subtitle1" sx={{ mt: 2 }}>Binned S (linear fit ΔV vs ΔT per T₀ bin)</Typography>
                <TableContainer sx={{ maxHeight: 220, overflowY: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>T₀ center [K]</TableCell>
                        <TableCell>T₀ range [K]</TableCell>
                        <TableCell>S [µV/K]</TableCell>
                        <TableCell>± uncertainty</TableCell>
                        <TableCell>n</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {analysis.map((r, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{r.T0_center_K}</TableCell>
                          <TableCell>{r.T0_min_K}–{r.T0_max_K}</TableCell>
                          <TableCell>{r.S_uV_per_K.toFixed(3)}</TableCell>
                          <TableCell>{r.S_uncertainty_uV_per_K != null ? '±' + r.S_uncertainty_uV_per_K.toFixed(3) : '—'}</TableCell>
                          <TableCell>{r.n_points}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            )}
          </Paper>
        </Box>
      </Box>
    </Box>
  );
};

export default SeebeckMeasurementPanel; 