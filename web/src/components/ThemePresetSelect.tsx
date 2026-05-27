import {
  FormControl,
  InputLabel,
  ListSubheader,
  MenuItem,
  Select,
} from '@mui/material'

import {
  getThemePresetLabel,
  THEME_PRESET_GROUPS,
  THEME_PRESET_GROUP_LABELS,
} from '../theme/registry'
import type { ThemePreset } from '../types/settings'

interface ThemePresetSelectProps {
  value: ThemePreset
  onChange: (value: ThemePreset) => void
}

export function ThemePresetSelect({ value, onChange }: ThemePresetSelectProps) {
  return (
    <FormControl fullWidth>
      <InputLabel>Theme preset</InputLabel>
      <Select
        label="Theme preset"
        value={value}
        onChange={(event) => onChange(event.target.value as ThemePreset)}
      >
        {THEME_PRESET_GROUPS.flatMap(({ group, presets }) => [
          <ListSubheader key={`${group}-header`}>{THEME_PRESET_GROUP_LABELS[group]}</ListSubheader>,
          ...presets.map((preset) => (
            <MenuItem key={preset} value={preset} sx={{ pl: 3 }}>
              {getThemePresetLabel(preset)}
            </MenuItem>
          )),
        ])}
      </Select>
    </FormControl>
  )
}
