import { defaultPlatformSettings } from './defaults'
import type { AppearanceSettings } from '../types/settings'

const APPEARANCE_STORAGE_KEY = 'kairos.appearance-settings.v1'

export function loadAppearanceSettings(): AppearanceSettings {
  if (typeof window === 'undefined') {
    return defaultPlatformSettings.appearance
  }

  const rawValue = window.localStorage.getItem(APPEARANCE_STORAGE_KEY)
  if (!rawValue) {
    return defaultPlatformSettings.appearance
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AppearanceSettings>
    return {
      ...defaultPlatformSettings.appearance,
      ...parsed,
    }
  } catch {
    return defaultPlatformSettings.appearance
  }
}

export function saveAppearanceSettings(value: AppearanceSettings): void {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(value))
}
