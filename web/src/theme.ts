import { createTheme } from '@mui/material/styles'

import type { AppearanceSettings } from './types/settings'

function resolveThemeMode(
  appearance: AppearanceSettings,
  prefersDarkMode: boolean,
): 'dark' | 'light' {
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

  return createTheme({
    palette: {
      mode,
      primary: {
        main: isDarkMode ? '#6cb8ff' : '#0f6cbd',
      },
      secondary: {
        main: isDarkMode ? '#7dd3fc' : '#0ea5b7',
      },
      background: {
        default: isDarkMode ? '#0d1117' : '#f5f7fb',
        paper: isDarkMode ? '#161b22' : '#ffffff',
      },
    },
    shape: {
      borderRadius: appearance.density === 'compact' ? 10 : 16,
    },
    spacing: appearance.density === 'compact' ? 6 : 8,
    typography: {
      fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
      h4: {
        fontWeight: 700,
        letterSpacing: '-0.03em',
      },
      h6: {
        fontWeight: 650,
      },
      button: {
        textTransform: 'none',
        fontWeight: 600,
      },
    },
    components: {
      MuiButton: {
        defaultProps: {
          size: appearance.density === 'compact' ? 'small' : 'medium',
        },
      },
      MuiTextField: {
        defaultProps: {
          size: appearance.density === 'compact' ? 'small' : 'medium',
        },
      },
      MuiFormControl: {
        defaultProps: {
          size: appearance.density === 'compact' ? 'small' : 'medium',
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: isDarkMode
              ? 'linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.01) 100%)'
              : 'linear-gradient(180deg, rgba(255,255,255,1) 0%, rgba(245,248,252,1) 100%)',
          },
        },
      },
    },
  })
}
