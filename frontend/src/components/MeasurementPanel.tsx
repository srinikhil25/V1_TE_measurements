import { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  TextField,
  Switch,
  FormControlLabel,
  CircularProgress,
  Alert,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { instrumentApi, type MeasurementData, type MeasurementConfig } from '../api/client';

const IRStreamPanel = () => {
  const [imgSrc, setImgSrc] = useState('');

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/api/ir_camera/ws');
    ws.onmessage = (event) => {
      setImgSrc('data:image/jpeg;base64,' + event.data);
    };
    ws.onerror = () => {
      setImgSrc('');
    };
    return () => ws.close();
  }, []);

  return (
    <Box sx={{ width: '100%', mb: 2 }}>
      <Typography variant="h6" gutterBottom>
        IR Camera Live Stream
      </Typography>
      {imgSrc ? (
        <img
          src={imgSrc}
          alt="IR Camera Stream"
          style={{ width: '100%', maxHeight: 400, objectFit: 'contain', borderRadius: 8, border: '1px solid #ccc' }}
        />
      ) : (
        <Box
          sx={{
            width: '100%',
            height: 400,
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
    </Box>
  );
};

const MeasurementPanel = () => {
  const queryClient = useQueryClient();
  const [config, setConfig] = useState<MeasurementConfig>({
    channel: 101,
    nplc: 1.0,
    auto_zero: true,
  });

  // Queries
  const statusQuery = useQuery({
    queryKey: ['status'],
    queryFn: instrumentApi.getStatus,
    refetchInterval: 5000,
  });

  const measurementsQuery = useQuery({
    queryKey: ['measurements'],
    queryFn: instrumentApi.getMeasurements,
    refetchInterval: 1000,
  });

  // Mutations
  const connectMutation = useMutation({
    mutationFn: instrumentApi.connect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: instrumentApi.disconnect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const configureMutation = useMutation({
    mutationFn: instrumentApi.configure,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
  });

  const measureMutation = useMutation({
    mutationFn: instrumentApi.takeMeasurement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['measurements'] });
    },
  });

  const clearMutation = useMutation({
    mutationFn: instrumentApi.clearMeasurements,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['measurements'] });
    },
  });

  // WebSocket connection for real-time updates
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/api/instrument/ws');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      queryClient.setQueryData(['measurements'], (old: MeasurementData[] = []) => [...old, data]);
    };

    return () => {
      ws.close();
    };
  }, [queryClient]);

  const handleConfigChange = (field: keyof MeasurementConfig) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = field === 'auto_zero' 
      ? event.target.checked 
      : Number(event.target.value);
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const isConnected = statusQuery.data?.connected;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Seebeck Measurement System
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 3 }}>
        {/* Status and Control Panel */}
        <Box sx={{ width: { xs: '100%', md: '33%' } }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Instrument Control
            </Typography>

            {statusQuery.isError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                Failed to fetch instrument status
              </Alert>
            )}

            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Status: {isConnected ? 'Connected' : 'Disconnected'}
              </Typography>
              {statusQuery.data?.resource_name && (
                <Typography variant="body2" color="text.secondary">
                  Resource: {statusQuery.data.resource_name}
                </Typography>
              )}
            </Box>

            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <Button
                variant="contained"
                color="primary"
                onClick={() => connectMutation.mutate()}
                disabled={isConnected || connectMutation.isPending}
              >
                {connectMutation.isPending ? <CircularProgress size={24} /> : 'Connect'}
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => disconnectMutation.mutate()}
                disabled={!isConnected || disconnectMutation.isPending}
              >
                {disconnectMutation.isPending ? <CircularProgress size={24} /> : 'Disconnect'}
              </Button>
            </Box>

            <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
              Configuration
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                label="Channel"
                type="number"
                value={config.channel}
                onChange={handleConfigChange('channel')}
                disabled={!isConnected}
              />
              <TextField
                label="NPLC"
                type="number"
                value={config.nplc}
                onChange={handleConfigChange('nplc')}
                disabled={!isConnected}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={config.auto_zero}
                    onChange={handleConfigChange('auto_zero')}
                    disabled={!isConnected}
                  />
                }
                label="Auto Zero"
              />
              <Button
                variant="contained"
                onClick={() => configureMutation.mutate(config)}
                disabled={!isConnected || configureMutation.isPending}
              >
                {configureMutation.isPending ? <CircularProgress size={24} /> : 'Apply Config'}
              </Button>
            </Box>
          </Paper>
        </Box>

        {/* Measurement Panel */}
        <Box sx={{ width: { xs: '100%', md: '67%' } }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Measurements
            </Typography>

            <Box sx={{ height: 400, mb: 2 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={measurementsQuery.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(timestamp) => new Date(timestamp * 1000).toLocaleTimeString()}
                  />
                  <YAxis />
                  <Tooltip
                    labelFormatter={(timestamp) => new Date(timestamp * 1000).toLocaleString()}
                    formatter={(value: number) => [value.toFixed(6), 'Voltage (V)']}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#1976d2"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>

            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button
                variant="contained"
                color="primary"
                onClick={() => measureMutation.mutate()}
                disabled={!isConnected || measureMutation.isPending}
              >
                {measureMutation.isPending ? <CircularProgress size={24} /> : 'Take Measurement'}
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => clearMutation.mutate()}
                disabled={!isConnected || clearMutation.isPending}
              >
                {clearMutation.isPending ? <CircularProgress size={24} /> : 'Clear Measurements'}
              </Button>
            </Box>
          </Paper>
        </Box>

        {/* IR Camera Panel */}
        <Box sx={{ width: { xs: '100%', md: '33%' } }}>
          <IRStreamPanel />
        </Box>
      </Box>
    </Box>
  );
};

export default MeasurementPanel; 