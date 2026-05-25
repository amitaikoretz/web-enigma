import { useContext } from 'react'

import { SettingsContext } from './context'

export function useSettings() {
  const value = useContext(SettingsContext)
  if (!value) {
    throw new Error('useSettings must be used within SettingsProvider')
  }
  return value
}
