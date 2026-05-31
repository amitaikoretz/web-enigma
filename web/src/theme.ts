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

  const presetId = appearance.theme_preset
  const elevatedGlass =
    presetId === 'fjord_porcelain' ||
    presetId === 'glacier_lilac' ||
    presetId === 'fjord_ink_fx' ||
    presetId === 'deep_fjord_fx' ||
    presetId === 'aurora_slate'

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
      h1: { fontFamily: preset.typography.headingFontFamily },
      h2: { fontFamily: preset.typography.headingFontFamily },
      h3: { fontFamily: preset.typography.headingFontFamily },
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
      h5: { fontFamily: preset.typography.headingFontFamily },
      subtitle1: { fontFamily: preset.typography.fontFamily },
      subtitle2: { fontFamily: preset.typography.fontFamily },
      body1: preset.typography.body1FontSize
        ? { fontSize: preset.typography.body1FontSize }
        : undefined,
      body2: { fontFamily: preset.typography.fontFamily },
      caption: { fontFamily: preset.typography.fontFamily },
      overline: { fontFamily: preset.typography.fontFamily },
      button: {
        textTransform: 'none',
        fontWeight: 600,
        ...buttonTypography,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            letterSpacing: '0.01em',
            backgroundColor: preset.palette.backgroundDefault,
            backgroundImage: preset.pageBackground ?? undefined,
            backgroundAttachment: 'fixed',
          },
          'code, pre, kbd, samp': {
            fontFamily:
              '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
          },
        },
      },
      MuiButton: {
        defaultProps: {
          size: isCompact ? 'small' : 'medium',
        },
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
            ...(elevatedGlass
              ? {
                  boxShadow: 'none',
                  backdropFilter: 'blur(14px)',
                  WebkitBackdropFilter: 'blur(14px)',
                }
              : null),
          }),
          contained: () =>
            elevatedGlass
              ? {
                  boxShadow:
                    '0 1px 0 rgba(255,255,255,0.12) inset, 0 12px 34px rgba(0,0,0,0.18)',
                }
              : {},
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
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
            ...paperOverrides,
          }),
        },
      },
      MuiCard: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
            ...(elevatedGlass
              ? {
                  overflow: 'hidden',
                  boxShadow: '0 18px 55px rgba(0,0,0,0.14)',
                }
              : null),
          }),
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiChip: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: Math.max(Number(theme.shape.borderRadius), 999),
            fontWeight: 600,
          }),
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiTableContainer: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
          }),
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root:
            appearance.theme_preset === 'oslo' && !isDarkMode
              ? {
                  borderBottom: '1px solid #111111',
                }
              : elevatedGlass
                ? {
                    backdropFilter: 'blur(18px)',
                    WebkitBackdropFilter: 'blur(18px)',
                    borderBottom: `1px solid ${String(palette.divider ?? 'rgba(255,255,255,0.12)')}`,
                    boxShadow: 'none',
                  }
                : {},
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: () =>
            elevatedGlass
              ? {
                  backdropFilter: 'blur(18px)',
                  WebkitBackdropFilter: 'blur(18px)',
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
