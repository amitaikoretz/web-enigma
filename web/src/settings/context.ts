import { createContext } from 'react'

import type { AppearanceSettings, PlatformSettings } from '../types/settings'

export interface SettingsContextValue {
  appearance: AppearanceSettings
  platformSettings: PlatformSettings
  loading: boolean
  saving: boolean
  error: string | null
  setAppearance: (value: AppearanceSettings) => void
  patchAppearance: (value: Partial<AppearanceSettings>) => void
  resetAppearance: () => void
  savePlatformSettings: (value: PlatformSettings) => Promise<void>
  refreshPlatformSettings: () => Promise<void>
}

export const SettingsContext = createContext<SettingsContextValue | null>(null)
