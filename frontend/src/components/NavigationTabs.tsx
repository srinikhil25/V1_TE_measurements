import React, { useState, useEffect } from 'react';
import { Tabs, Tab } from '@mui/material';
import { useNavigate, useLocation } from 'react-router-dom';

function NavigationTabs() {
  const navigate = useNavigate();
  const location = useLocation();
  const [value, setValue] = useState(0);

  useEffect(() => {
    switch (location.pathname) {
      case '/seebeck':
        setValue(0);
        break;
      case '/iv':
        setValue(1);
        break;
      case '/seebeck-resistivity':
        setValue(2);
        break;
      default:
        setValue(0);
        navigate('/seebeck', { replace: true });
        break;
    }
  }, [location.pathname, navigate]);

  const handleChange = (event: React.SyntheticEvent, newValue: number) => {
    setValue(newValue);
    switch (newValue) {
      case 0:
        navigate('/seebeck');
        break;
      case 1:
        navigate('/iv');
        break;
      case 2:
        navigate('/seebeck-resistivity');
        break;
      default:
        navigate('/seebeck');
        break;
    }
  };

  return (
    <Tabs
      value={value}
      onChange={handleChange}
      textColor="inherit"
      indicatorColor="secondary"
      centered
      sx={{
        minHeight: '32px',
        '& .MuiTab-root': {
          minHeight: '32px',
          minWidth: 'unset',
          px: { xs: 0.8, sm: 1.5 },
          fontSize: { xs: '0.7rem', sm: '0.75rem' },
          fontWeight: 600,
          textTransform: 'none',
          opacity: 0.8,
          '&.Mui-selected': {
            opacity: 1,
          },
        },
        '& .MuiTabs-indicator': {
          height: 2,
          borderRadius: '2px 2px 0 0',
        },
      }}
    >
      <Tab label="Seebeck" />
      <Tab label="I-V" />
      <Tab label="Seebeck & Resistivity" />
    </Tabs>
  );
}

export default NavigationTabs; 