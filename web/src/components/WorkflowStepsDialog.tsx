import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DownloadIcon from '@mui/icons-material/Download'
import RefreshIcon from '@mui/icons-material/Refresh'
import CloseIcon from '@mui/icons-material/Close'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Snackbar,
  Stack,
  TextField,
  Tab,
  Tabs,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { downloadWorkflowJson, fetchWorkflow, fetchWorkflowDebugConfig, fetchWorkflowPodLogs } from '../api/argo'
import type { ArgoWorkflow, WorkflowStepsDescriptor } from '../types/argo'
import { normalizeWorkflowSteps, type WorkflowStepSummary } from '../utils/workflowSteps'

type WorkflowFilter = 'all' | 'pending' | 'running' | 'succeeded' | 'failed' | 'error' | 'skipped'

interface WorkflowStepFetchState {
  loading: boolean
  error: string | null
  logs: string | null
  containerName: string | null
}

interface DebugConfigFetchState {
  loading: boolean
  error: string | null
  snippet: string | null
}

interface WorkflowStepsDialogProps extends WorkflowStepsDescriptor {
  open: boolean
  onClose: () => void
}

type StepDetailTab = 'overview' | 'inputs' | 'outputs' | 'logs'

function getStatusColor(phase: string | null | undefined): 'default' | 'info' | 'success' | 'warning' | 'error' {
  switch ((phase ?? '').toLowerCase()) {
    case 'running':
    case 'active':
      return 'info'
    case 'succeeded':
    case 'success':
      return 'success'
    case 'failed':
    case 'error':
      return 'error'
    case 'pending':
    case 'queued':
      return 'warning'
    default:
      return 'default'
  }
}

function formatFieldValue(value: string): string {
  return value.trim().length > 0 ? value : '—'
}

function isLongFieldValue(value: string): boolean {
  return value.length > 160 || value.includes('\n')
}

function ArgumentList({
  title,
  items,
}: {
  title: string
  items: Array<{ name: string; value: string }>
}) {
  const [expandedItems, setExpandedItems] = useState<Set<string>>(() => new Set())

  const toggleItem = (key: string) => {
    setExpandedItems((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {items.length > 0 ? (
        <Stack spacing={1}>
          {items.map((item) => {
            const itemKey = `${title}-${item.name}`
            const longValue = isLongFieldValue(item.value)
            const expanded = expandedItems.has(itemKey)
            return (
              <Box
                key={itemKey}
                sx={{
                  borderRadius: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'background.default',
                  px: 1.5,
                  py: 1.25,
                }}
              >
                <Stack spacing={0.5}>
                  <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                    {item.name}
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace',
                      fontSize: '0.85rem',
                      lineHeight: 1.55,
                      maxHeight: longValue && !expanded ? 88 : 'none',
                      overflow: longValue && !expanded ? 'hidden' : 'visible',
                      position: 'relative',
                    }}
                  >
                    {formatFieldValue(item.value)}
                  </Box>
                  {longValue && (
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => toggleItem(itemKey)}
                      sx={{ alignSelf: 'flex-start', px: 0, minWidth: 'auto' }}
                    >
                      {expanded ? 'Show less' : 'Show more'}
                    </Button>
                  )}
                </Stack>
              </Box>
            )
          })}
        </Stack>
      ) : (
        <Typography color="text.secondary" variant="body2">
          No {title.toLowerCase()} were recorded for this step.
        </Typography>
      )}
    </Stack>
  )
}

function TabPanel({
  active,
  children,
}: {
  active: boolean
  children: ReactNode
}) {
  if (!active) {
    return null
  }

  return <Box sx={{ minHeight: 0 }}>{children}</Box>
}

