import { Alert, Box } from '@mui/material'
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ChartErrorBoundaryProps {
  children: ReactNode
}

interface ChartErrorBoundaryState {
  error: Error | null
}

export class ChartErrorBoundary extends Component<ChartErrorBoundaryProps, ChartErrorBoundaryState> {
  state: ChartErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ChartErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Chart render failed', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <Box sx={{ p: 2 }}>
          <Alert severity="error">
            The chart could not be rendered. Refresh the page or try a different date range.
          </Alert>
        </Box>
      )
    }

    return this.props.children
  }
}
