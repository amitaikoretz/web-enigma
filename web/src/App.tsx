import AssignmentIcon from '@mui/icons-material/Assignment'
import BarChartIcon from '@mui/icons-material/BarChart'
import CloseIcon from '@mui/icons-material/Close'
import CloudDownloadIcon from '@mui/icons-material/CloudDownload'
import InsightsIcon from '@mui/icons-material/Insights'
import MenuIcon from '@mui/icons-material/Menu'
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart'
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
  useTheme,
} from '@mui/material'
import { useMemo, useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { ChartPage } from './components/ChartPage'
import { useSettings } from './settings/useSettings'
import { BacktestDetailPage } from './pages/BacktestDetailPage'
import { BacktestsListPage } from './pages/BacktestsListPage'
import { BacktestWizardPage } from './pages/BacktestWizardPage'
import { ContractsPage } from './pages/ContractsPage'
import { DataDownloadDetailPage } from './pages/DataDownloadDetailPage'
import { DataDownloadsListPage } from './pages/DataDownloadsListPage'
import { DataDownloadWizardPage } from './pages/DataDownloadWizardPage'
import { RuntimePage } from './pages/RuntimePage'
import { SettingsPage } from './pages/SettingsPage'

const NAV_ITEMS = [
  { label: 'Backtests', to: '/backtests', icon: <InsightsIcon /> },
  { label: 'Data', to: '/data/downloads', icon: <CloudDownloadIcon /> },
  { label: 'Contracts', to: '/contracts', icon: <AssignmentIcon /> },
  { label: 'Runtime', to: '/runtime', icon: <MonitorHeartIcon /> },
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
  const theme = useTheme()
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

  const isDarkMode = theme.palette.mode === 'dark'

  return (
    <Box
      className={isDarkMode ? 'theme-dark' : 'theme-light'}
      sx={{
        position: 'relative',
        minHeight: '100vh',
        bgcolor: 'background.default',
        backgroundImage:
          appearance.reduced_motion
            ? 'none'
            : appearance.theme_preset === 'alpine'
              ? 'radial-gradient(circle at top left, rgba(2,132,199,0.06), transparent 35%), radial-gradient(circle at bottom right, rgba(30,58,138,0.04), transparent 45%)'
              : appearance.theme_preset === 'solaris'
                ? 'radial-gradient(circle at top right, rgba(245,158,11,0.05), transparent 40%)'
                : appearance.theme_preset === 'aurora'
                  ? 'none'
                  : 'radial-gradient(circle at top left, rgba(108,184,255,0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(14,165,183,0.12), transparent 28%)',
      }}
    >
      {appearance.theme_preset === 'aurora' && (
        <div className="aurora-bg">
          <div
            className="aurora-sphere sphere-1"
            style={appearance.reduced_motion ? { animation: 'none' } : undefined}
          />
          <div
            className="aurora-sphere sphere-2"
            style={appearance.reduced_motion ? { animation: 'none' } : undefined}
          />
          <div
            className="aurora-sphere sphere-3"
            style={appearance.reduced_motion ? { animation: 'none' } : undefined}
          />
        </div>
      )}

      <AppBar
        position="sticky"
        elevation={0}
        sx={(theme) => ({
          position: 'relative',
          zIndex: 2,
          backdropFilter: 'blur(18px)',
          bgcolor:
            theme.palette.mode === 'dark'
              ? appearance.theme_preset === 'aurora'
                ? 'rgba(11,15,25,0.65)'
                : 'rgba(13,17,23,0.82)'
              : appearance.theme_preset === 'alpine'
                ? 'rgba(241,245,249,0.8)'
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
        sx={{ display: { xs: 'block', md: 'none' }, zIndex: 1201 }}
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
        sx={{ position: 'relative', zIndex: 1, py: 3 }}
      >
        <Routes>
          <Route path="/" element={<Navigate to={landingPage} replace />} />
          <Route path="/chart" element={<ChartPage />} />
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/backtests/new" element={<BacktestWizardPage />} />
          <Route path="/backtests/:backtestId" element={<BacktestDetailPage />} />
          <Route path="/data/downloads" element={<DataDownloadsListPage />} />
          <Route path="/data/downloads/new" element={<DataDownloadWizardPage />} />
          <Route path="/data/downloads/:jobId" element={<DataDownloadDetailPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/runtime" element={<RuntimePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Container>
    </Box>
  )
}

export default App
