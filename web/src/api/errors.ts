export async function readApiError(response: Response, fallback: string): Promise<string> {
  let detail = `${fallback} (${response.status})`
  try {
    const body = (await response.json()) as { detail?: string | string[] }
    if (Array.isArray(body.detail)) {
      detail = body.detail.join('; ')
    } else if (body.detail) {
      detail = body.detail
    }
  } catch {
    // keep default message
  }
  return detail
}
