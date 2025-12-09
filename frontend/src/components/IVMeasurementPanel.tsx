import React, { useState, useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  CircularProgress,
  FormControlLabel,
  Switch,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { runIVSweep } from '../api/iv';
import html2canvas from 'html2canvas';
import ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';

interface DataRow {
  idx: number;
  voltage: number | null;
  current: number | null;
  resistance: number | null;
  resistivity?: number | null;
}

const IVMeasurementPanel: React.FC = () => {
  const [startVoltage, setStartVoltage] = useState(0);
  const [stopVoltage, setStopVoltage] = useState(10);
  const [points, setPoints] = useState(10);
  const [delayMs, setDelayMs] = useState(50);
  const [currentLimit, setCurrentLimit] = useState(0.1);
  const [voltageLimit, setVoltageLimit] = useState(21);
  const [length, setLength] = useState<number | undefined>(undefined);
  const [width, setWidth] = useState<number | undefined>(undefined);
  const [thickness, setThickness] = useState<number | undefined>(undefined);
  const [data, setData] = useState<DataRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showResistivity, setShowResistivity] = useState(false);
  const [voltageUnit, setVoltageUnit] = useState<'V' | 'mV' | 'uV'>('V');
  const [currentUnit, setCurrentUnit] = useState<'A' | 'mA' | 'uA' | 'nA'>('A');
  const [graphFormat, setGraphFormat] = useState<'scatter' | 'scatter-line'>('scatter');
  const [fileName, setFileName] = useState<string>('iv_data.csv');
  const ivGraphRef = useRef<HTMLDivElement | null>(null);
  const rGraphRef = useRef<HTMLDivElement | null>(null);

  const handleRun = async () => {
    setError(null);
    setLoading(true);
    setData([]);
    try {
      const resp = await runIVSweep({
        start_voltage: startVoltage,
        stop_voltage: stopVoltage,
        points,
        delay_ms: delayMs,
        current_limit: currentLimit,
        voltage_limit: voltageLimit,
        length,
        width,
        thickness,
      });
      const rows: DataRow[] = resp.map((p, idx) => ({
        idx,
        voltage: p.voltage,
        current: p.current,
        resistance: p.resistance,
        resistivity: p.resistivity ?? null,
      }));
      setData(rows);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to run I-V sweep');
    } finally {
      setLoading(false);
    }
  };

  const ivChartData = data
    .filter((d) => d.voltage !== null && d.current !== null)
    .map((d) => {
      const vScale = voltageUnit === 'V' ? 1 : voltageUnit === 'mV' ? 1e3 : 1e6;
      const iScale =
        currentUnit === 'A' ? 1 : currentUnit === 'mA' ? 1e3 : currentUnit === 'uA' ? 1e6 : 1e9;
      return {
        voltage: d.voltage! * vScale,
        current: d.current! * iScale,
      };
    });

  const rChartData = data
    .filter((d) => d.voltage !== null && d.resistance !== null)
    .map((d) => ({ voltage: d.voltage!, resistance: d.resistance! }));

  const voltageLabel = `Voltage (${voltageUnit})`;
  const currentLabel = `Current (${currentUnit})`;

  const ivFitLine = (() => {
    if (ivChartData.length < 2) return null;
    const xs = ivChartData.map((p) => p.voltage);
    const ys = ivChartData.map((p) => p.current);
    const n = xs.length;
    const sumx = xs.reduce((a, b) => a + b, 0);
    const sumy = ys.reduce((a, b) => a + b, 0);
    const sumxy = xs.reduce((acc, x, idx) => acc + x * ys[idx], 0);
    const sumx2 = xs.reduce((acc, x) => acc + x * x, 0);
    const denom = n * sumx2 - sumx * sumx;
    if (denom === 0) return null;
    const m = (n * sumxy - sumx * sumy) / denom;
    const b = (sumy - m * sumx) / n;
    const minx = Math.min(...xs);
    const maxx = Math.max(...xs);
    return [
      { voltage: minx, current: m * minx + b },
      { voltage: maxx, current: m * maxx + b },
    ];
  })();

  const handleDownloadExcel = async () => {
    if (!data.length) return;

    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet('IV Data');

    // Header
    sheet.addRow(['#', 'Voltage (V)', 'Current (A)', 'Resistance (Ohm)', 'Resistivity (Ohm·m)']);

    data.forEach((d) => {
      sheet.addRow([
        d.idx + 1,
        d.voltage ?? '',
        d.current ?? '',
        d.resistance ?? '',
        d.resistivity ?? '',
      ]);
    });

    sheet.columns.forEach((col) => {
      col.width = 18;
    });

    // Capture graphs as images
    const captureAndInsert = async (ref: React.RefObject<HTMLDivElement>, rowStart: number, title: string) => {
      if (!ref.current) return rowStart;
      const canvas = await html2canvas(ref.current);
      const imgData = canvas.toDataURL('image/png');
      sheet.addRow([]);
      sheet.addRow([title]);
      const imageId = workbook.addImage({ base64: imgData, extension: 'png' });
      sheet.addImage(imageId, {
        tl: { col: 0, row: rowStart + 1 },
        ext: { width: canvas.width * 0.5, height: canvas.height * 0.5 },
      });
      return rowStart + Math.ceil((canvas.height * 0.5) / 15) + 3;
    };

    let rowCursor = data.length + 3;
    rowCursor = await captureAndInsert(ivGraphRef, rowCursor, 'I–V Curve');
    rowCursor = await captureAndInsert(rGraphRef, rowCursor, 'Resistance vs Voltage');

    const buffer = await workbook.xlsx.writeBuffer();
    saveAs(new Blob([buffer]), fileName.replace(/\.csv$/i, '.xlsx') || 'iv_data.xlsx');
  };

  return (
    <Box sx={{ width: '100%', p: 2 }}>
      <Typography variant="h5" gutterBottom sx={{ mb: 2 }}>
        I–V Measurement / I–V測定
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2 }}>
        {/* Left: Measurement Parameters */}
        <Box sx={{ flex: 1.1 }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Measurement Parameters
            </Typography>

            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
                gap: 1,
              }}
            >
              <TextField
                fullWidth
                label="Start Voltage (V)"
                type="number"
                value={startVoltage}
                onChange={(e) => setStartVoltage(parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Stop Voltage (V)"
                type="number"
                value={stopVoltage}
                onChange={(e) => setStopVoltage(parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Points"
                type="number"
                value={points}
                onChange={(e) => setPoints(parseInt(e.target.value, 10))}
                size="small"
                inputProps={{ min: 2 }}
              />
              <TextField
                fullWidth
                label="Delay (ms)"
                type="number"
                value={delayMs}
                onChange={(e) => setDelayMs(parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Current limit (A)"
                type="number"
                value={currentLimit}
                onChange={(e) => setCurrentLimit(parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Voltage limit (V)"
                type="number"
                value={voltageLimit}
                onChange={(e) => setVoltageLimit(parseFloat(e.target.value))}
                size="small"
              />
            </Box>

            <Typography variant="subtitle1" sx={{ mt: 2, mb: 1 }}>
              Sample Dimensions (optional, for resistivity)
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
                gap: 1,
              }}
            >
              <TextField
                fullWidth
                label="Length (m)"
                type="number"
                value={length ?? ''}
                onChange={(e) => setLength(e.target.value === '' ? undefined : parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Width (m)"
                type="number"
                value={width ?? ''}
                onChange={(e) => setWidth(e.target.value === '' ? undefined : parseFloat(e.target.value))}
                size="small"
              />
              <TextField
                fullWidth
                label="Thickness (m)"
                type="number"
                value={thickness ?? ''}
                onChange={(e) => setThickness(e.target.value === '' ? undefined : parseFloat(e.target.value))}
                size="small"
              />
            </Box>

            <FormControlLabel
              sx={{ mt: 1 }}
              control={
                <Switch
                  checked={showResistivity}
                  onChange={(e) => setShowResistivity(e.target.checked)}
                />
              }
              label="Show resistivity (requires sample dimensions)"
            />

            <Button
              sx={{ mt: 2 }}
              variant="contained"
              fullWidth
              onClick={handleRun}
              disabled={loading}
            >
              {loading ? 'Running...' : 'Do it'}
            </Button>
            {error && (
              <Alert sx={{ mt: 1 }} severity="error">
                {error}
              </Alert>
            )}

            {/* Data Handling */}
            <Typography variant="h6" sx={{ mt: 3 }} gutterBottom>
              Data Handling
            </Typography>

            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Voltage
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, mb: 1 }}>
              {(['V', 'mV', 'uV'] as const).map((u) => (
                <FormControlLabel
                  key={u}
                  control={
                    <input
                      type="radio"
                      checked={voltageUnit === u}
                      onChange={() => setVoltageUnit(u)}
                      style={{ marginRight: 6 }}
                    />
                  }
                  label={u}
                />
              ))}
            </Box>

            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Current
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, mb: 1 }}>
              {(['A', 'mA', 'uA', 'nA'] as const).map((u) => (
                <FormControlLabel
                  key={u}
                  control={
                    <input
                      type="radio"
                      checked={currentUnit === u}
                      onChange={() => setCurrentUnit(u)}
                      style={{ marginRight: 6 }}
                    />
                  }
                  label={u}
                />
              ))}
            </Box>

            <Button
              sx={{ mt: 1 }}
              variant="outlined"
              fullWidth
              onClick={() => {
                // changing units triggers re-render; no extra action needed
              }}
            >
              Change Scales
            </Button>

            {/* Graph Format */}
            <Typography variant="h6" sx={{ mt: 3 }} gutterBottom>
              Graph Format
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <FormControlLabel
                control={
                  <input
                    type="radio"
                    checked={graphFormat === 'scatter'}
                    onChange={() => setGraphFormat('scatter')}
                    style={{ marginRight: 6 }}
                  />
                }
                label="Scatter plot"
              />
              <FormControlLabel
                control={
                  <input
                    type="radio"
                    checked={graphFormat === 'scatter-line'}
                    onChange={() => setGraphFormat('scatter-line')}
                    style={{ marginRight: 6 }}
                  />
                }
                label="Scatter plot (with linear approximation)"
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 2 }}>
              <TextField
                fullWidth
                label="FileName"
                size="small"
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
              />
              <Button variant="contained" onClick={handleDownloadExcel}>
                Save (data + graphs)
              </Button>
            </Box>
          </Paper>
        </Box>

        {/* Right: Data and Graphs */}
        <Box sx={{ flex: 1.4, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Data Table
            </Typography>
            <TableContainer sx={{ maxHeight: 260 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>#</TableCell>
                    <TableCell>Voltage (V)</TableCell>
                    <TableCell>Current (A)</TableCell>
                    <TableCell>Resistance (Ω)</TableCell>
                    {showResistivity && <TableCell>Resistivity (Ω·m)</TableCell>}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.map((row) => (
                    <TableRow key={row.idx}>
                      <TableCell>{row.idx + 1}</TableCell>
                      <TableCell>{row.voltage !== null && row.voltage !== undefined ? row.voltage.toFixed(6) : '—'}</TableCell>
                      <TableCell>{row.current !== null && row.current !== undefined ? row.current.toExponential(3) : '—'}</TableCell>
                      <TableCell>{row.resistance !== null && row.resistance !== undefined ? row.resistance.toExponential(3) : '—'}</TableCell>
                      {showResistivity && (
                        <TableCell>
                          {row.resistivity !== null && row.resistivity !== undefined ? row.resistivity.toExponential(3) : '—'}
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {loading && <CircularProgress size={24} sx={{ mt: 2 }} />}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              I–V Curve
            </Typography>
            <Box sx={{ height: 260 }} ref={ivGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={ivChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <ReferenceLine x={0} stroke="#000" />
                  <ReferenceLine y={0} stroke="#000" />
                  <XAxis
                    type="number"
                    dataKey="voltage"
                    domain={['auto', 'auto']}
                    label={{ value: voltageLabel, position: 'insideBottom', offset: -5 }}
                  />
                  <YAxis
                    type="number"
                    domain={['auto', 'auto']}
                    label={{ value: currentLabel, angle: -90, position: 'insideLeft' }}
                  />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="current" stroke="#1976d2" dot />
                  {graphFormat === 'scatter-line' && ivFitLine && (
                    <Line
                      type="linear"
                      data={ivFitLine}
                      dataKey="current"
                      stroke="#555"
                      dot={false}
                      legendType="none"
                      name="fit"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </Box>

            <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
              Resistance vs Voltage
            </Typography>
            <Box sx={{ height: 260 }} ref={rGraphRef}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <ReferenceLine x={0} stroke="#000" />
                  <ReferenceLine y={0} stroke="#000" />
                  <XAxis
                    type="number"
                    dataKey="voltage"
                    domain={['auto', 'auto']}
                    label={{ value: 'Voltage (V)', position: 'insideBottom', offset: -5 }}
                  />
                  <YAxis
                    type="number"
                    domain={['auto', 'auto']}
                    label={{ value: 'Resistance (Ω)', angle: -90, position: 'insideLeft' }}
                  />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="resistance" stroke="#d32f2f" dot />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
};

export default IVMeasurementPanel;