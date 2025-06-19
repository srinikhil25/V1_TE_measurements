import React, { useState, useRef, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress, Alert
} from '@mui/material';
import axios from 'axios';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import MeasurementDiagramForm from './MeasurementDiagramForm';
import html2canvas from 'html2canvas';
import ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';

interface DataRow {
  "Time [s]": number;
  "TEMF [mV]": number;
  "Temp1 [oC]": number;
  "Temp2 [oC]": number;
  "Delta Temp [oC]": number;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.host}/api/seebeck`;

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

const IRStreamPanel = () => {
  const [imgSrc, setImgSrc] = useState('');
  const [avgTemp, setAvgTemp] = useState('--');
  const [minTemp, setMinTemp] = useState('--');
  const [maxTemp, setMaxTemp] = useState('--');
  const [temps, setTemps] = useState<number[][] | null>(null);
  const [hoverTemp, setHoverTemp] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{x: number, y: number} | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: number | null = null;

    const connect = () => {
      let wsUrl;
      if (import.meta.env.VITE_WS_BASE_URL) {
        wsUrl = `${import.meta.env.VITE_WS_BASE_URL}/ir_camera/ws`;
      } else if (window.location.port === "5173") {
        wsUrl = "ws://localhost:8080/api/ir_camera/ws";
      } else {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsUrl = `${wsProtocol}//${window.location.host}/api/ir_camera/ws`;
      }
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setImgSrc('data:image/jpeg;base64,' + data.image);
          setAvgTemp(data.avg.toFixed(1));
          setMinTemp(data.min.toFixed(1));
          setMaxTemp(data.max.toFixed(1));
          setTemps(data.temps);
        } catch {
          setImgSrc('data:image/jpeg;base64,' + event.data);
        }
      };
      ws.onerror = () => {
        ws && ws.close();
      };
      ws.onclose = () => {
        reconnectTimeout = window.setTimeout(connect, 1000);
      };
    };

    connect();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

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
        IR Camera Live Stream
      </Typography>
      <Box sx={{ position: 'relative', width: '100%' }}>
        {imgSrc ? (
          <img
            ref={imgRef}
            src={imgSrc}
            alt="IR Camera Stream"
            style={{ width: '100%', maxHeight: 420, objectFit: 'contain', borderRadius: 8, border: '1px solid #ccc', display: 'block' }}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          />
        ) : (
          <Box
            sx={{
              width: '100%',
              height: 420,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px dashed #ccc',
              borderRadius: 2,
              color: '#888',
              background: '#fafafa',
            }}
          >
            No IR stream available
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
  const [startVolt, setStartVolt] = useState(0.0);
  const [stopVolt, setStopVolt] = useState(1.0);
  const [incRate, setIncRate] = useState(1.0);
  const [decRate, setDecRate] = useState(1.0);
  const [holdTime, setHoldTime] = useState(600);
  const [fileName, setFileName] = useState('seebeck_results.csv');
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<DataRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const liveGraphRef = useRef<HTMLDivElement>(null);
  const deltaGraphRef = useRef<HTMLDivElement>(null);

  // Poll session status and data
  useEffect(() => {
    if (running) {
      timerRef.current = setInterval(async () => {
        try {
          console.log('API_BASE_URL:', API_BASE_URL);
          const statusResp = await api.get('/status');
          setStatus(statusResp.data);
          const dataResp = await api.get('/data');
          console.log('Fetched data:', dataResp.data);
          const arr = Array.isArray(dataResp.data) ? dataResp.data : dataResp.data.data;
          setData(Array.isArray(arr) ? arr : []);
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

  const handleStart = async () => {
    setError(null);
    setData([]);
    setLoading(true);
    try {
      const params = {
        interval: interval,
        pre_time: preTime,
        start_volt: startVolt,
        stop_volt: stopVolt,
        inc_rate: incRate,
        dec_rate: decRate,
        hold_time: holdTime
      };
      
      // Debug log
      console.log('Sending params:', params);
      
      const response = await api.post('/start', params, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });
      
      console.log('Response:', response);
      
      if (response.data.status === 'started') {
        setRunning(true);
      } else {
        setError('Failed to start measurement');
        setLoading(false);
      }
    } catch (err: any) {
      console.error('Start error:', err);
      console.error('Request config:', err.config);
      console.error('Request data:', err.config?.data);
      setError(err.response?.data?.detail || 'Failed to start measurement');
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
  };

  const handleDownloadExcelWithGraph = async () => {
    if (!liveGraphRef.current) {
      alert('Live Graph is not rendered yet.');
      return;
    }
    const canvas = await html2canvas(liveGraphRef.current, { backgroundColor: null });
    const imgData = canvas.toDataURL('image/png');
    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet('Data');
    // Add header
    sheet.addRow(["Time [s]", "TEMF [mV]", "Temp1 [oC]", "Temp2 [oC]", "Delta Temp (Δt) / 差温度 [°C]"]);
    // Add data
    const safeData = Array.isArray(data) ? data : [];
    safeData.forEach(row => {
      sheet.addRow([
        row["Time [s]"],
        row["TEMF [mV]"],
        row["Temp1 [oC]"],
        row["Temp2 [oC]"],
        row["Delta Temp [oC]"]
      ]);
    });
    // Add image
    const imageId = workbook.addImage({ base64: imgData, extension: 'png' });
    // Place image below the data (row count + 2)
    const imgRow = safeData.length + 3;
    sheet.addImage(imageId, {
      tl: { col: 0, row: imgRow },
      ext: { width: 600, height: 300 }
    });
    // Save
    const buffer = await workbook.xlsx.writeBuffer();
    saveAs(new Blob([buffer]), 'data_sheet.xlsx');
  };

  // Defensive: ensure data is always an array
  const safeData = Array.isArray(data) ? data : [];

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
            />
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
            {status && status.status && <Alert severity="info" sx={{ mt: 2 }}>Status: {status.status}</Alert>}
          </Paper>
        </Box>
        {/* Right: IR Camera Panel (wider) */}
        <Box sx={{ flex: 1.8, minWidth: 340, display: 'flex' }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 420, height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <IRStreamPanel />
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
                  <Line yAxisId="right" type="monotone" dataKey="Temp1 [oC]" stroke="#d32f2f" dot={false} name="Temp1 [°C]" />
                  <Line yAxisId="right" type="monotone" dataKey="Temp2 [oC]" stroke="#388e3c" dot={false} name="Temp2 [°C]" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            <Typography variant="h6" gutterBottom>
              TEMF vs Delta Temp (Δt) / TEMF vs 差温度
            </Typography>
            <Box sx={{ height: 250 }} ref={deltaGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={safeData} margin={{ top: 10, right: 40, left: 40, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="Delta Temp [oC]"
                    label={{ value: 'Delta Temp (Δt) / 差温度 [°C]', position: 'insideBottom', offset: -5 }}
                    tickFormatter={engFormat}
                    tick={{ fontSize: 12 }}
                    angle={-30}
                    tickCount={8}
                  />
                  <YAxis label={{ value: 'TEMF [mV]', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend verticalAlign="bottom" align="center" />
                  <Line type="monotone" dataKey="TEMF [mV]" stroke="#1976d2" dot={true} name="TEMF [mV]" />
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
                    <TableCell>Delta Temp (Δt) / 差温度 [°C]</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {safeData.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{row["Time [s]"]}</TableCell>
                      <TableCell>{row["TEMF [mV]"]?.toFixed(3)}</TableCell>
                      <TableCell>{row["Temp1 [oC]"]?.toFixed(2)}</TableCell>
                      <TableCell>{row["Temp2 [oC]"]?.toFixed(2)}</TableCell>
                      <TableCell>{row["Delta Temp [oC]"]?.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
};

export default SeebeckMeasurementPanel; 