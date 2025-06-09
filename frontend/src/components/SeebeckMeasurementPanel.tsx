import React, { useState, useRef, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Grid, TextField, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress, Alert
} from '@mui/material';
import { CSVLink } from 'react-csv';
import axios from 'axios';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';

interface DataRow {
  "Time [s]": number;
  "TEMF [mV]": number;
  "Temp1 [oC]": number;
  "Temp2 [oC]": number;
}

const API_BASE_URL = 'http://localhost:8080/api/seebeck';

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

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Seebeck Measurement (Web)
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Measurement Parameters
            </Typography>
            <TextField label="Measurement Interval (s)" type="number" value={interval} onChange={e => setIntervalVal(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Pre Time (s)" type="number" value={preTime} onChange={e => setPreTime(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Start Value" type="number" value={startVolt} onChange={e => setStartVolt(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Stop Value" type="number" value={stopVolt} onChange={e => setStopVolt(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Inc. Rate (mA/s)" type="number" value={incRate} onChange={e => setIncRate(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Dec. Rate (mA/s)" type="number" value={decRate} onChange={e => setDecRate(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="Hold Time (s)" type="number" value={holdTime} onChange={e => setHoldTime(Number(e.target.value))} fullWidth margin="normal" />
            <TextField label="File Name" value={fileName} onChange={e => setFileName(e.target.value)} fullWidth margin="normal" />
            <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
              <Button variant="contained" color="primary" onClick={handleStart} disabled={running || loading}>
                Start Measurement
              </Button>
              <Button variant="outlined" color="secondary" onClick={handleStop} disabled={!running}>
                Stop Measurement
              </Button>
            </Box>
            <Box sx={{ mt: 2 }}>
              <CSVLink data={data} filename={fileName} style={{ textDecoration: 'none' }}>
                <Button variant="outlined" disabled={data.length === 0}>Download CSV</Button>
              </CSVLink>
            </Box>
            {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            {status && status.status && <Alert severity="info" sx={{ mt: 2 }}>Status: {status.status}</Alert>}
          </Paper>
        </Grid>
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Live Graph
            </Typography>
            <Box sx={{ height: 300, mb: 2 }}>
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
              Data Table
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Time [s]</TableCell>
                    <TableCell>TEMF [mV]</TableCell>
                    <TableCell>Temp1 [°C]</TableCell>
                    <TableCell>Temp2 [°C]</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{row["Time [s]"]}</TableCell>
                      <TableCell>{row["TEMF [mV]"]?.toFixed(3)}</TableCell>
                      <TableCell>{row["Temp1 [oC]"]?.toFixed(2)}</TableCell>
                      <TableCell>{row["Temp2 [oC]"]?.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {loading && <CircularProgress sx={{ mt: 2 }} />}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default SeebeckMeasurementPanel; 