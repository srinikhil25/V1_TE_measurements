import React from 'react';
import { Box, Typography, Paper } from '@mui/material';

const IVMeasurementPanel: React.FC = () => {
  return (
    <Box sx={{ width: '100%', p: 2 }}>
      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          I-V Measurement / I-V測定
        </Typography>
        <Typography variant="body1">
          This page will contain controls and displays for I-V measurements.
        </Typography>
      </Paper>
      {/* Future I-V measurement components will go here */}
    </Box>
  );
};

export default IVMeasurementPanel; 