import React from 'react';
import { Box, Typography, Paper } from '@mui/material';

const SeebeckResistivityPanel: React.FC = () => {
  return (
    <Box sx={{ width: '100%', p: 2 }}>
      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          Seebeck and Resistivity Measurement / ゼーベック・抵抗率測定
        </Typography>
        <Typography variant="body1" sx={{ mt: 2, fontSize: '1.2rem' }}>
          Coming Soon...
        </Typography>
        {/* Future Seebeck and Resistivity measurement components will go here */}
      </Paper>
    </Box>
  );
};

export default SeebeckResistivityPanel; 