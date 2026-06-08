import AssignmentIcon from '@mui/icons-material/Assignment'
import BarChartIcon from '@mui/icons-material/BarChart'
import CloseIcon from '@mui/icons-material/Close'
import CloudDownloadIcon from '@mui/icons-material/CloudDownload'
import InsightsIcon from '@mui/icons-material/Insights'
import MenuIcon from '@mui/icons-material/Menu'
import ManageSearchIcon from '@mui/icons-material/ManageSearch'
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart'
import QueryStatsIcon from '@mui/icons-material/QueryStats'
import SettingsSuggestIcon from '@mui/icons-material/SettingsSuggest'
import ShieldIcon from '@mui/icons-material/Shield'
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

import { ApiHealthIndicator } from './components/ApiHealthIndicator'
import { ChartPage } from './components/ChartPage'
import { useSettings } from './settings/useSettings'
import { navActiveBackground, ThemeAtmosphere } from './theme/atmosphere'
import { getAppBarBackground, getPageBackground } from './theme/registry'
import { BacktestDetailPage } from './pages/BacktestDetailPage'
import { BacktestsListPage } from './pages/BacktestsListPage'
import { DatasetsListPage } from './pages/DatasetsListPage'
import { DatasetWizardPage } from './pages/DatasetWizardPage'
import { DatasetDetailPage } from './pages/DatasetDetailPage'
import { BacktestWizardPage } from './pages/BacktestWizardPage'
import { ContractsPage } from './pages/ContractsPage'
import { DataDownloadDetailPage } from './pages/DataDownloadDetailPage'
import { DataDownloadsListPage } from './pages/DataDownloadsListPage'
import { DataDownloadWizardPage } from './pages/DataDownloadWizardPage'
import { RuntimePage } from './pages/RuntimePage'
import { ScanRunDetailPage } from './pages/ScanRunDetailPage'
import { ScannersLandingPage } from './pages/ScannersLandingPage'
import { ScannerTypePage } from './pages/ScannerTypePage'
import { SettingsPage } from './pages/SettingsPage'
import { ModelsLandingPage } from './pages/ModelsLandingPage'
import { RiskModelsListPage } from './pages/RiskModelsListPage'
import { RiskModelDetailPage } from './pages/RiskModelDetailPage'
import { ReturnForecastModelsListPage } from './pages/ReturnForecastModelsListPage'
import { ReturnForecastModelDetailPage } from './pages/ReturnForecastModelDetailPage'
import { DailyIndexForecastModelsListPage } from './pages/DailyIndexForecastModelsListPage'
import { DailyIndexForecastModelDetailPage } from './pages/DailyIndexForecastModelDetailPage'
import { DailyIndexForecastWizardPage } from './pages/DailyIndexForecastWizardPage'
import { RiskModelWizardPage } from './pages/RiskModelWizardPage'
import { ReturnForecastModelWizardPage } from './pages/ReturnForecastModelWizardPage'
import { MarketOverviewPage } from './pages/MarketOverviewPage'

export const NAV_ITEMS = [
  { label: 'Overview', to: '/market-overview', icon: <QueryStatsIcon /> },
  { label: 'Backtests', to: '/backtests', icon: <InsightsIcon /> },
  { label: 'Models', to: '/models', icon: <ShieldIcon /> },
  { label: 'Data', to: '/data/downloads', icon: <CloudDownloadIcon /> },
  { label: 'Scanners', to: '/scanners', icon: <ManageSearchIcon /> },
  { label: 'Contracts', to: '/contracts', icon: <AssignmentIcon /> },
  { label: 'Runtime', to: '/runtime', icon: <MonitorHeartIcon /> },
  { label: 'Chart', to: '/chart', icon: <BarChartIcon /> },
  { label: 'Settings', to: '/settings', icon: <SettingsSuggestIcon /> },
]

function resolveLandingPage(preferredLandingPage: 'overview' | 'backtests' | 'new_backtest' | 'chart'): string {
  if (preferredLandingPage === 'overview') {
    return '/market-overview'
  }
  if (preferredLandingPage === 'backtests') {
    return '/backtests'
  }
  if (preferredLandingPage === 'chart') {
    return '/chart'
  }
  return '/market-overview'
}

