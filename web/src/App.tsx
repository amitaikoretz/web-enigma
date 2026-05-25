import BarChartIcon from '@mui/icons-material/BarChart'
import CloseIcon from '@mui/icons-material/Close'
import InsightsIcon from '@mui/icons-material/Insights'
import MenuIcon from '@mui/icons-material/Menu'
import SettingsSuggestIcon from '@mui/icons-material/SettingsSuggest'
import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Drawer,
  IconButton,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material'
import { useMemo, useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { ChartPage } from './components/ChartPage'
import { useSettings } from './settings/useSettings'
import { BacktestDetailPage } from './pages/BacktestDetailPage'
import { BacktestsListPage } from './pages/BacktestsListPage'
import { BacktestWizardPage } from './pages/BacktestWizardPage'
import { SettingsPage } from './pages/SettingsPage'

const NAV_ITEMS = [
  { label: 'Backtests', to: '/backtests', icon: <InsightsIcon /> },
  { label: 'Chart', to: '/chart', icon: <BarChartIcon /> },
  { label: 'Settings', to: '/settings', icon: <SettingsSuggestIcon /> },
]

function resolveLandingPage(preferredLandingPage: 'backtests' | 'new_backtest' | 'chart'): string {
  if (preferredLandingPage === 'backtests') {
    return '/backtests'
  }
  if (preferredLandingPage === 'chart') {
    return '/chart'
  }
  return '/backtests/new'
}

function NavButtons({
  onNavigate,
}: {
  onNavigate?: () => void
}) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
      {NAV_ITEMS.map((item) => (
        <Button
          key={item.to}
          color="inherit"
          component={NavLink}
          to={item.to}
          onClick={onNavigate}
          startIcon={item.icon}
          sx={{
            justifyContent: { xs: 'flex-start', sm: 'center' },
            '&.active': {
              bgcolor: 'rgba(255,255,255,0.12)',
            },
          }}
        >
          {item.label}
        </Button>
      ))}
    </Stack>
  )
}

function App() {
  const { platformSettings, appearance, loading } = useSettings()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const landingPage = useMemo(
    () => resolveLandingPage(platformSettings.platform_behavior.preferred_landing_page),
    [platformSettings.platform_behavior.preferred_landing_page],
  )

  if (loading) {
    return (
      <Stack sx={{ minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }} spacing={1.5}>
        <CircularProgress />
        <Typography color="text.secondary">Loading platform settings…</Typography>
      </Stack>
    )
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        backgroundImage:
          appearance.reduced_motion
            ? 'none'
            : 'radial-gradient(circle at top left, rgba(108,184,255,0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(14,165,183,0.12), transparent 28%)',
      }}
    >
      <AppBar
        position="sticky"
        elevation={0}
        sx={(theme) => ({
          backdropFilter: 'blur(18px)',
          bgcolor:
            theme.palette.mode === 'dark'
              ? 'rgba(13,17,23,0.82)'
              : 'rgba(255,255,255,0.84)',
          color: theme.palette.text.primary,
          borderBottom: `1px solid ${theme.palette.divider}`,
        })}
      >
        <Toolbar sx={{ justifyContent: 'space-between', gap: 2 }}>
          <Stack spacing={0.25}>
            <Typography variant="h6" component="h1">
              Kairos
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Backtesting workspace
            </Typography>
          </Stack>

          <Box sx={{ display: { xs: 'none', md: 'block' } }}>
            <NavButtons />
          </Box>

          <IconButton
            color="inherit"
            sx={{ display: { xs: 'inline-flex', md: 'none' } }}
            onClick={() => setMobileNavOpen(true)}
          >
            <MenuIcon />
          </IconButton>
        </Toolbar>
      </AppBar>

      <Drawer
        anchor="right"
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        sx={{ display: { xs: 'block', md: 'none' } }}
      >
        <Stack sx={{ width: 280, p: 2 }} spacing={2}>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">Navigate</Typography>
            <IconButton onClick={() => setMobileNavOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Stack>
          <NavButtons onNavigate={() => setMobileNavOpen(false)} />
        </Stack>
      </Drawer>

      <Container
        maxWidth={appearance.layout_width === 'wide' ? false : 'xl'}
        sx={{ py: 3 }}
      >
        <Routes>
          <Route path="/" element={<Navigate to={landingPage} replace />} />
          <Route path="/chart" element={<ChartPage />} />
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/backtests/new" element={<BacktestWizardPage />} />
          <Route path="/backtests/:backtestId" element={<BacktestDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Container>
    </Box>
  )
}

export default App
