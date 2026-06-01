import ManageSearchIcon from '@mui/icons-material/ManageSearch'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import { Card, CardActionArea, CardContent, Grid, Stack, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'

const SCANNERS = [
  {
    type: 'momentum' as const,
    title: 'Stock Momentum Scanner',
    description: 'Find momentum candidates based on your parameters.',
    icon: <TrendingUpIcon />,
  },
  {
    type: 'options' as const,
    title: 'Options Scanner',
    description: 'Scan option chains for setups and filters.',
    icon: <ManageSearchIcon />,
  },
  {
    type: 'trend' as const,
    title: 'Trend Scanner',
    description: 'Identify trending names and technical trend signals.',
    icon: <ShowChartIcon />,
  },
]

export function ScannersLandingPage() {
  const navigate = useNavigate()

  return (
    <Stack spacing={2.5}>
      <Stack spacing={0.5}>
        <Typography variant="h4">Scanners</Typography>
        <Typography color="text.secondary">
          Runs execute in Argo Workflows and produce a JSON results file.
        </Typography>
      </Stack>

      <Grid container spacing={2}>
        {SCANNERS.map((scanner) => (
          <Grid key={scanner.type} size={{ xs: 12, md: 4 }}>
            <Card variant="outlined">
              <CardActionArea onClick={() => navigate(`/scanners/${scanner.type}`)}>
                <CardContent>
                  <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                    {scanner.icon}
                    <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                      <Typography variant="h6">{scanner.title}</Typography>
                      <Typography color="text.secondary">{scanner.description}</Typography>
                    </Stack>
                  </Stack>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Stack>
  )
}