function NavButtons({
  onNavigate,
}: {
  onNavigate?: () => void
}) {
  const theme = useTheme()
  const activeBg = navActiveBackground(
    theme.palette.mode === 'dark',
    theme.palette.primary.main,
  )

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
              bgcolor: activeBg,
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
  const pageBackground = getPageBackground(
    appearance.theme_preset,
    theme.palette.mode,
    appearance.reduced_motion,
  )
  const appBarBackground = getAppBarBackground(appearance.theme_preset, theme.palette.mode)
  const contentPaddingY = appearance.theme_preset === 'polar' ? 4 : 3

  return (
    <Box
      className={isDarkMode ? 'theme-dark' : 'theme-light'}
      sx={{
        position: 'relative',
        minHeight: '100vh',
        bgcolor: 'background.default',
        backgroundImage: pageBackground ?? 'none',
      }}
    >
      <ThemeAtmosphere
        preset={appearance.theme_preset}
        reducedMotion={appearance.reduced_motion}
      />

      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          position: 'relative',
          zIndex: 2,
          backdropFilter: 'blur(18px)',
          bgcolor: appBarBackground,
          color: theme.palette.text.primary,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between', gap: 2 }}>
          <Stack spacing={0.25} sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
              <Typography variant="h6" component="h1">
                Kalyx
              </Typography>
              <ApiHealthIndicator />
            </Stack>
          </Stack>

          <Box sx={{ display: { xs: 'none', md: 'flex' }, flex: 1, justifyContent: 'center' }}>
            <NavButtons />
          </Box>

          <IconButton
            color="inherit"
            sx={{ display: { xs: 'inline-flex', md: 'none' }, flexShrink: 0 }}
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation menu"
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
        sx={{ position: 'relative', zIndex: 1, py: contentPaddingY }}
      >
        <Routes>
          <Route path="/" element={<Navigate to={landingPage} replace />} />
          <Route path="/chart" element={<ChartPage />} />
          <Route path="/market-overview" element={<MarketOverviewPage />} />
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/backtests/datasets" element={<DatasetsListPage />} />
          <Route path="/backtests/datasets/new" element={<DatasetWizardPage />} />
          <Route path="/backtests/datasets/:datasetId" element={<DatasetDetailPage />} />
          <Route path="/backtests/new" element={<BacktestWizardPage />} />
          <Route path="/backtests/:backtestId" element={<BacktestDetailPage />} />
          <Route path="/models" element={<ModelsLandingPage />} />
          <Route path="/models/risk" element={<RiskModelsListPage />} />
          <Route path="/models/risk/new" element={<RiskModelWizardPage />} />
          <Route path="/models/risk/:groupId" element={<RiskModelDetailPage />} />
          <Route path="/models/returns" element={<ReturnForecastModelsListPage />} />
          <Route path="/models/returns/new" element={<ReturnForecastModelWizardPage />} />
          <Route path="/models/returns/:groupId" element={<ReturnForecastModelDetailPage />} />
          <Route path="/models/daily-index" element={<DailyIndexForecastModelsListPage />} />
          <Route path="/models/daily-index/new" element={<DailyIndexForecastWizardPage />} />
          <Route path="/models/daily-index/:groupId" element={<DailyIndexForecastModelDetailPage />} />
          <Route path="/data/downloads" element={<DataDownloadsListPage />} />
          <Route path="/data/downloads/new" element={<DataDownloadWizardPage />} />
          <Route path="/data/downloads/:jobId" element={<DataDownloadDetailPage />} />
          <Route path="/scanners" element={<ScannersLandingPage />} />
          <Route path="/scanners/:scanType" element={<ScannerTypePage />} />
          <Route path="/scanners/:scanType/runs/:scanId" element={<ScanRunDetailPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/runtime" element={<RuntimePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Container>
    </Box>
  )
}

export default App
