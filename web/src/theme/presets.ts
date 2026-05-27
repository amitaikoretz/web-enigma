import type { ThemePreset } from '../types/settings'

export type ThemePresetGroup = 'adaptive' | 'light' | 'dark'

export interface ThemePresetDefinition {
  id: ThemePreset
  label: string
  group: ThemePresetGroup
  palette: {
    primary: string
    secondary: string
    backgroundDefault: string
    backgroundPaper: string
    divider: string
    textPrimary: string
    textSecondary: string
  }
  typography: {
    fontFamily: string
    headingFontFamily: string
    h4FontSize: string
    h4FontWeight: number
    h6FontWeight: number
    body1FontSize?: string
    buttonFontFamily?: string
  }
  shape: {
    borderRadius: number
    compactBorderRadius: number
  }
  spacingUnit: number
  paperOverrides: Record<string, unknown>
  pageBackground: string | null
  appBarLight: string
  appBarDark: string
  glassAtmosphere: boolean
  auroraAtmosphere: boolean
}

const DEFAULT_LIGHT_GRADIENT =
  'radial-gradient(circle at top left, rgba(108,184,255,0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(14,165,183,0.12), transparent 28%)'

export const THEME_PRESET_DEFINITIONS: Record<ThemePreset, ThemePresetDefinition> = {
  default: {
    id: 'default',
    label: 'Default Standard',
    group: 'adaptive',
    palette: {
      primary: '#0f6cbd',
      secondary: '#0ea5b7',
      backgroundDefault: '#f5f7fb',
      backgroundPaper: '#ffffff',
      divider: 'rgba(0, 0, 0, 0.12)',
      textPrimary: '#0f172a',
      textSecondary: '#64748b',
    },
    typography: {
      fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
      headingFontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
      h4FontSize: '2.125rem',
      h4FontWeight: 700,
      h6FontWeight: 650,
    },
    shape: { borderRadius: 16, compactBorderRadius: 10 },
    spacingUnit: 8,
    paperOverrides: {
      backgroundImage:
        'linear-gradient(180deg, rgba(255,255,255,1) 0%, rgba(245,248,252,1) 100%)',
    },
    pageBackground: DEFAULT_LIGHT_GRADIENT,
    appBarLight: 'rgba(255,255,255,0.84)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  alpine: {
    id: 'alpine',
    label: 'Alpine Frost',
    group: 'light',
    palette: {
      primary: '#0284c7',
      secondary: '#1e3a8a',
      backgroundDefault: '#f1f5f9',
      backgroundPaper: 'rgba(255, 255, 255, 0.75)',
      divider: 'rgba(148, 163, 184, 0.25)',
      textPrimary: '#0f172a',
      textSecondary: '#64748b',
    },
    typography: {
      fontFamily: '"Inter", "Outfit", sans-serif',
      headingFontFamily: '"Outfit", sans-serif',
      h4FontSize: '2.125rem',
      h4FontWeight: 800,
      h6FontWeight: 650,
    },
    shape: { borderRadius: 20, compactBorderRadius: 12 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
      border: '1px solid rgba(148, 163, 184, 0.25)',
      boxShadow: '0 10px 30px rgba(15, 23, 42, 0.04)',
      backgroundImage: 'none',
    },
    pageBackground:
      'radial-gradient(circle at top left, rgba(2,132,199,0.06), transparent 35%), radial-gradient(circle at bottom right, rgba(30,58,138,0.04), transparent 45%)',
    appBarLight: 'rgba(241,245,249,0.8)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  fjord: {
    id: 'fjord',
    label: 'Fjord White',
    group: 'light',
    palette: {
      primary: '#0c1c30',
      secondary: '#1e3a5f',
      backgroundDefault: '#ffffff',
      backgroundPaper: '#ffffff',
      divider: 'rgba(12, 28, 48, 0.07)',
      textPrimary: '#0c1c30',
      textSecondary: 'rgba(12, 28, 48, 0.46)',
    },
    typography: {
      fontFamily: '"Jost", "Segoe UI", sans-serif',
      headingFontFamily: '"Cormorant Garamond", Georgia, serif',
      h4FontSize: '2.35rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 2, compactBorderRadius: 2 },
    spacingUnit: 9,
    paperOverrides: {
      border: '1px solid rgba(12, 28, 48, 0.07)',
      boxShadow: 'none',
      backgroundImage: 'none',
    },
    pageBackground: null,
    appBarLight: 'rgba(255,255,255,0.96)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  oslo: {
    id: 'oslo',
    label: 'Oslo Editorial',
    group: 'light',
    palette: {
      primary: '#111111',
      secondary: '#333333',
      backgroundDefault: '#ffffff',
      backgroundPaper: '#ffffff',
      divider: 'rgba(0, 0, 0, 0.06)',
      textPrimary: '#111111',
      textSecondary: 'rgba(17, 17, 17, 0.44)',
    },
    typography: {
      fontFamily: '"Newsreader", Georgia, serif',
      headingFontFamily: '"Playfair Display", Georgia, serif',
      h4FontSize: '2.5rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '1rem',
      buttonFontFamily: '"Instrument Sans", "Segoe UI", sans-serif',
    },
    shape: { borderRadius: 0, compactBorderRadius: 0 },
    spacingUnit: 9,
    paperOverrides: {
      border: '1px solid rgba(0, 0, 0, 0.06)',
      boxShadow: '2px 2px 0 rgba(26, 26, 26, 0.06)',
      backgroundImage: 'none',
    },
    pageBackground: null,
    appBarLight: 'rgba(255,255,255,0.98)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  helsinki: {
    id: 'helsinki',
    label: 'Helsinki Air',
    group: 'light',
    palette: {
      primary: '#1a4f7a',
      secondary: '#2c6287',
      backgroundDefault: '#ffffff',
      backgroundPaper: '#ffffff',
      divider: 'rgba(20, 60, 100, 0.06)',
      textPrimary: '#0e1a28',
      textSecondary: 'rgba(14, 26, 40, 0.4)',
    },
    typography: {
      fontFamily: '"Outfit", "Segoe UI", sans-serif',
      headingFontFamily: '"Cormorant Garamond", Georgia, serif',
      h4FontSize: '2.3rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 6, compactBorderRadius: 4 },
    spacingUnit: 9,
    paperOverrides: {
      border: '1px solid rgba(20, 60, 100, 0.06)',
      boxShadow: 'none',
      backgroundImage: 'none',
    },
    pageBackground:
      'radial-gradient(ellipse 80% 50% at 100% 0%, rgba(26,79,122,0.04), transparent 55%)',
    appBarLight: 'rgba(255,255,255,0.96)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  polar: {
    id: 'polar',
    label: 'Polar Linen',
    group: 'light',
    palette: {
      primary: '#141c28',
      secondary: '#283848',
      backgroundDefault: '#ffffff',
      backgroundPaper: '#ffffff',
      divider: 'rgba(30, 40, 55, 0.05)',
      textPrimary: '#141c28',
      textSecondary: 'rgba(20, 28, 40, 0.38)',
    },
    typography: {
      fontFamily: '"Instrument Sans", "Segoe UI", sans-serif',
      headingFontFamily: '"Newsreader", Georgia, serif',
      h4FontSize: '2.15rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.96875rem',
    },
    shape: { borderRadius: 8, compactBorderRadius: 6 },
    spacingUnit: 10,
    paperOverrides: {
      border: '1px solid rgba(30, 40, 55, 0.055)',
      boxShadow: '0 1px 0 rgba(255,255,255,1) inset',
      backgroundImage: 'none',
    },
    pageBackground: null,
    appBarLight: 'rgba(255,255,255,0.98)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  frost: {
    id: 'frost',
    label: 'Morning Frost',
    group: 'light',
    palette: {
      primary: '#2c4a62',
      secondary: '#3d5a72',
      backgroundDefault: '#e9eef3',
      backgroundPaper: 'rgba(255, 255, 255, 0.62)',
      divider: 'rgba(255, 255, 255, 0.75)',
      textPrimary: '#1a2430',
      textSecondary: 'rgba(26, 36, 48, 0.5)',
    },
    typography: {
      fontFamily: '"Inter", "Segoe UI", sans-serif',
      headingFontFamily: '"Outfit", sans-serif',
      h4FontSize: '2rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 16, compactBorderRadius: 12 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(24px)',
      WebkitBackdropFilter: 'blur(24px)',
      border: '1px solid rgba(255, 255, 255, 0.75)',
      boxShadow: '0 8px 40px rgba(26, 36, 48, 0.06)',
      backgroundImage: 'none',
    },
    pageBackground: 'linear-gradient(165deg, #eef2f6 0%, #dde5ed 100%)',
    appBarLight: 'rgba(255,255,255,0.5)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: true,
    auroraAtmosphere: false,
  },
  silica: {
    id: 'silica',
    label: 'Silica',
    group: 'light',
    palette: {
      primary: '#3d5a6c',
      secondary: '#4a6778',
      backgroundDefault: '#e8eaec',
      backgroundPaper: 'rgba(255, 255, 255, 0.55)',
      divider: 'rgba(255, 255, 255, 0.7)',
      textPrimary: '#1c2228',
      textSecondary: 'rgba(28, 34, 40, 0.46)',
    },
    typography: {
      fontFamily: '"Inter", "Segoe UI", sans-serif',
      headingFontFamily: '"Outfit", sans-serif',
      h4FontSize: '1.95rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 14, compactBorderRadius: 10 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.7)',
      boxShadow: '0 6px 32px rgba(28, 34, 40, 0.05)',
      backgroundImage: 'none',
    },
    pageBackground:
      'radial-gradient(circle at 70% 20%, rgba(200,210,220,0.5), transparent 50%), linear-gradient(160deg, #eef0f2, #dfe3e7)',
    appBarLight: 'rgba(255,255,255,0.48)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: true,
    auroraAtmosphere: false,
  },
  alto: {
    id: 'alto',
    label: 'Altostratus',
    group: 'light',
    palette: {
      primary: '#283848',
      secondary: '#3a4858',
      backgroundDefault: '#dfe2e6',
      backgroundPaper: 'rgba(255, 255, 255, 0.5)',
      divider: 'rgba(255, 255, 255, 0.65)',
      textPrimary: '#181c22',
      textSecondary: 'rgba(24, 28, 34, 0.5)',
    },
    typography: {
      fontFamily: '"Instrument Sans", "Segoe UI", sans-serif',
      headingFontFamily: '"Instrument Sans", "Segoe UI", sans-serif',
      h4FontSize: '1.875rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 12, compactBorderRadius: 8 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(18px)',
      WebkitBackdropFilter: 'blur(18px)',
      border: '1px solid rgba(255, 255, 255, 0.72)',
      boxShadow:
        '0 1px 0 rgba(255,255,255,0.6) inset, 0 8px 32px rgba(24,28,34,0.04)',
      backgroundImage: 'none',
    },
    pageBackground: 'linear-gradient(135deg, #e8eaed 0%, #d5d9de 50%, #e2e5e9 100%)',
    appBarLight: 'rgba(255,255,255,0.38)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: true,
    auroraAtmosphere: false,
  },
  glacial: {
    id: 'glacial',
    label: 'Glacial Veil',
    group: 'light',
    palette: {
      primary: '#1e5070',
      secondary: '#2a6080',
      backgroundDefault: '#e4ebf0',
      backgroundPaper: 'rgba(255, 255, 255, 0.6)',
      divider: 'rgba(255, 255, 255, 0.78)',
      textPrimary: '#142030',
      textSecondary: 'rgba(20, 32, 48, 0.46)',
    },
    typography: {
      fontFamily: '"Jost", "Segoe UI", sans-serif',
      headingFontFamily: '"Cormorant Garamond", Georgia, serif',
      h4FontSize: '2.1rem',
      h4FontWeight: 600,
      h6FontWeight: 600,
      body1FontSize: '0.9375rem',
    },
    shape: { borderRadius: 20, compactBorderRadius: 14 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(26px)',
      WebkitBackdropFilter: 'blur(26px)',
      border: '1px solid rgba(255, 255, 255, 0.78)',
      boxShadow: '0 12px 44px rgba(20, 32, 48, 0.06)',
      backgroundImage: 'none',
    },
    pageBackground:
      'radial-gradient(ellipse 60% 40% at 0% 0%, rgba(180,200,220,0.35), transparent 50%), radial-gradient(ellipse 50% 35% at 100% 100%, rgba(200,215,230,0.3), transparent 45%), linear-gradient(180deg, #edf2f6, #dde6ee)',
    appBarLight: 'rgba(255,255,255,0.52)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: true,
    auroraAtmosphere: false,
  },
  solaris: {
    id: 'solaris',
    label: 'Solaris Amber',
    group: 'dark',
    palette: {
      primary: '#f59e0b',
      secondary: '#ea580c',
      backgroundDefault: '#0a0908',
      backgroundPaper: '#12100e',
      divider: 'rgba(245, 158, 11, 0.16)',
      textPrimary: '#fbfbfb',
      textSecondary: '#a1a1aa',
    },
    typography: {
      fontFamily: '"Plus Jakarta Sans", sans-serif',
      headingFontFamily: '"Plus Jakarta Sans", sans-serif',
      h4FontSize: '2.125rem',
      h4FontWeight: 800,
      h6FontWeight: 700,
    },
    shape: { borderRadius: 10, compactBorderRadius: 6 },
    spacingUnit: 8,
    paperOverrides: {
      border: '1px solid rgba(245, 158, 11, 0.16)',
      boxShadow: '0 6px 25px rgba(0, 0, 0, 0.4)',
      backgroundImage: 'none',
    },
    pageBackground: 'radial-gradient(circle at top right, rgba(245,158,11,0.05), transparent 40%)',
    appBarLight: 'rgba(255,255,255,0.84)',
    appBarDark: 'rgba(13,17,23,0.82)',
    glassAtmosphere: false,
    auroraAtmosphere: false,
  },
  aurora: {
    id: 'aurora',
    label: 'Aurora Mirage',
    group: 'dark',
    palette: {
      primary: '#38bdf8',
      secondary: '#f472b6',
      backgroundDefault: '#0b0f19',
      backgroundPaper: 'rgba(255, 255, 255, 0.05)',
      divider: 'rgba(255, 255, 255, 0.15)',
      textPrimary: '#ffffff',
      textSecondary: '#cbd5e1',
    },
    typography: {
      fontFamily: '"Inter", "Outfit", sans-serif',
      headingFontFamily: '"Outfit", sans-serif',
      h4FontSize: '2.125rem',
      h4FontWeight: 800,
      h6FontWeight: 600,
    },
    shape: { borderRadius: 24, compactBorderRadius: 14 },
    spacingUnit: 8,
    paperOverrides: {
      backdropFilter: 'blur(35px)',
      WebkitBackdropFilter: 'blur(35px)',
      border: '1px solid rgba(255, 255, 255, 0.15)',
      boxShadow: '0 12px 40px rgba(0, 0, 0, 0.3)',
      backgroundImage: 'none',
    },
    pageBackground: null,
    appBarLight: 'rgba(255,255,255,0.84)',
    appBarDark: 'rgba(11,15,25,0.65)',
    glassAtmosphere: false,
    auroraAtmosphere: true,
  },
}

export function getThemePresetDefinition(preset: ThemePreset): ThemePresetDefinition {
  return THEME_PRESET_DEFINITIONS[preset]
}
