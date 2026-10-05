/**
 * Extracts a safe, renderable string from an API error.
 *
 * FastAPI's 422 validation errors return `detail` as an array of
 * `{type, loc, msg, input, ctx}` objects, not a string. Passing that
 * straight into a React child (e.g. `setError(err.response?.data?.detail)`
 * then `{error}`) throws "Minified React error #31: Objects are not valid
 * as a React child" - this normalizes every shape `detail` can take into
 * a plain string first.
 */
export function getErrorMessage(error: unknown, fallback: string): string {
  const anyErr = error as Record<string, unknown> | null

  // Axios client timeout (ECONNABORTED / "timeout of Xms exceeded"): the backend
  // LLM call outlived the client timeout. Explain instead of showing raw ms text
  // that users misread as a quota ("limit exceeded 3000s").
  const code = (anyErr as { code?: unknown } | null)?.code
  const msg = (anyErr as { message?: unknown } | null)?.message
  if (code === "ECONNABORTED" || (typeof msg === "string" && msg.toLowerCase().includes("timeout of"))) {
    return "Request is taking longer than expected. Please wait a moment and retry."
  }

  // axios shape: error.response.data.detail can be string | {msg}[] | object
  const resp = (anyErr as { response?: { data?: { detail?: unknown; correlation_id?: unknown }; headers?: Record<string, string> } } | null)?.response
  const detail = resp?.data?.detail
  const correlationId =
    (resp?.data as { correlation_id?: unknown } | undefined)?.correlation_id ??
    resp?.headers?.["x-correlation-id"] ??
    resp?.headers?.["X-Correlation-ID"]
  const withRef = (text: string) =>
    typeof correlationId === "string" && correlationId && correlationId !== "-"
      ? `${text} (ref: ${correlationId})`
      : text

  if (typeof detail === "string" && detail.trim()) {
    // Backend catch-all hides internals as "Unexpected error" - point to ref.
    if (detail === "Unexpected error") {
      return withRef("Unexpected error. Please retry and share the reference ID if it persists.")
    }
    return withRef(detail)
  }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d === "string") return d
        if (d && typeof d === "object" && "msg" in (d as Record<string, unknown>)) return String((d as { msg: unknown }).msg)
        return ""
      })
      .filter(Boolean)
      .join("; ")
    if (msgs) return msgs
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail)
    } catch {
      // ignore
    }
  }

  // error.error is used by JobStatus
  if (anyErr && typeof (anyErr as { error?: unknown }).error === "string") return String((anyErr as { error: string }).error)
  if (anyErr && typeof (anyErr as { message?: unknown }).message === "string") return String((anyErr as { message: string }).message)
  return fallback
}