export function WorkflowStepsDialog({
  entityKind,
  entityLabel,
  workflowName,
  namespace,
  workflowTitle,
  open,
  onClose,
}: WorkflowStepsDialogProps) {
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'))
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [workflowError, setWorkflowError] = useState<string | null>(null)
  const [workflowDocument, setWorkflowDocument] = useState<ArgoWorkflow | null>(null)
  const [workflow, setWorkflow] = useState<WorkflowStepSummary[]>([])
  const [workflowPhase, setWorkflowPhase] = useState<string | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [selectedTab, setSelectedTab] = useState<StepDetailTab>('overview')
  const [stepFilter, setStepFilter] = useState<WorkflowFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [copied, setCopied] = useState(false)
  const [debugStateByPod, setDebugStateByPod] = useState<Record<string, DebugConfigFetchState>>({})
  const [logsStateByPod, setLogsStateByPod] = useState<Record<string, WorkflowStepFetchState>>({})
  const [snackbarMessage, setSnackbarMessage] = useState<string | null>(null)

  const loadLogsForStep = (step: WorkflowStepSummary, forceReload = false) => {
    const podName = step.podName
    if (!workflowName || !podName) {
      return
    }
    if (!forceReload && logsStateByPod[podName]) {
      return
    }
    setLogsStateByPod((current) => ({
      ...current,
      [podName]: { loading: true, error: null, logs: null, containerName: null },
    }))
    void fetchWorkflowPodLogs(workflowName, podName, namespace)
      .then((response) => {
        setLogsStateByPod((current) => ({
          ...current,
          [podName]: {
            loading: false,
            error: null,
            logs: response.logs,
            containerName: response.container_name,
          },
        }))
      })
      .catch((err) => {
        setLogsStateByPod((current) => ({
          ...current,
          [podName]: {
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load logs',
            logs: null,
            containerName: null,
          },
        }))
      })
  }

  const focusStep = (step: WorkflowStepSummary) => {
    setSelectedStepId(step.id)
    setSelectedTab('overview')
  }

  useEffect(() => {
    if (!open || !workflowName) {
      return undefined
    }

    let cancelled = false
    /* eslint-disable react-hooks/set-state-in-effect */
    setWorkflowLoading(true)
    setWorkflowError(null)
    setWorkflowDocument(null)
    setWorkflow([])
    setWorkflowPhase(null)
    setSelectedStepId(null)
    setSelectedTab('overview')
    setDebugStateByPod({})
    setLogsStateByPod({})
    /* eslint-enable react-hooks/set-state-in-effect */

    void fetchWorkflow(workflowName, namespace)
      .then((response) => {
        if (cancelled) {
          return
        }
        const nextSteps = normalizeWorkflowSteps(response)
        setWorkflowDocument(response)
        setWorkflow(nextSteps)
        setWorkflowPhase(response.status?.phase ?? null)
        if (nextSteps.length > 0) {
          const preferredStep =
            nextSteps.find((step) => ['failed', 'error'].includes((step.phase ?? '').toLowerCase())) ??
            nextSteps.find((step) => (step.phase ?? '').toLowerCase() === 'running') ??
            nextSteps[0]
          setSelectedStepId(preferredStep.id)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setWorkflowError(err instanceof Error ? err.message : 'Failed to load workflow')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setWorkflowLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [namespace, open, workflowName])

  const filteredSteps = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return workflow.filter((step) => {
      if (stepFilter !== 'all' && (step.phase ?? '').toLowerCase() !== stepFilter) {
        return false
      }
      if (!query) {
        return true
      }
      return step.searchText.includes(query)
    })
  }, [searchQuery, stepFilter, workflow])

  const selectedStep = useMemo(
    () => workflow.find((step) => step.id === selectedStepId) ?? filteredSteps[0] ?? null,
    [filteredSteps, selectedStepId, workflow],
  )

  useEffect(() => {
    if (filteredSteps.length === 0) {
      return
    }
    const hasSelectedStep = selectedStepId ? filteredSteps.some((step) => step.id === selectedStepId) : false
    if (!hasSelectedStep) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setSelectedStepId(filteredSteps[0].id)
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [filteredSteps, selectedStepId])

  useEffect(() => {
    if (!open || !workflowName || !selectedStep) {
      return undefined
    }

    const podName = selectedStep.podName
    if (!podName) {
      return undefined
    }
    if (!logsStateByPod[podName]) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setLogsStateByPod((current) => ({
        ...current,
        [podName]: { loading: true, error: null, logs: null, containerName: null },
      }))
      /* eslint-enable react-hooks/set-state-in-effect */
      void fetchWorkflowPodLogs(workflowName, podName, namespace)
        .then((response) => {
          setLogsStateByPod((current) => ({
            ...current,
            [podName]: {
              loading: false,
              error: null,
              logs: response.logs,
              containerName: response.container_name,
            },
          }))
        })
        .catch((err) => {
          setLogsStateByPod((current) => ({
            ...current,
            [podName]: {
              loading: false,
              error: err instanceof Error ? err.message : 'Failed to load logs',
              logs: null,
              containerName: null,
            },
          }))
        })
    }

    return undefined
  }, [namespace, open, selectedStep, selectedStep?.podName, workflowName, logsStateByPod])

  useEffect(() => {
    if (!open || !workflowName || !selectedStep) {
      return undefined
    }

    const podName = selectedStep.podName
    if (!podName) {
      return undefined
    }
    if (!debugStateByPod[podName]) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setDebugStateByPod((current) => ({
        ...current,
        [podName]: { loading: true, error: null, snippet: null },
      }))
      /* eslint-enable react-hooks/set-state-in-effect */
      void fetchWorkflowDebugConfig(workflowName, podName, namespace)
        .then((response) => {
          setDebugStateByPod((current) => ({
            ...current,
            [podName]: { loading: false, error: null, snippet: response.snippet },
          }))
        })
        .catch((err) => {
          setDebugStateByPod((current) => ({
            ...current,
            [podName]: {
              loading: false,
              error: err instanceof Error ? err.message : 'Failed to load debug configuration',
              snippet: null,
            },
          }))
        })
    }

    return undefined
  }, [namespace, open, selectedStep, selectedStep?.podName, workflowName, debugStateByPod])

  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const step of workflow) {
      const phase = (step.phase ?? 'unknown').toLowerCase()
      counts.set(phase, (counts.get(phase) ?? 0) + 1)
    }
    return Array.from(counts.entries()).sort(([left], [right]) => left.localeCompare(right))
  }, [workflow])

  const selectedPodName = selectedStep?.podName ?? null
  const debugState = selectedPodName ? debugStateByPod[selectedPodName] : null
  const logsState = selectedPodName ? logsStateByPod[selectedPodName] : null
  const logsContainerName = logsState?.containerName ?? null
  const logsErrorOutputs = selectedStep?.errorOutputs ?? []
  const selectedStepIsPodBacked = Boolean(selectedStep?.podName)
  const selectedStepPodLabel = selectedStep?.podName ?? ''
  const logsText =
    logsState?.logs && logsState.logs.trim().length > 0
      ? logsState.logs
      : logsErrorOutputs.length > 0
        ? logsErrorOutputs.map((entry) => `${entry.name}: ${entry.value}`).join('\n')
        : selectedStep?.rawNode.message ?? null
  const debugSnippet = debugState?.snippet ?? null
  const canDownloadWorkflowJson = Boolean(workflowDocument && workflowName)

  async function handleCopyDebugSnippet() {
    if (!debugSnippet) {
      return
    }
    try {
      await navigator.clipboard.writeText(debugSnippet)
      setCopied(true)
      setSnackbarMessage('Debug configuration copied to clipboard')
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setSnackbarMessage('Unable to copy debug configuration')
    }
  }

  function handleDownloadWorkflowJson() {
    if (!workflowDocument || !workflowName) {
      return
    }
    downloadWorkflowJson(workflowName, workflowDocument)
    setSnackbarMessage('Workflow JSON download started')
  }

  const hasLoadedSteps = workflow.length > 0

  return (
    <>
      <Dialog
        open={open && Boolean(workflowName)}
        onClose={onClose}
        fullScreen={fullScreen}
        fullWidth
        maxWidth="xl"
        aria-labelledby="workflow-steps-dialog-title"
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(4px)',
              backgroundColor: 'rgba(15, 23, 42, 0.38)',
            },
          },
          paper: {
            sx: {
              width: '100%',
              height: { xs: '100%', md: '88vh' },
              maxHeight: { xs: '100%', md: '88vh' },
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: { xs: 0, md: 3 },
              bgcolor: 'background.paper',
            },
          },
        }}
      >
        <DialogTitle
          id="workflow-steps-dialog-title"
          sx={{
            pb: 1.5,
            pr: 2,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="h5" component="span" sx={{ fontWeight: 700 }}>
                  Workflow steps
                </Typography>
                {workflowPhase && <Chip size="small" label={workflowPhase} color={getStatusColor(workflowPhase)} />}
                <Chip size="small" variant="outlined" label={entityKind} />
              </Stack>
              <Typography color="text.secondary" variant="body2">
                {entityLabel}
                {workflowTitle ? ` · ${workflowTitle}` : ''}
                {workflowName ? ` · ${workflowName}` : ''}
                {namespace ? ` (${namespace})` : ''}
              </Typography>
            </Stack>

            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <Tooltip title={canDownloadWorkflowJson ? 'Download Argo workflow JSON' : 'Workflow JSON is not available yet'}>
                <span>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<DownloadIcon />}
                    disabled={!canDownloadWorkflowJson}
                    onClick={handleDownloadWorkflowJson}
                  >
                    Download JSON
                  </Button>
                </span>
              </Tooltip>
              <IconButton aria-label="Close workflow steps dialog" onClick={onClose} size="small">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
        </DialogTitle>

        <DialogContent
          dividers
          sx={(muiTheme) => ({
            p: 0,
            overflow: 'hidden',
            display: 'flex',
            flex: 1,
            minHeight: 0,
            bgcolor: muiTheme.palette.background.default,
          })}
        >
          {workflowLoading ? (
            <Stack sx={{ py: 8, alignItems: 'center', width: '100%' }} spacing={1.5}>
              <CircularProgress />
              <Typography color="text.secondary">Loading workflow steps…</Typography>
            </Stack>
          ) : workflowError ? (
            <Box sx={{ p: 3, width: '100%' }}>
              <Alert severity="error">{workflowError}</Alert>
            </Box>
          ) : hasLoadedSteps ? (
            <Box
              sx={(muiTheme) => ({
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', md: '330px minmax(0, 1fr)' },
                height: '100%',
                minHeight: 0,
                width: '100%',
                bgcolor: muiTheme.palette.background.default,
              })}
            >
              <Box
                sx={(muiTheme) => ({
                  borderRight: { xs: 'none', md: `1px solid ${muiTheme.palette.divider}` },
                  borderBottom: { xs: `1px solid ${muiTheme.palette.divider}`, md: 'none' },
                  bgcolor: muiTheme.palette.background.paper,
                  p: 2,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1.5,
                  minHeight: 0,
                })}
              >
                    <Stack spacing={1.25}>
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                          Pods
                        </Typography>
                      </Stack>

                  <TextField
                    size="small"
                    fullWidth
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Filter steps"
                  />
                  <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
                    <Chip
                      size="small"
                      label="All"
                      variant={stepFilter === 'all' ? 'filled' : 'outlined'}
                      color={stepFilter === 'all' ? 'primary' : 'default'}
                      onClick={() => setStepFilter('all')}
                    />
                    {statusCounts.map(([phase, count]) => (
                      <Chip
                        key={phase}
                        size="small"
                        label={`${phase} (${count})`}
                        variant={stepFilter === phase ? 'filled' : 'outlined'}
                        color={getStatusColor(phase)}
                        onClick={() => setStepFilter(phase as WorkflowFilter)}
                      />
                    ))}
                  </Stack>
                </Stack>

                <Box sx={{ overflowY: 'auto', pr: 0.5, flex: 1, minHeight: 0 }}>
                  <Stack spacing={1}>
                    {filteredSteps.length > 0 ? (
                      filteredSteps.map((step) => {
                        const active = step.id === selectedStep?.id
                        const statusTone = getStatusColor(step.phase)
                        return (
                          <Paper
                            key={step.id}
                            variant="outlined"
                            onClick={() => focusStep(step)}
                            role="button"
                            tabIndex={0}
                            sx={(muiTheme) => ({
                              p: 1.5,
                              cursor: 'pointer',
                              borderColor: active ? muiTheme.palette.primary.main : muiTheme.palette.divider,
                              borderLeft: `4px solid ${active ? muiTheme.palette.primary.main : 'transparent'}`,
                              bgcolor: active
                                ? alpha(muiTheme.palette.primary.main, 0.06)
                                : muiTheme.palette.background.paper,
                              boxShadow: 'none',
                              position: 'relative',
                              overflow: 'hidden',
                              transition: 'border-color 120ms ease, background-color 120ms ease, transform 120ms ease, box-shadow 120ms ease',
                              '&:hover': {
                                borderColor: muiTheme.palette.primary.light,
                                bgcolor: muiTheme.palette.action.hover,
                                transform: 'translateY(-1px)',
                              },
                            })}
                          >
                            <Stack spacing={0.9}>
                              <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <Box sx={{ minWidth: 0 }}>
                                  <Typography variant="body2" sx={{ fontWeight: 750, lineHeight: 1.35 }} noWrap>
                                    {step.podName}
                                  </Typography>
                                  {step.displayName && (
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                      noWrap
                                      sx={{
                                        display: 'block',
                                        fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace',
                                      }}
                                    >
                                      {step.displayName}
                                    </Typography>
                                  )}
                                </Box>
                                <Chip size="small" label={step.phase ?? 'unknown'} color={statusTone} />
                              </Stack>
                              <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
                                <Chip size="small" variant="outlined" label={step.templateName ?? 'Template unknown'} />
                                {step.durationLabel && <Chip size="small" variant="outlined" label={step.durationLabel} />}
                              </Stack>
                            </Stack>
                          </Paper>
                        )
                      })
                    ) : (
                      <Alert severity="info">No steps match the current filters.</Alert>
                    )}
                  </Stack>
                </Box>
              </Box>

              <Box
                sx={(muiTheme) => ({
                  p: 2.5,
                  minWidth: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1.75,
                  bgcolor: muiTheme.palette.background.default,
                })}
              >
                {selectedStep ? (
                  <>
                    <Paper
                      variant="outlined"
                      sx={(muiTheme) => ({
                        p: 2,
                        bgcolor: muiTheme.palette.background.paper,
                        borderColor: muiTheme.palette.divider,
                        borderRadius: 2,
                      })}
                    >
                      <Stack spacing={1.25}>
                        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                          <Stack spacing={0.35}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ letterSpacing: 0.6, fontWeight: 700 }}
                            >
                              {selectedStep.podName}
                            </Typography>
                          </Stack>

                          <Tooltip title={copied ? 'Copied' : 'Copy debug configuration'}>
                            <span>
                              <Button
                                size="small"
                                variant="contained"
                                startIcon={<ContentCopyIcon />}
                                disabled={!selectedStepIsPodBacked}
                                onClick={() => void handleCopyDebugSnippet()}
                              >
                                Debug
                              </Button>
                            </span>
                          </Tooltip>
                        </Stack>
                      </Stack>
                    </Paper>

                    <Paper
                      variant="outlined"
                      sx={(muiTheme) => ({
                        flex: 1,
                        minHeight: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        overflow: 'hidden',
                        borderRadius: 2,
                        borderColor: muiTheme.palette.divider,
                        bgcolor: muiTheme.palette.background.paper,
                      })}
                    >
                      <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 1.5, pt: 1 }}>
                        <Tabs
                          value={selectedTab}
                          onChange={(_, value: StepDetailTab) => setSelectedTab(value)}
                          variant="scrollable"
                          scrollButtons="auto"
                        >
                          <Tab value="overview" label="Overview" />
                          <Tab value="inputs" label="Inputs" />
                          <Tab value="outputs" label="Outputs" />
                          <Tab value="logs" label="Logs" />
                        </Tabs>
                      </Box>

                      <Box
                        sx={{
                          flex: 1,
                          minHeight: 0,
                          overflowY: 'auto',
                          p: 2,
                        }}
                      >
                        <TabPanel active={selectedTab === 'overview'}>
                          <Stack spacing={2}>
                            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                              <Chip size="small" variant="outlined" label={selectedStep.templateName ?? 'Template unknown'} />
                              <Chip size="small" variant="outlined" label={selectedStep.displayName} />
                              {selectedStep.rawNode.startedAt && (
                                <Chip size="small" variant="outlined" label={`Started ${selectedStep.rawNode.startedAt}`} />
                              )}
                              {selectedStep.rawNode.finishedAt && (
                                <Chip size="small" variant="outlined" label={`Finished ${selectedStep.rawNode.finishedAt}`} />
                              )}
                            </Stack>
                            {logsErrorOutputs.length > 0 && (
                              <ArgumentList title="Captured error outputs" items={logsErrorOutputs} />
                            )}
                          </Stack>
                        </TabPanel>

                        <TabPanel active={selectedTab === 'inputs'}>
                          <ArgumentList title="Input parameters" items={selectedStep.inputArguments} />
                        </TabPanel>

                        <TabPanel active={selectedTab === 'outputs'}>
                          <ArgumentList title="Output parameters" items={selectedStep.outputArguments} />
                        </TabPanel>

                        <TabPanel active={selectedTab === 'logs'}>
                          <Stack spacing={1.5}>
                            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
                              <Stack spacing={0.25}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                  Logs
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {`Pod ${selectedStepPodLabel} · Step ${selectedStep.displayName}${logsContainerName ? ` · Container ${logsContainerName}` : ''}`}
                                </Typography>
                              </Stack>
                            <Tooltip title={selectedStepIsPodBacked ? 'Refresh logs' : 'Logs are unavailable for this step'}>
                              <span>
                                <IconButton
                                  size="small"
                                  onClick={() => {
                                    loadLogsForStep(selectedStep, true)
                                  }}
                                  disabled={!selectedStepIsPodBacked}
                                >
                                  <RefreshIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          </Stack>

                            {logsState?.loading ? (
                              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', py: 1 }}>
                                <CircularProgress size={18} />
                                <Typography color="text.secondary">Loading logs…</Typography>
                              </Stack>
                            ) : logsState?.error ? (
                              <Stack spacing={1.25}>
                                <Alert severity="warning">
                                  {logsState.error}. Showing captured workflow outputs instead.
                                </Alert>
                                {logsErrorOutputs.length > 0 ? (
                                  <ArgumentList title="Captured error outputs" items={logsErrorOutputs} />
                                ) : null}
                                {!logsErrorOutputs.length && selectedStep.rawNode.message && (
                              <Box
                                component="pre"
                                sx={(muiTheme) => ({
                                  m: 0,
                                  p: 1.5,
                                  maxHeight: 280,
                                  overflow: 'auto',
                                  borderRadius: 1.5,
                                  border: `1px solid ${muiTheme.palette.divider}`,
                                  bgcolor: muiTheme.palette.background.paper,
                                      fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace',
                                      fontSize: '0.82rem',
                                      lineHeight: 1.55,
                                      whiteSpace: 'pre-wrap',
                                    })}
                                  >
                                    {selectedStep.rawNode.message}
                                  </Box>
                                )}
                              </Stack>
                            ) : logsText ? (
                              <Box
                                component="pre"
                                sx={(muiTheme) => ({
                                  m: 0,
                                  p: 1.5,
                                  maxHeight: 420,
                                  overflow: 'auto',
                                  borderRadius: 1.5,
                                  border: `1px solid ${muiTheme.palette.divider}`,
                                  bgcolor: muiTheme.palette.background.paper,
                                  fontFamily: '"IBM Plex Mono", "SFMono-Regular", Menlo, monospace',
                                  fontSize: '0.82rem',
                                  lineHeight: 1.55,
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                })}
                              >
                                {logsText}
                              </Box>
                            ) : (
                              <Typography color="text.secondary" variant="body2">
                                No logs are available for this step yet.
                              </Typography>
                            )}
                          </Stack>
                        </TabPanel>

                      </Box>
                    </Paper>
                  </>
                ) : (
                  <Alert severity="info">
                    {workflow.length === 0
                      ? 'No workflow steps were found for this workflow.'
                      : 'Select a step to inspect its arguments, logs, and debug configuration.'}
                  </Alert>
                )}
              </Box>
            </Box>
          ) : (
            <Box sx={{ p: 3 }}>
              <Alert severity="info">No workflow steps were returned for this workflow.</Alert>
            </Box>
          )}
        </DialogContent>
      </Dialog>

      <Snackbar
        open={snackbarMessage !== null}
        autoHideDuration={2200}
        onClose={() => setSnackbarMessage(null)}
        message={snackbarMessage ?? ''}
      />
    </>
  )
}
