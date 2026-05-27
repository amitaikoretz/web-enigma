function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (typeof entry === 'string') {
          return entry
        }
        if (entry && typeof entry === 'object' && 'msg' in entry) {
          const message = (entry as { msg?: unknown }).msg
          return typeof message === 'string' ? message : JSON.stringify(entry)
        }
        return JSON.stringify(entry)
      })
      .filter(Boolean)
    return parts.length > 0 ? parts.join('; ') : null
  }
  return null
}

export async function readApiError(response: Response, fallback: string): Promise<string> {
  const fallbackWithStatus = `${fallback} (${response.status})`
  let detail = fallbackWithStatus

  try {
    const raw = await response.text()
    if (raw.trim()) {
      try {
        const body = JSON.parse(raw) as { detail?: unknown; message?: unknown }
        detail =
          formatErrorDetail(body.detail) ??
          (typeof body.message === 'string' && body.message.trim() ? body.message : null) ??
          raw.trim()
      } catch {
        detail = raw.trim()
      }
    }
  } catch {
    // keep fallback with status
  }

  console.error(`API error ${response.status} ${response.url}:`, detail)
  return detail
}
