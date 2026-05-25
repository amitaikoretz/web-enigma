import {
  CssBaseline,
  ThemeProvider,
  useMediaQuery,
} from '@mui/material'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { fetchPlatformSettings, updatePlatformSettings } from '../api/settings'
import { SettingsContext, type SettingsContextValue } from './context'
import { defaultPlatformSettings } from './defaults'
import { loadAppearanceSettings, saveAppearanceSettings } from './storage'
import { createAppTheme } from '../theme'
import type { AppearanceSettings, PlatformSettings, ServerPlatformSettings } from '../types/settings'

const EASTERN_TIMEZONE = 'America/New_York'

function normalizeServerSettings(settings: ServerPlatformSettings): ServerPlatformSettings {
  if (settings.platform_behavior.timezone === 'UTC') {
    return {
      ...settings,
      platform_behavior: {
        ...settings.platform_behavior,
        timezone: EASTERN_TIMEZONE,
      },
    }
  }
  return settings
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)')
  const [appearance, setAppearanceState] = useState<AppearanceSettings>(() => loadAppearanceSettings())
  const [serverSettings, setServerSettings] = useState<ServerPlatformSettings>({
    backtest_defaults: defaultPlatformSettings.backtest_defaults,
    platform_behavior: defaultPlatformSettings.platform_behavior,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const theme = useMemo(
    () => createAppTheme(appearance, prefersDarkMode),
    [appearance, prefersDarkMode],
  )

  const platformSettings = useMemo<PlatformSettings>(
    () => ({
      appearance,
      ...serverSettings,
    }),
    [appearance, serverSettings],
  )

  useEffect(() => {
    saveAppearanceSettings(appearance)
  }, [appearance])

  const refreshPlatformSettings = async () => {
    setError(null)
    try {
      const next = normalizeServerSettings(await fetchPlatformSettings())
      setServerSettings(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load platform settings')
      setServerSettings({
        backtest_defaults: defaultPlatformSettings.backtest_defaults,
        platform_behavior: defaultPlatformSettings.platform_behavior,
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const next = normalizeServerSettings(await fetchPlatformSettings())
        if (!cancelled) {
          setServerSettings(next)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load platform settings')
          setServerSettings({
            backtest_defaults: defaultPlatformSettings.backtest_defaults,
            platform_behavior: defaultPlatformSettings.platform_behavior,
          })
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  const value: SettingsContextValue = {
    appearance,
    platformSettings,
    loading,
    saving,
    error,
    setAppearance: (next) => setAppearanceState(next),
    patchAppearance: (patch) =>
      setAppearanceState((current) => ({
        ...current,
        ...patch,
      })),
    resetAppearance: () => setAppearanceState(defaultPlatformSettings.appearance),
    savePlatformSettings: async (next) => {
      setSaving(true)
      setError(null)
      try {
        const payload: ServerPlatformSettings = {
          backtest_defaults: next.backtest_defaults,
          platform_behavior: next.platform_behavior,
        }
        const saved = await updatePlatformSettings(payload)
        setServerSettings(saved)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save platform settings')
        throw err
      } finally {
        setSaving(false)
      }
    },
    refreshPlatformSettings,
  }

  return (
    <SettingsContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </SettingsContext.Provider>
  )
}
