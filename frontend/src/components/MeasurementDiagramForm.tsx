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

const boxStyle = {
  fill: '#ffff99',
  stroke: '#000',
  strokeWidth: 1,
};

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
    <Box sx={{ width: 480, mx: 'auto', mb: 3 }}>
      <svg width={480} height={300}>
        {/* Main diagram lines/arrows */}
        <rect x={10} y={30} width={460} height={200} fill="#fff" stroke="#000" strokeWidth={1} />
        {/* Pre time arrow */}
        <line x1={60} y1={200} x2={160} y2={200} stroke="#000" strokeWidth={2} markerEnd="url(#arrow)" />
        <text x={110} y={215} fontSize={14}>t<sub>Pre</sub></text>
        {/* Pre time box */}
        <foreignObject x={90} y={210} width={40} height={30}>
          <TextField
            value={preTime}
            onChange={e => setPreTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        <text x={135} y={230} fontSize={12}>-s</text>
        {/* Start value box */}
        <foreignObject x={40} y={180} width={40} height={30}>
          <TextField
            value={startVolt}
            onChange={e => setStartVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        {/* Stop value box */}
        <foreignObject x={400} y={80} width={40} height={30}>
          <TextField
            value={stopVolt}
            onChange={e => setStopVolt(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 36 } }}
          />
        </foreignObject>
        {/* Hold time arrow */}
        <line x1={220} y1={80} x2={380} y2={80} stroke="#d32f2f" strokeWidth={2} markerEnd="url(#arrow)" />
        <text x={290} y={70} fontSize={14}>t<sub>Hold</sub></text>
        {/* Hold time box */}
        <foreignObject x={320} y={50} width={60} height={30}>
          <TextField
            value={holdTime}
            onChange={e => setHoldTime(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={385} y={70} fontSize={14}>s</text>
        {/* Inc. Rate box */}
        <foreignObject x={180} y={120} width={60} height={30}>
          <TextField
            value={incRate}
            onChange={e => setIncRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={245} y={140} fontSize={14}>mA/s</text>
        <text x={180} y={115} fontSize={14}>Inc. Rate</text>
        {/* Dec. Rate box */}
        <foreignObject x={320} y={120} width={60} height={30}>
          <TextField
            value={decRate}
            onChange={e => setDecRate(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={385} y={140} fontSize={14}>mA/s</text>
        <text x={320} y={115} fontSize={14}>Dec. Rate</text>
        {/* Measurement Interval box */}
        <foreignObject x={200} y={10} width={60} height={30}>
          <TextField
            value={interval}
            onChange={e => setIntervalVal(Number(e.target.value))}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 50 } }}
          />
        </foreignObject>
        <text x={265} y={30} fontSize={14}>s</text>
        <text x={120} y={30} fontSize={16}>Measurement Interval</text>
        {/* File Name box */}
        <foreignObject x={180} y={260} width={120} height={30}>
          <TextField
            value={fileName}
            onChange={e => setFileName(e.target.value)}
            variant="outlined"
            size="small"
            inputProps={{ style: { background: '#ffff99', textAlign: 'center', width: 110 } }}
          />
        </foreignObject>
        <text x={120} y={280} fontSize={14}>File Name</text>
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