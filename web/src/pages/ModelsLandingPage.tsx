import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import BoltIcon from '@mui/icons-material/Bolt'
import ShieldIcon from '@mui/icons-material/Shield'
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import { useMemo } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') && value.length > 1 ? value.slice(0, -1) : value
}

function familyFromPath(pathname: string): 'risk' | 'returns' | 'daily-index' | 'overview' {
  const normalized = stripTrailingSlash(pathname)
  if (normalized.startsWith('/models/risk')) {
    return 'risk'
  }
  if (normalized.startsWith('/models/returns')) {
    return 'returns'
  }
  if (normalized.startsWith('/models/daily-index')) {
    return 'daily-index'
  }
  return 'overview'
}

export function ModelsLandingPage() {
  const location = useLocation()
  const selected = useMemo(() => familyFromPath(location.pathname), [location.pathname])

  return (
    <Stack spacing={3}>
      <Stack spacing={0.75}>
        <Typography variant="h4" component="h1">
          Models
        </Typography>
        <Typography color="text.secondary" sx={{ maxWidth: 820 }}>
          Browse risk models, return forecast models, and the new Daily Index Forecast family from one shared entry
          point. All three preserve the same workflow diagnostics and status scaffolding.
        </Typography>
      </Stack>

      <Tabs value={selected} variant="scrollable" allowScrollButtonsMobile>
        <Tab
          value="overview"
          label="Overview"
          component={RouterLink}
          to="/models"
          icon={<ShieldIcon />}
          iconPosition="start"
        />
        <Tab
          value="risk"
          label="Risk Models"
          component={RouterLink}
          to="/models/risk"
          icon={<ShieldIcon />}
          iconPosition="start"
        />
        <Tab
          value="returns"
          label="Return Forecast Models"
          component={RouterLink}
          to="/models/returns"
          icon={<BoltIcon />}
          iconPosition="start"
        />
        <Tab
          value="daily-index"
          label="Daily Index Forecast"
          component={RouterLink}
          to="/models/daily-index"
          icon={<BoltIcon />}
          iconPosition="start"
        />
      </Tabs>

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
        }}
      >
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.25}>
              <ShieldIcon color="primary" />
              <Typography variant="h6">Risk Models</Typography>
              <Typography color="text.secondary">
                Training-set driven model groups with detailed targets, metrics, and workflow diagnostics.
              </Typography>
            </Stack>
          </CardContent>
          <CardActions sx={{ px: 2, pb: 2 }}>
            <Button component={RouterLink} to="/models/risk" endIcon={<ArrowForwardIcon />}>
              Open risk models
            </Button>
          </CardActions>
        </Card>

        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.25}>
              <BoltIcon color="warning" />
              <Typography variant="h6">Return Forecast Models</Typography>
              <Typography color="text.secondary">
                Short-horizon forecast groups with the same operational workflow treatment and status controls.
              </Typography>
            </Stack>
          </CardContent>
          <CardActions sx={{ px: 2, pb: 2 }}>
            <Button component={RouterLink} to="/models/returns" endIcon={<ArrowForwardIcon />}>
              Open return forecasts
            </Button>
          </CardActions>
        </Card>

        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.25}>
              <BoltIcon color="info" />
              <Typography variant="h6">Daily Index Forecast</Typography>
              <Typography color="text.secondary">
                Research-only daily forecast runs with reusable session-level features, walk-forward evaluation, and
                holdout metrics.
              </Typography>
            </Stack>
          </CardContent>
          <CardActions sx={{ px: 2, pb: 2 }}>
            <Button component={RouterLink} to="/models/daily-index" endIcon={<ArrowForwardIcon />}>
              Open daily index forecasts
            </Button>
          </CardActions>
        </Card>
      </Box>
    </Stack>
  )
}
