import { createTheme } from '@mui/material/styles'

import type { AppearanceSettings } from './types/settings'
import { getThemePresetDefinition } from './theme/presets'
import { resolveThemeMode } from './theme/registry'

export function createAppTheme(
  appearance: AppearanceSettings,
  prefersDarkMode: boolean,
) {
  const preset = getThemePresetDefinition(appearance.theme_preset)
  const mode = resolveThemeMode(
    appearance.theme_preset,
    appearance.theme_mode,
    prefersDarkMode,
  )
  const isDarkMode = mode === 'dark'
  const isCompact = appearance.density === 'compact'

  const palette = isDarkMode
    ? {
        primary: { main: '#6cb8ff' },
        secondary: { main: '#7dd3fc' },
        background: {
          default: preset.group === 'dark' ? preset.palette.backgroundDefault : '#0d1117',
          paper: preset.group === 'dark' ? preset.palette.backgroundPaper : '#161b22',
        },
        text: {
          primary: preset.group === 'dark' ? preset.palette.textPrimary : '#ffffff',
          secondary: preset.group === 'dark' ? preset.palette.textSecondary : '#8b949e',
        },
        divider:
          preset.group === 'dark' ? preset.palette.divider : 'rgba(255, 255, 255, 0.12)',
      }
    : {
        primary: { main: preset.palette.primary },
        secondary: { main: preset.palette.secondary },
        background: {
          default: preset.palette.backgroundDefault,
          paper: preset.palette.backgroundPaper,
        },
        text: {
          primary: preset.palette.textPrimary,
          secondary: preset.palette.textSecondary,
        },
        divider: preset.palette.divider,
      }

  const borderRadius = isCompact ? preset.shape.compactBorderRadius : preset.shape.borderRadius
  const paperOverrides = isDarkMode
    ? preset.group === 'dark'
      ? preset.paperOverrides
      : {
          backgroundImage:
            'linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.01) 100%)',
        }
    : preset.paperOverrides

  const buttonTypography = preset.typography.buttonFontFamily
    ? { fontFamily: preset.typography.buttonFontFamily }
    : {}

  return createTheme({
    palette: {
      mode,
      ...palette,
    },
    shape: {
      borderRadius,
    },
    spacing: isCompact ? Math.max(preset.spacingUnit - 2, 6) : preset.spacingUnit,
    typography: {
      fontFamily: preset.typography.fontFamily,
      h4: {
        fontFamily: preset.typography.headingFontFamily,
        fontSize: preset.typography.h4FontSize,
        fontWeight: preset.typography.h4FontWeight,
        letterSpacing: '-0.03em',
      },
      h6: {
        fontFamily: preset.typography.headingFontFamily,
        fontWeight: preset.typography.h6FontWeight,
      },
      body1: preset.typography.body1FontSize
        ? { fontSize: preset.typography.body1FontSize }
        : undefined,
      button: {
        textTransform: 'none',
        fontWeight: 600,
        ...buttonTypography,
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
      MuiAppBar: {
        styleOverrides: {
          root:
            appearance.theme_preset === 'oslo' && !isDarkMode
              ? {
                  borderBottom: '1px solid #111111',
                }
              : {},
        },
      },
      MuiTableCell: {
        styleOverrides: {
          head:
            appearance.theme_preset === 'oslo' && !isDarkMode
              ? {
                  borderBottom: '1px solid #111111',
                }
              : {},
        },
      },
    },
  })
}
