import React, { useState, useRef, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress, Alert
} from '@mui/material';
import { CSVLink } from 'react-csv';
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

const API_BASE_URL = 'http://localhost:8080/api/seebeck';

// Engineering notation formatter for axis
function engFormat(val: number): string {
  if (val === 0) return '0';
  const abs = Math.abs(val);
  if (abs < 1e-6) return (val * 1e9).toPrecision(3) + ' n';
  if (abs < 1e-3) return (val * 1e6).toPrecision(3) + ' μ';
  if (abs < 1) return (val * 1e3).toPrecision(3) + ' m';
  return val.toPrecision(3);
}

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
          const statusResp = await axios.get(`${API_BASE_URL}/status`);
          setStatus(statusResp.data);
          const dataResp = await axios.get(`${API_BASE_URL}/data`);
          setData(dataResp.data.data);
          if (statusResp.data.status === 'finished' || statusResp.data.status === 'stopped' || statusResp.data.status?.startsWith('error')) {
            setRunning(false);
            setLoading(false);
            if (timerRef.current) clearInterval(timerRef.current);
          }
        } catch (err: any) {
          setError('Failed to fetch session status/data');
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
      await axios.post(`${API_BASE_URL}/start`, {
        interval,
        pre_time: preTime,
        start_volt: startVolt,
        stop_volt: stopVolt,
        inc_rate: incRate,
        dec_rate: decRate,
        hold_time: holdTime,
      });
      setRunning(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start measurement');
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);
    try {
      await axios.post(`${API_BASE_URL}/stop`);
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
    data.forEach(row => {
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
    const imgRow = data.length + 3;
    sheet.addImage(imageId, {
      tl: { col: 0, row: imgRow },
      ext: { width: 600, height: 300 }
    });
    // Save
    const buffer = await workbook.xlsx.writeBuffer();
    saveAs(new Blob([buffer]), 'data_sheet.xlsx');
  };

  return (
    <Box sx={{ width: '100%' }}>
      {/* Top: Diagram and Controls (full width) */}
      <Paper sx={{ p: 2, mb: 2 }}>
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
          <CSVLink data={data} filename={fileName} style={{ textDecoration: 'none' }}>
            <Button variant="outlined" disabled={data.length === 0}>Download CSV / CSVダウンロード</Button>
          </CSVLink>
          */}
          <Button variant="outlined" onClick={handleDownloadGraphsPng} disabled={data.length === 0}>
            Download Graphs as PNG / グラフPNGダウンロード
          </Button>
          <Button variant="outlined" onClick={handleDownloadExcelWithGraph} disabled={data.length === 0}>
            Download data sheet / データシートダウンロード
          </Button>
        </Box>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {status && status.status && <Alert severity="info" sx={{ mt: 2 }}>Status: {status.status}</Alert>}
      </Paper>
      {/* Bottom: Graphs and Data Table side by side */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, width: '100%' }}>
        {/* Left: Graphs */}
        <Box sx={{ flex: 1, minWidth: 350, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 300, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6" gutterBottom>
              Live Graph / ライブグラフ
            </Typography>
            <Box sx={{ height: 250, mb: 2 }} ref={liveGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
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
                <LineChart data={data} margin={{ top: 10, right: 40, left: 40, bottom: 60 }}>
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
                  <Legend />
                  <Line type="monotone" dataKey="TEMF [mV]" stroke="#1976d2" dot={true} name="TEMF [mV]" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            {loading && <CircularProgress sx={{ mt: 2 }} />}
          </Paper>
        </Box>
        {/* Right: Data Table */}
        <Box sx={{ minWidth: 520, flex: '0 0 520px', mb: { xs: 2, md: 0 } }}>
          <Paper sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6" gutterBottom>
              Data Table / データ表
            </Typography>
            <TableContainer ref={tableContainerRef} sx={{ maxHeight: 600, overflowY: 'auto', overflowX: 'hidden' }}>
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
                  {data.map((row, idx) => (
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