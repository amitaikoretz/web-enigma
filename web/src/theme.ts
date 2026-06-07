import { createTheme } from '@mui/material/styles'

import type { AppearanceSettings } from './types/settings'
import { getThemePresetDefinition } from './theme/presets'
import { resolveThemeMode } from './theme/registry'

export function createAppTheme(
  appearance: AppearanceSettings,
  prefersDarkMode: boolean,
) {
  const preset = getThemePresetDefinition(appearance.theme_preset)
  const presetId = appearance.theme_preset
  const mode = resolveThemeMode(
    presetId,
    appearance.theme_mode,
    prefersDarkMode,
  )
  const isDarkMode = mode === 'dark'
  const isCompact = appearance.density === 'compact'
  const isStrata = presetId === 'strata'
  const isInkMica = presetId === 'ink_mica'
  const isCitrusPorcelain = presetId === 'citrus_porcelain'

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

  const elevatedGlass =
    presetId === 'fjord_porcelain' ||
    presetId === 'glacier_lilac' ||
    presetId === 'halo' ||
    presetId === 'fjord_ink_fx' ||
    presetId === 'deep_fjord_fx' ||
    presetId === 'aurora_slate' ||
    presetId === 'glass_blue' ||
    presetId === 'azure_slate' ||
    presetId === 'strata' ||
    presetId === 'citrus_porcelain'

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
        letterSpacing: isInkMica
          ? '-0.045em'
          : isCitrusPorcelain
            ? '-0.02em'
            : isStrata
              ? '-0.04em'
          : '-0.03em',
      },
      h6: {
        fontFamily: preset.typography.headingFontFamily,
        fontWeight: preset.typography.h6FontWeight,
        letterSpacing: isInkMica
          ? '0.08em'
          : isCitrusPorcelain
            ? '0.02em'
            : isStrata
              ? '0.18em'
          : undefined,
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
            letterSpacing: isInkMica ? '0.02em' : isStrata ? '0.012em' : '0.01em',
            lineHeight: isInkMica ? 1.7 : isStrata ? 1.68 : 1.6,
            backgroundColor: preset.palette.backgroundDefault,
            backgroundImage: preset.pageBackground ?? undefined,
            backgroundAttachment: 'fixed',
            ...(isInkMica
              ? {
                  fontFeatureSettings: '"liga" 1, "kern" 1, "onum" 1',
                }
              : isStrata
                ? {
                    fontFeatureSettings: '"liga" 1, "kern" 1',
                    textRendering: 'optimizeLegibility',
                  }
              : null),
          },
          'code, pre, kbd, samp': {
            fontFamily:
              '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
          },
          '::selection': {
            backgroundColor: isInkMica
              ? 'rgba(17, 17, 17, 0.12)'
              : 'rgba(255, 127, 61, 0.16)',
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
            ...(isInkMica
              ? {
                  borderRadius: 0,
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  borderColor: theme.palette.divider,
                  boxShadow: 'none',
                }
                : isCitrusPorcelain
                  ? {
                    borderRadius: 999,
                    paddingInline: theme.spacing(2.2),
                    boxShadow: '0 10px 24px rgba(122, 60, 33, 0.10)',
                  }
                : isStrata
                  ? {
                      borderRadius: 0,
                      textTransform: 'uppercase',
                      letterSpacing: '0.16em',
                      fontWeight: 650,
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: theme.palette.divider,
                      boxShadow: 'none',
                    }
                : null),
            ...(elevatedGlass
              ? {
                  boxShadow: 'none',
                  backdropFilter: 'blur(14px)',
                  WebkitBackdropFilter: 'blur(14px)',
                }
              : null),
          }),
          contained: () =>
            isInkMica
              ? {
                  color: '#ffffff',
                  backgroundColor: '#111111',
                  boxShadow: '0 12px 20px rgba(17, 17, 17, 0.18)',
                  '&:hover': {
                    backgroundColor: '#000000',
                  },
                }
                : isCitrusPorcelain
                  ? {
                    color: '#fffaf4',
                    backgroundImage: 'linear-gradient(135deg, #ff6a3d 0%, #ffbe3d 100%)',
                    boxShadow: '0 12px 24px rgba(255, 106, 61, 0.22)',
                    '&:hover': {
                      backgroundImage: 'linear-gradient(135deg, #ff5b2c 0%, #ffb21f 100%)',
                    },
                  }
                : isStrata
                  ? {
                      color: '#f7f7f5',
                      backgroundColor: '#12110f',
                      boxShadow: '0 10px 18px rgba(16, 12, 8, 0.16)',
                      '&:hover': {
                        backgroundColor: '#090807',
                      },
                    }
                : elevatedGlass
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
            ...(isInkMica
              ? {
                  borderRadius: 0,
                  border: `1px solid ${String(theme.palette.divider)}`,
                  boxShadow: '3px 3px 0 rgba(17, 17, 17, 0.06)',
                }
                : isCitrusPorcelain
                  ? {
                    borderRadius: Math.max(Number(theme.shape.borderRadius), 32),
                    border: `1px solid ${String(theme.palette.divider)}`,
                    boxShadow: '0 22px 54px rgba(122, 60, 33, 0.09)',
                  }
                : isStrata
                  ? {
                      borderRadius: 0,
                      border: `1px solid ${String(theme.palette.divider)}`,
                      boxShadow: '0 18px 44px rgba(16, 12, 8, 0.08)',
                    }
                : null),
            ...paperOverrides,
          }),
        },
      },
      MuiCard: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: theme.shape.borderRadius,
            ...(isInkMica
              ? {
                  borderRadius: 0,
                  overflow: 'hidden',
                  border: `1px solid ${String(theme.palette.divider)}`,
                  boxShadow: '3px 3px 0 rgba(17, 17, 17, 0.06)',
                }
                : isCitrusPorcelain
                  ? {
                    overflow: 'hidden',
                    border: `1px solid ${String(theme.palette.divider)}`,
                    boxShadow: '0 20px 48px rgba(122, 60, 33, 0.08)',
                  }
                : isStrata
                  ? {
                      borderRadius: 0,
                      overflow: 'hidden',
                      border: `1px solid ${String(theme.palette.divider)}`,
                      boxShadow: '0 22px 52px rgba(16, 12, 8, 0.08)',
                    }
                : null),
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
            borderRadius: isInkMica || isStrata ? 0 : theme.shape.borderRadius,
          }),
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : theme.shape.borderRadius,
          }),
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : theme.shape.borderRadius,
          }),
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : theme.shape.borderRadius,
          }),
        },
      },
      MuiChip: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : Math.max(Number(theme.shape.borderRadius), 999),
            fontWeight: 600,
            ...(isInkMica
              ? {
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  backgroundColor: 'rgba(17, 17, 17, 0.04)',
                  border: `1px solid ${String(theme.palette.divider)}`,
                }
              : isCitrusPorcelain
                ? {
                    paddingInline: theme.spacing(0.75),
                    boxShadow: '0 10px 24px rgba(255, 106, 61, 0.08)',
                  }
                : isStrata
                  ? {
                      textTransform: 'uppercase',
                      letterSpacing: '0.14em',
                      fontSize: '0.78rem',
                      border: `1px solid ${String(theme.palette.divider)}`,
                    }
                : null),
          }),
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : isCitrusPorcelain ? 999 : theme.shape.borderRadius,
            ...(isInkMica
              ? {
                  backgroundColor: 'rgba(255, 252, 247, 0.86)',
                }
              : isStrata
                ? {
                    backgroundColor: 'rgba(255, 255, 255, 0.56)',
                  }
              : null),
          }),
        },
      },
      MuiTableContainer: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderRadius: isInkMica || isStrata ? 0 : theme.shape.borderRadius,
          }),
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root:
            isInkMica
              ? {
                  borderBottom: `2px solid ${String(palette.divider ?? '#111111')}`,
                  boxShadow: 'none',
                  backgroundImage: 'none',
                }
              : isStrata
                ? {
                    borderBottom: `1px solid ${String(palette.divider ?? 'rgba(255,255,255,0.12)')}`,
                    boxShadow: 'none',
                    backgroundImage:
                      'linear-gradient(180deg, rgba(255,255,255,0.66) 0%, rgba(255,255,255,0.34) 100%)',
                  }
              : isCitrusPorcelain
                ? {
                    backdropFilter: 'blur(20px)',
                    WebkitBackdropFilter: 'blur(20px)',
                    borderBottom: `1px solid ${String(palette.divider ?? 'rgba(255,255,255,0.12)')}`,
                    boxShadow: '0 1px 0 rgba(255,255,255,0.38) inset',
                  }
              : appearance.theme_preset === 'oslo' && !isDarkMode
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
            isInkMica
              ? {
                  borderRight: '2px solid rgba(17, 17, 17, 0.12)',
                }
              : isStrata
                ? {
                    borderRight: `1px solid ${String(palette.divider ?? 'rgba(18,17,15,0.14)')}`,
                    backgroundImage: 'none',
                  }
              : elevatedGlass
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
            isInkMica
              ? {
                  borderBottom: `2px solid ${String(palette.divider ?? '#111111')}`,
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  fontSize: '0.72rem',
                }
              : isStrata
                ? {
                    borderBottom: `1px solid ${String(palette.divider ?? 'rgba(18,17,15,0.14)')}`,
                    textTransform: 'uppercase',
                    letterSpacing: '0.14em',
                    fontSize: '0.72rem',
                  }
              : appearance.theme_preset === 'oslo' && !isDarkMode
              ? {
                  borderBottom: '1px solid #111111',
                }
              : {},
        },
      },
    },
  })
}
