import { ThemeProvider, createTheme, CssBaseline, Box, Container, IconButton, AppBar, Toolbar, Typography } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SeebeckMeasurementPanel from './components/SeebeckMeasurementPanel';
import IVMeasurementPanel from './components/IVMeasurementPanel';
import SeebeckResistivityPanel from './components/SeebeckResistivityPanel';
import NavigationTabs from './components/NavigationTabs';
import { useMemo, useState, useEffect } from 'react';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';

const queryClient = new QueryClient();

function App() {
  // Theme mode state with localStorage persistence
  const [mode, setMode] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('themeMode');
    return saved === 'dark' ? 'dark' : 'light';
  });

  useEffect(() => {
    localStorage.setItem('themeMode', mode);
  }, [mode]);

  const theme = useMemo(() => createTheme({
    palette: {
      mode,
      primary: { main: '#1976d2' },
      secondary: { main: '#dc004e' },
      background: {
        default: mode === 'light' ? '#f0f2f5' : '#121212',
        paper: mode === 'light' ? '#ffffff' : '#1e1e1e',
      },
    },
    typography: {
      fontFamily: 'Roboto, Arial, sans-serif',
    },
  }), [mode]);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter>
          <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: 4 }}>
            <AppBar position="static" color="primary" elevation={0} sx={{ py: 0 }}>
              <Toolbar sx={{ minHeight: { xs: '48px', md: '56px' }, py: 0, justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', py: 0 }}>
                  <Typography variant="subtitle2" component="div" sx={{ fontWeight: 600, lineHeight: 1.1 }}>
                    TE - Measurements
                  </Typography>
                  <Typography variant="caption" component="div" sx={{ mt: 0, lineHeight: 1.1, color: 'rgba(255, 255, 255, 0.7)' }}>
                    Ikeda-Hamasaki Laboratory
                  </Typography>
                </Box>
                <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'unset' }}>
                  <NavigationTabs />
                </Box>
                <IconButton onClick={() => setMode(mode === 'light' ? 'dark' : 'light')} color="inherit" size="small">
                  {mode === 'dark' ? <Brightness7Icon sx={{ fontSize: '1.3rem' }} /> : <Brightness4Icon sx={{ fontSize: '1.3rem' }} />}
                </IconButton>
              </Toolbar>
            </AppBar>
            <Container maxWidth="lg" sx={{ mt: 4 }}>
              <Routes>
                <Route path="/" element={<SeebeckMeasurementPanel />} />
                <Route path="/seebeck" element={<SeebeckMeasurementPanel />} />
                <Route path="/iv" element={<IVMeasurementPanel />} />
                <Route path="/seebeck-resistivity" element={<SeebeckResistivityPanel />} />
              </Routes>
            </Container>
          </Box>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
