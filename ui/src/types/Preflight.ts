export interface PreflightCheck {
  name: string
  status: 'pass' | 'warn' | 'block'
  message: string
  details?: Record<string, unknown>
}

export interface PreflightResult {
  status: 'pass' | 'warn' | 'block'
  summary: string
  checks: PreflightCheck[]
  warnings: string[]
  errors: string[]
  technicalCompatibility: {
    status: 'compatible' | 'review' | 'incompatible' | 'unknown'
    notes: string[]
  }
}
