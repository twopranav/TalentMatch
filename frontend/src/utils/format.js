// Sentence-case for enum values coming from the API: "full_time" -> "Full time"
export function formatEnumLabel(value) {
  if (!value) return null
  const words = String(value).replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// Safely extract a user-facing message from an Axios error.
// FastAPI validation errors (422) send `detail` as an ARRAY of
// {msg, loc, type} objects, not a string. Rendering that array directly
// (e.g. `err.response?.data?.detail || fallback`) into JSX crashes the
// app, since React can't render a plain object as a child. Every other
// error shape sends `detail` as a string, which we pass through as-is.
export function getErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg).filter(Boolean).join(' ') || fallback
  }
  if (typeof detail === 'string' && detail) return detail
  return fallback
}