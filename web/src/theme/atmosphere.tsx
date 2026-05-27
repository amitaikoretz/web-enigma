import { alpha, Box } from '@mui/material'

import type { ThemePreset } from '../types/settings'
import { getThemePresetDefinition } from './presets'

interface ThemeAtmosphereProps {
  preset: ThemePreset
  reducedMotion: boolean
}

export function ThemeAtmosphere({ preset, reducedMotion }: ThemeAtmosphereProps) {
  const definition = getThemePresetDefinition(preset)

  if (definition.auroraAtmosphere) {
    return (
      <div className="aurora-bg">
        <div
          className="aurora-sphere sphere-1"
          style={reducedMotion ? { animation: 'none' } : undefined}
        />
        <div
          className="aurora-sphere sphere-2"
          style={reducedMotion ? { animation: 'none' } : undefined}
        />
        <div
          className="aurora-sphere sphere-3"
          style={reducedMotion ? { animation: 'none' } : undefined}
        />
      </div>
    )
  }

  if (!definition.glassAtmosphere || reducedMotion) {
    return null
  }

  return (
    <Box className="glass-atmosphere" aria-hidden>
      <div className={`glass-wash glass-wash-${preset}`} />
      <div className={`glass-wash glass-wash-${preset}-b`} />
    </Box>
  )
}

export function navActiveBackground(isDarkMode: boolean, primaryMain: string): string {
  return isDarkMode ? 'rgba(255,255,255,0.12)' : alpha(primaryMain, 0.08)
}
