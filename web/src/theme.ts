import { createTheme } from '@mui/material/styles'

import type { AppearanceSettings } from './types/settings'

function resolveThemeMode(
  appearance: AppearanceSettings,
  prefersDarkMode: boolean,
): 'dark' | 'light' {
  if (appearance.theme_preset === 'alpine') {
    return 'light'
  }
  if (appearance.theme_preset === 'solaris' || appearance.theme_preset === 'aurora') {
    return 'dark'
  }
  if (appearance.theme_mode === 'system') {
    return prefersDarkMode ? 'dark' : 'light'
  }
  return appearance.theme_mode
}

export function createAppTheme(
  appearance: AppearanceSettings,
  prefersDarkMode: boolean,
) {
  const mode = resolveThemeMode(appearance, prefersDarkMode)
  const isDarkMode = mode === 'dark'
  const isCompact = appearance.density === 'compact'

  // Define theme specific attributes
  let primaryMain = isDarkMode ? '#6cb8ff' : '#0f6cbd'
  let secondaryMain = isDarkMode ? '#7dd3fc' : '#0ea5b7'
  let bgDefault = isDarkMode ? '#0d1117' : '#f5f7fb'
  let bgPaper = isDarkMode ? '#161b22' : '#ffffff'
  let dividerColor = isDarkMode ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.12)'
  let textPrimary = isDarkMode ? '#ffffff' : '#0f172a'
  let textSecondary = isDarkMode ? '#8b949e' : '#64748b'
  
  let borderRadius = isCompact ? 10 : 16
  let fontFamily = '"IBM Plex Sans", "Segoe UI", sans-serif'
  let headingFontFamily = '"IBM Plex Sans", "Segoe UI", sans-serif'
  let h4Weight = 700
  let h6Weight = 650
  
  // Custom Paper overrides for glassmorphism and theme styling
  let paperOverrides: Record<string, unknown> = {
    backgroundImage: isDarkMode
      ? 'linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.01) 100%)'
      : 'linear-gradient(180deg, rgba(255,255,255,1) 0%, rgba(245,248,252,1) 100%)',
  }

  // 1. ALPINE FROST (Glacial Light Mode)
  if (appearance.theme_preset === 'alpine') {
    primaryMain = '#0284c7' // Glacial blue
    secondaryMain = '#1e3a8a' // Glacier navy
    bgDefault = '#f1f5f9'
    bgPaper = 'rgba(255, 255, 255, 0.75)'
    dividerColor = 'rgba(148, 163, 184, 0.25)'
    textPrimary = '#0f172a'
    textSecondary = '#64748b'
    
    borderRadius = isCompact ? 12 : 20
    fontFamily = '"Inter", "Outfit", sans-serif'
    headingFontFamily = '"Outfit", sans-serif'
    h4Weight = 800
    h6Weight = 650
    
    paperOverrides = {
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
      border: '1px solid rgba(148, 163, 184, 0.25)',
      boxShadow: '0 10px 30px rgba(15, 23, 42, 0.04)',
      backgroundImage: 'none',
    }
  }
  // 2. SOLARIS AMBER (High-Frequency Carbon Dark Mode)
  else if (appearance.theme_preset === 'solaris') {
    primaryMain = '#f59e0b' // Amber gold
    secondaryMain = '#ea580c' // Fiery Sunset Orange
    bgDefault = '#0a0908' // Carbon black
    bgPaper = '#12100e' // Warm basalt charcoal
    dividerColor = 'rgba(245, 158, 11, 0.16)'
    textPrimary = '#fbfbfb'
    textSecondary = '#a1a1aa'
    
    borderRadius = isCompact ? 6 : 10
    fontFamily = '"Plus Jakarta Sans", sans-serif'
    headingFontFamily = '"Plus Jakarta Sans", sans-serif'
    h4Weight = 800
    h6Weight = 700
    
    paperOverrides = {
      border: '1px solid rgba(245, 158, 11, 0.16)',
      boxShadow: '0 6px 25px rgba(0, 0, 0, 0.4)',
      backgroundImage: 'none',
    }
  }
  // 3. AURORA MIRAGE (frosted satin glass overlaying glowing aurora canvas)
  else if (appearance.theme_preset === 'aurora') {
    primaryMain = '#38bdf8' // Sky blue
    secondaryMain = '#f472b6' // Sunset pink
    bgDefault = '#0b0f19' // Dark indigo void
    bgPaper = 'rgba(255, 255, 255, 0.05)'
    dividerColor = 'rgba(255, 255, 255, 0.15)'
    textPrimary = '#ffffff'
    textSecondary = '#cbd5e1'
    
    borderRadius = isCompact ? 14 : 24
    fontFamily = '"Inter", "Outfit", sans-serif'
    headingFontFamily = '"Outfit", sans-serif'
    h4Weight = 800
    h6Weight = 600
    
    paperOverrides = {
      backdropFilter: 'blur(35px)',
      WebkitBackdropFilter: 'blur(35px)',
      border: '1px solid rgba(255, 255, 255, 0.15)',
      boxShadow: '0 12px 40px rgba(0, 0, 0, 0.3)',
      backgroundImage: 'none',
    }
  }

  return createTheme({
    palette: {
      mode,
      primary: {
        main: primaryMain,
      },
      secondary: {
        main: secondaryMain,
      },
      background: {
        default: bgDefault,
        paper: bgPaper,
      },
      text: {
        primary: textPrimary,
        secondary: textSecondary,
      },
      divider: dividerColor,
    },
    shape: {
      borderRadius,
    },
    spacing: isCompact ? 6 : 8,
    typography: {
      fontFamily,
      h4: {
        fontFamily: headingFontFamily,
        fontWeight: h4Weight,
        letterSpacing: '-0.03em',
      },
      h6: {
        fontFamily: headingFontFamily,
        fontWeight: h6Weight,
      },
      button: {
        textTransform: 'none',
        fontWeight: 600,
      },
    },
    components: {
      MuiButton: {
        defaultProps: {
          size: isCompact ? 'small' : 'medium',
        },
      },
      MuiTextField: {
        defaultProps: {
          size: isCompact ? 'small' : 'medium',
        },
      },
      MuiFormControl: {
        defaultProps: {
          size: isCompact ? 'small' : 'medium',
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: paperOverrides,
        },
      },
    },
  })
}
