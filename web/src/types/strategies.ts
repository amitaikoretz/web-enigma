export interface StrategyParameterMetadata {
  type: string
  default: unknown
  required: boolean
  title?: string | null
  description?: string | null
  enum?: unknown[] | null
  multipleOf?: number | null
  minimum?: number | null
  maximum?: number | null
  exclusiveMinimum?: number | null
  exclusiveMaximum?: number | null
  minLength?: number | null
  maxLength?: number | null
  pattern?: string | null
}

export interface StrategyMetadata {
  name: string
  description: string
  parameters: Record<string, StrategyParameterMetadata>
}
