import { FormControl, FormControlLabel, InputLabel, MenuItem, Select, Stack, Switch, TextField } from '@mui/material'

type JsonSchema = Record<string, unknown>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function schemaType(schema: JsonSchema): string | null {
  const t = schema.type
  if (typeof t === 'string') return t
  if (Array.isArray(t) && t.every((x) => typeof x === 'string')) {
    // Pydantic sometimes uses unions like ["string","null"].
    const nonNull = t.filter((x) => x !== 'null')
    return nonNull.length === 1 ? nonNull[0] : nonNull[0] ?? null
  }
  return null
}

function titleFor(name: string, schema: JsonSchema): string {
  if (typeof schema.title === 'string' && schema.title.trim()) return schema.title
  // snake_case -> Title Case
  return name
    .split('_')
    .filter(Boolean)
    .map((w) => w.slice(0, 1).toUpperCase() + w.slice(1))
    .join(' ')
}

function descriptionFor(schema: JsonSchema): string | undefined {
  return typeof schema.description === 'string' ? schema.description : undefined
}

function clampNumber(raw: number, schema: JsonSchema): number {
  const min = typeof schema.minimum === 'number' ? schema.minimum : undefined
  const max = typeof schema.maximum === 'number' ? schema.maximum : undefined
  if (min != null && raw < min) return min
  if (max != null && raw > max) return max
  return raw
}

export function ScanParamsForm(props: {
  schema: unknown
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  disabled?: boolean
}) {
  if (!isRecord(props.schema) || schemaType(props.schema) !== 'object' || !isRecord(props.schema.properties)) {
    return null
  }

  const properties = props.schema.properties as Record<string, unknown>

  return (
    <Stack spacing={1.5}>
      {Object.entries(properties).map(([name, rawSchema]) => {
        if (!isRecord(rawSchema)) return null

        const t = schemaType(rawSchema)
        const label = titleFor(name, rawSchema)
        const helperText = descriptionFor(rawSchema)
        const fieldValue = props.value[name]

        // enums (string/number) -> Select
        if (Array.isArray(rawSchema.enum) && rawSchema.enum.length > 0) {
          const options = rawSchema.enum.filter((v) => typeof v === 'string' || typeof v === 'number')
          if (options.length === 0) return null
          return (
            <FormControl key={name} fullWidth disabled={props.disabled}>
              <InputLabel id={`${name}-label`}>{label}</InputLabel>
              <Select
                labelId={`${name}-label`}
                label={label}
                value={typeof fieldValue === 'string' || typeof fieldValue === 'number' ? fieldValue : String(options[0])}
                onChange={(e) => props.onChange({ ...props.value, [name]: e.target.value })}
              >
                {options.map((opt) => (
                  <MenuItem key={String(opt)} value={opt}>
                    {String(opt)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )
        }

        if (t === 'boolean') {
          return (
            <FormControlLabel
              key={name}
              control={
                <Switch
                  checked={typeof fieldValue === 'boolean' ? fieldValue : Boolean(rawSchema.default)}
                  onChange={(_, checked) => props.onChange({ ...props.value, [name]: checked })}
                  disabled={props.disabled}
                />
              }
              label={label}
            />
          )
        }

        if (t === 'integer' || t === 'number') {
          const numeric = typeof fieldValue === 'number' ? fieldValue : typeof rawSchema.default === 'number' ? rawSchema.default : 0
          return (
            <TextField
              key={name}
              label={label}
              helperText={helperText}
              type="number"
              value={numeric}
              onChange={(e) => {
                const parsed = t === 'integer' ? parseInt(e.target.value, 10) : parseFloat(e.target.value)
                const next = Number.isFinite(parsed) ? clampNumber(parsed, rawSchema) : numeric
                props.onChange({ ...props.value, [name]: next })
              }}
              fullWidth
              disabled={props.disabled}
            />
          )
        }

        // arrays: support common case list[str] as comma-separated
        if (t === 'array' && isRecord(rawSchema.items)) {
          const itemType = schemaType(rawSchema.items)
          if (itemType === 'string') {
            const arr = Array.isArray(fieldValue) ? fieldValue.filter((v) => typeof v === 'string') : []
            return (
              <TextField
                key={name}
                label={label}
                helperText={helperText ?? 'Comma-separated'}
                value={arr.join(', ')}
                onChange={(e) => {
                  const nextArr = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                  props.onChange({ ...props.value, [name]: nextArr })
                }}
                fullWidth
                disabled={props.disabled}
              />
            )
          }
        }

        if (t === 'string') {
          const str = typeof fieldValue === 'string' ? fieldValue : typeof rawSchema.default === 'string' ? rawSchema.default : ''
          return (
            <TextField
              key={name}
              label={label}
              helperText={helperText}
              value={str}
              onChange={(e) => props.onChange({ ...props.value, [name]: e.target.value })}
              fullWidth
              disabled={props.disabled}
            />
          )
        }

        // Unsupported type; omit rather than rendering broken input
        return null
      })}
    </Stack>
  )
}

