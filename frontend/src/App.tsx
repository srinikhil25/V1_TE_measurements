import { ThemeProvider, createTheme, CssBaseline, Box, Container } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SeebeckMeasurementPanel from './components/SeebeckMeasurementPanel';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box sx={{ 
          minHeight: '100vh',
          bgcolor: 'background.default',
          py: 4
        }}>
          <Container maxWidth="lg">
            <SeebeckMeasurementPanel />
          </Container>
        </Box>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
