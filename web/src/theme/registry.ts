import type { ThemePreset } from '../types/settings'

import {
  getThemePresetDefinition,
  THEME_PRESET_DEFINITIONS,
  type ThemePresetDefinition,
  type ThemePresetGroup,
} from './presets'

export const ADAPTIVE_THEME_PRESETS: ThemePreset[] = ['default']

export const LIGHT_THEME_PRESETS: ThemePreset[] = [
  'alpine',
  'fjord',
  'fjord_porcelain',
  'oslo',
  'helsinki',
  'polar',
  'frost',
  'silica',
  'alto',
  'glacial',
  'glacier_lilac',
  'graphite_teal',
]

export const DARK_THEME_PRESETS: ThemePreset[] = [
  'solaris',
  'aurora',
  'fjord_ink_fx',
  'deep_fjord_fx',
  'aurora_slate',
  'obsidian_cobalt',
  'plum_neon',
  'steel_ember',
]

export const THEME_PRESET_GROUP_LABELS: Record<ThemePresetGroup, string> = {
  adaptive: 'Adaptive',
  light: 'Light themes',
  dark: 'Dark themes',
}

export const THEME_PRESET_GROUPS: Array<{
  group: ThemePresetGroup
  presets: ThemePreset[]
}> = [
  { group: 'adaptive', presets: ADAPTIVE_THEME_PRESETS },
  { group: 'light', presets: LIGHT_THEME_PRESETS },
  { group: 'dark', presets: DARK_THEME_PRESETS },
]

export function isLightThemePreset(preset: ThemePreset): boolean {
  return LIGHT_THEME_PRESETS.includes(preset)
}

export function isDarkThemePreset(preset: ThemePreset): boolean {
  return DARK_THEME_PRESETS.includes(preset)
}

export function isAdaptiveThemePreset(preset: ThemePreset): boolean {
  return ADAPTIVE_THEME_PRESETS.includes(preset)
}

export function resolveThemeMode(
  preset: ThemePreset,
  themeMode: 'dark' | 'light' | 'system',
  prefersDarkMode: boolean,
): 'dark' | 'light' {
  if (isLightThemePreset(preset)) {
    return 'light'
  }
  if (isDarkThemePreset(preset)) {
    return 'dark'
  }
  if (themeMode === 'system') {
    return prefersDarkMode ? 'dark' : 'light'
  }
  return themeMode
}

export function getThemePresetLabel(preset: ThemePreset): string {
  return getThemePresetDefinition(preset).label
}

export function getAppBarBackground(
  preset: ThemePreset,
  mode: 'dark' | 'light',
): string {
  const definition = getThemePresetDefinition(preset)
  return mode === 'dark' ? definition.appBarDark : definition.appBarLight
}

export function getPageBackground(
  preset: ThemePreset,
  mode: 'dark' | 'light',
  reducedMotion: boolean,
): string | null {
  if (reducedMotion) {
    return null
  }
  const definition = getThemePresetDefinition(preset)
  if (mode === 'dark' && preset === 'default') {
    return 'radial-gradient(circle at top left, rgba(108,184,255,0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(14,165,183,0.12), transparent 28%)'
  }
  if (mode === 'dark' && !definition.pageBackground) {
    return null
  }
  return definition.pageBackground
}

export function normalizeThemePreset(value: unknown): ThemePreset {
  if (typeof value === 'string' && value in THEME_PRESET_DEFINITIONS) {
    return value as ThemePreset
  }
  return 'default'
}

export function suggestedThemeModeForPreset(
  preset: ThemePreset,
): 'dark' | 'light' | 'system' | null {
  if (isLightThemePreset(preset)) {
    return 'light'
  }
  if (isDarkThemePreset(preset)) {
    return 'dark'
  }
  return null
}

export type { ThemePresetDefinition }
