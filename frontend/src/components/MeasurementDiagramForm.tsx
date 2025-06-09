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
      <svg width={500} height={320}>
        {/* Main diagram lines/arrows */}
        <rect x={10} y={40} width={480} height={200} fill="#fff" stroke="#000" strokeWidth={1} />
        {/* Pre time arrow */}
        <line x1={60} y1={220} x2={160} y2={220} stroke="#000" strokeWidth={2} markerEnd="url(#arrow)" />
        <text x={110} y={240} fontSize={14}>t<sub>Pre</sub></text>
        {/* Pre time box */}
        <foreignObject x={90} y={245} width={40} height={30}>
          <TextField
            value={preTime}
            onChange={e => setPreTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        <text x={135} y={265} fontSize={12}>-s</text>
        {/* Start value box and label */}
        <text x={30} y={210} fontSize={14}>I₀</text>
        <foreignObject x={40} y={190} width={40} height={30}>
          <TextField
            value={startVolt}
            onChange={e => setStartVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        {/* Stop value box and label */}
        <foreignObject x={420} y={90} width={40} height={30}>
          <TextField
            value={stopVolt}
            onChange={e => setStopVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        <text x={465} y={110} fontSize={14}>I</text>
        {/* Hold time arrow and label */}
        <line x1={240} y1={90} x2={400} y2={90} stroke="#d32f2f" strokeWidth={2} markerEnd="url(#arrow)" />
        <text x={300} y={80} fontSize={14}>t<sub>Hold</sub></text>
        {/* Hold time box */}
        <foreignObject x={340} y={60} width={60} height={30}>
          <TextField
            value={holdTime}
            onChange={e => setHoldTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={405} y={80} fontSize={14}>s</text>
        {/* Inc. Rate box and label */}
        <text x={180} y={170} fontSize={14}>Inc. Rate</text>
        <foreignObject x={180} y={180} width={60} height={30}>
          <TextField
            value={incRate}
            onChange={e => setIncRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={245} y={200} fontSize={14}>mA/s</text>
        {/* Dec. Rate box and label */}
        <text x={320} y={170} fontSize={14}>Dec. Rate</text>
        <foreignObject x={320} y={180} width={60} height={30}>
          <TextField
            value={decRate}
            onChange={e => setDecRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={385} y={200} fontSize={14}>mA/s</text>
        {/* Measurement Interval box and label */}
        <text x={200} y={55} fontSize={16}>Measurement Interval</text>
        <foreignObject x={320} y={20} width={60} height={30}>
          <TextField
            value={interval}
            onChange={e => setIntervalVal(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={385} y={40} fontSize={14}>s</text>
        {/* File Name box and label */}
        <text x={120} y={300} fontSize={14}>File Name</text>
        <foreignObject x={180} y={280} width={120} height={30}>
          <TextField
            value={fileName}
            onChange={e => setFileName(e.target.value)}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 110 } }}
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