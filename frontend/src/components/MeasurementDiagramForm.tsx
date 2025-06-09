import React from 'react';
import { TextField, Box } from '@mui/material';

interface MeasurementDiagramFormProps {
  interval: number;
  setIntervalVal: (v: number) => void;
  preTime: number;
  setPreTime: (v: number) => void;
  startVolt: number;
  setStartVolt: (v: number) => void;
  stopVolt: number;
  setStopVolt: (v: number) => void;
  incRate: number;
  setIncRate: (v: number) => void;
  decRate: number;
  setDecRate: (v: number) => void;
  holdTime: number;
  setHoldTime: (v: number) => void;
  fileName: string;
  setFileName: (v: string) => void;
}

const MeasurementDiagramForm: React.FC<MeasurementDiagramFormProps> = ({
  interval, setIntervalVal,
  preTime, setPreTime,
  startVolt, setStartVolt,
  stopVolt, setStopVolt,
  incRate, setIncRate,
  decRate, setDecRate,
  holdTime, setHoldTime,
  fileName, setFileName,
}) => {
  return (
    <Box sx={{ width: 500, mx: 'auto', mb: 3 }}>
      <svg width={500} height={340}>
        {/* Main box */}
        <rect x={10} y={40} width={480} height={200} fill="#fff" stroke="#000" strokeWidth={1} />
        {/* Y axis */}
        <line x1={60} y1={220} x2={60} y2={60} stroke="#000" strokeWidth={2} />
        {/* X axis */}
        <line x1={60} y1={220} x2={440} y2={220} stroke="#000" strokeWidth={2} markerEnd="url(#arrow)" />
        {/* Pre time horizontal */}
        <line x1={60} y1={200} x2={140} y2={200} stroke="#000" strokeWidth={2} />
        {/* Pre time vertical */}
        <line x1={140} y1={200} x2={140} y2={220} stroke="#000" strokeWidth={2} />
        {/* Pre time dashed */}
        <line x1={140} y1={200} x2={140} y2={80} stroke="#000" strokeWidth={1} strokeDasharray="4 3" />
        {/* Ramp up */}
        <polyline points="140,200 200,120 320,120" fill="none" stroke="#d32f2f" strokeWidth={2} />
        {/* Plateau */}
        <polyline points="320,120 400,120" fill="none" stroke="#d32f2f" strokeWidth={2} />
        {/* Ramp down */}
        <polyline points="400,120 460,200" fill="none" stroke="#d32f2f" strokeWidth={2} />
        {/* Hold time arrow */}
        <line x1={340} y1={110} x2={390} y2={110} stroke="#d32f2f" strokeWidth={2} markerEnd="url(#arrow)" />
        {/* Measurement Interval label and box */}
        <text x={140} y={60} fontSize={16}>Measurement Interval</text>
        <foreignObject x={270} y={40} width={40} height={28}>
          <TextField
            value={interval}
            onChange={e => setIntervalVal(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 32 } }}
          />
        </foreignObject>
        <text x={315} y={60} fontSize={14}>s</text>
        {/* Pre time label and box */}
        <text x={80} y={215} fontSize={14}>t<sub>Pre</sub></text>
        <foreignObject x={110} y={205} width={32} height={28}>
          <TextField
            value={preTime}
            onChange={e => setPreTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 28 } }}
          />
        </foreignObject>
        <text x={145} y={220} fontSize={12}>-s</text>
        {/* Start value label and box */}
        <text x={30} y={195} fontSize={14}>I₀</text>
        <foreignObject x={40} y={180} width={32} height={28}>
          <TextField
            value={startVolt}
            onChange={e => setStartVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 28 } }}
          />
        </foreignObject>
        {/* Stop value label and box */}
        <foreignObject x={440} y={110} width={32} height={28}>
          <TextField
            value={stopVolt}
            onChange={e => setStopVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 28 } }}
          />
        </foreignObject>
        <text x={475} y={130} fontSize={14}>I</text>
        {/* Hold time label and box */}
        <text x={350} y={100} fontSize={14}>t<sub>Hold</sub></text>
        <foreignObject x={370} y={80} width={48} height={28}>
          <TextField
            value={holdTime}
            onChange={e => setHoldTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 40 } }}
          />
        </foreignObject>
        <text x={420} y={100} fontSize={14}>s</text>
        {/* Inc. Rate label and box */}
        <text x={180} y={150} fontSize={14}>Inc. Rate</text>
        <foreignObject x={180} y={160} width={48} height={28}>
          <TextField
            value={incRate}
            onChange={e => setIncRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 40 } }}
          />
        </foreignObject>
        <text x={230} y={180} fontSize={14}>mA/s</text>
        {/* Dec. Rate label and box */}
        <text x={320} y={150} fontSize={14}>Dec. Rate</text>
        <foreignObject x={320} y={160} width={48} height={28}>
          <TextField
            value={decRate}
            onChange={e => setDecRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 40 } }}
          />
        </foreignObject>
        <text x={370} y={180} fontSize={14}>mA/s</text>
        {/* File Name label and box */}
        <text x={120} y={300} fontSize={14}>File Name</text>
        <foreignObject x={180} y={285} width={140} height={28}>
          <TextField
            value={fileName}
            onChange={e => setFileName(e.target.value)}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 120 } }}
          />
        </foreignObject>
        {/* SVG arrow marker */}
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="10" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L10,5 L0,10 L2,5 Z" fill="#000" />
          </marker>
        </defs>
      </svg>
    </Box>
  );
};

export default MeasurementDiagramForm; 